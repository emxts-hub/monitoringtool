import os
import sys
import json
import re
import threading
import time
import uuid
import platform
import subprocess
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
import pyodbc
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool
from config import SERVER_CONFIGS, MONITORED_PORTS, EXPECTED_PORTS, get_logs_dir, load_email_alerts


_LOG_WRITE_LOCK = threading.Lock()
_ALERT_STATE_LOCK = threading.Lock()
_LAST_ASP_ALERT_STATE = {}


def _normalize_recipients(value):
    if isinstance(value, str):
        recipients = [item.strip() for item in value.split(',') if item.strip()]
    elif isinstance(value, (list, tuple, set)):
        recipients = [str(item).strip() for item in value if str(item).strip()]
    else:
        recipients = []
    return recipients


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
    """Sends an ASP notification only on threshold crossings and respects cooldown."""
    alert_cfg = load_email_alerts()
    if not alert_cfg.get("enabled"):
        return False

    threshold_percent = float(alert_cfg.get("threshold_percent", 90.0) or 90.0)
    cooldown_seconds = max(0, int(float(alert_cfg.get("cooldown_minutes", 30) or 30) * 60))

    with _ALERT_STATE_LOCK:
        state = _LAST_ASP_ALERT_STATE.get(server_name, {"armed": False, "sent_at": 0.0})
        now = time.monotonic()

        if asp_value < threshold_percent:
            state["armed"] = False
            _LAST_ASP_ALERT_STATE[server_name] = state
            return False

        if state.get("armed") and (now - float(state.get("sent_at", 0.0))) < cooldown_seconds:
            return False

        state["armed"] = True
        state["sent_at"] = now
        _LAST_ASP_ALERT_STATE[server_name] = state

    return send_asp_alert(server_name, asp_value, threshold_percent)


def ping_ip(host_ip, timeout_ms=1000):
    """Pings a host IP address to check network reachability directly on background thread."""
    if not host_ip or host_ip == "N/A":
        return False
    
    is_windows = platform.system().lower() == "windows"
    param = "-n" if is_windows else "-c"
    timeout_param = "-w" if is_windows else "-W"
    timeout_val = str(timeout_ms) if is_windows else str(max(1, int(timeout_ms / 1000)))
    
    command = ["ping", param, "1", timeout_param, timeout_val, host_ip]
    try:
        # Prevent a visible console window on Windows when running the ping binary
        creation_flags = 0
        if is_windows and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW
        res = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)
        return res.returncode == 0
    except Exception:
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


def save_single_lpar_log(sys_info, server_configs=None):
    """Appends a single LPAR result directly to the daily JSON history file upon worker completion."""
    logs_dir = get_logs_dir()
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    filepath = os.path.join(logs_dir, f"lpar_history_{date_str}.json")

    configs = server_configs or SERVER_CONFIGS

    down_services = []
    if sys_info.get("ports"):
        down_services = [
            p.get("name") or p.get("service") 
            for p in sys_info["ports"] 
            if not p.get("is_up")
        ]

    services_down_val = down_services if down_services else "None"
    server_name = sys_info.get("server")
    
    cfg = configs.get(server_name, {})
    ip_addr = cfg.get("host", "N/A") if isinstance(cfg, dict) else str(cfg)

    record = {
        "entry_id": uuid.uuid4().hex,
        "timestamp": timestamp_str,
        "lpar": server_name,
        "server": server_name,
        "ip": ip_addr,
        "cpu": sys_info.get("cpu", 0.0),
        "asp": sys_info.get("asp", 0.0),
        "jobs": sys_info.get("jobs", 0),
        "status": sys_info.get("status", "OFFLINE"),
        "subsystems_summary": f"{len(sys_info.get('subsystems', []))} Active",
        "subsystems_detail": sys_info.get("subsystems", []),
        "services_down": services_down_val
    }

    entry = {
        "timestamp": timestamp_str,
        "records": [record]
    }

    with _LOG_WRITE_LOCK:
        existing_data = []
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = [existing_data]
            except Exception:
                existing_data = []

        existing_data.append(entry)

        temp_path = None
        try:
            temp_path = f"{filepath}.{uuid.uuid4().hex}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)
            os.replace(temp_path, filepath)
        except Exception:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        cleanup_old_logs(days_to_keep=30)


class LparWorkerSignals(QObject):
    """Signals for communicating LPAR query execution results safely to GUI widgets."""
    server_fetched = pyqtSignal(dict)


class SingleLparRunnable(QRunnable):
    """Concurrent worker task for fetching metrics from a single LPAR connection."""
    def __init__(self, server, cfg, username, password, cancel_event=None):
        super().__init__()
        self.server = server
        self.cfg = cfg
        self.username = username
        self.password = password
        self.cancel_event = cancel_event or threading.Event()
        self.signals = LparWorkerSignals()

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

        # Pre-check IP reachability via ICMP ping on this background thread
        if not ping_ip(host):
            result = {
                "server": self.server,
                "status": "OFFLINE",
                "error": f"[{self.server}] Host {host} is unreachable / VPN disconnected.",
                "cpu": 0.0,
                "asp": 0.0,
                "jobs": 0,
                "subsystems": [],
                "ports": [],
                "sync_duration_ms": max(0, int((time.monotonic() - started_at) * 1000)),
            }
            if not self.is_cancelled():
                save_single_lpar_log(result)
                self.signals.server_fetched.emit(result)
            return

        try:
            conn = pyodbc.connect(
                f"DRIVER={{IBM i Access ODBC Driver}};"
                f"SYSTEM={host};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"SSL=0;"
                f"DATABASE={db};"
                f"CONN_TIMEOUT=3;"
                f"QUERY_TIMEOUT=3;",
                timeout=3,
                autocommit=True
            )
            cursor = conn.cursor()

            if self.check_cancelled():
                return

            active_jobs = 0
            asp_used = 0.0
            cpu_util = 0.0
            metric_errors = []

            try:
                cursor.execute("SELECT COUNT(*) FROM TABLE(QSYS2.ACTIVE_JOB_INFO())")
                job_row = cursor.fetchone()
                if job_row and job_row[0] is not None:
                    active_jobs = job_row[0]

                cursor.execute("SELECT SYSTEM_ASP_USED FROM QSYS2.SYSTEM_STATUS_INFO")
                asp_row = cursor.fetchone()
                if asp_row and asp_row[0] is not None:
                    asp_used = float(round(asp_row[0], 2))
            except Exception as e:
                metric_errors.append(f"jobs/ASP: {e}")

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

            try:
                cursor.execute(
                    """
                    SELECT ROUND(AVERAGE_CPU_UTILIZATION, 2) AS CPU_UTILIZATION 
                    FROM TABLE(QSYS2.SYSTEM_ACTIVITY_INFO())
                    """
                )
                cpu_row = cursor.fetchone()
                if cpu_row and cpu_row[0] is not None:
                    cpu_util = float(cpu_row[0])
            except Exception as e:
                metric_errors.append(f"CPU: {e}")

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
                cursor.execute(
                    """
                    SELECT LOCAL_PORT 
                    FROM QSYS2.NETSTAT_INFO 
                    WHERE TCP_STATE IN ('LISTEN')
                    """
                )
                active_ports = {
                    int(r[0]) for r in cursor.fetchall() if r[0] is not None and str(r[0]).isdigit()
                }

                target_ports = EXPECTED_PORTS.get(self.server, [])
                if not target_ports and isinstance(MONITORED_PORTS, dict):
                    target_ports = [{"port": p, "name": s} for p, s in MONITORED_PORTS.items()]

                for p_info in target_ports:
                    if self.check_cancelled():
                        return
                    p_num = p_info.get("port") if isinstance(p_info, dict) else p_info
                    p_name = p_info.get("name", f"PORT_{p_num}") if isinstance(p_info, dict) else str(p_num)
                    
                    if str(p_num).isdigit():
                        port_status_list.append({
                            "port": int(p_num),
                            "name": p_name,
                            "service": p_name,
                            "is_up": int(p_num) in active_ports
                        })
            except Exception as e:
                metric_errors.append(f"ports: {e}")

            result = {
                "server": self.server,
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
                maybe_send_asp_alert(self.server, float(result.get("asp", 0.0) or 0.0))
            except Exception:
                pass
            save_single_lpar_log(result)
            self.signals.server_fetched.emit(result)