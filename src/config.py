import os
import sys
import json
from datetime import datetime, timezone

APP_NAME = "IBMi_Dashboard"

APP_NAME = "LPAR Manager"
APP_VERSION = "1.0.0"

# Hardcoded cut-off date (set to December 31, 2026)
# To disable hard expiration, set HARD_EXPIRATION_DATE = None
HARD_EXPIRATION_DATE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

# GitHub Pages URL serving your version metadata
VERSION_CHECK_URL = "https://emxts-hub.github.io/monitoringtool/version.json"

def is_build_expired() -> bool:
    """Check if local system time has exceeded the hard expiration threshold."""
    if HARD_EXPIRATION_DATE is None:
        return False
    now = datetime.now(timezone.utc)
    return now > HARD_EXPIRATION_DATE


def parse_version(ver_str: str) -> tuple:
    """Convert semver string ('1.0.0') to integer tuple (1, 0, 0) for comparison."""
    try:
        clean_str = ver_str.split("-")[0].strip()
        return tuple(map(int, clean_str.split(".")))
    except (ValueError, AttributeError):
        return (0, 0, 0)


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


# Optional keyring integration for secure password storage
try:
    import keyring
    _KEYRING_AVAILABLE = True
except Exception:
    keyring = None
    _KEYRING_AVAILABLE = False

_EMAIL_SERVICE_NAME = f"{APP_NAME}_smtp"


def save_email_password(username, password):
    """Store SMTP password securely in keyring when available.

    Falls back to storing in config.json if keyring is not available.
    Returns True on success, False otherwise.
    """
    if not username:
        return False
    if _KEYRING_AVAILABLE and keyring is not None:
        try:
            keyring.set_password(_EMAIL_SERVICE_NAME, username, password or "")
            return True
        except Exception:
            return False

    # Fallback: persist password into config.json (insecure) to maintain compatibility
    try:
        config_path = get_config_path()
        data = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f) or {}
                except Exception:
                    data = {}
        email_section = data.get("EMAIL_ALERTS", {}) if isinstance(data.get("EMAIL_ALERTS"), dict) else {}
        email_section["password"] = password or ""
        data["EMAIL_ALERTS"] = email_section
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False


def get_email_password(username):
    """Retrieve SMTP password from keyring when available; otherwise fall back to config.json."""
    if not username:
        return ""
    if _KEYRING_AVAILABLE and keyring is not None:
        try:
            val = keyring.get_password(_EMAIL_SERVICE_NAME, username)
            return val or ""
        except Exception:
            pass

    # Fallback: read from config.json
    try:
        config_path = get_config_path()
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f) or {}
                    email_section = data.get("EMAIL_ALERTS") or {}
                    return str(email_section.get("password", "") or "")
                except Exception:
                    return ""
    except Exception:
        return ""


def load_email_alerts():
    """Loads email alert settings from config.json if present; otherwise returns defaults.

    Ensures that to_addresses is always a list and normalizes types. Password is retrieved from the keyring when possible.
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

    # Populate password from keyring (or fallback to any value in merged)
    try:
        merged_password = get_email_password(merged.get("username", ""))
        if merged_password:
            merged["password"] = merged_password
        else:
            # keep whatever was in the config if keyring empty
            merged["password"] = merged.get("password", "")
    except Exception:
        merged["password"] = merged.get("password", "")

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

    # If a password was supplied, try to store it securely and remove it from the JSON to avoid plaintext
    try:
        pwd = merged_email.pop("password", None)
        username = merged_email.get("username", "")
        if pwd is not None and username:
            try:
                save_email_password(username, pwd)
            except Exception:
                # best-effort; if saving fails we keep the password out of the JSON
                pass
    except Exception:
        pass

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

    # Persist the email settings under EMAIL_ALERTS (password intentionally omitted)
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