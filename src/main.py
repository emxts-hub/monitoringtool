import sys
import os
import ctypes
from config import get_resource_path
from PyQt6.QtWidgets import QApplication
from config import APP_VERSION, is_build_expired, parse_version
from dialogs import AppExpirationDialog

from version_worker import VersionCheckWorker
# Prevent CMD window flashing without breaking C-extensions
if sys.platform == "win32":
    # 1. Detach console if running in a compiled binary
    if getattr(sys, 'frozen', False):
        try:
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from ui.styles import LIGHT_STYLESHEET
import ui.main_window

# Force Windows Taskbar to pin/show custom app icon
myappid = 'ibmi.dashboard.ecosystem.1'
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def resource_path(relative_path):
    return get_resource_path(relative_path)

def main():
    if is_build_expired():
        dialog = AppExpirationDialog(
            title="Build Expired",
            message=f"This evaluation build of LPAR Manager (v{APP_VERSION}) has expired. Please download a newer release.",
        )
        dialog.exec()
        sys.exit(0)



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

    
    app = QApplication(sys.argv)
    app.setProperty("is_dark_theme", False)
    app.setStyleSheet(LIGHT_STYLESHEET)
    
    app_icon = QIcon(resource_path("logo.png"))
    app.setWindowIcon(app_icon)

    window = ui.main_window.IBMiDashboard()
    window.setWindowIcon(app_icon)
    window.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()