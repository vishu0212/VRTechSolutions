"""Lightweight record classes matching the existing VR Tech Solutions D1 schema.

These are data-transfer objects, not SQLAlchemy models. They intentionally
mirror the columns imported from Dump20261029.sql.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, ClassVar, Iterable

from .database import D1Row


def _to_int(value: Any) -> Any:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _to_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _to_datetime(value: Any) -> Any:
    if value is None or isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return value
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        # MySQL dumps commonly use YYYY-MM-DD HH:MM:SS.
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value


def _to_date(value: Any) -> Any:
    if value is None or isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return value


class D1Model:
    TABLE: ClassVar[str] = ""
    COLUMNS: ClassVar[tuple[str, ...]] = ()
    BOOLEAN_COLUMNS: ClassVar[frozenset[str]] = frozenset()
    DATETIME_COLUMNS: ClassVar[frozenset[str]] = frozenset(
        {"created_at", "updated_at"}
    )
    DATE_COLUMNS: ClassVar[frozenset[str]] = frozenset()
    INTEGER_COLUMNS: ClassVar[frozenset[str]] = frozenset(
        {"id", "job_id", "display_order"}
    )

    def __init__(self, **values: Any):
        for column in self.COLUMNS:
            value = values.get(column)
            if column in self.BOOLEAN_COLUMNS:
                value = _to_bool(value)
            elif column in self.DATETIME_COLUMNS:
                value = _to_datetime(value)
            elif column in self.DATE_COLUMNS:
                value = _to_date(value)
            elif column in self.INTEGER_COLUMNS:
                value = _to_int(value)
            setattr(self, column, value)

    @classmethod
    def from_row(cls, row: D1Row | dict[str, Any] | Any):
        values = {}
        for column in cls.COLUMNS:
            try:
                values[column] = row.get(column) if hasattr(row, "get") else row[column]
            except (KeyError, TypeError, AttributeError):
                values[column] = None
        return cls(**values)

    @classmethod
    def from_rows(cls, rows: Iterable[D1Row]):
        return [cls.from_row(row) for row in rows]

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for column in self.COLUMNS:
            value = getattr(self, column, None)
            if isinstance(value, (date, datetime)):
                value = value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
            result[column] = value
        return result


class Admin(D1Model):
    TABLE = "admins"
    COLUMNS = (
        "id", "username", "email", "password_hash", "is_active", "created_at"
    )
    BOOLEAN_COLUMNS = frozenset({"is_active"})

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)


class ContactEnquiry(D1Model):
    TABLE = "contact_enquiries"
    COLUMNS = (
        "id", "name", "email", "phone", "company", "subject", "message",
        "status", "admin_notes", "created_at", "updated_at",
    )


class JobApplication(D1Model):
    TABLE = "job_applications"
    COLUMNS = (
        "id", "job_id", "full_name", "email", "phone", "current_location",
        "experience", "cover_letter", "resume_filename", "status",
        "admin_notes", "created_at", "updated_at",
    )


class Job(D1Model):
    TABLE = "jobs"
    COLUMNS = (
        "id", "title", "slug", "department", "location", "employment_type",
        "experience", "salary_range", "short_description", "description",
        "requirements", "is_active", "closing_date", "created_at", "updated_at",
    )
    BOOLEAN_COLUMNS = frozenset({"is_active"})
    DATE_COLUMNS = frozenset({"closing_date"})
    INTEGER_COLUMNS = frozenset({"id"})

    def __init__(self, **values: Any):
        super().__init__(**values)
        # The existing admin templates use job.applications to decide whether
        # a vacancy can be deleted. D1 routes populate this list when needed.
        self.applications = values.get("applications", [])


class Project(D1Model):
    TABLE = "projects"
    COLUMNS = (
        "id", "title", "slug", "category", "short_description", "description",
        "image_url", "project_url", "technologies", "is_featured", "is_active",
        "display_order", "created_at", "updated_at",
    )
    BOOLEAN_COLUMNS = frozenset({"is_featured", "is_active"})


class Service(D1Model):
    TABLE = "services"
    COLUMNS = (
        "id", "title", "slug", "short_description", "description", "icon",
        "image_url", "is_active", "display_order", "created_at", "updated_at",
    )
    BOOLEAN_COLUMNS = frozenset({"is_active"})


class SiteSetting(D1Model):
    TABLE = "site_settings"
    COLUMNS = ("key", "value", "updated_at")
    INTEGER_COLUMNS = frozenset()


MODEL_BY_TABLE = {
    model.TABLE: model
    for model in (
        Admin,
        ContactEnquiry,
        JobApplication,
        Job,
        Project,
        Service,
        SiteSetting,
    )
}
