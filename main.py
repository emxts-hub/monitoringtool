import sys
import os
import ctypes
from config import get_resource_path
import updater

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
    # Perform startup checks (expiration, remote version) before launching GUI
    try:
        should_continue = updater.check_startup_and_update()
    except Exception:
        should_continue = True

    if should_continue:
        main()
    else:
        # updater scheduled replacement or app expired; exit now
        sys.exit(0)