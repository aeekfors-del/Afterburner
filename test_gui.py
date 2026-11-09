#!/usr/bin/env python3
"""Test GUI widgets standalone"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from ui_widgets import CircularGaugeWidget, SparklineWidget, InfoCardWidget

app = QApplication(sys.argv)

# Create popup-like window
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel
from PyQt6.QtCore import Qt

class TestPopup(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Afterburner - GUI Test")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.CustomizeWindowHint
        )
        self.setStyleSheet("background: #0a0e17;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Header
        header = QHBoxLayout()
        title = QLabel("AFTERBURNER")
        title.setStyleSheet("color: #e8eaf0; font-size: 14px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        time_label = QLabel("22:45")
        time_label.setStyleSheet("color: #7a8ba8; font-size: 12px;")
        header.addWidget(time_label)
        uptime_label = QLabel("Uptime: 3d 14h")
        uptime_label.setStyleSheet("color: #7a8ba8; font-size: 12px;")
        header.addWidget(uptime_label)
        layout.addLayout(header)

        # Gauges and cards
        content = QGridLayout()
        content.setSpacing(15)

        cpu_gauge = CircularGaugeWidget("accent_blue")
        cpu_gauge.set_label("CPU")
        cpu_gauge.set_sublabel("Temp", "65°C")
        cpu_gauge.set_value(65)
        content.addWidget(cpu_gauge, 0, 0)

        gpu_gauge = CircularGaugeWidget("accent_cyan")
        gpu_gauge.set_label("GPU")
        gpu_gauge.set_sublabel("VRAM", "8/12 GB")
        gpu_gauge.set_value(42)
        content.addWidget(gpu_gauge, 0, 1)

        info_card = InfoCardWidget()
        info_card.add_item("RAM", "73%", "accent_purple")
        info_card.add_item("Disk", "56%", "accent_green")
        content.addWidget(info_card, 0, 2)

        layout.addLayout(content)

        # Sparklines
        spark_layout = QHBoxLayout()
        spark_layout.setSpacing(10)

        cpu_spark = SparklineWidget("accent_blue")
        gpu_spark = SparklineWidget("accent_cyan")
        ram_spark = SparklineWidget("accent_purple")

        # Add some data
        for i in range(30):
            cpu_spark.add_value(40 + i * 1.5)
            gpu_spark.add_value(30 + i * 0.8)
            ram_spark.add_value(60 + i * 0.5)

        spark_layout.addWidget(cpu_spark)
        spark_layout.addWidget(gpu_spark)
        spark_layout.addWidget(ram_spark)
        layout.addLayout(spark_layout)

        self.resize(800, 450)

popup = TestPopup()
popup.show()
popup.raise_()

sys.exit(app.exec())
