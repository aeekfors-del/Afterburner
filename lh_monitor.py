#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LibreHardwareMonitor HTTP API client.
Connects to running LibreHardwareMonitor instance via HTTP.

Requirements:
  - LibreHardwareMonitor running with HTTP Server enabled
  - Default: http://localhost:8085
  - Enable in LHM: Tools → Settings → HTTP Server → Enable HTTP server
"""

import json
import logging
import re
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("Afterburner.lh_monitor")


class LhSensor:
    """Single sensor from LibreHardwareMonitor."""
    __slots__ = ["name", "value", "unit", "sensor_type", "sensor_id", "hardware"]

    def __init__(self) -> None:
        self.name: str = ""
        self.value: float = 0.0
        self.unit: str = ""
        self.sensor_type: str = ""
        self.sensor_id: str = ""
        self.hardware: str = ""

    def __repr__(self) -> str:
        return f"LhSensor({self.name}: {self.value:.2f} {self.unit})"


class LibreHardwareMonitor:
    """
    Client for LibreHardwareMonitor HTTP API.
    
    LHM exposes sensor data via:
      GET /data.json — full sensor tree in JSON
    """

    def __init__(self, base_url: str = "http://localhost:8085") -> None:
        self._base_url = base_url.rstrip("/")
        self._available = False
        self._sensors: List[LhSensor] = []
        self._last_fetch = 0.0
        self._cache_ttl = 0.15
        self._fetch()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def base_url(self) -> str:
        return self._base_url

    def _fetch(self) -> bool:
        """Fetch all sensor data from LHM /data.json endpoint."""
        try:
            url = f"{self._base_url}/data.json"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if time.time() - self._last_fetch > 10:
                logger.debug("LHM not reachable: %s", exc)
            self._available = False
            return False

        self._parse(data)
        self._available = True
        self._last_fetch = time.time()
        return True

    def _parse(self, data: Any) -> None:
        """Parse LHM JSON response into sensor list."""
        self._sensors = []
        if isinstance(data, dict):
            self._parse_node(data)

    def _parse_node(self, node: Dict[str, Any]) -> None:
        """Recursively parse LHM node tree."""
        children = node.get("Children", None)
        if children is not None and len(children) > 0:
            for child in children:
                if isinstance(child, dict):
                    self._parse_node(child)
            return

        sensor_type = node.get("Type", "")
        raw_value = node.get("RawValue", "")
        hardware_id = node.get("HardwareId", "")

        if not sensor_type or not raw_value:
            return

        sensor = LhSensor()
        sensor.name = node.get("Text", "")
        sensor.sensor_id = node.get("SensorId", "")
        sensor.hardware = hardware_id
        sensor.sensor_type = sensor_type.lower()

        # Parse value based on type
        value_str = node.get("Value", "")
        try:
            val_str = re.sub(r"[^\d.,-]", "", value_str.replace(",", "."))
            if val_str:
                sensor.value = float(val_str)
            else:
                sensor.value = 0.0
        except (ValueError, TypeError):
            sensor.value = 0.0

        # Parse unit from value string
        unit_match = re.search(r"([^\d.,\-]+)$", value_str)
        sensor.unit = unit_match.group(1).strip() if unit_match else ""

        self._sensors.append(sensor)

    # ============================================================
    # PUBLIC API
    # ============================================================

    def get_fan_speeds(self) -> List[Tuple[str, int]]:
        """Get all fan speeds in RPM."""
        if not self._available or not self._check_cache():
            self._fetch()
        return [(s.name, int(s.value)) for s in self._sensors
                if s.sensor_type == "fan" and s.value > 0]

    def get_voltages(self) -> List[Tuple[str, float]]:
        """Get all voltages in Volts."""
        if not self._available or not self._check_cache():
            self._fetch()
        return [(s.name, round(s.value, 3)) for s in self._sensors
                if s.sensor_type == "voltage" and s.value > 0]

    def get_temperatures(self) -> List[Tuple[str, float]]:
        """Get all temperatures in °C."""
        if not self._available or not self._check_cache():
            self._fetch()
        return [(s.name, round(s.value, 1)) for s in self._sensors
                if s.sensor_type == "temperature" and s.value > 0]

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
                "id": s.sensor_id,
                "hardware": s.hardware,
            }
            for s in self._sensors
        ]

    def _check_cache(self) -> bool:
        """Return True if cache is still valid."""
        return (time.time() - self._last_fetch) < self._cache_ttl

    def close(self) -> None:
        """Release resources."""
        self._sensors.clear()
        self._available = False
