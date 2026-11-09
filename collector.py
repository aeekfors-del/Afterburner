#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afterburner - Data collector module
Handles system metrics collection (CPU, GPU, RAM, Fans, Disk, Uptime).
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import pynvml
import psutil

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

from PyQt6.QtCore import QThread, pyqtSignal

from config import config, thresholds

logger = logging.getLogger("Afterburner.collector")


# ============================================================
# DATA MODEL
# ============================================================

class SystemData:
    """Holds current system metrics - plain data class."""

    __slots__ = [
        "cpu_usage", "cpu_per_core", "cpu_temp", "cpu_freq_current",
        "cpu_freq_max", "cpu_cores", "cpu_threads", "cpu_power",
        "gpu_usage", "gpu_temp", "gpu_mem_used", "gpu_mem_total",
        "gpu_mem_pct", "gpu_freq", "gpu_power", "gpu_name",
        "ram_total", "ram_used", "ram_avail", "ram_pct", "ram_speed",
        "fans", "disk_total", "disk_used", "disk_pct", "uptime",
    ]

    def __init__(self) -> None:
        self.cpu_usage: float = 0.0
        self.cpu_per_core: List[float] = []
        self.cpu_temp: Dict[str, float] = {}
        self.cpu_freq_current: float = 0.0
        self.cpu_freq_max: float = 0.0
        self.cpu_cores: int = 0
        self.cpu_threads: int = 0
        self.cpu_power: float = 0.0
        self.gpu_usage: float = 0.0
        self.gpu_temp: float = 0.0
        self.gpu_mem_used: float = 0.0
        self.gpu_mem_total: float = 0.0
        self.gpu_mem_pct: float = 0.0
        self.gpu_freq: float = 0.0
        self.gpu_power: float = 0.0
        self.gpu_name: str = "N/A"
        self.ram_total: float = 0.0
        self.ram_used: float = 0.0
        self.ram_avail: float = 0.0
        self.ram_pct: float = 0.0
        self.ram_speed: int = 0
        self.fans: List[Tuple[str, int]] = []
        self.disk_total: float = 0.0
        self.disk_used: float = 0.0
        self.disk_pct: float = 0.0
        self.uptime: float = 0.0

    def __repr__(self) -> str:
        return (
            f"SystemData(cpu={self.cpu_usage:.1f}%, gpu={self.gpu_usage:.1f}%, "
            f"ram={self.ram_pct:.1f}%)"
        )


# ============================================================
# DATA COLLECTOR THREAD
# ============================================================

class DataCollectorThread(QThread):
    """Background service thread that collects system metrics."""

    data_updated = pyqtSignal(SystemData)

    def __init__(self) -> None:
        super().__init__()
        self._running: bool = True
        self._wmi: Any = None
        if HAS_WMI:
            try:
                self._wmi = wmi.WMI()
            except Exception:
                logger.warning("Failed to initialize WMI")

    def run(self) -> None:
        """Main collection loop."""
        psutil.cpu_percent(interval=None, percpu=True)
        while self._running:
            try:
                data = self._collect()
                self.data_updated.emit(data)
            except Exception:
                logger.error("Collection error", exc_info=True)
            self.msleep(config.get("update_interval_ms", 1000))

    def stop(self) -> None:
        """Stop the collector thread."""
        self._running = False
        self.wait()

    def _collect(self) -> SystemData:
        """Collect all system metrics."""
        data = SystemData()

        if not psutil:
            return data

        self._collect_cpu(data)
        self._collect_gpu(data)
        self._collect_ram(data)
        self._collect_fans(data)
        self._collect_disk(data)
        self._collect_uptime(data)

        return data

    def _collect_cpu(self, data: SystemData) -> None:
        """Collect CPU metrics."""
        try:
            data.cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
            data.cpu_usage = (
                sum(data.cpu_per_core) / len(data.cpu_per_core)
                if data.cpu_per_core
                else 0.0
            )
            data.cpu_cores = psutil.cpu_count(logical=False) or 0
            data.cpu_threads = psutil.cpu_count(logical=True) or 0

            freq = psutil.cpu_freq()
            if freq:
                data.cpu_freq_current = freq.current or 0.0
                data.cpu_freq_max = (freq.max or freq.current or 0.0)
        except Exception:
            logger.warning("Failed to collect CPU metrics", exc_info=True)

        # CPU Temperature
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                temp_list: List[float] = []
                for entries in temps.values():
                    for entry in entries:
                        if entry.current and entry.current > 0:
                            temp_list.append(entry.current)

                if temp_list:
                    data.cpu_temp = {"CPU": round(max(temp_list), 1)}
                    for key, entries in temps.items():
                        for i, entry in enumerate(entries):
                            if entry.current and entry.current > 0:
                                label = entry.label or f"Core {i}"
                                data.cpu_temp[label] = round(entry.current, 1)
        except Exception:
            logger.warning("Failed to collect CPU temperature", exc_info=True)

    def _collect_gpu(self, data: SystemData) -> None:
        """Collect GPU info using NVML or WMI."""
        # Method 1: NVML via pynvml (NVIDIA)
        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count > 0:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                data.gpu_name = pynvml.nvmlDeviceGetName(handle)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                data.gpu_usage = float(util.gpu)
                data.gpu_temp = float(
                    pynvml.nvmlDeviceGetTemperature(
                        handle, pynvml.NVML_TEMPERATURE_GPU
                    )
                )
                data.gpu_power = (
                    pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                )
                pynvml.nvmlShutdown()
                return
        except Exception:
            pass

        # Method 2: WMI fallback
        if self._wmi:
            try:
                for gpu in self._wmi.Win32_VideoController():
                    if hasattr(gpu, "Name") and gpu.Name:
                        data.gpu_name = gpu.Name
                    if hasattr(gpu, "AdapterRAM") and gpu.AdapterRAM:
                        data.gpu_mem_total = gpu.AdapterRAM / (1024 ** 2)
            except Exception:
                logger.warning("Failed to collect GPU info via WMI", exc_info=True)

            try:
                for gpu in self._wmi.Win32_PerfFormattedData_AdapterVideo():
                    if hasattr(gpu, "PercentIdleTime"):
                        data.gpu_usage = max(0.0, 100.0 - gpu.PercentIdleTime)
            except Exception:
                logger.warning("Failed to collect GPU usage via WMI", exc_info=True)

    def _collect_ram(self, data: SystemData) -> None:
        """Collect RAM metrics."""
        try:
            vm = psutil.virtual_memory()
            data.ram_total = vm.total / (1024 ** 3)
            data.ram_used = vm.used / (1024 ** 3)
            data.ram_avail = vm.available / (1024 ** 3)
            data.ram_pct = float(vm.percent)

            if self._wmi:
                for mem in self._wmi.Win32_PhysicalMemory():
                    if hasattr(mem, "Speed") and mem.Speed:
                        data.ram_speed = int(mem.Speed)
                        break
        except Exception:
            logger.warning("Failed to collect RAM metrics", exc_info=True)

    def _collect_fans(self, data: SystemData) -> None:
        """Collect fan speed metrics."""
        try:
            fans = psutil.sensors_fans()
            if fans:
                data.fans = []
                for key, entries in fans.items():
                    for entry in entries:
                        rpm = entry.fans[0] if entry.fans else 0
                        label = entry.label or f"{key} Fan"
                        data.fans.append((label, rpm))
        except Exception:
            logger.warning("Failed to collect fan metrics", exc_info=True)

    def _collect_disk(self, data: SystemData) -> None:
        """Collect disk usage metrics."""
        try:
            for part in psutil.disk_partitions(all=False):
                if "cdrom" in part.opts or part.fstype == "":
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    data.disk_total = usage.total / (1024 ** 3)
                    data.disk_used = usage.used / (1024 ** 3)
                    data.disk_pct = float(usage.percent)
                    break
                except PermissionError:
                    continue
        except Exception:
            logger.warning("Failed to collect disk metrics", exc_info=True)

    def _collect_uptime(self, data: SystemData) -> None:
        """Collect system uptime."""
        try:
            boot_time = psutil.boot_time()
            data.uptime = (time.time() - boot_time) / 3600.0
        except Exception:
            logger.warning("Failed to collect uptime", exc_info=True)


# ============================================================
# NOTIFICATION MANAGER
# ============================================================

class NotificationManager:
    """Manages Windows toast notifications for threshold alerts."""

    def __init__(self) -> None:
        self._last_notification: Dict[str, float] = {}
        self._cooldown: float = thresholds.get("notification_cooldown_ms", 30000)

    def check_and_notify(
        self, key: str, message: str, severity: str = "info"
    ) -> None:
        """Check cooldown and show notification if needed."""
        if not config.get("notifications_enabled", True):
            return

        now = time.time()
        last = self._last_notification.get(key, 0)
        if (now - last) * 1000 < self._cooldown:
            return

        self._last_notification[key] = now
        self._show_notification(message, severity)

    def _show_notification(self, message: str, severity: str) -> None:
        """Show Windows toast notification via PowerShell."""
        try:
            import subprocess

            if severity == "critical":
                title = "CRITICAL - Afterburner"
            elif severity == "warning":
                title = "WARNING - Afterburner"
            else:
                title = "Afterburner"

            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$toast = [System.Windows.Forms.ToastNotificationManager]::"
                "CreateToastNotifier('Afterburner'); "
                "$text = '" + title + "\\n" + message + "'; "
                "$toast.Show($text)"
            )
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            logger.warning("Failed to show notification", exc_info=True)


# ============================================================
# ALERT CHECKER
# ============================================================

class AlertChecker:
    """Checks metrics against thresholds and triggers notifications."""

    def __init__(self, notification_manager: NotificationManager) -> None:
        self._notif = notification_manager
        self._last_alert_time: Dict[str, float] = {}
        self.alert_triggered = None  # Will be set by main.py if needed

    def check(self, data: SystemData) -> None:
        """Check all metrics against thresholds."""
        self._check_cpu_temp(data)
        self._check_gpu_temp(data)
        self._check_cpu_usage(data)
        self._check_gpu_usage(data)
        self._check_ram_usage(data)

    def _check_cpu_temp(self, data: SystemData) -> None:
        """Check CPU temperature thresholds."""
        temps = data.cpu_temp
        if not temps:
            return

        max_temp = max(temps.values())

        if max_temp >= thresholds["cpu_temp_crit"]:
            self._alert(
                "cpu_temp_crit",
                f"CPU temperature critical: {max_temp:.0f}\u00b0C",
                "critical",
            )
        elif max_temp >= thresholds["cpu_temp_warn"]:
            self._alert(
                "cpu_temp_warn",
                f"CPU temperature high: {max_temp:.0f}\u00b0C",
                "warning",
            )

    def _check_gpu_temp(self, data: SystemData) -> None:
        """Check GPU temperature thresholds."""
        if data.gpu_temp >= thresholds["gpu_temp_crit"]:
            self._alert(
                "gpu_temp_crit",
                f"GPU temperature critical: {data.gpu_temp:.0f}\u00b0C",
                "critical",
            )
        elif data.gpu_temp >= thresholds["gpu_temp_warn"]:
            self._alert(
                "gpu_temp_warn",
                f"GPU temperature high: {data.gpu_temp:.0f}\u00b0C",
                "warning",
            )

    def _check_cpu_usage(self, data: SystemData) -> None:
        """Check CPU usage threshold."""
        if data.cpu_usage >= thresholds["cpu_usage_warn"]:
            self._alert(
                "cpu_usage_warn",
                f"CPU usage high: {data.cpu_usage:.0f}%",
                "warning",
            )

    def _check_gpu_usage(self, data: SystemData) -> None:
        """Check GPU usage threshold."""
        if data.gpu_usage >= thresholds["gpu_usage_warn"]:
            self._alert(
                "gpu_usage_warn",
                f"GPU usage high: {data.gpu_usage:.0f}%",
                "warning",
            )

    def _check_ram_usage(self, data: SystemData) -> None:
        """Check RAM usage threshold."""
        if data.ram_pct >= thresholds["ram_usage_warn"]:
            self._alert(
                "ram_usage_warn",
                f"RAM usage high: {data.ram_pct:.0f}%",
                "warning",
            )

    def _alert(
        self, key: str, message: str, severity: str
    ) -> None:
        """Trigger alert if cooldown has passed."""
        now = time.time()
        last = self._last_alert_time.get(key, 0)
        cooldown = thresholds.get("notification_cooldown_ms", 30000) / 1000.0

        if (now - last) < cooldown:
            return

        self._last_alert_time[key] = now
        self._notif.check_and_notify(key, message, severity)

        if self.alert_triggered:
            self.alert_triggered.emit(key, message, severity)
