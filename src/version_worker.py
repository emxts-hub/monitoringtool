import requests
from PyQt6.QtCore import QThread, pyqtSignal
from config import APP_VERSION, VERSION_CHECK_URL


class VersionCheckWorker(QThread):
    # Signal emits: (success, min_required_version, latest_version, update_url, error_msg)
    version_checked = pyqtSignal(bool, str, str, str, str)

    def run(self):
        try:
            headers = {"User-Agent": f"LPARManager/{APP_VERSION}"}
            response = requests.get(VERSION_CHECK_URL, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                latest_ver = data.get("latest_version", APP_VERSION)
                min_ver = data.get("min_required_version", APP_VERSION)
                update_url = data.get("update_url", "https://github.com")

                self.version_checked.emit(True, min_ver, latest_ver, update_url, "")
            else:
                self.version_checked.emit(
                    False,
                    "",
                    "",
                    "",
                    f"HTTP Server returned status code {response.status_code}",
                )
        except Exception as e:
            # Allow fallback on network connection failure
            self.version_checked.emit(False, "", "", "", str(e))