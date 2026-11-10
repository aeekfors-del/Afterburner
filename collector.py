#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data collector for Afterburner system monitor.
Integrates psutil, pynvml, and LibreHardwareMonitor.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import pynvml
import psutil
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

try:
    from lh_monitor import LibreHardwareMonitor
    HAS_LHM = True
except ImportError:
    HAS_LHM = False

from config import config

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
        "gpu_mem_pct", "gpu_freq", "gpu_mem_freq", "gpu_power", 
        "gpu_voltage", "gpu_name",
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
        self.gpu_mem_freq: float = 0.0  # <-- НОВОЕ
        self.gpu_power: float = 0.0
        self.gpu_voltage: float = 0.0   # <-- НОВОЕ
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
        self._lhm: Optional[LibreHardwareMonitor] = None
        
        if HAS_WMI:
            try:
                self._wmi = wmi.WMI()
            except Exception:
                logger.warning("Failed to initialize WMI")
                
        if HAS_LHM:
            try:
                self._lhm = LibreHardwareMonitor()
                if self._lhm.available:
                    logger.info("LibreHardwareMonitor connected successfully")
                else:
                    logger.warning("LibreHardwareMonitor not reachable (is HTTP server enabled?)")
            except Exception as e:
                logger.warning(f"Failed to initialize LibreHardwareMonitor: {e}")

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
        if self._lhm:
            self._lhm.close()
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
                if data.cpu_per_core else 0.0
            )
            data.cpu_cores = psutil.cpu_count(logical=False) or 0
            data.cpu_threads = psutil.cpu_count(logical=True) or 0

            freq = psutil.cpu_freq()
            if freq:
                data.cpu_freq_current = freq.current or 0.0
                data.cpu_freq_max = (freq.max or freq.current or 0.0)
                
            # CPU Temperature fallback to LHM if psutil fails (typical on Windows)
            if not data.cpu_temp and self._lhm and self._lhm.available:
                temps = self._lhm.get_temperatures()
                cpu_temps = [t for t in temps if "cpu" in t[0].lower() or "package" in t[0].lower()]
                if cpu_temps:
                    data.cpu_temp = {"CPU": max(t[1] for t in cpu_temps)}
                    
        except Exception:
            logger.warning("Failed to collect CPU metrics", exc_info=True)

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
                    pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                )
                
                data.gpu_power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
                
                # <-- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Частоты GPU -->
                try:
                    data.gpu_freq = float(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS))
                except Exception:
                    pass
                    
                try:
                    data.gpu_mem_freq = float(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM))
                except Exception:
                    pass

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
        """Collect fan speeds."""
        try:
            fans = psutil.sensors_fans()
            if fans:
                data.fans = []
                for key, entries in fans.items():
                    for entry in entries:
                        rpm = entry.current if hasattr(entry, 'current') else (entry.fans[0] if entry.fans else 0)
                        label = entry.label if entry.label else f"{key} Fan"
                        data.fans.append((label, int(rpm)))
        except Exception:
            pass
            
        # Fallback to LHM if psutil returned nothing (typical on Windows)
        if not data.fans and self._lhm and self._lhm.available:
            data.fans = self._lhm.get_fan_speeds()

    def _collect_disk(self, data: SystemData) -> None:
        """Collect disk metrics (first non-removable drive)."""
        try:
            for part in psutil.disk_partitions(all=False):
                if 'cdrom' in part.opts or part.fstype == '':
                    continue
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    data.disk_total = usage.total / (1024 ** 3)
                    data.disk_used = usage.used / (1024 ** 3)
                    data.disk_pct = usage.percent
                except Exception:
                    pass
                break  # Берем только первый основной диск для простоты
        except Exception:
            logger.warning("Failed to collect disk metrics", exc_info=True)

    def _collect_uptime(self, data: SystemData) -> None:
        """Collect system uptime."""
        try:
            boot_time = psutil.boot_time()
            data.uptime = (time.time() - boot_time) / 3600
        except Exception:
            pass