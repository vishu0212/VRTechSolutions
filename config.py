
"""Configuration for VR Tech Solutions."""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


# =========================================================
# ENVIRONMENT
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from the project root.
load_dotenv(BASE_DIR / ".env")

IS_VERCEL = bool(os.getenv("VERCEL"))


# =========================================================
# PROJECT PATHS
# =========================================================

APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"

# Local private resume storage.
LOCAL_RESUME_FOLDER = (
    BASE_DIR / "instance" / "uploads" / "resumes"
)

# Temporary resume storage on Vercel.
VERCEL_RESUME_FOLDER = (
    Path("/tmp/vr_tech_solutions_instance")
    / "uploads"
    / "resumes"
)

RESUME_UPLOAD_FOLDER = (
    VERCEL_RESUME_FOLDER
    if IS_VERCEL
    else LOCAL_RESUME_FOLDER
)

# Public image uploads.
PUBLIC_UPLOAD_FOLDER = STATIC_DIR / "uploads"


# =========================================================
# ENVIRONMENT HELPERS
# =========================================================

def get_bool(name: str, default: bool = False) -> bool:
    """Read a Boolean environment variable."""

    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_int(name: str, default: int) -> int:
    """Read an integer environment variable."""

    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        return int(value)

    except ValueError as exc:
        raise ValueError(
            f"Environment variable {name} must be an integer."
        ) from exc


# =========================================================
# FLASK CONFIGURATION
# =========================================================

class Config:
    """Main Flask application configuration."""

    # -----------------------------------------------------
    # SECURITY
    # -----------------------------------------------------

    SECRET_KEY = os.getenv("SECRET_KEY")

    DEBUG = get_bool("FLASK_DEBUG", False)
    TESTING = False

    # -----------------------------------------------------
    # MONGODB ATLAS
    # -----------------------------------------------------

    MONGODB_URI = os.getenv("MONGODB_URI")

    MONGODB_DATABASE = "vr_tech_solutions"

    # -----------------------------------------------------
    # FILE UPLOADS
    # -----------------------------------------------------

    RESUME_UPLOAD_FOLDER = str(
        RESUME_UPLOAD_FOLDER
    )

    PUBLIC_UPLOAD_FOLDER = str(
        PUBLIC_UPLOAD_FOLDER
    )

    MAX_CONTENT_LENGTH = get_int(
        "MAX_CONTENT_LENGTH",
        5 * 1024 * 1024,
    )

    ALLOWED_RESUME_EXTENSIONS = {
        "pdf",
        "doc",
        "docx",
    }

    # -----------------------------------------------------
    # SESSION SECURITY
    # -----------------------------------------------------

    SESSION_COOKIE_HTTPONLY = True

    SESSION_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_SECURE = get_bool(
        "COOKIE_SECURE",
        IS_VERCEL,
    )

    REMEMBER_COOKIE_SECURE = get_bool(
        "COOKIE_SECURE",
        IS_VERCEL,
    )

    REMEMBER_COOKIE_HTTPONLY = True

    REMEMBER_COOKIE_SAMESITE = "Lax"

    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=8
    )

    # -----------------------------------------------------
    # CSRF PROTECTION
    # -----------------------------------------------------

    WTF_CSRF_ENABLED = True

    WTF_CSRF_TIME_LIMIT = 3600

    # -----------------------------------------------------
    # APPLICATION SETTINGS
    # -----------------------------------------------------

    ITEMS_PER_PAGE = get_int(
        "ITEMS_PER_PAGE",
        12,
    )

    SITE_NAME = os.getenv(
        "SITE_NAME",
        "VR Tech Solutions",
    )

    SITE_URL = os.getenv(
        "SITE_URL",
        "http://127.0.0.1:5000",
    )
