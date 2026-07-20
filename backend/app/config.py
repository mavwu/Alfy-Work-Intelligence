import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass


APP_NAME = "Alfy Work Intelligence"
DEFAULT_WORKSPACE_NAME = "Ride Yanga"
DEFAULT_USER_NAME = "Alfy"
DEFAULT_PROFILE_ROLE_TITLE = ""
DEFAULT_PROFILE_TIMEZONE = ""
DEFAULT_REPORT_SIGNATURE = ""
DEFAULT_REPORT_AUDIENCE = "Stakeholder"
RIDE_YANGA_REPORT_AUDIENCE = "CTO / Management"


def data_dir() -> Path:
    configured = os.getenv("ALFY_DATA_DIR")
    root = Path(os.path.expandvars(configured)).expanduser() if configured else Path.home() / ".alfy-work-intelligence"
    root.mkdir(parents=True, exist_ok=True)
    (root / "imports").mkdir(exist_ok=True)
    (root / "exports").mkdir(exist_ok=True)
    return root


def database_url() -> str:
    return f"sqlite:///{data_dir() / 'alfy_work_intelligence.sqlite3'}"


OLLAMA_URL = os.getenv("ALFY_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DEFAULT_IGNORE_PATTERNS = [
    "node_modules",
    "build",
    "dist",
    ".gradle",
    ".dart_tool",
    "coverage",
    "vendor",
    ".venv",
    "__pycache__",
]
