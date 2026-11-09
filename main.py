#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afterburner - System Monitor Service
Main entry point with system tray and popup window.
"""

import atexit
import logging
import os
import sys
import time

from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt6.QtGui import QAction, QIcon, QCursor, QPainter, QColor, QFont, QPen
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout
)

from config import config, thresholds, load_config, save_config, Colors
from collector import DataCollectorThread, SystemData, AlertChecker, NotificationManager
from ui_widgets import CircularGaugeWidget, SparklineWidget, InfoCardWidget, MainChartWidget

logger = logging.getLogger("Afterburner.main")

# Module-level reference for cleanup
_collector = None


def cleanup():
    """Gracefully stop background threads on exit."""
    global _collector
    try:
        if _collector is not None:
            _collector.stop()
            logger.info("Collector stopped gracefully")
    except Exception:
        logger.warning("Cleanup error", exc_info=True)


atexit.register(cleanup)


# ============================================================
# SYSTEM TRAY ICON
# ============================================================

class SystemTrayIcon(QSystemTrayIcon):
    """System tray icon with popup menu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_visible = False
        self._popup_widget = None

        # Set icon
        self._create_icon()

        # Create menu
        self._create_menu()
        self.setContextMenu(self._menu)

        # Show tooltip
        self.setToolTip("Afterburner - System Monitor")

        # Connect signals
        self.activated.connect(self._on_activated)

        # Create popup widget
        self._setup_popup()

    def _create_icon(self):
        """Create a visible icon programmatically."""
        # Try to load from file first
        icon_path = "icon.png"
        if os.path.exists(icon_path):
            self.setIcon(QIcon(icon_path))
            return

        # Fallback: create a simple colored icon
        self._set_programmatic_icon()

    def _set_programmatic_icon(self):
        """Set icon drawn with QPainter."""
        from PyQt6.QtGui import QPixmap

        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor("#0a0e17"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Outer circle
        painter.setPen(QPen(QColor("#06b6d4"), 3))
        painter.setBrush(QColor("#0a0e17"))
        painter.drawEllipse(3, 3, size - 6, size - 6)

        # Letter "A"
        font = QFont("Arial", 32, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#06b6d4"))
        painter.drawText(
            QRectF(0, 0, size, size),
            Qt.AlignmentFlag.AlignCenter,
            "A",
        )

        painter.end()

        self.setIcon(QIcon(pixmap))

    def _create_menu(self):
        """Create context menu."""
        self._menu = QMenu()

        # Show/Hide action
        self._show_action = QAction("Show Popup", self._menu)
        self._show_action.triggered.connect(self._toggle_popup)
        self._menu.addAction(self._show_action)

        self._menu.addSeparator()

        # Settings action
        settings_action = QAction("Settings", self._menu)
        settings_action.triggered.connect(self._open_settings)
        self._menu.addAction(settings_action)

        self._menu.addSeparator()

        # Exit action
        exit_action = QAction("Exit", self._menu)
        exit_action.triggered.connect(self._exit_app)
        self._menu.addAction(exit_action)

    def _setup_popup(self):
        """Setup the popup widget."""
        self._popup_widget = PopupWidget()
        self._popup_widget.hide_event = lambda event: self._on_popup_hidden()

    def _toggle_popup(self):
        """Show or hide the popup."""
        if self._popup_visible:
            self._popup_widget.hide()
            self._popup_visible = False
        else:
            self._popup_widget.show()
            self._popup_widget.raise_()
            self._popup_visible = True

    def _on_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_popup()

    def _on_popup_hidden(self):
        """Handle popup window hiding."""
        self._popup_visible = False

    def _open_settings(self):
        """Open settings dialog."""
        logger.info("Settings requested")

    def set_collector(self, collector):
        """Connect data collector to popup widget."""
        self._popup_widget.set_collector(collector)

    def _exit_app(self):
        """Exit the application."""
        logger.info("Exiting application")
        QApplication.quit()


# ============================================================
# POPUP WIDGET
# ============================================================

class PopupWidget(QWidget):
    """Popup window displaying system metrics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide_event = lambda event: None

        self._setup_ui()
        self._setup_styles()
        self._setup_timer()

        # Connect to data collector
        self._collector = None

    def _setup_ui(self):
        """Setup the popup UI layout."""
        self.setWindowTitle("Afterburner")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        self._title_label = QLabel("AFTERBURNER")
        self._title_label.setStyleSheet("color: #e8eaf0; font-size: 14px; font-weight: bold;")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        self._time_label = QLabel("")
        self._time_label.setStyleSheet("color: #7a8ba8; font-size: 12px;")
        header_layout.addWidget(self._time_label)

        self._uptime_label = QLabel("Uptime: 0d 0h")
        self._uptime_label.setStyleSheet("color: #7a8ba8; font-size: 12px;")
        header_layout.addWidget(self._uptime_label)

        main_layout.addLayout(header_layout)

        # Main content - gauges and cards
        content_layout = QGridLayout()
        content_layout.setSpacing(15)

        # Left gauge - CPU
        self._cpu_gauge = CircularGaugeWidget("accent_blue")
        self._cpu_gauge.set_label("CPU")
        self._cpu_gauge.set_sublabel("Temp", "0°C")
        content_layout.addWidget(self._cpu_gauge, 0, 0)

        # Right gauge - GPU
        self._gpu_gauge = CircularGaugeWidget("accent_cyan")
        self._gpu_gauge.set_label("GPU")
        self._gpu_gauge.set_sublabel("VRAM", "0 GB")
        content_layout.addWidget(self._gpu_gauge, 0, 1)

        # Center panel - info cards
        self._info_card = InfoCardWidget()
        content_layout.addWidget(self._info_card, 0, 2)

        main_layout.addLayout(content_layout)

        # Bottom sparklines
        sparkline_layout = QHBoxLayout()
        sparkline_layout.setSpacing(10)

        self._cpu_sparkline = SparklineWidget("accent_blue")
        self._gpu_sparkline = SparklineWidget("accent_cyan")
        self._ram_sparkline = SparklineWidget("accent_purple")

        sparkline_layout.addWidget(self._cpu_sparkline)
        sparkline_layout.addWidget(self._gpu_sparkline)
        sparkline_layout.addWidget(self._ram_sparkline)

        main_layout.addLayout(sparkline_layout)

        # Set fixed size
        self.resize(800, 450)

    def _setup_styles(self):
        """Setup widget styles."""
        self.setStyleSheet(
            "PopupWidget { "
            "   background: rgba(10, 14, 23, 0.95); "
            "   border: 1px solid #1e2a45; "
            "   border-radius: 12px; "
            "}"
        )

    def _setup_timer(self):
        """Setup timer for updating time display."""
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self._update_time)
        self._time_timer.start(1000)
        self._update_time()

    def _update_time(self):
        """Update time display."""
        from datetime import datetime
        now = datetime.now()
        self._time_label.setText(now.strftime("%H:%M"))

    def set_collector(self, collector):
        """Connect to data collector thread."""
        self._collector = collector
        collector.data_updated.connect(self._on_data_updated)

    def _on_data_updated(self, data):
        """Handle new data from collector."""
        # Update CPU gauge
        self._cpu_gauge.set_value(data.cpu_usage)
        temp_str = f"{data.cpu_temp.get('CPU', 0):.0f}°C" if data.cpu_temp else "0°C"
        self._cpu_gauge.set_sublabel("Temp", temp_str)

        # Update GPU gauge
        self._gpu_gauge.set_value(data.gpu_usage)
        vram_str = f"{data.gpu_mem_used:.0f}/{data.gpu_mem_total:.0f} GB"
        self._gpu_gauge.set_sublabel("VRAM", vram_str)

        # Update info card
        self._info_card.clear_items()
        self._info_card.add_item("RAM", f"{data.ram_pct:.0f}%", "accent_purple")
        self._info_card.add_item("Disk", f"{data.disk_pct:.0f}%", "accent_green")

        # Update uptime
        days = int(data.uptime // 24)
        hours = int(data.uptime % 24)
        self._uptime_label.setText(f"Uptime: {days}d {hours}h")

        # Update sparklines
        self._cpu_sparkline.add_value(data.cpu_usage)
        self._gpu_sparkline.add_value(data.gpu_usage)
        self._ram_sparkline.add_value(data.ram_pct)

        # Update window title with key metrics
        self.setWindowTitle(f"Afterburner - CPU: {data.cpu_usage:.0f}% GPU: {data.gpu_usage:.0f}%")

    def hideEvent(self, event):
        """Handle hide event."""
        self.hide_event(event)
        super().hideEvent(event)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _on_alert_triggered(key, message, severity):
    """Handle alert triggered signal."""
    logger.warning(f"ALERT [{severity.upper()}]: {message}")


def _show_popup_tray(tray):
    """Show popup window centered on screen (called via QTimer)."""
    logger.info("Showing popup window via QTimer...")
    try:
        popup = tray._popup_widget
        # Center on primary screen
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - popup.width()) // 2
        y = (screen.height() - popup.height()) // 2
        popup.move(x, y)
        popup.show()
        popup.raise_()
        popup.activateWindow()
        logger.info(f"Popup shown at ({x}, {y}), visible: {popup.isVisible()}")
    except Exception as e:
        logger.error(f"Failed to show popup: {e}", exc_info=True)


# ============================================================
# MAIN APPLICATION
# ============================================================

def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("=" * 60)
    logger.info("Afterburner starting...")
    logger.info("=" * 60)

    # Load configuration
    logger.info("Loading configuration...")
    try:
        load_config()
        logger.info(f"Config loaded: update_interval={config.get('update_interval_ms')}ms")
        logger.info(f"Thresholds: cpu_temp_warn={thresholds['cpu_temp_warn']}°C")
    except Exception as e:
        logger.error(f"Failed to load config: {e}", exc_info=True)
        raise

    # Create Qt application
    logger.info("Creating QApplication...")
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Afterburner")
        app.setOrganizationName("Afterburner")
        logger.info("QApplication created successfully")
    except Exception as e:
        logger.error(f"Failed to create QApplication: {e}", exc_info=True)
        raise

    # Create data collector
    logger.info("Creating DataCollectorThread...")
    try:
        global _collector
        _collector = DataCollectorThread()
        _collector.start()
        logger.info(f"Collector started, thread ID: {_collector.thread()}")
    except Exception as e:
        logger.error(f"Failed to create collector: {e}", exc_info=True)
        raise

    # Check system tray availability
    logger.info("Checking system tray availability...")
    from PyQt6.QtWidgets import QSystemTrayIcon as QSTI
    tray_available = QSTI.isSystemTrayAvailable()
    logger.info(f"System tray available: {tray_available}")
    if not tray_available:
        logger.error("No system tray available! Check display settings.")
        # Create a simple window as fallback
        fallback = QLabel("System tray not available. Check display settings.")
        fallback.setWindowTitle("Afterburner")
        fallback.resize(400, 100)
        fallback.show()
        sys.exit(app.exec())

    # Create tray icon
    logger.info("Creating SystemTrayIcon...")
    try:
        tray = SystemTrayIcon()
        logger.info(f"SystemTrayIcon created, popup_widget exists: {tray._popup_widget is not None}")
        logger.info(f"Tray icon set: {tray.icon().isNull() if tray.icon() else 'NO ICON'}")
        logger.info(f"Has context menu: {tray.contextMenu() is not None}")
        # QSystemTrayIcon auto-appears in system tray — no show() needed
        logger.info("Tray icon should now be visible in system tray")
    except Exception as e:
        logger.error(f"Failed to create tray icon: {e}", exc_info=True)
        raise

    # Connect collector to popup
    logger.info("Connecting collector to popup widget...")
    try:
        tray.set_collector(_collector)
        logger.info("Collector connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect collector: {e}", exc_info=True)
        raise

    # Initialize AlertChecker and NotificationManager
    logger.info("Initializing AlertChecker and NotificationManager...")
    try:
        notif_manager = NotificationManager()
        alert_checker = AlertChecker(notif_manager)
        alert_checker.alert_triggered.connect(_on_alert_triggered)
        _collector.data_updated.connect(alert_checker.check)
        logger.info("AlertChecker initialized, threshold monitoring active")
        logger.info(f"Thresholds: cpu_temp_warn={thresholds['cpu_temp_warn']}°C, "
                     f"gpu_temp_warn={thresholds['gpu_temp_warn']}°C, "
                     f"cpu_usage_warn={thresholds['cpu_usage_warn']}%")
    except Exception as e:
        logger.error(f"Failed to initialize AlertChecker: {e}", exc_info=True)
        raise

    # Show initial popup if configured (disabled during dev for tray debugging)
    if config.get("show_popup_on_click", True):
        logger.info("Showing popup window after 1s delay...")
        try:
            # Small delay to ensure tray icon appears first
            QTimer.singleShot(1000, lambda: _show_popup_tray(tray))
        except Exception as e:
            logger.error(f"Failed to schedule popup: {e}", exc_info=True)
    else:
        logger.info("Popup auto-show disabled (tray only mode)")

    logger.info("=" * 60)
    logger.info("Afterburner started successfully!")
    logger.info("Check system tray for icon")
    logger.info("=" * 60)

    # Start application event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
