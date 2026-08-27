import sys
import os
import ctypes
from config import get_resource_path, APP_VERSION, is_build_expired, parse_version
from dialogs import AppExpirationDialog
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from ui.styles import LIGHT_STYLESHEET
import ui.main_window
from version_worker import VersionCheckWorker

# Prevent CMD window flashing without breaking C-extensions
if sys.platform == "win32":
    if getattr(sys, 'frozen', False):
        try:
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

# Force Windows Taskbar to pin/show custom app icon
myappid = 'ibmi.dashboard.ecosystem.1'
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def resource_path(relative_path):
    return get_resource_path(relative_path)

def main():
    # 1. Initialize QApplication FIRST (Required before any QWidget/QDialog)
    app = QApplication(sys.argv)
    app.setProperty("is_dark_theme", False)
    app.setStyleSheet(LIGHT_STYLESHEET)
    
    app_icon = QIcon(resource_path("logo.png"))
    app.setWindowIcon(app_icon)

    # 2. Check Expiration right after QApplication setup
    if is_build_expired():
        dialog = AppExpirationDialog(
            title="Application Expired",
            message="This build of the application has expired.",
            download_url="https://github.com/emxts-hub/monitoringtool/releases/latest"
        )
        dialog.exec()
        sys.exit(0)  # Stop execution completely if expired

    # 3. Load Main UI
    window = ui.main_window.IBMiDashboard()
    window.setWindowIcon(app_icon)
    window.showMaximized()

    # 4. Asynchronous Version Check
    def handle_version_check(success, min_ver, latest_ver, download_url, err):
        if success:
            current_ver_tuple = parse_version(APP_VERSION)
            min_ver_tuple = parse_version(min_ver)

            # Enforce update if installed version is below required minimum
            if current_ver_tuple < min_ver_tuple:
                window.hide()
                dialog = AppExpirationDialog(
                    title="Update Required",
                    message=f"Your version ({APP_VERSION}) is no longer supported. Minimum required version is {min_ver}.",
                    download_url=download_url,
                )
                dialog.exec()
                sys.exit(0)

    worker = VersionCheckWorker()
    worker.version_checked.connect(handle_version_check)
    worker.start()

    # Keep worker instance alive in window reference to avoid garbage collection
    window._version_worker = worker

    sys.exit(app.exec())

if __name__ == "__main__":
    main()