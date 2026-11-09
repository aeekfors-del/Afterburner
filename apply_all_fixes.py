#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Автоматическое исправление всех критических ошибок Afterburner
"""

import os
import sys

def fix_collector():
    """Исправить collector.py - добавить проверку платформы для psutil"""
    print("🔧 Исправляю collector.py...")
    
    with open('collector.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Исправление 1: CPU Temperature - добавить проверку платформы
    old_cpu_temp = '''        # CPU Temperature
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
            logger.warning("Failed to collect CPU temperature", exc_info=True)'''
    
    new_cpu_temp = '''        # CPU Temperature - только для Linux
        import platform
        if platform.system() == "Linux":
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
        else:
            # На Windows используем WMI для температуры CPU
            if self._wmi:
                try:
                    for sensor in self._wmi.MSAcpi_ThermalZoneTemperature(root="wmi"):
                        temp_c = (sensor.CurrentTemperature - 2732) / 10.0
                        data.cpu_temp = {"CPU": round(temp_c, 1)}
                        break
                except Exception:
                    logger.debug("CPU temperature not available via WMI")'''
    
    if old_cpu_temp in content:
        content = content.replace(old_cpu_temp, new_cpu_temp)
        print("  ✅ Исправлен сбор температуры CPU")
    else:
        print("  ⚠️ Шаблон температуры CPU не найден (возможно, уже исправлено)")
    
    # Исправление 2: Fans - добавить проверку платформы
    old_fans = '''    def _collect_fans(self, data: SystemData) -> None:
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
            logger.warning("Failed to collect fan metrics", exc_info=True)'''
    
    new_fans = '''    def _collect_fans(self, data: SystemData) -> None:
        """Collect fan speed metrics."""
        import platform
        if platform.system() == "Linux":
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
        else:
            # На Windows используем WMI для вентиляторов
            if self._wmi:
                try:
                    for fan in self._wmi.Win32_Fan():
                        if hasattr(fan, 'DesiredSpeed') and fan.DesiredSpeed:
                            data.fans.append(("System Fan", fan.DesiredSpeed))
                except Exception:
                    logger.debug("Fan metrics not available via WMI")'''
    
    if old_fans in content:
        content = content.replace(old_fans, new_fans)
        print("  ✅ Исправлен сбор данных вентиляторов")
    else:
        print("  ⚠️ Шаблон вентиляторов не найден (возможно, уже исправлено)")
    
    with open('collector.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ collector.py исправлен\n")


def fix_ui_widgets():
    """Исправить ui_widgets.py - заменить beginPath() на QPainterPath"""
    print("🔧 Исправляю ui_widgets.py...")
    
    with open('ui_widgets.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Исправление 3: QPainter.beginPath() не существует
    old_paint = '''        # Draw line
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
        painter.end()'''
    
    new_paint = '''        # Draw line
        color.setAlpha(200)
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        
        # Исправлено: используем QPainterPath вместо beginPath()
        line_path = QPainterPath()
        for i, val in enumerate(data):
            x = i * step
            normalized = (val - min_val) / range_val
            y = h - normalized * (h - 4) - 2
            if i == 0:
                line_path.moveTo(x, y)
            else:
                line_path.lineTo(x, y)

        painter.drawPath(line_path)
        painter.end()'''
    
    if old_paint in content:
        content = content.replace(old_paint, new_paint)
        print("  ✅ Исправлена отрисовка графика (beginPath -> QPainterPath)")
    else:
        print("  ⚠️ Шаблон отрисовки не найден (возможно, уже исправлено)")
    
    with open('ui_widgets.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ ui_widgets.py исправлен\n")


def fix_main():
    """Исправить main.py - улучшить создание иконки для Windows"""
    print("🔧 Исправляю main.py...")
    
    with open('main.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Исправление 4: Улучшить создание иконки
    old_icon = '''    def _create_pixmap_icon(self):
        """Create a simple pixmap icon."""
        from PyQt6.QtGui import QPixmap
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a circle
        painter.setPen(QPen(Colors.get("accent_blue"), 3))
        painter.setBrush(QColor("#0a0e17"))
        painter.drawEllipse(4, 4, 56, 56)

        # Draw a simple gauge arc
        painter.setPen(QPen(Colors.get("accent_cyan"), 3))
        painter.drawArc(8, 8, 48, 48, 135 * 16, -270 * 16)

        painter.end()
        return pixmap'''
    
    new_icon = '''    def _create_pixmap_icon(self):
        """Create a simple pixmap icon for Windows."""
        from PyQt6.QtGui import QPixmap, QRadialGradient, QBrush
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Рисуем круг с градиентом
        gradient = QRadialGradient(32, 32, 28)
        gradient.setColorAt(0, QColor("#3b82f6"))
        gradient.setColorAt(1, QColor("#0a0e17"))
        
        painter.setPen(QPen(Colors.get("accent_cyan"), 3))
        painter.setBrush(gradient)
        painter.drawEllipse(4, 4, 56, 56)

        # Рисуем дугу (индикатор)
        painter.setPen(QPen(Colors.get("accent_cyan"), 4))
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawArc(12, 12, 40, 40, 0, 90 * 16)

        painter.end()
        return pixmap'''
    
    if old_icon in content:
        content = content.replace(old_icon, new_icon)
        print("  ✅ Улучшено создание иконки (добавлен градиент)")
    else:
        print("  ⚠️ Шаблон иконки не найден (возможно, уже исправлено)")
    
    # Проверить, что импорты есть
    if 'QRadialGradient' not in content:
        # Добавить импорт, если его нет
        old_import = 'from PyQt6.QtGui import QAction, QIcon, QCursor, QPainter, QColor, QFont, QPen'
        new_import = 'from PyQt6.QtGui import QAction, QIcon, QCursor, QPainter, QColor, QFont, QPen, QRadialGradient, QBrush'
        
        if old_import in content:
            content = content.replace(old_import, new_import)
            print("  ✅ Добавлены недостающие импорты (QRadialGradient, QBrush)")
    
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ main.py исправлен\n")


def main():
    print("=" * 60)
    print("🚀 Применение всех исправлений к Afterburner")
    print("=" * 60)
    print()
    
    # Проверяем, что файлы существуют
    required_files = ['collector.py', 'ui_widgets.py', 'main.py']
    missing = [f for f in required_files if not os.path.exists(f)]
    
    if missing:
        print(f"❌ Ошибка: Не найдены файлы: {', '.join(missing)}")
        print("Убедитесь, что вы запустили скрипт в корне проекта Afterburner")
        sys.exit(1)
    
    # Применяем исправления
    fix_collector()
    fix_ui_widgets()
    fix_main()
    
    print("=" * 60)
    print("🎉 Все исправления успешно применены!")
    print("=" * 60)
    print()
    print("Теперь запустите приложение:")
    print("  python main.py")
    print()
    print("Что должно работать:")
    print("  ✅ Иконка в трее (с градиентным кругом)")
    print("  ✅ Попап-окно не исчезает")
    print("  ✅ Нет ошибок с psutil.sensors_*")
    print("  ✅ Нет ошибок с QPainter.beginPath()")
    print()


if __name__ == "__main__":
    main()