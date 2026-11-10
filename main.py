#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afterburner - System Monitor Service
Main entry point with skin-based UI (MSI Cyborg Red style).
"""

import atexit
import logging
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QAction, QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu

from config import config, load_config
from collector import DataCollectorThread, SystemData

logger = logging.getLogger("Afterburner.main")

# Module-level reference for cleanup
_collector = None

SKIN_DIR = Path(__file__).parent / "Skins" / "MSICyborgRed"

# ============================================================
# НАСТРОЙКИ ПОЗИЦИЙ
# ============================================================

LEFT_CX = 130       # Центр левого тахометра (GPU Clock / Mem Clock)
RIGHT_CX = 600      # Центр правого тахометра (Voltage / Temp)

TOP_Y = 177         # Верхняя строка
BOT_Y = 218         # Нижняя строка

# Фиксированная ширина полей в символах
W_FREQ = 5          # частоты: "02262", "14001"
W_VOLT = 4          # напряжение: "1010"
W_TEMP = 4          # температура: "0040"

# Размер символа из DigitFont.png
CHAR_W = 16
CHAR_H = 32
BASE_CHAR = ord('-')   # первый символ в спрайт-листе


# ============================================================
# SKIN LOADING
# ============================================================

def _load_skin_with_transparency(path: Path) -> QPixmap:
    """Load PNG skin with color key transparency."""
    img = QImage(str(path))
    if img.isNull():
        logger.error("Skin file not found: %s", path)
        return QPixmap()

    key = img.pixelColor(0, 0)

    out = img.convertToFormat(QImage.Format.Format_ARGB32)
    for y in range(out.height()):
        for x in range(out.width()):
            c = out.pixelColor(x, y)
            if (abs(c.red() - key.red()) < 10 and
                    abs(c.green() - key.green()) < 10 and
                    abs(c.blue() - key.blue()) < 10):
                out.setPixelColor(x, y, QColor(0, 0, 0, 0))

    return QPixmap.fromImage(out)


# ============================================================
# MAIN WINDOW
# ============================================================

class CyborgWindow(QWidget):
    """Skin-based UI window for Afterburner."""

    def __init__(self):
        super().__init__()
        
        # Frameless transparent window
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Загрузка скина
        self._bg = _load_skin_with_transparency(SKIN_DIR / "SkinBase.png")
        if self._bg.isNull():
            logger.error("SkinBase.png не найден")
            sys.exit(1)

        self.resize(self._bg.size())

        # Цифровой шрифт
        self._font_px = QPixmap(str(SKIN_DIR / "DigitFont.png"))

        # Данные
        self._data = SystemData()
        self._collector = DataCollectorThread()
        self._collector.data_updated.connect(self._on_data)
        self._collector.start()

        # Таймер для обновления
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(50)  # 20 FPS

        logger.info("Cyborg Window готов")

    def _on_data(self, data: SystemData):
        """Handle new data from collector."""
        self._data = data

    def paintEvent(self, event):
        """Paint the window."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, self._bg)

        d = self._data

        # Левый тахометр - GPU Clock / Mem Clock
        gpu_f = int(d.gpu_freq) if d.gpu_freq > 0 else 0
        self._draw_text(painter, LEFT_CX, TOP_Y, f"{gpu_f:0{W_FREQ}d}", W_FREQ)

        mem_f = int(d.gpu_mem_freq) if d.gpu_mem_freq > 0 else 0
        self._draw_text(painter, LEFT_CX, BOT_Y, f"{mem_f:0{W_FREQ}d}", W_FREQ)

        # Правый тахометр - GPU Voltage / Temp
        volt = int(d.gpu_voltage * 1000) if d.gpu_voltage > 0 else 0
        self._draw_text(painter, RIGHT_CX, TOP_Y, f"{volt:0{W_VOLT}d}", W_VOLT)

        temp = int(d.gpu_temp) if d.gpu_temp > 0 else 0
        self._draw_text(painter, RIGHT_CX, BOT_Y, f"{temp:0{W_TEMP}d}", W_TEMP)

        painter.end()

    def _draw_text(self, painter: QPainter, cx: int, y: int, text: str, width: int):
        """Рисует текст фиксированной ширины, центрированный по cx."""
        total_w = width * CHAR_W
        x = cx - total_w // 2

        for ch in text:
            idx = ord(ch) - BASE_CHAR
            max_idx = self._font_px.height() // CHAR_H
            if 0 <= idx < max_idx:
                src = QRectF(0, idx * CHAR_H, CHAR_W, CHAR_H)
                dst = QRectF(x, y, CHAR_W, CHAR_H)
                painter.drawPixmap(dst, self._font_px, src)
            x += CHAR_W

    def closeEvent(self, event):
        """Handle close event."""
        self._collector.stop()
        event.accept()


# ============================================================
# SYSTEM TRAY ICON
# ============================================================

class SystemTrayIcon(QSystemTrayIcon):
    """System tray icon with popup menu."""

    def __init__(self, window: CyborgWindow, parent=None):
        super().__init__(parent)
        self._window = window

        # Set icon
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            self._create_fallback_icon()

        # Create menu
        self._create_menu()
        self.setContextMenu(self._menu)
        self.setToolTip("Afterburner - System Monitor")

        self.activated.connect(self._on_activated)

    def _create_fallback_icon(self):
        """Create a fallback icon."""
        from PyQt6.QtGui import QFont, QIcon, QPen
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor("#ef4444"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#ffffff"), 3))
        painter.setBrush(QColor("#ef4444"))
        painter.drawEllipse(3, 3, 58, 58)
        font = QFont("Arial", 36, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, "A")
        painter.end()
        self.setIcon(QIcon(pixmap))

    def _create_menu(self):
        """Create context menu."""
        self._menu = QMenu()

        show_action = QAction("Show", self._menu)
        show_action.triggered.connect(self._window.show)
        self._menu.addAction(show_action)

        hide_action = QAction("Hide", self._menu)
        hide_action.triggered.connect(self._window.hide)
        self._menu.addAction(hide_action)

        self._menu.addSeparator()

        exit_action = QAction("Exit", self._menu)
        exit_action.triggered.connect(self._exit_app)
        self._menu.addAction(exit_action)

    def _on_activated(self, reason):
        """Handle tray icon activation."""
        from PyQt6.QtWidgets import QSystemTrayIcon
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._window.isVisible():
                self._window.hide()
            else:
                self._window.show()

    def _exit_app(self):
        """Exit the application."""
        self._window._collector.stop()
        QApplication.quit()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

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

    # Загрузка конфигурации
    logger.info("Loading configuration...")
    try:
        load_config()
        logger.info(f"Config loaded: update_interval={config.get('update_interval_ms')}ms")
    except Exception as e:
        logger.error(f"Failed to load config: {e}", exc_info=True)
        raise

    # Создаем Qt приложение
    logger.info("Creating QApplication...")
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Afterburner")
        app.setOrganizationName("Afterburner")
        app.setQuitOnLastWindowClosed(False)
        logger.info("QApplication created successfully")
    except Exception as e:
        logger.error(f"Failed to create QApplication: {e}", exc_info=True)
        raise

    # Создаем сборщик данных
    logger.info("Creating DataCollectorThread...")
    try:
        global _collector
        _collector = DataCollectorThread()
        _collector.start()
        logger.info(f"Collector started, thread ID: {_collector.thread()}")
    except Exception as e:
        logger.error(f"Failed to create collector: {e}", exc_info=True)
        raise

    # Создаем окно
    logger.info("Creating CyborgWindow...")
    try:
        window = CyborgWindow()
        logger.info("CyborgWindow created successfully")
    except Exception as e:
        logger.error(f"Failed to create window: {e}", exc_info=True)
        raise

    # Создаем иконку в трее
    logger.info("Creating SystemTrayIcon...")
    try:
        tray = SystemTrayIcon(window)
        tray.show()
        logger.info("SystemTrayIcon created and shown")
    except Exception as e:
        logger.error(f"Failed to create tray icon: {e}", exc_info=True)
        raise

    # Показываем окно
    logger.info("Showing main window...")
    try:
        window.show()
        logger.info("Window shown")
    except Exception as e:
        logger.error(f"Failed to show window: {e}", exc_info=True)
        raise

    logger.info("=" * 60)
    logger.info("Afterburner started successfully!")
    logger.info("Check system tray for icon")
    logger.info("=" * 60)

    # Запускаем приложение
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
