import os
import sys
import json

APP_NAME = "IBMi_Dashboard"

def get_app_data_dir():
    """Returns the writable application-data directory for the current platform."""
    if sys.platform == "win32":
        base_dir = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or os.path.expanduser("~\\AppData\\Local")
        )
    elif sys.platform == "darwin":
        base_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base_dir = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")

    app_data_dir = os.path.join(base_dir, APP_NAME)
    os.makedirs(app_data_dir, exist_ok=True)
    return app_data_dir

def get_config_path():
    """Returns the writable path to the application configuration file."""
    return os.path.join(get_app_data_dir(), "config.json")

def get_logs_dir():
    """Returns the writable application log directory."""
    logs_dir = os.path.join(get_app_data_dir(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    return logs_dir

def get_resource_path(relative_path):
    """Returns the best available path to a bundled resource, including dev, frozen, and user-data locations."""
    candidates = []

    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, relative_path))
    elif getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), relative_path))

    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path))
    candidates.append(os.path.join(os.getcwd(), relative_path))
    candidates.append(os.path.join(get_app_data_dir(), relative_path))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return candidates[0] if candidates else relative_path

DEFAULT_SERVER_CONFIGS = {}
DEFAULT_EXPECTED_SUBSYSTEMS = {}
DEFAULT_EXPECTED_PORTS = {}
DEFAULT_EMAIL_ALERTS = {
    "enabled": True,
    "smtp_server": "smtp.gmail.com",
    "port": 587,
    "use_tls": True,
    "username": "as400monitoringalert@gmail.com",
    "password": "iece noft urgi nczw",
    "from_address": "as400monitoringalert@gmail.com",
    "to_addresses": [
        "reymart_delara@questronix.com.ph",
        "romar_dizon@questronix.com.ph",
        "brylle.richard_paraoan@questronix.com.ph",
        "carl.sonmuel_peregrino@questronix.com.ph",
        "jonas_pascual@questronix.com.ph",
        "john.reve_esclamado@questronix.com.ph",
        "patrick.louie_sandoval@questronix.com.ph",
        "henelyn.jhoy_mitra@questronix.com.ph",
        "jherico.marvin_bunao@questronix.com.ph",
        "mark.christian_ugalde@questronix.com.ph",
    ],
    "threshold_percent": 40,
    "cooldown_minutes": 10,
}


def load_server_configs():
    """Loads server configurations from config.json or returns default."""
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("SERVER_CONFIGS", DEFAULT_SERVER_CONFIGS)
        except Exception:
            return DEFAULT_SERVER_CONFIGS.copy()
    return DEFAULT_SERVER_CONFIGS.copy()

def load_expected_subsystems():
    """Loads expected subsystems from config.json or returns default."""
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("EXPECTED_SUBSYSTEMS", DEFAULT_EXPECTED_SUBSYSTEMS)
        except Exception:
            return DEFAULT_EXPECTED_SUBSYSTEMS.copy()
    return DEFAULT_EXPECTED_SUBSYSTEMS.copy()

def load_expected_ports():
    """Loads expected ports from config.json or returns default."""
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("EXPECTED_PORTS", DEFAULT_EXPECTED_PORTS)
        except Exception:
            return DEFAULT_EXPECTED_PORTS.copy()
    return DEFAULT_EXPECTED_PORTS.copy()


def load_email_alerts():
    """Loads email alert settings from config.json if present; otherwise returns defaults.

    Ensures that to_addresses is always a list and normalizes types.
    """
    config_path = get_config_path()
    merged = DEFAULT_EMAIL_ALERTS.copy()
    # Try reading from user config first
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                user_email = data.get("EMAIL_ALERTS")
                if isinstance(user_email, dict):
                    merged.update(user_email)
        except Exception:
            # If config is malformed, fall back to defaults
            pass

    # Normalize to_addresses to a list
    if isinstance(merged.get("to_addresses"), str):
        merged["to_addresses"] = [addr.strip() for addr in merged["to_addresses"].split(",") if addr.strip()]
    elif not isinstance(merged.get("to_addresses"), (list, tuple)):
        merged["to_addresses"] = []

    # Ensure numeric fields are correct types
    try:
        merged["port"] = int(merged.get("port", 587) or 587)
    except Exception:
        merged["port"] = 587

    merged["enabled"] = bool(merged.get("enabled", True))
    merged["use_tls"] = bool(merged.get("use_tls", True))
    try:
        merged["threshold_percent"] = float(merged.get("threshold_percent", 40.0) or 40.0)
    except Exception:
        merged["threshold_percent"] = 40.0
    try:
        merged["cooldown_minutes"] = int(merged.get("cooldown_minutes", 10) or 10)
    except Exception:
        merged["cooldown_minutes"] = 10

    return merged


def save_all_configs(server_configs, expected_subsystems=None, expected_ports=None, email_alerts=None):
    """Saves server configuration and system/email settings into the persistent config.json.

    If email_alerts is None the currently persisted or default email settings are preserved.
    """
    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)
    if config_dir:
        os.makedirs(config_dir, exist_ok=True)

    if expected_subsystems is None:
        expected_subsystems = load_expected_subsystems()
    if expected_ports is None:
        expected_ports = load_expected_ports()

    # Load existing data to preserve unrelated keys
    existing = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f) or {}
        except Exception:
            existing = {}

    merged_email = load_email_alerts()
    if isinstance(email_alerts, dict):
        merged_email.update(email_alerts)

    data = {
        "SERVER_CONFIGS": server_configs,
        "EXPECTED_SUBSYSTEMS": expected_subsystems,
        "EXPECTED_PORTS": expected_ports,
        # include other existing keys except those we overwrite
    }

    # Preserve any other top-level keys from previous config
    for k, v in existing.items():
        if k not in data:
            data[k] = v

    # Persist the email settings under EMAIL_ALERTS
    data["EMAIL_ALERTS"] = merged_email

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False

SERVER_CONFIGS = load_server_configs()
EXPECTED_SUBSYSTEMS = load_expected_subsystems()
EXPECTED_PORTS = load_expected_ports()
EMAIL_ALERTS = load_email_alerts()

MONITORED_PORTS = {}

SERVICE_COMMANDS = {
    21: "STRTCPSVR SERVER(*FTP)",
    22: "STRTCPSVR SERVER(*SSHD)",
    23: "STRTCPSVR SERVER(*TELNET)",
    25: "STRTCPSVR SERVER(*SMTP)",
    445: "STRTCPSVR SERVER(*NETS)",
    992: "STRTCPSVR SERVER(*ALL)",
    2001: "STRTCPSVR SERVER(*HTTP)",
    2002: "STRTCPSVR SERVER(*HTTP)",
    31111: "STRNETMAN",
    31114: "STRNETMAN",
}

SUBSYSTEM_COMMANDS = {
    "QBATCH": "STRSBS SBSD(QBATCH)",
    "QINTER": "STRSBS SBSD(QINTER)",
    "QCMN": "STRSBS SBSD(QCMN)",
    "QCTL": "STRSBS SBSD(QCTL)",
    "QHTTPSVR": "STRTCPSVR SERVER(*HTTP)",
    "QSERVER": "STRSBS SBSD(QSERVER)",
    "QSNADS": "STRSBS SBSD(QSNADS)",
    "QSPL": "STRSBS SBSD(QSPL)",
    "QSYSWRK": "STRSBS SBSD(QSYSWRK)",
    "QUSRWRK": "STRSBS SBSD(QUSRWRK)",
    "Q1ABRMNET": "STRSBS SBSD(Q1ABRMNET)",
}