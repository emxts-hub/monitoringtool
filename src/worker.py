import os
import sys
import json
import re
import struct
import threading
import time
import uuid
import subprocess
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
import pyodbc
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal
from config import (
    SERVER_CONFIGS, 
    MONITORED_PORTS, 
    EXPECTED_PORTS, 
    get_logs_dir, 
    load_email_alerts, 
    get_resource_path, 
    EXPECTED_SUBSYSTEMS,
    safe_json_append_and_save
)

_LOG_WRITE_LOCK = threading.Lock()
_ALERT_STATE_LOCK = threading.Lock()
_LAST_ASP_ALERT_STATE = {}
_LAST_ASP_SOUND_STATE = {"armed": False, "sent_at": 0.0}
_LAST_ASP_EMAIL_STATE = {}
_ALERT_SOUND_STOP_EVENT = threading.Event()
_ALERT_SOUND_PROCESSES = set()
_ALERT_SOUND_PROCESS_LOCK = threading.Lock()


def _new_connection(host, db, username, password):
    # Performance tuning parameters for IBM i ODBC driver
    extra_params = (
        "NAM=1;"              # SQL System Naming (reduces library resolve time)
        "LAZYCLOSE=1;"        # Keep cursors active for fast statement execution
        "TRANSLATE=0;"        # Disable automatically converting CCSID values
    )
    return pyodbc.connect(
        f"DRIVER={{IBM i Access ODBC Driver}};"
        f"SYSTEM={host};"
        f"UID={username};"
        f"PWD={password};"
        f"SSL=0;"
        f"DATABASE={db};"
        f"CONN_TIMEOUT=3;"
        f"QUERY_TIMEOUT=3;"
        f"{extra_params}",
        timeout=3,
        autocommit=True,
    )


def _normalize_recipients(value):
    if isinstance(value, str):
        recipients = [item.strip() for item in value.split(',') if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        recipients = [str(item).strip() for item in value if str(item).strip()]
    else:
        recipients = []
    return recipients


def _repair_wav_file_if_needed(wav_path):
    """Fixes common WAV header corruption so Windows does not fall back to the system default chime."""
    try:
        with open(wav_path, "rb") as f:
            data = f.read()
    except Exception:
        return False

    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False

    riff_size = len(data) - 8
    data_idx = data.find(b"data")
    if data_idx == -1:
        return False

    data_size = len(data) - data_idx - 8
    current_riff = struct.unpack("<I", data[4:8])[0]
    current_data = struct.unpack("<I", data[data_idx + 4:data_idx + 8])[0]

    if current_riff == riff_size and current_data == data_size:
        return True

    try:
        fixed = bytearray(data)
        fixed[4:8] = struct.pack("<I", riff_size)
        fixed[data_idx + 4:data_idx + 8] = struct.pack("<I", data_size)
        with open(wav_path, "wb") as f:
            f.write(fixed)
        return True
    except Exception:
        return False


def play_asp_alert_sound():
    """Locates warning.wav, ngani.wav, and alert.wav and plays them sequentially (1 -> 2 -> 3) in the background."""
    """target_names = ["warning.wav", "ngani.wav", "alert.wav"]"""
    target_names = ["warning.wav"]
    wav_paths = []

    for name in target_names:
        candidate_paths = [
            get_resource_path(f"src/{name}"),
            get_resource_path(name),
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "src", name
            ),
            os.path.join(os.getcwd(), "src", name),
        ]

        found_path = None
        for path in candidate_paths:
            if path and os.path.exists(path):
                found_path = path
                break

        if not found_path:
            base_dir = getattr(
                sys,
                "_MEIPASS",
                os.path.dirname(os.path.abspath(__file__)),
            )
            for root, _, files in os.walk(base_dir):
                if name.lower() in [f.lower() for f in files]:
                    found_path = os.path.join(root, name)
                    break

        if found_path and os.path.exists(found_path):
            wav_paths.append(found_path)

    """if len(wav_paths) < 3:"""
    if len(wav_paths) < 1:
        print(
            f"Alert sound error: Expected at least 1 sound file, found {len(wav_paths)}."
        )
        return False

    try:
        for path in wav_paths:
            try:
                _repair_wav_file_if_needed(path)
            except Exception:
                pass

        def _play_sequential():
            for p in wav_paths:
                if _ALERT_SOUND_STOP_EVENT.is_set():
                    return
                if sys.platform == "win32":
                    import winsound
                    winsound.PlaySound(
                        str(p),
                        winsound.SND_FILENAME | winsound.SND_NODEFAULT | winsound.SND_ASYNC,
                    )

                elif sys.platform == "darwin":
                    p_proc = subprocess.Popen(
                        ["afplay", str(p)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    with _ALERT_SOUND_PROCESS_LOCK:
                        _ALERT_SOUND_PROCESSES.add(p_proc)
                    try:
                        p_proc.wait()
                    finally:
                        with _ALERT_SOUND_PROCESS_LOCK:
                            _ALERT_SOUND_PROCESSES.discard(p_proc)

                else:
                    try:
                        p_proc = subprocess.Popen(
                            ["ffplay", "-nodisp", "-autoexit", str(p)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        with _ALERT_SOUND_PROCESS_LOCK:
                            _ALERT_SOUND_PROCESSES.add(p_proc)
                        try:
                            p_proc.wait()
                        finally:
                            with _ALERT_SOUND_PROCESS_LOCK:
                                _ALERT_SOUND_PROCESSES.discard(p_proc)
                    except Exception:
                        p_proc = subprocess.Popen(
                            ["aplay", str(p)],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        with _ALERT_SOUND_PROCESS_LOCK:
                            _ALERT_SOUND_PROCESSES.add(p_proc)
                        try:
                            p_proc.wait()
                        finally:
                            with _ALERT_SOUND_PROCESS_LOCK:
                                _ALERT_SOUND_PROCESSES.discard(p_proc)

        threading.Thread(target=_play_sequential, daemon=True).start()
        return True

    except Exception as e:
        print(f"Failed to play alert sounds: {e}")
        return False


def reset_asp_alert_sound():
    """Allow alert playback for a new monitoring session."""
    _ALERT_SOUND_STOP_EVENT.clear()


def stop_asp_alert_sound():
    """Stop any alert playback started by the monitoring worker."""
    _ALERT_SOUND_STOP_EVENT.set()

    def _stop_playback():
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
                winsound.PlaySound(None, 0)
            except Exception:
                pass

        with _ALERT_SOUND_PROCESS_LOCK:
            processes = list(_ALERT_SOUND_PROCESSES)
            _ALERT_SOUND_PROCESSES.clear()

        for process in processes:
            try:
                if process.poll() is None:
                    process.terminate()
            except Exception:
                pass

    threading.Thread(target=_stop_playback, daemon=True).start()


def send_asp_alert(server_name, asp_value, threshold_percent):
    """Sends an SMTP notification when ASP usage crosses the configured threshold."""
    alert_cfg = load_email_alerts()
    if not alert_cfg.get("enabled"):
        return False

    smtp_server = str(alert_cfg.get("smtp_server", "")).strip()
    recipients = _normalize_recipients(alert_cfg.get("to_addresses", []))
    if not smtp_server or not recipients:
        return False

    username = str(alert_cfg.get("username", "")).strip()
    password = str(alert_cfg.get("password", "")).strip()
    from_address = str(alert_cfg.get("from_address", "")).strip() or username or "alerts@localhost"
    port = int(alert_cfg.get("port", 587) or 587)
    use_tls = bool(alert_cfg.get("use_tls", True))

    try:
        msg = EmailMessage()
        msg["Subject"] = f"ASP Threshold Alert - {server_name}"
        msg["From"] = from_address
        msg["To"] = ", ".join(recipients)
        msg.set_content(
            f"ASP usage on {server_name} reached {asp_value:.2f}% and exceeded the configured threshold of {threshold_percent:.2f}%.\n\n"
            f"This notification was generated automatically by the IBM i dashboard."
        )

        with smtplib.SMTP(smtp_server, port, timeout=15) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
        return True
    except Exception:
        return False


def maybe_send_asp_alert(server_name, asp_value):
    """Plays the ASP sound on each refresh while the server remains above threshold; email keeps its own cooldown."""
    alert_cfg = load_email_alerts()
    email_enabled = bool(alert_cfg.get("enabled"))

    try:
        asp_value = float(asp_value or 0.0)
    except (TypeError, ValueError):
        asp_value = 0.0

    threshold_percent = float(alert_cfg.get("threshold_percent", 90.0) or 90.0)
    cooldown_seconds = max(0, int(float(alert_cfg.get("cooldown_minutes", 10) or 10) * 60))

    with _ALERT_STATE_LOCK:
        now = time.monotonic()
        state = _LAST_ASP_ALERT_STATE.get(server_name, {"armed": False, "sent_at": 0.0})

        if asp_value < threshold_percent:
            state["armed"] = False
            state["sent_at"] = 0.0
            _LAST_ASP_ALERT_STATE[server_name] = state
            return False

        state["armed"] = True
        _LAST_ASP_ALERT_STATE[server_name] = state

        email_state = _LAST_ASP_EMAIL_STATE.get(server_name, {"sent_at": 0.0})
        email_due = not email_enabled or (now - float(email_state.get("sent_at", 0.0))) >= cooldown_seconds
        if email_enabled and email_due:
            email_state["sent_at"] = now
            _LAST_ASP_EMAIL_STATE[server_name] = email_state
            email_should_send = True
        else:
            email_should_send = False

    sound_played = play_asp_alert_sound()
    if email_should_send:
        return send_asp_alert(server_name, asp_value, threshold_percent) or sound_played
    return sound_played


def has_vpn_ip(prefix="10.212."):
    """Returns whether Windows has an IPv4 address assigned in the VPN range."""
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "(Get-NetIPAddress -AddressFamily IPv4).IPAddress",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and any(
            address.strip().startswith(prefix)
            for address in result.stdout.splitlines()
        )
    except (OSError, subprocess.SubprocessError):
        return False


def cleanup_old_logs(days_to_keep=30):
    """Deletes log files in the 'logs' folder older than days_to_keep."""
    logs_dir = get_logs_dir()
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    log_pattern = re.compile(r"^lpar_history_(\d{4}-\d{2}-\d{2})\.json$")

    if not os.path.exists(logs_dir):
        return

    for filename in os.listdir(logs_dir):
        match = log_pattern.match(filename)
        if match:
            file_date_str = match.group(1)
            try:
                file_date = datetime.strptime(file_date_str, "%Y-%m-%d")
                if file_date < cutoff_date:
                    file_path = os.path.join(logs_dir, filename)
                    os.remove(file_path)
            except Exception:
                pass


def _has_server_issues(sys_info, server_configs=None):
    """Check if server has issues worth logging (status not online, DOWN subsystems/services/ports, or errors)."""
    status = str(sys_info.get("status", "OFFLINE")).upper()
    if status not in ("ONLINE",):
        return True
    
    subsystems = sys_info.get("subsystems", [])
    if isinstance(subsystems, list):
        for sub in subsystems:
            if not isinstance(sub, dict):
                continue
            status = str(sub.get("status", "ACTIVE")).upper()
            name = str(sub.get("name", "")).strip()
            if name and status != "ACTIVE":
                return True

    configs = server_configs or SERVER_CONFIGS
    config_key = sys_info.get("config_key") or sys_info.get("server") or sys_info.get("host_name")
    cfg = configs.get(config_key, {})
    expected_key = cfg.get("expected_subsystems_key", config_key)
    expected_subs = EXPECTED_SUBSYSTEMS.get(expected_key, {})
    if isinstance(subsystems, list) and expected_subs:
        active_names = {
            str(sub.get("name", "")).strip().upper()
            for sub in subsystems
            if isinstance(sub, dict) and sub.get("name")
        }
        expected_names = {str(name).strip().upper() for name in expected_subs}
        if any(name not in active_names for name in expected_names):
            return True
    
    ports = sys_info.get("ports", [])
    if isinstance(ports, list):
        for port in ports:
            if isinstance(port, dict) and port.get("is_up") is False:
                return True
    
    if sys_info.get("error"):
        return True
    
    return False


def save_single_lpar_log(sys_info, server_configs=None):
    with _LOG_WRITE_LOCK:
        return _save_single_lpar_log(sys_info, server_configs)


def _save_single_lpar_log(sys_info, server_configs=None):
    """Appends a single LPAR result to the local offline log using safe re-read and atomic replacement."""
    logs_dir = get_logs_dir()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    filepath = os.path.join(logs_dir, f"lpar_history_{date_str}.json")

    configs = server_configs or SERVER_CONFIGS
    config_key = sys_info.get("config_key") or sys_info.get("server") or sys_info.get("host_name") or "unknown"
    resolved_name = sys_info.get("host_name") or sys_info.get("server") or config_key
    server_name = resolved_name if str(resolved_name).strip() and not re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", str(resolved_name).strip()) else config_key
    server_name = str(server_name).strip() or config_key

    is_issue_state = _has_server_issues(sys_info, server_configs)
    if not is_issue_state:
        try:
            existing_data = []
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    existing_data = json.load(f) or []
                    if not isinstance(existing_data, list):
                        existing_data = [existing_data]
            current_hour_prefix = now.strftime("%Y-%m-%d %H")
            for entry in existing_data:
                if not isinstance(entry, dict):
                    continue
                for rec in entry.get("records", []):
                    if not isinstance(rec, dict):
                        continue
                    rec_server = str(rec.get("server") or rec.get("lpar") or rec.get("config_key") or "").strip()
                    rec_ts = str(rec.get("timestamp") or "").strip()
                    if rec_server == server_name and rec_ts.startswith(current_hour_prefix):
                        return "already_recorded"
        except json.JSONDecodeError:
            return "failed"
        except OSError:
            return "file_busy"
        except Exception:
            return "failed"

    down_services = []
    ports = sys_info.get("ports")
    if isinstance(ports, list):
        for port in ports:
            if not isinstance(port, dict):
                continue
            if port.get("is_up") is False:
                name = port.get("name") or port.get("service")
                if name is None and port.get("port") is not None:
                    name = f"Port {port.get('port')}"
                if name:
                    down_services.append(name)

    services_down_val = down_services if down_services else "None"

    cfg = configs.get(config_key, configs.get(str(sys_info.get("server") or sys_info.get("host_name") or config_key), {}))
    ip_addr = cfg.get("host", "N/A") if isinstance(cfg, dict) else str(cfg)

    subsystems_list = sys_info.get("subsystems", [])
    down_subsystems = []
    active_names = set()

    if isinstance(subsystems_list, list):
        for sub in subsystems_list:
            if not isinstance(sub, dict):
                continue
            name = str(sub.get("name", "")).strip()
            status = str(sub.get("status", "ACTIVE")).upper()
            if name:
                active_names.add(name.upper())
            if status != "ACTIVE" and name:
                down_subsystems.append({
                    "name": name,
                    "status": status
                })

    expected_key = cfg.get("expected_subsystems_key", config_key) if isinstance(cfg, dict) else config_key
    expected_subs = EXPECTED_SUBSYSTEMS.get(expected_key, {})
    if not down_subsystems and expected_subs:
        expected_names = {str(name).strip().upper(): name for name in expected_subs}
        for expected_upper, expected_name in expected_names.items():
            if expected_upper not in active_names:
                down_subsystems.append({
                    "name": expected_name,
                    "status": "DOWN"
                })
    
    if down_subsystems:
        subsystems_summary = f"{len(down_subsystems)} Down"
        subsystems_detail = down_subsystems
    else:
        subsystems_summary = "None"
        subsystems_detail = []

    record = {
        "entry_id": uuid.uuid4().hex,
        "timestamp": timestamp_str,
        "config_key": str(config_key),
        "lpar": server_name,
        "server": server_name,
        "ip": ip_addr,
        "cpu": sys_info.get("cpu", 0.0),
        "asp": sys_info.get("asp", 0.0),
        "jobs": sys_info.get("jobs", 0),
        "status": sys_info.get("status", "OFFLINE"),
        "subsystems_summary": subsystems_summary,
        "subsystems_detail": subsystems_detail,
        "services_down": services_down_val
    }

    entry = {
        "timestamp": timestamp_str,
        "records": [record]
    }

    # OneDrive-safe atomic append; the caller holds the process-wide log lock.
    if not safe_json_append_and_save(filepath, entry):
        return "file_busy"
    cleanup_old_logs(days_to_keep=30)
    return "saved"


def _persist_and_emit(runnable, result):
    persistence_status = save_single_lpar_log(result, SERVER_CONFIGS)
    if persistence_status in ("saved", "already_recorded"):
        runnable.signals.server_fetched.emit(result)
    else:
        runnable.signals.server_failed.emit({
            "server": runnable.server,
            "status": "OFFLINE",
            "error": f"Log persistence {persistence_status}; result withheld.",
        })
        print(
            f"[{runnable.server}] Result not emitted because log persistence "
            f"returned {persistence_status}."
        )


class LparWorkerSignals(QObject):
    """Signals for communicating LPAR query execution results safely to GUI widgets."""
    server_fetched = pyqtSignal(dict)
    server_failed = pyqtSignal(dict)


class SingleLparRunnable(QRunnable):
    """Concurrent worker task for fetching metrics from a single LPAR connection."""
    def __init__(self, server, cfg, username, password, cancel_event=None, signal_parent=None):
        super().__init__()
        self.setAutoDelete(False)
        self.server = server
        self.cfg = cfg
        self.username = username
        self.password = password
        self.cancel_event = cancel_event or threading.Event()
        self.signals = LparWorkerSignals(signal_parent)

    def cancel(self):
        self.cancel_event.set()

    def is_cancelled(self):
        return self.cancel_event.is_set()

    def check_cancelled(self):
        if self.is_cancelled():
            return True
        return False

    def run(self):
        conn = None
        started_at = time.monotonic()
        host = self.cfg.get("host", "") if isinstance(self.cfg, dict) else str(self.cfg)
        db = self.cfg.get("db", "*LOCAL") if isinstance(self.cfg, dict) else "*LOCAL"

        if self.check_cancelled():
            return

        try:
            conn = _new_connection(host, db, self.username, self.password)
            cursor = conn.cursor()

            if self.check_cancelled():
                return

            system_name = self.server
            try:
                cursor.execute("SELECT HOST_NAME FROM QSYS2.SYSTEM_STATUS_INFO")
                row = cursor.fetchone()
                if row and row[0] is not None:
                    resolved_name = str(row[0]).strip()
                    if resolved_name:
                        system_name = resolved_name
            except Exception:
                pass

            active_jobs = 0
            asp_used = 0.0
            cpu_util = 0.0
            metric_errors = []

            try:
                cursor.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM TABLE(QSYS2.ACTIVE_JOB_INFO(RESET_STATISTICS => 'NO'))) AS ACTIVE_JOBS,
                        (SELECT SYSTEM_ASP_USED FROM QSYS2.SYSTEM_STATUS_INFO) AS ASP_USED,
                        (SELECT ROUND(AVERAGE_CPU_UTILIZATION, 2) FROM TABLE(QSYS2.SYSTEM_ACTIVITY_INFO())) AS CPU_UTIL
                    FROM SYSIBM.SYSDUMMY1
                    WITH NC
                    """
                )
                combined_row = cursor.fetchone()
                if combined_row:
                    if combined_row[0] is not None:
                        active_jobs = int(combined_row[0])
                    if combined_row[1] is not None:
                        asp_used = float(round(combined_row[1], 2))
                    if combined_row[2] is not None:
                        cpu_util = float(combined_row[2])
            except Exception as e:
                metric_errors.append(f"jobs/ASP/CPU: {e}")

            if self.check_cancelled():
                return

            if asp_used == 0.0:
                try:
                    cursor.execute("SELECT PERCENT_PROCESSING_UNIT_USED FROM QSYS2.SYSTEM_ASP_INFO")
                    asp_row = cursor.fetchone()
                    if asp_row and asp_row[0] is not None:
                        asp_used = float(round(asp_row[0], 2))
                except Exception as e:
                    metric_errors.append(f"ASP fallback: {e}")

            if self.check_cancelled():
                return

            active_subsystems = []
            try:
                cursor.execute(
                    """
                    SELECT 
                        SUBSYSTEM_DESCRIPTION, 
                        STATUS, 
                        CURRENT_ACTIVE_JOBS, 
                        SIGNON_DEVICE_FILE_LIBRARY, 
                        TEXT_DESCRIPTION 
                    FROM QSYS2.SUBSYSTEM_INFO 
                    WHERE STATUS = 'ACTIVE'
                    """
                )
                for r in cursor.fetchall():
                    active_subsystems.append({
                        "name": str(r[0]).strip() if r[0] else "",
                        "status": str(r[1]).strip() if r[1] else "",
                        "active_jobs": r[2] if r[2] is not None else 0,
                        "library": str(r[3]).strip() if r[3] else "",
                        "description": str(r[4]).strip() if r[4] else ""
                    })
            except Exception as e:
                metric_errors.append(f"subsystems: {e}")

            if self.check_cancelled():
                return

            port_status_list = []
            try:
                target_ports = EXPECTED_PORTS.get(self.server, [])
                if not target_ports and isinstance(MONITORED_PORTS, dict):
                    target_ports = [{"port": p, "name": s} for p, s in MONITORED_PORTS.items()]

                requested_ports = []
                for p_info in target_ports:
                    p_num = p_info.get("port") if isinstance(p_info, dict) else p_info
                    try:
                        requested_ports.append(int(p_num))
                    except (TypeError, ValueError):
                        continue

                if requested_ports:
                    placeholders = ", ".join("?" for _ in requested_ports)
                    cursor.execute(
                        f"""
                        SELECT LOCAL_PORT
                        FROM QSYS2.NETSTAT_INFO
                        WHERE TCP_STATE = 'LISTEN'
                          AND LOCAL_PORT IN ({placeholders})
                        """,
                                                *requested_ports,
                    )
                    active_ports = {
                        int(r[0]) for r in cursor.fetchall() if r[0] is not None and str(r[0]).isdigit()
                    }

                    for p_info in target_ports:
                        if self.check_cancelled():
                            return
                        p_num = p_info.get("port") if isinstance(p_info, dict) else p_info
                        p_name = p_info.get("name", f"PORT_{p_num}") if isinstance(p_info, dict) else str(p_num)
                        try:
                            port_number = int(p_num)
                        except (TypeError, ValueError):
                            continue
                        port_status_list.append({
                            "port": port_number,
                            "name": p_name,
                            "service": p_name,
                            "is_up": port_number in active_ports
                        })
            except Exception as e:
                metric_errors.append(f"ports: {e}")

            result = {
                "server": system_name,
                "host_name": system_name,
                "config_key": self.server,
                "status": "DEGRADED" if metric_errors else "ONLINE",
                "cpu": cpu_util,
                "asp": asp_used,
                "jobs": active_jobs,
                "subsystems": active_subsystems,
                "ports": port_status_list,
            }
            if metric_errors:
                result["error"] = "; ".join(metric_errors)

        except Exception as e:
            err_msg = str(e)
            if any(k in err_msg.lower() for k in ["28000", "cwbsy0011", "disabled", "password", "authentication"]):
                result = {
                    "server": self.server,
                    "host_name": self.server,
                    "config_key": self.server,
                    "status": "AUTH_ERROR",
                    "error": f"[{self.server}] {err_msg}",
                    "cpu": 0.0,
                    "asp": 0.0,
                    "jobs": 0,
                    "subsystems": [],
                    "ports": [],
                }
            else:
                result = {
                    "server": self.server,
                    "host_name": self.server,
                    "config_key": self.server,
                    "status": "OFFLINE",
                    "error": f"[{self.server}] {err_msg}",
                    "cpu": 0.0,
                    "asp": 0.0,
                    "jobs": 0,
                    "subsystems": [],
                    "ports": [],
                }
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        if not self.is_cancelled():
            result["sync_duration_ms"] = max(0, int((time.monotonic() - started_at) * 1000))
            try:
                maybe_send_asp_alert(str(result.get("server") or self.server), float(result.get("asp", 0.0) or 0.0))
            except Exception:
                pass
            _persist_and_emit(self, result)