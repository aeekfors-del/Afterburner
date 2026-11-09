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
import subprocess
import winreg
from collections import deque
from datetime import datetime
from pathlib import Path

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

# Load config
config = DEFAULT_CONFIG.copy()
thresholds = DEFAULT_THRESHOLDS.copy()

if CONFIG_PATH.exists():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        if "config" in saved:
            config.update(saved["config"])
        if "thresholds" in saved:
            thresholds.update(saved["thresholds"])
    except Exception:
        pass


def save_config():
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
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
# DATA MODEL (plain data class, no QObject)
# ============================================================

class SystemData:
    """Holds current system metrics - plain data class"""
    __slots__ = [
        'cpu_usage', 'cpu_per_core', 'cpu_temp', 'cpu_freq_current',
        'cpu_freq_max', 'cpu_cores', 'cpu_threads', 'cpu_power',
        'gpu_usage', 'gpu_temp', 'gpu_mem_used', 'gpu_mem_total',
        'gpu_mem_pct', 'gpu_freq', 'gpu_power', 'gpu_name',
        'ram_total', 'ram_used', 'ram_avail', 'ram_pct', 'ram_speed',
        'fans', 'disk_total', 'disk_used', 'disk_pct', 'uptime',
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
        # Initialize psutil CPU percent
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
                    if hasattr(mem, 'Speed') and mem.Speed:
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
                if 'cdrom' in part.opts or part.fstype == '':
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    data.disk_total = usage.total / (1024**3)
                    data.disk_used = usage.used / (1024**3)
                    data.disk_pct = usage.percent
                except Exception:
                    pass
                break
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
        # Method 1: NVML (NVIDIA)
        try:
            nvml_lib = None
            for lib_path in ["C:\\Windows\\System32\\nvml.dll", "nvml.dll"]:
                try:
                    nvml_lib = ctypes.CDLL(lib_path)
                    break
                except Exception:
                    pass
            if nvml_lib is None:
                return
            nvml_lib.nvmlInit.restype = ctypes.c_int
            nvml_lib.nvmlInit()
            device_count = ctypes.c_int(0)
            nvml_lib.nvmlDeviceGetCount(ctypes.byref(device_count))
            if device_count.value > 0:
                handle = ctypes.c_int(0)
                nvml_lib.nvmlDeviceGetHandleByIndex(0, ctypes.byref(handle))
                name_buf = ctypes.create_string_buffer(128)
                nvml_lib.nvmlDeviceGetName(handle, name_buf, 128)
                data.gpu_name = name_buf.value.decode('utf-8', errors='ignore')
                utilization = ctypes.c_int(0)
                nvml_lib.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(utilization))
                data.gpu_usage = utilization.value
                temp = ctypes.c_int(0)
                nvml_lib.nvmlDeviceGetTemperature(handle, 0, ctypes.byref(temp))
                data.gpu_temp = temp.value
                power = ctypes.c_int(0)
                nvml_lib.nvmlDeviceGetPowerUsage(handle, ctypes.byref(power))
                data.gpu_power = power.value / 1000.0
                nvml_lib.nvmlShutdown()
                return
        except Exception:
            pass

        # Method 2: WMI
        if self._wmi:
            try:
                for gpu in self._wmi.Win32_VideoController():
                    if hasattr(gpu, 'Name') and gpu.Name:
                        data.gpu_name = gpu.Name
                    if hasattr(gpu, 'AdapterRAM') and gpu.AdapterRAM:
                        data.gpu_mem_total = gpu.AdapterRAM / (1024**2)
            except Exception:
                pass
            try:
                for gpu in self._wmi.Win32_PerfFormattedData_AdapterVideo():
                    if hasattr(gpu, 'PercentIdleTime'):
                        data.gpu_usage = max(0, 100 - gpu.PercentIdleTime)
            except Exception:
                pass


# ============================================================
# NOTIFICATION MANAGER - Windows toast notifications
# ============================================================

class NotificationManager(QObject):
    """Manages Windows toast notifications for threshold alerts"""
    def __init__(self):
        super().__init__()
        self._last_notification = {}
        self._cooldown = thresholds.get("notification_cooldown_ms", 30000)

    def check_and_notify(self, key, message, severity="info"):
        if not config.get("notifications_enabled", True):
            return
        now = time.time()
        last = self._last_notification.get(key, 0)
        if (now - last) * 1000 < self._cooldown:
            return
        self._last_notification[key] = now
        self._show_notification(message, severity)

    def _show_notification(self, message, severity):
        try:
            import subprocess
            if severity == "critical":
                title = "CRITICAL - Afterburner"
            elif severity == "warning":
                title = "WARNING - Afterburner"
            else:
                title = "Afterburner"

            # Use PowerShell to show notification
            ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
$toast = [System.Windows.Forms.ToastNotificationManager]::CreateToastNotifier("Afterburner")
$text = @"
{title}
{message}
"@
$toast.Show($text)
'''
            subprocess.run(['powershell', '-Command', ps_script],
                          capture_output=True, timeout=5)
        except Exception:
            pass


# ============================================================
# ALERT CHECKER - Threshold monitoring with notifications
# ============================================================

class AlertChecker(QObject):
    """Checks metrics against thresholds and triggers notifications"""
    alert_triggered = pyqtSignal(str, str, str)  # key, message, severity

    def __init__(self, notification_manager):
        super().__init__()
        self._notif = notification_manager
        self._last_alert_time = {}

    def check(self, data):
        """Check all metrics against thresholds"""
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
        if max_temp >= thresholds["cpu_temp_crit"]:
            self._alert("cpu_temp_crit", f"CPU temperature critical: {max_temp:.0f}°C", "critical")
        elif max_temp >= thresholds["cpu_temp_warn"]:
            self._alert("cpu_temp_warn", f"CPU temperature high: {max_temp:.0f}°C", "warning")

    def _check_gpu_temp(self, data):
        if data.gpu_temp >= thresholds["gpu_temp_crit"]:
            self._alert("gpu_temp_crit", f"GPU temperature critical: {data.gpu_temp:.0f}°C", "critical")
        elif data.gpu_temp >= thresholds["gpu_temp_warn"]:
            self._alert("gpu_temp_warn", f"GPU temperature high: {data.gpu_temp:.0f}°C", "warning")

    def _check_cpu_usage(self, data):
        if data.cpu_usage >= thresholds["cpu_usage_warn"]:
            self._alert("cpu_usage_warn", f"CPU usage high: {data.cpu_usage:.0f}%", "warning")

    def _check_gpu_usage(self, data):
        if data.gpu_usage >= thresholds["gpu_usage_warn"]:
            self._alert("gpu_usage_warn", f"GPU usage high: {data.gpu_usage:.0f}%", "warning")

    def _check_ram_usage(self, data):
        if data.ram_pct >= thresholds["ram_usage_warn"]:
            self._alert("ram_usage_warn", f"RAM usage high: {data.ram_pct:.0f}%", "warning")

    def _alert(self, key, message, severity):
        now = time.time()
        last = self._last_alert_time.get(key, 0)
        cooldown = thresholds.get("notification_cooldown_ms", 30000) / 1000.0
        if (now - last) < cooldown:
            return
        self._last_alert_time[key] = now
        self._notif.check_and_notify(key, message, severity)
        self.alert_triggered.emit(key, message, severity)


# ============================================================
# CUSTOM WIDGETS - GAUGES & CHARTS
# ============================================================


class SparklineWidget(QFrame):
    """Mini sparkline chart for showing history"""
    def __init__(self, color="accent_blue", parent=None):
        super().__init__(parent)
        self._color = color
        self._data = deque(maxlen=config.get("sparkline_history_len", 60))
        self.setMinimumHeight(50)
        self.setMaximumHeight(50)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "SparklineWidget { background: transparent; border: none; }"
        )

    def add_value(self, value):
        self._data.append(value)
        self.update()

    def clear(self):
        self._data.clear()
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        data = list(self._data)
        max_val = max(data) if data else 1
        if max_val == 0:
            max_val = 1
        min_val = min(data) if data else 0
        range_val = max_val - min_val if max_val != min_val else 1

        color = Colors.get(self._color)
        color.setAlpha(180)

        path = QPainterPath()
        step = w / (len(data) - 1) if len(data) > 1 else w
        path.moveTo(0, h)
        for i, val in enumerate(data):
            x = i * step
            normalized = (val - min_val) / range_val
            y = h - normalized * (h - 4) - 2
            if i == 0:
                path.lineTo(x, y)
            else:
                prev_x = (i - 1) * step
                prev_normalized = (data[i-1] - min_val) / range_val
                prev_y = h - prev_normalized * (h - 4) - 2
                cx = (prev_x + x) / 2
                path.quadTo(QPointF(prev_x, prev_y), QPointF(cx, (prev_y + y) / 2))
                path.lineTo(x, y)
        path.lineTo(w, h)
        path.closeSubpath()

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0, color.lighter(130))
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillPath(path, gradient)

        color.setAlpha(200)
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.beginPath()
        for i, val in enumerate(data):
            x = i * step
            normalized = (val - min_val) / range_val
            y = h - normalized * (h - 4) - 2
            if i == 0:
                painter.moveTo(x, y)
            else:
                painter.lineTo(x, y)
        painter.strokePath(painter.path(), pen)
        painter.end()


class CircularGaugeWidget(QFrame):
    """Circular gauge for CPU/GPU/RAM usage"""
    def __init__(self, color="accent_blue", parent=None):
        super().__init__(parent)
        self._color = color
        self._value = 0.0
        self._target_value = 0.0
        self._label = ""
        self._unit = "%"
        self._sublabel = ""
        self._subvalue = ""
        self._size = 160
        self.setMinimumSize(self._size, self._size)
        self.setMaximumSize(self._size, self._size)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("CircularGaugeWidget { background: transparent; border: none; }")

    def set_value(self, value):
        self._target_value = max(0, min(100, value))
        self.update()

    def set_label(self, label):
        self._label = label

    def set_sublabel(self, sublabel, subvalue=""):
        self._sublabel = sublabel
        self._subvalue = subvalue

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        radius = min(w, h) / 2 - 10
        value = self._target_value
        color = Colors.get(self._color)

        # Background arc
        start_angle = 135 * 16
        span_angle = -270 * 16
        painter.setPen(QPen(QColor(30, 42, 69), 8))
        painter.drawArc(
            QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
            start_angle, span_angle
        )

        # Value arc
        value_angle = int(span_angle * value / 100)
        gradient = QLinearGradient(
            cx + radius * math.cos(math.radians(225)),
            cy + radius * math.sin(math.radians(225)),
            cx + radius * math.cos(math.radians(45)),
            cy + radius * math.sin(math.radians(45))
        )
        gradient.setColorAt(0, Colors.get("accent_cyan"))
        gradient.setColorAt(0.5, color)
        gradient.setColorAt(1, Colors.get("accent_red") if value > 80 else color)
        painter.setPen(QPen(gradient, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(
            QRectF(cx - radius, cy - radius, radius * 2, radius * 2),
            start_angle, value_angle
        )

        # Center text - percentage
        font = QFont("Segoe UI", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(config["theme"]["text_primary"]))
        painter.drawText(
            QRectF(cx - radius, cy, radius * 2, radius * 0.8),
            Qt.AlignmentFlag.AlignCenter,
            f"{value:.0f}{self._unit}"
        )

        # Label
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        painter.setPen(QColor(config["theme"]["text_secondary"]))
        painter.drawText(
            QRectF(cx - radius, cy + radius * 0.5, radius * 2, 20),
            Qt.AlignmentFlag.AlignCenter,
            self._label
        )

        # Sub-label
        if self._sublabel:
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            painter.setPen(QColor(config["theme"]["text_dim"]))
            sub_text = f"{self._sublabel}: {self._subvalue}" if self._subvalue else self._sublabel
            painter.drawText(
                QRectF(cx - radius, cy + radius * 0.8, radius * 2, 16),
                Qt.AlignmentFlag.AlignCenter,
                sub_text
            )
        painter.end()


class InfoCardWidget(QFrame):
    """Card widget for displaying info items"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "InfoCardWidget {"
            "   background: #131a2b;"
            "   border: 1px solid #1e2a45;"
            "   border-radius: 12px;"
            "   padding: 12px;"
            "}"
            "InfoCardWidget:hover {"
            "   background: #1a2340;"
            "   border: 1px solid #2a3a5a;"
            "}"
        )

    def add_item(self, label, value, color="accent_blue"):
        self._items.append((label, value, color))
        self.update()

    def clear_items(self):
        self._items.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = 15
        for label, value, color in self._items:
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            painter.setPen(QColor(config["theme"]["text_secondary"]))
            painter.drawText(15, y + 10, label)
            font = QFont("Segoe UI", 13, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(Colors.get(color))
            painter.drawText(15, y + 30, value)
            y += 38
        painter.end()


class MainChartWidget(QFrame):
    """Main chart showing multiple metrics over time"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cpu_history = deque(maxlen=config["chart_history_len"])
        self._gpu_history = deque(maxlen=config["chart_history_len"])
        self._ram_history = deque(maxlen=config["chart_history_len"])
        self.setMinimumHeight(200)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "MainChartWidget {"
            "   background: #131a2b;"
            "   border: 1px solid #1e2a45;"
            "   border-radius: 12px;"
            "}"
        )
        self._legend_items = [
            ("CPU", "accent_blue"),
            ("GPU", "accent_cyan"),
            ("RAM", "accent_purple"),
        ]

    def add_data(self, cpu, gpu, ram):
        self._cpu_history.append(cpu)
        self._gpu_history.append(gpu)
        self._ram_history.append(ram)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        margin_top = 35
        margin_bottom = 25
        margin_left = 45
        margin_right = 15
        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        painter.setPen(QPen(QColor(30, 42, 69, 100), 1))
        for i in range(5):
            y = margin_top + chart_h * i / 4
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))
            val = 100 - i * 25
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.setPen(QColor(config["theme"]["text_dim"]))
            painter.drawText(5, int(y) + 4, f"{val}%")

        datasets = [
            (self._cpu_history, "accent_blue"),
            (self._gpu_history, "accent_cyan"),
            (self._ram_history, "accent_purple"),
        ]
        for data, color_name in datasets:
            if len(data) < 2:
                continue
            color = Colors.get(color_name)
            pen = QPen(color, 2)
            painter.setPen(pen)
            step = chart_w / (len(data) - 1) if len(data) > 1 else chart_w
            painter.beginPath()
            for i, val in enumerate(data):
                x = margin_left + i * step
                y = margin_top + chart_h * (1 - val / 100)
                if i == 0:
                    painter.moveTo(x, y)
                else:
                    painter.lineTo(x, y)
            painter.strokePath(painter.path(), pen)

        x = w - margin_right
        for name, color_name in reversed(self._legend_items):
            x -= 80
            color = Colors.get(color_name)
            painter.fillRect(x, 10, 12, 3, color)
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.setPen(QColor(config["theme"]["text_secondary"]))
            painter.drawText(x + 16, 14, name)
        painter.end()


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()
        self._data = None
        self._collector = None
        self._setup_ui()
        self._start_monitoring()

    def _setup_ui(self):
        self.setWindowTitle("Afterburner - System Monitor")
        self.resize(config["window_width"], config["window_height"])
        self.setMinimumSize(900, 700)

        # Dark theme
        self.setStyleSheet(
            "QMainWindow {"
            f"   background: {config['theme']['bg_dark']};"
            "}"
            "QLabel {"
            f"   color: {config['theme']['text_primary']};"
            "}"
            "QScrollArea {"
            f"   background: {config['theme']['bg_dark']};"
            f"   border: none;"
            "}"
        )

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Header
        header = self._create_header()
        main_layout.addWidget(header)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameStyle(QFrame.Shape.NoFrame)

        scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(15)

        # Row 1: CPU + GPU gauges
        gauge_row = self._create_gauge_row()
        self._scroll_layout.addWidget(gauge_row)

        # Row 2: RAM + Info cards
        info_row = self._create_info_row()
        self._scroll_layout.addWidget(info_row)

        # Row 3: Main chart
        self._main_chart = MainChartWidget()
        self._scroll_layout.addWidget(self._main_chart)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Store references to widgets for updates
        self._cpu_gauge = self.findChild(CircularGaugeWidget, "cpu_gauge")
        self._gpu_gauge = self.findChild(CircularGaugeWidget, "gpu_gauge")
        self._ram_gauge = self.findChild(CircularGaugeWidget, "ram_gauge")
        self._cpu_sparkline = self.findChild(SparklineWidget, "cpu_spark")
        self._gpu_sparkline = self.findChild(SparklineWidget, "gpu_spark")
        self._ram_sparkline = self.findChild(SparklineWidget, "ram_spark")
        self._info_card_cpu = self.findChild(InfoCardWidget, "cpu_info")
        self._info_card_gpu = self.findChild(InfoCardWidget, "gpu_info")
        self._info_card_sys = self.findChild(InfoCardWidget, "sys_info")

    def _create_header(self):
        header = QFrame()
        header.setFrameStyle(QFrame.Shape.StyledPanel)
        header.setStyleSheet(
            "QFrame {"
            f"   background: {config['theme']['bg_card']};"
            f"   border: 1px solid {config['theme']['border_color']};"
            "   border-radius: 12px;"
            "}"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 15, 20, 15)

        # Title
        title = QLabel("⚡ Afterburner")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {config['theme']['accent_cyan']};")
        layout.addWidget(title)

        layout.addStretch()

        # System info
        self._uptime_label = QLabel("Uptime: --")
        self._uptime_label.setFont(QFont("Segoe UI", 10))
        self._uptime_label.setStyleSheet(f"color: {config['theme']['text_secondary']};")
        layout.addWidget(self._uptime_label)

        self._time_label = QLabel()
        self._time_label.setFont(QFont("Segoe UI", 10))
        self._time_label.setStyleSheet(f"color: {config['theme']['text_secondary']};")
        layout.addWidget(self._time_label)

        # Update clock
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        return header

    def _update_clock(self):
        now = datetime.now()
        self._time_label.setText(now.strftime("%H:%M:%S"))

    def _create_gauge_row(self):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # CPU Gauge
        cpu_container = self._create_gauge_container("CPU", "accent_blue", "cpu_gauge", "cpu_spark")
        layout.addWidget(cpu_container, 1)

        # GPU Gauge
        gpu_container = self._create_gauge_container("GPU", "accent_cyan", "gpu_gauge", "gpu_spark")
        layout.addWidget(gpu_container, 1)

        # RAM Gauge
        ram_container = self._create_gauge_container("RAM", "accent_purple", "ram_gauge", "ram_spark")
        layout.addWidget(ram_container, 1)

        return row

    def _create_gauge_container(self, label, color_name, gauge_name, spark_name):
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.StyledPanel)
        container.setStyleSheet(
            f"QFrame {{ background: {config['theme']['bg_card']}; border: 1px solid {config['theme']['border_color']}; border-radius: 12px; }}"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        gauge = CircularGaugeWidget(color_name)
        gauge.setObjectName(gauge_name)
        gauge.set_label(label)
        layout.addWidget(gauge, alignment=Qt.AlignmentFlag.AlignCenter)

        spark = SparklineWidget(color_name)
        spark.setObjectName(spark_name)
        layout.addWidget(spark)

        return container

    def _create_info_row(self):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        # CPU Info
        cpu_info = InfoCardWidget()
        cpu_info.setObjectName("cpu_info")
        layout.addWidget(cpu_info, 1)

        # GPU Info
        gpu_info = InfoCardWidget()
        gpu_info.setObjectName("gpu_info")
        layout.addWidget(gpu_info, 1)

        # System Info
        sys_info = InfoCardWidget()
        sys_info.setObjectName("sys_info")
        layout.addWidget(sys_info, 1)

        return row

    def _start_monitoring(self):
        self._collector = DataCollectorThread()
        self._collector.data_updated.connect(self._on_data_updated)
        self._collector.start()

    def _on_data_updated(self, data):
        self._data = data

        # Update gauges
        if self._cpu_gauge:
            self._cpu_gauge.set_value(data.cpu_usage)
            temps = list(data.cpu_temp.values())
            temp_str = f"{max(temps):.0f}°C" if temps else "N/A"
            freq_str = f"{data.cpu_freq_current/1000:.2f} GHz" if data.cpu_freq_current > 0 else "N/A"
            self._cpu_gauge.set_sublabel(f"{data.cpu_cores}C/{data.cpu_threads}T", temp_str)

        if self._gpu_gauge:
            self._gpu_gauge.set_value(data.gpu_usage)
            temp_str = f"{data.gpu_temp:.0f}°C" if data.gpu_temp > 0 else "N/A"
            mem_str = f"{data.gpu_mem_used:.0f}/{data.gpu_mem_total:.0f} GB" if data.gpu_mem_total > 0 else ""
            self._gpu_gauge.set_sublabel(data.gpu_name[:15] if len(data.gpu_name) > 15 else data.gpu_name, temp_str)

        if self._ram_gauge:
            self._ram_gauge.set_value(data.ram_pct)
            speed_str = f"{data.ram_speed} MHz" if data.ram_speed > 0 else ""
            self._ram_gauge.set_sublabel(f"{data.ram_used:.1f}/{data.ram_total:.1f} GB", speed_str)

        # Update sparklines
        if self._cpu_sparkline:
            self._cpu_sparkline.add_value(data.cpu_usage)
        if self._gpu_sparkline:
            self._gpu_sparkline.add_value(data.gpu_usage)
        if self._ram_sparkline:
            self._ram_sparkline.add_value(data.ram_pct)

        # Update info cards
        if self._info_card_cpu:
            self._info_card_cpu.clear_items()
            temps = data.cpu_temp
            max_temp = max(temps.values()) if temps else 0
            self._info_card_cpu.add_item("CPU Usage", f"{data.cpu_usage:.1f}%", "accent_blue")
            self._info_card_cpu.add_item("Temperature", f"{max_temp:.0f}°C", "accent_red" if max_temp > 75 else "accent_yellow")
            self._info_card_cpu.add_item("Clock Speed", f"{data.cpu_freq_current/1000:.2f} GHz", "accent_cyan")
            self._info_card_cpu.add_item("Power (est.)", f"{data.cpu_power:.0f} W", "accent_orange")

        if self._info_card_gpu:
            self._info_card_gpu.clear_items()
            self._info_card_gpu.add_item("GPU Usage", f"{data.gpu_usage:.1f}%", "accent_cyan")
            self._info_card_gpu.add_item("Temperature", f"{data.gpu_temp:.0f}°C", "accent_red" if data.gpu_temp > 75 else "accent_yellow")
            self._info_card_gpu.add_item("VRAM", f"{data.gpu_mem_used:.0f}/{data.gpu_mem_total:.0f} GB", "accent_purple")
            self._info_card_gpu.add_item("Power", f"{data.gpu_power:.0f} W", "accent_orange")

        if self._info_card_sys:
            self._info_card_sys.clear_items()
            fans_text = ", ".join([f"{n}: {r} RPM" for n, r in data.fans[:3]]) if data.fans else "N/A"
            self._info_card_sys.add_item("Fans", fans_text, "accent_green")
            self._info_card_sys.add_item("RAM Speed", f"{data.ram_speed} MHz", "accent_blue")
            self._info_card_sys.add_item("Disk", f"{data.disk_used:.0f}/{data.disk_total:.0f} GB", "accent_yellow")
            hours = int(data.uptime)
            days = hours // 24
            rem_hours = hours % 24
            self._info_card_sys.add_item("Uptime", f"{days}d {rem_hours}h", "accent_pink")

        # Update main chart
        if self._main_chart:
            self._main_chart.add_data(data.cpu_usage, data.gpu_usage, data.ram_pct)

        # Update uptime
        if hasattr(self, '_uptime_label'):
            hours = int(data.uptime)
            days = hours // 24
            rem_hours = hours % 24
            self._uptime_label.setText(f"Uptime: {days}d {rem_hours}h")

    def closeEvent(self, event):
        if self._collector:
            self._collector.stop()
        event.accept()


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

def check_dependencies():
    """Check if required dependencies are available"""
    missing = []
    if not HAS_PSUTIL:
        missing.append("psutil")
    if not HAS_PSUTIL:
        missing.append("PyQt6")

    if missing:
        print(f"Warning: Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False
    return True


def main():
    if not check_dependencies():
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Afterburner")
    app.setOrganizationName("Afterburner")

    # Set application font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()

