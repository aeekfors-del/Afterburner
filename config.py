#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afterburner - Configuration module
Handles loading, saving, and managing application settings.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from PyQt6.QtGui import QColor

logger = logging.getLogger("Afterburner.config")

# ============================================================
# PATHS & DEFAULTS
# ============================================================

APPDATA = os.getenv("APPDATA", str(Path.home()))
CONFIG_PATH = Path(APPDATA) / "Afterburner" / "config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
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

DEFAULT_THRESHOLDS: Dict[str, float] = {
    "cpu_temp_warn": 80.0,
    "cpu_temp_crit": 90.0,
    "gpu_temp_warn": 75.0,
    "gpu_temp_crit": 85.0,
    "cpu_usage_warn": 85.0,
    "gpu_usage_warn": 85.0,
    "ram_usage_warn": 85.0,
    "notification_cooldown_ms": 30000,
}


# ============================================================
# GLOBAL CONFIG STATE
# ============================================================

config: Dict[str, Any] = DEFAULT_CONFIG.copy()
thresholds: Dict[str, float] = DEFAULT_THRESHOLDS.copy()


def load_config() -> None:
    """Load configuration from JSON file."""
    global config, thresholds

    if not CONFIG_PATH.exists():
        return

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved: Dict[str, Any] = json.load(f)

        if "config" in saved and isinstance(saved["config"], dict):
            config.update(saved["config"])
        if "thresholds" in saved and isinstance(saved["thresholds"], dict):
            thresholds.update(saved["thresholds"])
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("Failed to load config: %s", exc, exc_info=True)


def save_config() -> None:
    """Save current configuration to JSON file."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"config": config, "thresholds": thresholds}, f, indent=2)
    except IOError as exc:
        logger.error("Failed to save config: %s", exc)


# ============================================================
# COLOR HELPERS
# ============================================================

class Colors:
    """Helper class for theme colors."""

    @staticmethod
    def get(name: str) -> QColor:
        """Get a QColor from the theme by name."""
        return QColor(config["theme"][name])

    @staticmethod
    def usage_color(usage: float) -> QColor:
        """Get color based on usage percentage."""
        if usage < 50:
            return Colors.get("accent_green")
        elif usage < 75:
            return Colors.get("accent_yellow")
        elif usage < 90:
            return Colors.get("accent_orange")
        else:
            return Colors.get("accent_red")
