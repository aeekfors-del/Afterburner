import os

def fix_all():
    print("🔧 Начинаю применение исправлений...")
    
    # 1. Fix config.py
    with open('config.py', 'r', encoding='utf-8') as f:
        config_content = f.read()
    if 'CONFIG_PATH = Path.home() / ".afterburner_config.json"' in config_content:
        config_content = config_content.replace(
            'CONFIG_PATH = Path.home() / ".afterburner_config.json"',
            'appdata_dir = os.getenv("APPDATA", str(Path.home()))\nCONFIG_PATH = Path(appdata_dir) / "Afterburner" / "config.json"'
        )
        if 'import os' not in config_content:
            config_content = 'import os\n' + config_content
        with open('config.py', 'w', encoding='utf-8') as f:
            f.write(config_content)
        print("✅ config.py: Путь изменен на %APPDATA%")

    # 2. Fix collector.py
    with open('collector.py', 'r', encoding='utf-8') as f:
        collector_content = f.read()
    old_notify = '''    def _show_notification(self, message: str, severity: str) -> None:
        """Show Windows toast notification via PowerShell."""
        try:
            import subprocess

            if severity == "critical":
                title = "CRITICAL - Afterburner"
            elif severity == "warning":
                title = "WARNING - Afterburner"
            else:
                title = "Afterburner"

            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$toast = [System.Windows.Forms.ToastNotificationManager]::"
                "CreateToastNotifier('Afterburner'); "
                "$text = '" + title + "n" + message + "'; "
                "$toast.Show($text)"
            )
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            logger.warning("Failed to show notification", exc_info=True)'''
    
    new_notify = '''    def _show_notification(self, message: str, severity: str) -> None:
        """Show Windows toast notification."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            title = "🚨 CRITICAL" if severity == "critical" else "⚠️ WARNING"
            toaster.show_toast(f"{title} - Afterburner", message, duration=5, threaded=True)
        except Exception as e:
            logger.warning(f"Failed to show notification: {e}", exc_info=True)'''
            
    if old_notify in collector_content:
        collector_content = collector_content.replace(old_notify, new_notify)
        with open('collector.py', 'w', encoding='utf-8') as f:
            f.write(collector_content)
        print("✅ collector.py: Уведомления переключены на win10toast")

    # 3. Fix main.py
    with open('main.py', 'r', encoding='utf-8') as f:
        main_content = f.read()

    # Fix 3a: setQuitOnLastWindowClosed
    if 'app.setQuitOnLastWindowClosed(False)' not in main_content:
        main_content = main_content.replace(
            'app.setOrganizationName("Afterburner")',
            'app.setOrganizationName("Afterburner")\n        app.setQuitOnLastWindowClosed(False)'
        )
        print("✅ main.py: Добавлено setQuitOnLastWindowClosed(False)")

    # Fix 3b: tray.show()
    if 'tray.show()' not in main_content:
        main_content = main_content.replace(
            'tray = SystemTrayIcon()\n        logger.info(f"SystemTrayIcon created, popup_widget exists: {tray._popup_widget is not None}")',
            'tray = SystemTrayIcon()\n        tray.show()  # CRITICAL: Show the tray icon\n        logger.info("SystemTrayIcon created and shown")'
        )
        print("✅ main.py: Добавлен вызов tray.show()")

    # Fix 3c: _create_icon
    old_icon = '''    def _create_icon(self):
        """Create a simple icon programmatically."""
        try:
            # Try to load from file
            icon_path = "icon.png"
            self.setIcon(QIcon(icon_path))
        except Exception:
            # Fallback: create a simple colored icon
            pixmap = self._create_pixmap_icon()
            self.setIcon(QIcon(pixmap))'''
    new_icon = '''    def _create_icon(self):
        """Create a simple icon programmatically."""
        icon = QIcon("icon.png")
        if icon.isNull():
            logger.info("icon.png not found, generating fallback icon")
            pixmap = self._create_pixmap_icon()
            icon = QIcon(pixmap)
        self.setIcon(icon)'''
    if old_icon in main_content:
        main_content = main_content.replace(old_icon, new_icon)
        print("✅ main.py: Исправлена проверка иконки (isNull)")

    # Fix 3d: AlertChecker
    if 'AlertChecker' not in main_content:
        old_connect = '''    # Connect collector to popup
    logger.info("Connecting collector to popup widget...")
    try:
        tray.set_collector(collector)
        logger.info("Collector connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect collector: {e}", exc_info=True)
        raise'''
        new_connect = '''    # Connect collector to popup
    logger.info("Connecting collector to popup widget...")
    try:
        tray.set_collector(collector)
        logger.info("Collector connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect collector: {e}", exc_info=True)
        raise

    # Initialize AlertChecker and NotificationManager
    logger.info("Initializing AlertChecker and NotificationManager...")
    from collector import AlertChecker, NotificationManager
    notification_manager = NotificationManager()
    alert_checker = AlertChecker(notification_manager)
    collector.data_updated.connect(alert_checker.check)
    logger.info("AlertChecker connected successfully")'''
        if old_connect in main_content:
            main_content = main_content.replace(old_connect, new_connect)
            print("✅ main.py: Подключен AlertChecker")

    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(main_content)

    # 4. Fix requirements.txt
    with open('requirements.txt', 'r', encoding='utf-8') as f:
        req_content = f.read()
    if 'win10toast' not in req_content:
        with open('requirements.txt', 'a', encoding='utf-8') as f:
            f.write('\nwin10toast>=0.1.2\n')
        print("✅ requirements.txt: Добавлен win10toast")

    print("🎉 Все исправления успешно применены!")

if __name__ == "__main__":
    fix_all()