#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afterburner - UI Widgets module
Custom PyQt6 widgets for displaying system metrics.
"""

import math
from collections import deque
from typing import Any, Deque, List, Tuple

from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QBrush, QFontMetrics
)
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from config import Colors, config


# ============================================================
# SPARKLINE WIDGET
# ============================================================

class SparklineWidget(QFrame):
    """Mini sparkline chart for showing history."""

    def __init__(self, color: str = "accent_blue", parent: Any = None) -> None:
        super().__init__(parent)
        self._color: str = color
        self._data: Deque[float] = deque(
            maxlen=config.get("sparkline_history_len", 60)
        )
        self.setMinimumHeight(50)
        self.setMaximumHeight(50)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "SparklineWidget { background: transparent; border: none; }"
        )

    def add_value(self, value: float) -> None:
        """Add a new value to the sparkline."""
        self._data.append(value)
        self.update()

    def clear(self) -> None:
        """Clear all data."""
        self._data.clear()
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: ANN201
        """Paint the sparkline chart."""
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

        # Draw filled area
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
                prev_normalized = (data[i - 1] - min_val) / range_val
                prev_y = h - prev_normalized * (h - 4) - 2
                cx = (prev_x + x) / 2
                path.quadTo(
                    QPointF(prev_x, prev_y),
                    QPointF(cx, (prev_y + y) / 2)
                )
                path.lineTo(x, y)

        path.lineTo(w, h)
        path.closeSubpath()

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0, color.lighter(130))
        gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillPath(path, gradient)

        # Draw line
        color.setAlpha(200)
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
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


# ============================================================
# CIRCULAR GAUGE WIDGET
# ============================================================

class CircularGaugeWidget(QFrame):
    """Circular gauge for CPU/GPU/RAM usage."""

    def __init__(
        self,
        color: str = "accent_blue",
        parent: Any = None
    ) -> None:
        super().__init__(parent)
        self._color: str = color
        self._value: float = 0.0
        self._target_value: float = 0.0
        self._label: str = ""
        self._unit: str = "%"
        self._sublabel: str = ""
        self._subvalue: str = ""
        self._size: int = 160

        self.setMinimumSize(self._size, self._size)
        self.setMaximumSize(self._size, self._size)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "CircularGaugeWidget { background: transparent; border: none; }"
        )

    def set_value(self, value: float) -> None:
        """Set the current gauge value (0-100)."""
        self._target_value = max(0.0, min(100.0, value))
        self.update()

    def set_label(self, label: str) -> None:
        """Set the gauge label."""
        self._label = label

    def set_sublabel(
        self, sublabel: str, subvalue: str = ""
    ) -> None:
        """Set sublabel text and value."""
        self._sublabel = sublabel
        self._subvalue = subvalue

    def paintEvent(self, event: Any) -> None:  # noqa: ANN201
        """Paint the circular gauge."""
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
        gradient.setColorAt(
            1,
            Colors.get("accent_red") if value > 80 else color
        )
        painter.setPen(
            QPen(
                gradient, 8,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap
            )
        )
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
            sub_text = (
                f"{self._sublabel}: {self._subvalue}"
                if self._subvalue
                else self._sublabel
            )
            painter.drawText(
                QRectF(cx - radius, cy + radius * 0.8, radius * 2, 16),
                Qt.AlignmentFlag.AlignCenter,
                sub_text
            )

        painter.end()


# ============================================================
# INFO CARD WIDGET
# ============================================================

class InfoCardWidget(QFrame):
    """Card widget for displaying info items."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._items: List[Tuple[str, str, str]] = []
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "InfoCardWidget { "
            "   background: #131a2b; "
            "   border: 1px solid #1e2a45; "
            "   border-radius: 12px; "
            "   padding: 12px; "
            "} "
            "InfoCardWidget:hover { "
            "   background: #1a2340; "
            "   border: 1px solid #2a3a5a; "
            "}"
        )

    def add_item(
        self, label: str, value: str, color: str = "accent_blue"
    ) -> None:
        """Add a metric item to the card."""
        self._items.append((label, value, color))
        self.update()

    def clear_items(self) -> None:
        """Clear all items."""
        self._items.clear()
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: ANN201
        """Paint the info card."""
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


# ============================================================
# MAIN CHART WIDGET
# ============================================================

class MainChartWidget(QFrame):
    """Main chart showing multiple metrics over time."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._cpu_history: Deque[float] = deque(
            maxlen=config["chart_history_len"]
        )
        self._gpu_history: Deque[float] = deque(
            maxlen=config["chart_history_len"]
        )
        self._ram_history: Deque[float] = deque(
            maxlen=config["chart_history_len"]
        )
        self.setMinimumHeight(200)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "MainChartWidget { "
            "   background: #131a2b; "
            "   border: 1px solid #1e2a45; "
            "   border-radius: 12px; "
            "}"
        )
        self._legend_items: List[Tuple[str, str]] = [
            ("CPU", "accent_blue"),
            ("GPU", "accent_cyan"),
            ("RAM", "accent_purple"),
        ]

    def add_data(self, cpu: float, gpu: float, ram: float) -> None:
        """Add new data points to the chart."""
        self._cpu_history.append(cpu)
        self._gpu_history.append(gpu)
        self._ram_history.append(ram)
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: ANN201
        """Paint the main chart."""
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

        # Grid lines
        painter.setPen(QPen(QColor(30, 42, 69, 100), 1))
        for i in range(5):
            y = margin_top + chart_h * i / 4
            painter.drawLine(
                margin_left, int(y), w - margin_right, int(y)
            )
            val = 100 - i * 25
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            painter.setPen(QColor(config["theme"]["text_dim"]))
            painter.drawText(5, int(y) + 4, f"{val}%")

        # Datasets
        datasets: List[Tuple[Any, str]] = [
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

            step = (
                chart_w / (len(data) - 1)
                if len(data) > 1
                else chart_w
            )

            painter.beginPath()
            for i, val in enumerate(data):
                x = margin_left + i * step
                y = margin_top + chart_h * (1 - val / 100)
                if i == 0:
                    painter.moveTo(x, y)
                else:
                    painter.lineTo(x, y)

            painter.strokePath(painter.path(), pen)

        # Legend
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
