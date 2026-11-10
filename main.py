#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Afterburner - System Monitor Service
Main entry point with skin-based UI (MSI Cyborg Red style) v1.1.0
"""

import atexit
import logging
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QRectF, QPoint
from PyQt6.QtGui import QAction, QColor, QImage, QPainter, QPixmap, QPolygon, QFont, QIcon, QPen
from PyQt6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu

from config import config, load_config
from collector import DataCollectorThread, SystemData

logger = logging.getLogger("Afterburner.main")

# Module-level reference for cleanup
_collector = None


def _resource_path(relative_path: str) -> Path:
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:
        base_path = Path(__file__).parent
    return base_path / relative_path


# Paths for embedded resources
SKIN_DIR = _resource_path("Skins/MSICyborgRed")
ICON_PATH = _resource_path("icon.png")
LHM_DIR = _resource_path("LHM")

# ============================================================
# НАСТРОЙКИ ПОЗИЦИЙ (ФИНАЛЬНЫЕ)
# ============================================================
LEFT_CX = 144       # Центр левого тахометра
RIGHT_CX = 608      # Центр правого тахометра

TOP_Y = 177         # Верхняя строка
BOT_Y = 218         # Нижняя строка

# Фиксированная ширина полей в символах
W_FREQ = 5          # частоты: "02262", "14001"
W_VOLT = 4          # напряжение: "1010"
W_TEMP = 4          # температура: "0040"

# Размер символа из DigitFont.png
CHAR_W = 16
CHAR_H = 32
BASE_CHAR = ord('-')

# Координаты переключателя GPU/CPU
SWITCH_X = 60       # Позиция по X
SWITCH_Y = 200      # Позиция по Y (между строками цифр)


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

        # Состояние интерфейса
        self._display_mode = 'gpu'  # 'gpu' или 'cpu'
        self._drag_pos = QPoint()   # Для перетаскивания окна

        # Данные
        self._data = SystemData()
        self._collector = DataCollectorThread()
        self._collector.data_updated.connect(self._on_data)
        self._collector.start()

        # Таймер для обновления
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(50)  # 20 FPS

        logger.info("Cyborg Window готов (с перетаскиванием и переключателем)")

    def _on_data(self, data: SystemData):
        self._data = data

    # --- Обработка мыши (Перетаскивание + Переключатель) ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()  # QPointF
            
            # Проверяем клик по области переключателя
            switch_rect = QRectF(SWITCH_X - 10, SWITCH_Y - 10, 100, 50)
            if switch_rect.contains(pos):
                self._display_mode = 'cpu' if self._display_mode == 'gpu' else 'gpu'
                logger.info(f"Режим переключен на: {self._display_mode.upper()}")
                self._drag_pos = QPoint()  # Сбрасываем перетаскивание
                self.update()
                event.accept()
            else:
                # Начинаем перетаскивание
                self._drag_pos = pos.toPoint()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            delta = event.position().toPoint() - self._drag_pos
            new_pos = self.pos() + delta
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = QPoint()
            event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, self._bg)

        # 1. Рисуем переключатель GPU/CPU
        self._draw_switch(painter)

        d = self._data
        mapping = config.get("display_mapping", {})

        # 2. Верхняя строка левого тахометра: переключается между GPU и CPU
        if self._display_mode == 'gpu':
            top_key = mapping.get("left_top_gpu", "gpu_freq")
        else:
            top_key = mapping.get("left_top_cpu", "cpu_freq_current")

        top_val = getattr(d, top_key, 0)
        top_num = int(top_val) if isinstance(top_val, (int, float)) and top_val > 0 else 0
        self._draw_text(painter, LEFT_CX, TOP_Y, f"{top_num:0{W_FREQ}d}", W_FREQ)

        # 3. Нижняя строка левого тахометра: всегда частота памяти GPU
        bottom_key = mapping.get("left_bottom", "gpu_mem_freq")
        bottom_val = getattr(d, bottom_key, 0)
        bottom_num = int(bottom_val) if isinstance(bottom_val, (int, float)) and bottom_val > 0 else 0
        self._draw_text(painter, LEFT_CX, BOT_Y, f"{bottom_num:0{W_FREQ}d}", W_FREQ)

        # 4. Правый тахометр: напряжение и температура GPU
        right_top_key = mapping.get("right_top", "gpu_voltage")
        right_bottom_key = mapping.get("right_bottom", "gpu_temp")

        volt_val = getattr(d, right_top_key, 0)
        volt = int(volt_val * 1000) if isinstance(volt_val, (int, float)) and volt_val > 0 else 0
        self._draw_text(painter, RIGHT_CX, TOP_Y, f"{volt:0{W_VOLT}d}", W_VOLT)

        temp_val = getattr(d, right_bottom_key, 0)
        temp = int(temp_val) if isinstance(temp_val, (int, float)) and temp_val > 0 else 0
        self._draw_text(painter, RIGHT_CX, BOT_Y, f"{temp:0{W_TEMP}d}", W_TEMP)

        painter.end()

    def _draw_switch(self, painter: QPainter):
        """Рисует треугольники и надписи GPU/CPU"""
        triangle_size = 10
        text_offset = 16
        
        # --- Верхний элемент: GPU ---
        is_gpu_active = (self._display_mode == 'gpu')
        painter.setBrush(QColor(255, 50, 50) if is_gpu_active else QColor(80, 80, 80))
        painter.setPen(Qt.PenStyle.NoPen)
        tri_gpu = QPolygon([
            QPoint(SWITCH_X, SWITCH_Y + triangle_size),
            QPoint(SWITCH_X + triangle_size // 2, SWITCH_Y),
            QPoint(SWITCH_X + triangle_size, SWITCH_Y + triangle_size)
        ])
        painter.drawPolygon(tri_gpu)
        
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255) if is_gpu_active else QColor(100, 100, 100))
        painter.drawText(SWITCH_X + text_offset, SWITCH_Y + triangle_size - 2, "GPU")

        # --- Нижний элемент: CPU ---
        boost_y = SWITCH_Y + 22
        is_cpu_active = (self._display_mode == 'cpu')
        painter.setBrush(QColor(255, 50, 50) if is_cpu_active else QColor(80, 80, 80))
        tri_cpu = QPolygon([
            QPoint(SWITCH_X, boost_y),
            QPoint(SWITCH_X + triangle_size // 2, boost_y + triangle_size),
            QPoint(SWITCH_X + triangle_size, boost_y)
        ])
        painter.drawPolygon(tri_cpu)
        
        painter.setPen(QColor(255, 255, 255) if is_cpu_active else QColor(100, 100, 100))
        painter.drawText(SWITCH_X + text_offset, boost_y + triangle_size - 2, "CPU")

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

        icon_path = ICON_PATH
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            self._create_fallback_icon()

        self._create_menu()
        self.setContextMenu(self._menu)
        self.setToolTip("Afterburner - System Monitor")

        self.activated.connect(self._on_activated)

    def _create_fallback_icon(self):
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
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._window.isVisible():
                self._window.hide()
            else:
                self._window.show()

    def _exit_app(self):
        self._window._collector.stop()
        QApplication.quit()

# ============================================================
# LIBREHARDWAREMONITOR AUTO-START
# ============================================================

_lhm_process = None


def _is_lhm_running() -> bool:
    """Check if LibreHardwareMonitor is already running."""
    import psutil
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and 'LibreHardwareMonitor' in proc.info['name']:
            return True
    return False


def _start_lhm() -> bool:
    """Start embedded LibreHardwareMonitor with HTTP server."""
    global _lhm_process
    
    if _is_lhm_running():
        logger.info("LibreHardwareMonitor already running")
        return True
    
    lhm_exe = LHM_DIR / "LibreHardwareMonitor.exe"
    if not lhm_exe.exists():
        logger.warning("LHM executable not found: %s", lhm_exe)
        return False
    
    try:
        logger.info("Starting LibreHardwareMonitor with HTTP server...")
        _lhm_process = subprocess.Popen(
            [str(lhm_exe), "-http"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=str(LHM_DIR),
        )
        logger.info("LHM started (PID: %d)", _lhm_process.pid)
        return True
    except Exception as exc:
        logger.error("Failed to start LHM: %s", exc)
        return False


def _stop_lhm():
    """Stop embedded LibreHardwareMonitor."""
    global _lhm_process
    if _lhm_process and _lhm_process.poll() is None:
        try:
            _lhm_process.terminate()
            _lhm_process.wait(timeout=3)
            logger.info("LHM stopped")
        except Exception:
            try:
                _lhm_process.kill()
            except Exception:
                pass


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def cleanup():
    global _collector
    try:
        if _collector is not None:
            _collector.stop()
            logger.info("Collector stopped gracefully")
    except Exception:
        logger.warning("Cleanup error", exc_info=True)
    _stop_lhm()

atexit.register(cleanup)

# ============================================================
# MAIN APPLICATION
# ============================================================

def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("=" * 60)
    logger.info("Afterburner v1.1.0 starting...")
    logger.info("=" * 60)

    try:
        load_config()
        logger.info(f"Config loaded: update_interval={config.get('update_interval_ms')}ms")
    except Exception as e:
        logger.error(f"Failed to load config: {e}", exc_info=True)
        raise

    # Auto-start LibreHardwareMonitor if not running
    logger.info("Checking for LibreHardwareMonitor...")
    if not _is_lhm_running():
        logger.info("LHM not found, starting embedded version...")
        if not _start_lhm():
            logger.warning("LHM auto-start failed — some sensors may be unavailable")
    else:
        logger.info("LHM already running")

    # Wait for LHM HTTP server to initialize
    import time
    time.sleep(1)

    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Afterburner")
        app.setOrganizationName("Afterburner")
        app.setQuitOnLastWindowClosed(False)
    except Exception as e:
        logger.error(f"Failed to create QApplication: {e}", exc_info=True)
        raise

    try:
        global _collector
        _collector = DataCollectorThread()
        _collector.start()
    except Exception as e:
        logger.error(f"Failed to create collector: {e}", exc_info=True)
        raise

    try:
        window = CyborgWindow()
        tray = SystemTrayIcon(window)
        tray.show()
        window.show()
    except Exception as e:
        logger.error(f"Failed to create UI: {e}", exc_info=True)
        raise

    logger.info("=" * 60)
    logger.info("Afterburner started successfully!")
    logger.info("=" * 60)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()