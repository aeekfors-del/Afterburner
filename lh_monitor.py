#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LibreHardwareMonitor HTTP API client.
Connects to running LibreHardwareMonitor instance via HTTP API.

Requirements:
  - LibreHardwareMonitor running with HTTP Server enabled
  - Default: http://localhost:8085
  - Enable in LHM: Settings → HTTP Server → Enable HTTP server
"""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Afterburner.lh_monitor")


class LhSensor:
    """Single sensor from LibreHardwareMonitor."""
    __slots__ = ["name", "value", "unit", "sensor_type", "identifier", "path"]

    def __init__(self) -> None:
        self.name: str = ""
        self.value: float = 0.0
        self.unit: str = ""
        self.sensor_type: str = ""
        self.identifier: str = ""
        self.path: str = ""

    def __repr__(self) -> str:
        return f"LhSensor({self.name}: {self.value:.2f} {self.unit})"


class LibreHardwareMonitor:
    """
    Client for LibreHardwareMonitor HTTP API.
    
    LHM exposes sensor data via REST-like endpoints:
      GET /api/search?type=sensor  — full sensor tree
      GET /api/values              — flat sensor values
    """

    # LHM unit names
    UNIT_TEMPERATURE = "degreeCelsius"
    UNIT_FAN_RPM = "revolutionsPerMinute"
    UNIT_VOLTAGE = "volt"
    UNIT_POWER = "watt"
    UNIT_CURRENT = "ampere"
    UNIT_CLOCK = "megahertz"
    UNIT_PERCENT = "percent"

    def __init__(self, base_url: str = "http://localhost:8085") -> None:
        self._base_url = base_url.rstrip("/")
        self._available = False
        self._sensors: List[LhSensor] = []
        self._last_fetch = 0.0
        self._cache_ttl = 0.15  # 150ms cache
        self._fetch()  # initial fetch

    @property
    def available(self) -> bool:
        return self._available

    @property
    def base_url(self) -> str:
        return self._base_url

    def _fetch(self) -> bool:
        """Fetch all sensor data from LHM HTTP API."""
        try:
            url = f"{self._base_url}/api/search?type=sensor"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            if time.time() - self._last_fetch > 10:
                logger.debug("LHM not reachable: %s", exc)
            self._available = False
            return False
        except Exception as exc:
            if time.time() - self._last_fetch > 10:
                logger.warning("LHM fetch error: %s", exc)
            self._available = False
            return False

        self._parse(data)
        self._available = True
        self._last_fetch = time.time()
        return True

    def _parse(self, data: List[Dict[str, Any]]) -> None:
        """Parse LHM JSON response into sensor list."""
        self._sensors = []
        for item in data:
            self._parse_node(item)

    def _parse_node(self, node: Dict[str, Any]) -> None:
        """Recursively parse LHM node tree."""
        identifier = node.get("Identifier", "")
        name = node.get("Name", "")

        # Parse groups (e.g., "GPU core", "Memory", "Heat sink")
        for group in node.get("Groups", []):
            self._parse_node(group)

        # Parse sections (e.g., "SMN", "CPU DIE")
        for section in node.get("Sections", []):
            self._parse_node(section)

        # Parse parameters (actual sensors)
        for param in node.get("Parameters", []):
            value = param.get("Value")
            if value is None:
                continue

            try:
                val = float(value)
            except (ValueError, TypeError):
                continue

            sensor = LhSensor()
            sensor.name = param.get("Name", name)
            sensor.value = val
            sensor.unit = param.get("Unit", "")
            sensor.identifier = param.get("Identifier", "")
            sensor.path = f"{identifier}/{name}" if identifier else name

            # Determine sensor type from unit
            unit = sensor.unit.lower()
            if unit == self.UNIT_TEMPERATURE:
                sensor.sensor_type = "temperature"
            elif unit == self.UNIT_FAN_RPM:
                sensor.sensor_type = "fan"
            elif unit == self.UNIT_VOLTAGE:
                sensor.sensor_type = "voltage"
            elif unit == self.UNIT_POWER:
                sensor.sensor_type = "power"
            elif unit == self.UNIT_CURRENT:
                sensor.sensor_type = "current"
            elif unit == self.UNIT_CLOCK:
                sensor.sensor_type = "clock"
            elif unit == self.UNIT_PERCENT:
                sensor.sensor_type = "percent"
            else:
                sensor.sensor_type = "other"

            self._sensors.append(sensor)

    # ============================================================
    # PUBLIC API — motherboard sensors
    # ============================================================

    def get_fan_speeds(self) -> List[Tuple[str, int]]:
        """Get all fan speeds in RPM."""
        if not self._available or not self._check_cache():
            self._fetch()
        result: List[Tuple[str, int]] = []
        for s in self._sensors:
            if s.sensor_type == "fan" and s.value > 0:
                result.append((s.name, int(s.value)))
        return result

    def get_voltages(self) -> List[Tuple[str, float]]:
        """Get all voltages in Volts."""
        if not self._available or not self._check_cache():
            self._fetch()
        result: List[Tuple[str, float]] = []
        for s in self._sensors:
            if s.sensor_type == "voltage" and s.value > 0:
                result.append((s.name, round(s.value, 3)))
        return result

    def get_temperatures(self) -> List[Tuple[str, float]]:
        """Get all temperatures in °C."""
        if not self._available or not self._check_cache():
            self._fetch()
        result: List[Tuple[str, float]] = []
        for s in self._sensors:
            if s.sensor_type == "temperature" and s.value > 0:
                result.append((s.name, round(s.value, 1)))
        return result

    def get_all(self) -> Dict[str, List[Tuple[str, Any]]]:
        """Get all sensor categories."""
        if not self._available or not self._check_cache():
            self._fetch()
        return {
            "fans": self.get_fan_speeds(),
            "voltages": self.get_voltages(),
            "temps": self.get_temperatures(),
        }

    def get_raw_list(self) -> List[Dict[str, Any]]:
        """Get all sensors as flat list of dicts."""
        if not self._available or not self._check_cache():
            self._fetch()
        return [
            {
                "name": s.name,
                "value": s.value,
                "unit": s.unit,
                "type": s.sensor_type,
                "identifier": s.identifier,
                "path": s.path,
            }
            for s in self._sensors
        ]

    def get_cpu(self) -> Dict[str, Any]:
        """Get CPU-specific sensors."""
        if not self._available or not self._check_cache():
            self._fetch()
        return {
            "temps": [(n, v) for n, v in self._get_by_type("temperature") if "cpu" in n.lower() or "core" in n.lower()],
            "clocks": [(n, v) for n, v in self._get_by_type("clock") if "cpu" in n.lower()],
            "power": [(n, v) for n, v in self._get_by_type("power") if "cpu" in n.lower()],
        }

    def get_gpu(self) -> Dict[str, Any]:
        """Get GPU-specific sensors."""
        if not self._available or not self._check_cache():
            self._fetch()
        return {
            "temps": [(n, v) for n, v in self._get_by_type("temperature") if "gpu" in n.lower()],
            "fans": [(n, v) for n, v in self._get_by_type("fan") if "gpu" in n.lower()],
            "clocks": [(n, v) for n, v in self._get_by_type("clock") if "gpu" in n.lower()],
            "power": [(n, v) for n, v in self._get_by_type("power") if "gpu" in n.lower()],
            "memory": [(n, v) for n, v in self._get_by_type("clock") if "memory" in n.lower()],
        }

    def _get_by_type(self, stype: str) -> List[Tuple[str, float]]:
        """Get sensors by type."""
        return [(s.name, s.value) for s in self._sensors if s.sensor_type == stype]

    def _check_cache(self) -> bool:
        """Return True if cache is still valid."""
        return (time.time() - self._last_fetch) < self._cache_ttl

    def close(self) -> None:
        """Release resources."""
        self._sensors.clear()
        self._available = False
