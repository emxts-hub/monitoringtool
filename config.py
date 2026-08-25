import os
import sys
import json

APP_NAME = "IBMi_Dashboard"

def get_app_data_dir():
    """Returns the writable application-data directory for the current platform."""
    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(__file__))

    if sys.platform == "win32":
        base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    elif sys.platform == "darwin":
        base_dir = os.path.expanduser("~/Library/Application Support")
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
    """Returns the path to a bundled resource in development or a frozen app."""
    if hasattr(sys, "_MEIPASS"):
        base_dir = sys._MEIPASS
    elif getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)

DEFAULT_SERVER_CONFIGS = {}
DEFAULT_EXPECTED_SUBSYSTEMS = {}
DEFAULT_EXPECTED_PORTS = {}

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

def save_all_configs(server_configs, expected_subsystems=None, expected_ports=None):
    """Saves updated SERVER_CONFIGS, EXPECTED_SUBSYSTEMS, and EXPECTED_PORTS directly to config.json."""
    config_path = get_config_path()
    if expected_subsystems is None:
        expected_subsystems = load_expected_subsystems()
    if expected_ports is None:
        expected_ports = load_expected_ports()

    data = {
        "SERVER_CONFIGS": server_configs,
        "EXPECTED_SUBSYSTEMS": expected_subsystems,
        "EXPECTED_PORTS": expected_ports
    }

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False

SERVER_CONFIGS = load_server_configs()
EXPECTED_SUBSYSTEMS = load_expected_subsystems()
EXPECTED_PORTS = load_expected_ports()

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