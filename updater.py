import os
import sys
import time
import json
import shutil
import urllib.request
import tempfile
import subprocess
from datetime import datetime
import ctypes

from config import get_app_data_dir, APP_NAME, APP_VERSION, load_update_settings, get_config_path


def _message_box(title, text, flags=0):
    # Use Windows native message box when available, else print
    try:
        if sys.platform == "win32":
            MB_OK = 0x0
            MB_YESNO = 0x04
            MB_ICONWARNING = 0x30
            # flags override if provided
            res = ctypes.windll.user32.MessageBoxW(0, str(text), str(title), flags or MB_OK)
            return res
    except Exception:
        pass
    print(f"{title}: {text}")
    return None


def _compare_versions(a, b):
    """Return -1 if a<b, 0 if equal, 1 if a>b for dotted versions."""
    def norm(v):
        parts = [int(x) if x.isdigit() else 0 for x in str(v).split('.')]
        return parts
    pa = norm(a)
    pb = norm(b)
    la = len(pa)
    lb = len(pb)
    l = max(la, lb)
    for i in range(l):
        va = pa[i] if i < la else 0
        vb = pb[i] if i < lb else 0
        if va < vb:
            return -1
        if va > vb:
            return 1
    return 0


def _download_file(url, dest_path, timeout=30):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, 'wb') as out_f:
                shutil.copyfileobj(resp, out_f)
        return True, None
    except Exception as e:
        return False, str(e)


def _write_replace_bat(new_file, target_file):
    # Create a .bat that waits for the target to be unlocked, replaces it and relaunches
    bat_fd, bat_path = tempfile.mkstemp(suffix='.bat', prefix='update_', dir=os.path.dirname(new_file))
    os.close(bat_fd)
    exe_name = os.path.basename(target_file)
    # Use tasklist to detect running process
    bat_contents = f"""@echo off
REM wait until the target process is gone, then replace and relaunch
set NEW=\"{new_file}\"
set TARGET=\"{target_file}\"
:loop
tasklist /FI "IMAGENAME eq {exe_name}" | find /I "{exe_name}" >nul
if %ERRORLEVEL%==0 (
    timeout /t 1 /nobreak >nul
    goto loop
)
REM attempt to replace (retry a few times)
move /Y %NEW% %TARGET%
if %ERRORLEVEL% neq 0 (
    timeout /t 1 /nobreak >nul
    move /Y %NEW% %TARGET%
)
start "" %TARGET%
REM self-delete
del "%~f0" >nul 2>&1
"""
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat_contents)
    return bat_path


def schedule_replace_and_relaunch(new_file, target_file):
    """Writes a helper batch file to replace target_file with new_file once target exits, then launches the batch.

    Returns True on successfully launching the updater helper.
    """
    try:
        bat_path = _write_replace_bat(new_file, target_file)
        # Launch the bat detached so it can continue after current process exits
        subprocess.Popen(["cmd", "/c", "start", "", bat_path], shell=False)
        return True, None
    except Exception as e:
        return False, str(e)


def check_startup_and_update():
    """Performs expiration check and optional update flow for packaged executables.

    Returns True if app should continue launching; False if the app should exit (either expired or update launched replacement).
    """
    settings = load_update_settings()
    exp = settings.get('expiration_date')
    version_url = settings.get('version_url') or ''

    # Expiration check
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp))
            now = datetime.now()
            if now.date() > exp_dt.date():
                _message_box("Application Expired", f"This copy of {APP_NAME} has expired on {exp_dt.date()}. Please contact support.", 0x30)
                return False
        except Exception:
            # ignore malformed expiration setting
            pass

    # Only perform update check for frozen (packaged) executables
    if not getattr(sys, 'frozen', False):
        return True

    if not version_url:
        return True

    # Fetch remote version JSON
    try:
        with urllib.request.urlopen(version_url, timeout=10) as resp:
            raw = resp.read()
            data = json.loads(raw.decode('utf-8'))
    except Exception as e:
        # network problems — continue
        return True

    remote_version = str(data.get('version', '') or '').strip()
    download_url = str(data.get('download_url', '') or '').strip()
    if not remote_version or not download_url:
        return True

    cmp = _compare_versions(APP_VERSION, remote_version)
    if cmp >= 0:
        # local is up-to-date or newer
        return True

    # Newer version found — ask user
    MB_YESNO = 0x04
    MB_ICONQUESTION = 0x20
    res = _message_box("Update Available", f"A newer version ({remote_version}) is available. Download and install now?", MB_YESNO | MB_ICONQUESTION)
    # On Windows MessageBox, ID 6 = Yes, 7 = No
    try:
        if sys.platform == 'win32' and res is not None:
            if int(res) != 6:
                return True
    except Exception:
        # if message box didn't return code, continue
        pass

    # Download to updates folder
    app_data = get_app_data_dir()
    updates_dir = os.path.join(app_data, 'updates')
    os.makedirs(updates_dir, exist_ok=True)
    filename = os.path.basename(download_url.split('?')[0]) or f"{APP_NAME}_update.exe"
    dest = os.path.join(updates_dir, filename)

    ok, err = _download_file(download_url, dest)
    if not ok:
        _message_box("Update Failed", f"Failed to download update: {err}")
        return True

    # Schedule replacement and relaunch
    target_exe = sys.executable
    ok2, err2 = schedule_replace_and_relaunch(dest, target_exe)
    if not ok2:
        _message_box("Update Failed", f"Failed to schedule updater: {err2}")
        return True

    # Exit current process to allow bat to replace and relaunch
    return False


if __name__ == '__main__':
    # for local testing
    res = check_startup_and_update()
    print('Should continue:', res)
