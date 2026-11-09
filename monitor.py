#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afterburner - System Monitor Service for Windows 11
Background service collecting hardware metrics with system tray UI.
"""

import sys
import os
import json
import math
import time
import ctypes
import logging
import pynvml
import subprocess
import winreg
from collections import deque
from datetime import datetime
from pathlib import Path

# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Afterburner")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QGridLayout, QScrollArea, QSizePolicy,
    QSystemTrayIcon, QMenu, QMessageBox, QSlider, QGroupBox,
    QFormLayout, QPushButton, QCheckBox, QSpinBox, QDialog,
    QTabWidget, QScrollArea as QScrollAreaWidget
)
from PyQt6.QtCore import (
    Qt, QTimer, QRectF, QPointF, pyqtSignal, QThread,
    QObject, QPoint, QSize, QRect, QPropertyAnimation, QEasingCurve,
    QEvent
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics,
    QLinearGradient, QRadialGradient, QPalette, QIcon,
    QPainterPath, QWheelEvent, QCursor, QDesktopServices
)

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False


# ============================================================
# CONFIGURATION & THRESHOLDS
# ============================================================

CONFIG_PATH = Path(os.path.expanduser("~/.afterburner_config.json"))

DEFAULT_CONFIG = {
    "update_interval_ms": 1000,
    "chart_history_len": 120,
    "sparkline_history_len": 60,
    "show_popup_on_click": True,
    "popup_auto_hide_ms": 5000,
    "notifications_enabled": True,
    "auto_start": False,
    "minimize_to_tray": True,
    "theme": {
        "bg_dark": "#0a0e17",
        "bg_card": "#131a2b",
        "bg_card_hover": "#1a2340",
        "border_color": "#1e2a45",
        "text_primary": "#e8eaf0",
        "text_secondary": "#7a8ba8",
        "text_dim": "#4a5568",
        "accent_blue": "#3b82f6",
        "accent_cyan": "#06b6d4",
        "accent_green": "#10b981",
        "accent_yellow": "#f59e0b",
        "accent_red": "#ef4444",
        "accent_purple": "#8b5cf6",
        "accent_orange": "#f97316",
        "accent_pink": "#ec4899",
    }
}

DEFAULT_THRESHOLDS = {
    "cpu_temp_warn": 80,
    "cpu_temp_crit": 90,
    "gpu_temp_warn": 75,
    "gpu_temp_crit": 85,
    "cpu_usage_warn": 85,
    "gpu_usage_warn": 85,
    "ram_usage_warn": 85,
    "notification_cooldown_ms": 30000,
}

config = DEFAULT_CONFIG.copy()
thresholds = DEFAULT_THRESHOLDS.copy()

if CONFIG_PATH.exists():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if "config" in saved:
            config.update(saved["config"])
        if "thresholds" in saved:
            thresholds.update(saved["thresholds"])
    except Exception:
        logger.warning("Failed to load config thresholds", exc_info=True)


def save_config():
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"config": config, "thresholds": thresholds}, f, indent=2)
    except Exception:
        pass


class Colors:
    @staticmethod
    def get(name):
        return QColor(config["theme"][name])

    @staticmethod
    def usage_color(usage):
        if usage < 50:
            return Colors.get("accent_green")
        elif usage < 75:
            return Colors.get("accent_yellow")
        elif usage < 90:
            return Colors.get("accent_orange")
        else:
            return Colors.get("accent_red")


# ============================================================
# DATA MODEL
# ============================================================

class SystemData:
    """Holds current system metrics - plain data class"""
    __slots__ = [
        "cpu_usage", "cpu_per_core", "cpu_temp", "cpu_freq_current",
        "cpu_freq_max", "cpu_cores", "cpu_threads", "cpu_power",
        "gpu_usage", "gpu_temp", "gpu_mem_used", "gpu_mem_total",
        "gpu_mem_pct", "gpu_freq", "gpu_power", "gpu_name",
        "ram_total", "ram_used", "ram_avail", "ram_pct", "ram_speed",
        "fans", "disk_total", "disk_used", "disk_pct", "uptime",
    ]

    def __init__(self):
        self.cpu_usage = 0.0
        self.cpu_per_core = []
        self.cpu_temp = {}
        self.cpu_freq_current = 0.0
        self.cpu_freq_max = 0.0
        self.cpu_cores = 0
        self.cpu_threads = 0
        self.cpu_power = 0.0
        self.gpu_usage = 0.0
        self.gpu_temp = 0.0
        self.gpu_mem_used = 0
        self.gpu_mem_total = 0
        self.gpu_mem_pct = 0.0
        self.gpu_freq = 0.0
        self.gpu_power = 0.0
        self.gpu_name = "N/A"
        self.ram_total = 0
        self.ram_used = 0
        self.ram_avail = 0
        self.ram_pct = 0.0
        self.ram_speed = 0
        self.fans = []
        self.disk_total = 0
        self.disk_used = 0
        self.disk_pct = 0.0
        self.uptime = 0.0


class DataCollectorThread(QThread):
    """Background service thread that collects system metrics"""
    data_updated = pyqtSignal(SystemData)

    def __init__(self):
        super().__init__()
        self._running = True
        self._wmi = None
        if HAS_WMI:
            try:
                self._wmi = wmi.WMI()
            except Exception:
                pass

    def run(self):
        psutil.cpu_percent(interval=None, percpu=True)
        while self._running:
            try:
                data = self._collect()
                self.data_updated.emit(data)
            except Exception:
                pass
            self.msleep(config.get("update_interval_ms", 1000))

    def stop(self):
        self._running = False
        self.wait()

    def _collect(self):
        data = SystemData()
        if not HAS_PSUTIL:
            return data

        # CPU
        data.cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        data.cpu_usage = sum(data.cpu_per_core) / len(data.cpu_per_core) if data.cpu_per_core else 0
        data.cpu_cores = psutil.cpu_count(logical=False) or 0
        data.cpu_threads = psutil.cpu_count(logical=True) or 0
        try:
            freq = psutil.cpu_freq()
            if freq:
                data.cpu_freq_current = freq.current
                data.cpu_freq_max = freq.max or freq.current
        except Exception:
            pass

        # CPU Temperature
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                temp_list = []
                for key, entries in temps.items():
                    for entry in entries:
                        if entry.current and entry.current > 0:
                            temp_list.append(entry.current)
                if temp_list:
                    data.cpu_temp = {"CPU": round(max(temp_list), 1)}
                    for key, entries in temps.items():
                        for i, entry in enumerate(entries):
                            if entry.current and entry.current > 0:
                                label = entry.label if entry.label else f"Core {i}"
                                data.cpu_temp[label] = round(entry.current, 1)
        except Exception:
            pass

        # GPU
        self._collect_gpu(data)

        # RAM
        try:
            vm = psutil.virtual_memory()
            data.ram_total = vm.total / (1024**3)
            data.ram_used = vm.used / (1024**3)
            data.ram_avail = vm.available / (1024**3)
            data.ram_pct = vm.percent
            if self._wmi:
                for mem in self._wmi.Win32_PhysicalMemory():
                    if hasattr(mem, "Speed") and mem.Speed:
                        data.ram_speed = int(mem.Speed)
                        break
        except Exception:
            pass

        # Fans
        try:
            fans = psutil.sensors_fans()
            if fans:
                data.fans = []
                for key, entries in fans.items():
                    for entry in entries:
                        rpm = entry.fans[0] if entry.fans else 0
                        label = entry.label if entry.label else f"{key} Fan"
                        data.fans.append((label, rpm))
        except Exception:
            pass

        # Disk
        try:
            for part in psutil.disk_partitions(all=False):
                if "cdrom" in part.opts or part.fstype == "":
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    data.disk_total = usage.total / (1024**3)
                    data.disk_used = usage.used / (1024**3)
                    data.disk_pct = usage.percent
                    break
                except Exception:
                    pass
        except Exception:
            pass

        # Uptime
        try:
            boot_time = psutil.boot_time()
            data.uptime = (time.time() - boot_time) / 3600
        except Exception:
            pass

        return data

    def _collect_gpu(self, data):
        """Collect GPU info using NVML or WMI"""
        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                data.gpu_name = pynvml.nvmlDeviceGetName(handle)
                data.gpu_usage = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
                data.gpu_temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                power = pynvml.nvmlDeviceGetPowerUsage(handle)
                data.gpu_power = power / 1000.0
                pynvml.nvmlShutdown()
                return
        except Exception:
            pass

        if self._wmi:
            try:
                for gpu in self._wmi.Win32_VideoController():
                    if hasattr(gpu, "Name") and gpu.Name:
                        data.gpu_name = gpu.Name
                    if hasattr(gpu, "AdapterRAM") and gpu.AdapterRAM:
                        data.gpu_mem_total = gpu.AdapterRAM / (1024**2)
            except Exception:
                pass
            try:
                for gpu in self._wmi.Win32_PerfFormattedData_AdapterVideo():
                    if hasattr(gpu, "PercentIdleTime"):
                        data.gpu_usage = max(0, 100 - gpu.PercentIdleTime)
            except Exception:
                pass


# ============================================================
# NOTIFICATION MANAGER
# ============================================================

class NotificationManager(QObject):
    def __init__(self):
        super().__init__()
        self._last_notification = {}
        self._cooldown = thresholds.get('notification_cooldown_ms', 30000)

    def check_and_notify(self, key, message, severity='info'):
        if not config.get('notifications_enabled', True):
            return
        now = time.time()
        last = self._last_notification.get(key, 0)
        if (now - last) * 1000 < self._cooldown:
            return
        self._last_notification[key] = now
        self._show_notification(message, severity)

    def _show_notification(self, message, severity):
        try:
            if severity == 'critical':
                title = 'CRITICAL - Afterburner'
            elif severity == 'warning':
                title = 'WARNING - Afterburner'
            else:
                title = 'Afterburner'
            import subprocess
            ps_script = 'Add-Type -AssemblyName System.Windows.Forms'
            ps_script += chr(13) + 'chr(13)'
            subprocess.run(['powershell', '-Command', ps_script], capture_output=True, timeout=5)
        except Exception:
            pass
# Part 4: NotificationManager and AlertChecker

class NotificationManager(QObject):
    def __init__(self):
        super().__init__()
        self._last_notification = {}
        self._cooldown = thresholds.get('notification_cooldown_ms', 30000)

    def check_and_notify(self, key, message, severity='info'):
        if not config.get('notifications_enabled', True):
            return
        now = time.time()
        last = self._last_notification.get(key, 0)
        if (now - last) * 1000 < self._cooldown:
            return
        self._last_notification[key] = now
        self._show_notification(message, severity)

    def _show_notification(self, message, severity):
        try:
            title = severity.upper() + ' - Afterburner' if severity != 'info' else 'Afterburner'
            ps_script = f'Add-Type -AssemblyName System.Windows.Forms'
            subprocess.run(['powershell', '-Command', ps_script], capture_output=True, timeout=5)
        except Exception:
            pass


class AlertChecker(QObject):
    alert_triggered = pyqtSignal(str, str, str)

    def __init__(self, notification_manager):
        super().__init__()
        self._notif = notification_manager
        self._last_alert_time = {}

    def check(self, data):
        self._check_cpu_temp(data)
        self._check_gpu_temp(data)
        self._check_cpu_usage(data)
        self._check_gpu_usage(data)
        self._check_ram_usage(data)

    def _check_cpu_temp(self, data):
        temps = data.cpu_temp
        if not temps:
            return
        max_temp = max(temps.values())
        if max_temp >= thresholds['cpu_temp_crit']:
            self._alert('cpu_temp_crit', f'CPU temperature critical: {max_temp:.0f}\u00b0C', 'critical')
        elif max_temp >= thresholds['cpu_temp_warn']:
            self._alert('cpu_temp_warn', f'CPU temperature high: {max_temp:.0f}\u00b0C', 'warning')

    def _check_gpu_temp(self, data):
        if data.gpu_temp >= thresholds['gpu_temp_crit']:
            self._alert('gpu_temp_crit', f'GPU temperature critical: {data.gpu_temp:.0f}\u00b0C', 'critical')
        elif data.gpu_temp >= thresholds['gpu_temp_warn']:
            self._alert('gpu_temp_warn', f'GPU temperature high: {data.gpu_temp:.0f}\u00b0C', 'warning')

    def _check_cpu_usage(self, data):
        if data.cpu_usage >= thresholds['cpu_usage_warn']:
            self._alert('cpu_usage_warn', f'CPU usage high: {data.cpu_usage:.0f}%', 'warning')

    def _check_gpu_usage(self, data):
        if data.gpu_usage >= thresholds['gpu_usage_warn']:
            self._alert('gpu_usage_warn', f'GPU usage high: {data.gpu_usage:.0f}%', 'warning')

    def _check_ram_usage(self, data):
        if data.ram_pct >= thresholds['ram_usage_warn']:
            self._alert('ram_usage_warn', f'RAM usage high: {data.ram_pct:.0f}%', 'warning')

    def _alert(self, key, message, severity):
        now = time.time()
        last = self._last_alert_time.get(key, 0)
        cooldown = thresholds.get('notification_cooldown_ms', 30000) / 1000.0
        if (now - last) < cooldown:
            return
        self._last_alert_time[key] = now
        self._notif.check_and_notify(key, message, severity)
        self.alert_triggered.emit(key, message, severity)
