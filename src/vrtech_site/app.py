"""D1-backed Flask application for VR Tech Solutions.

Separate from the current local SQLAlchemy app. This staged Worker version
keeps the local application untouched while moving production routes to D1.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any
from types import SimpleNamespace
import re
import uuid
from urllib.parse import quote, urlsplit

from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    render_template_string,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf import CSRFProtect
from jinja2 import DictLoader
from pyodide.ffi import JsException, run_sync
from js import Array, Object, Uint8Array, fetch

from d1_core.database import D1Database, D1QueryError
from d1_core.models import Admin, ContactEnquiry, Job, JobApplication, Project, Service, SiteSetting


# ---------------------------------------------------------------------------
# Password verification
# ---------------------------------------------------------------------------

_MAX_RESUME_BYTES = 5 * 1024 * 1024
_ALLOWED_RESUME_TYPES = {
    "pdf": ("application/pdf", b"%PDF-"),
    "doc": ("application/msword", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"PK\x03\x04",
    ),
}


def _to_uint8array(data: bytes):
    values = Array.new(len(data))

    for index, value in enumerate(data):
        values[index] = value

    result = Uint8Array.new(len(data))
    result.set(values)
    return result


def _supabase_storage_request(
    method: str,
    object_key: str,
    body: bytes | None = None,
    content_type: str | None = None,
):
    """Send an authenticated request to the private Supabase Storage bucket."""

    worker_env = request.environ.get("workers.env")
    supabase_url = _get_member(worker_env, "SUPABASE_URL")
    supabase_key = _get_member(worker_env, "SUPABASE_SECRET_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError("Supabase Storage credentials are not configured.")

    encoded_key = quote(object_key, safe="/")
    endpoint = (
        f"{str(supabase_url).rstrip('/')}"
        f"/storage/v1/object/resumes/{encoded_key}"
    )

    options = Object.new()
    headers = Object.new()

    Object.assign(
        headers,
        {
            "Authorization": f"Bearer {supabase_key}",
            "apikey": str(supabase_key),
        },
    )

    if content_type:
        Object.assign(
            headers,
            {"Content-Type": content_type},
        )

    options.method = method
    options.headers = headers

    if body is not None:
        options.body = _to_uint8array(body)

    try:
        response = run_sync(fetch(endpoint, options))

        if not _get_member(response, "ok", False):
            status = _get_member(response, "status", "unknown")
            error_text = run_sync(response.text())
            raise RuntimeError(
                f"Supabase Storage error ({status}): "
                f"{str(error_text)[:500]}"
            )

        return response

    except JsException as error:
        raise RuntimeError(
            "Supabase Storage request could not be completed."
        ) from error


def _verify_pbkdf2(stored_hash: str, password: str) -> bool:
    try:
        method, salt, expected_hash = stored_hash.split("$", 2)

        parts = method.split(":")

        if (
            len(parts) != 3
            or parts[0] != "pbkdf2"
            or parts[1] != "sha256"
        ):
            return False

        iterations = int(parts[2])

        if iterations != 600000:
            return False

        if len(expected_hash) != 64:
            return False

        if any(c not in "0123456789abcdefABCDEF" for c in expected_hash):
            return False

        if not salt or len(salt) > 128:
            return False
        password_bytes = password.encode("utf-8")
        salt_bytes = salt.encode("utf-8")
        salt_bytes = salt.encode("utf-8")

        block = salt_bytes + b"\x00\x00\x00\x01"

        u = hmac.new(password_bytes, block, hashlib.sha256).digest()
        result = bytearray(u)

        for _ in range(iterations - 1):
            u = hmac.new(password_bytes, u, hashlib.sha256).digest()

            for index in range(32):
                result[index] ^= u[index]

        actual_hash = bytes(result).hex()

        return hmac.compare_digest(
            actual_hash,
            expected_hash.lower(),
        )

    except Exception as error:
        print(
            "ADMIN_PASSWORD_VERIFY_ERROR:",
            type(error).__name__,
            str(error),
        )
        return False


def _check_admin_password(stored_hash: str, password: str) -> bool:
    if not stored_hash or not password:
        return False

    return _verify_pbkdf2(stored_hash, password)

try:
    from .templates_data import TEMPLATES
except ImportError:
    TEMPLATES: dict[str, str] = {}


d1 = D1Database()
login_manager = LoginManager()
csrf = CSRFProtect()
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
main_bp = Blueprint("main", __name__)
careers_bp = Blueprint("careers", __name__)

_PENDING_TEMPLATE = """<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>{{ section }} migration</title>
<style>
:root{color-scheme:light}body{font-family:Inter,system-ui,Segoe UI,sans-serif;background:#f4f7fb;color:#172033;margin:0;min-height:100vh;display:grid;place-items:center}
main{background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:32px;max-width:620px;margin:24px;box-shadow:0 18px 50px rgba(15,23,42,.08)}
h1{margin-top:0;font-size:24px}p{line-height:1.6;color:#475569}.tag{display:inline-block;background:#fff7ed;color:#9a3412;padding:6px 10px;border-radius:999px;font-size:12px;font-weight:700}
a{color:#1d4ed8;text-decoration:none;font-weight:600}
</style></head><body><main><span class=\"tag\">Migration in progress</span><h1>{{ section }}</h1>
<p>This section has not been connected to Cloudflare D1 yet. Your existing local Flask version remains unchanged.</p>
<p><a href=\"{{ url_for('admin.dashboard') }}\">Return to the admin dashboard</a></p></main></body></html>"""


def _get_member(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    try:
        return getattr(obj, name)
    except (AttributeError, TypeError):
        try:
            return obj[name]
        except (KeyError, TypeError, IndexError, AttributeError):
            return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class WorkerEnvironmentMiddleware:
    """Set the Worker secret before Flask opens its signed-cookie session."""

    def __init__(self, wsgi_app, flask_app: Flask):
        self.wsgi_app = wsgi_app
        self.flask_app = flask_app

    def __call__(self, environ, start_response):
        worker_env = environ.get("workers.env")
        secret_key = _get_member(worker_env, "SECRET_KEY")
        if not secret_key:
            body = b"Worker secret SECRET_KEY is not configured."
            start_response(
                "500 Internal Server Error",
                [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                    ("Cache-Control", "no-store"),
                ],
            )
            return [body]

        self.flask_app.secret_key = str(secret_key)
        cookie_secure = _as_bool(_get_member(worker_env, "COOKIE_SECURE"), False)
        self.flask_app.config["SESSION_COOKIE_SECURE"] = cookie_secure
        self.flask_app.config["REMEMBER_COOKIE_SECURE"] = cookie_secure
        return self.wsgi_app(environ, start_response)


def _safe_next(value: str) -> bool:
    return (
        value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
    )


def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(d1.scalar(sql, params, default=0) or 0)


def _pending(section: str):
    return render_template_string(_PENDING_TEMPLATE, section=section), 501


# ---------------------------------------------------------------------------
# Administrator authentication and read-only dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username_or_email = request.form.get("username", "").strip()[:254]
        password = request.form.get("password", "")

        if not username_or_email or not password:
            flash("Please enter your username/email and password.", "error")
            return render_template("admin/login.html"), 400

        row = d1.fetch_one(
            """SELECT id, username, email, password_hash, is_active, created_at
               FROM admins
               WHERE username = ? COLLATE NOCASE
                  OR email = ? COLLATE NOCASE
               LIMIT 1""",
            (username_or_email, username_or_email),
        )
        admin = Admin.from_row(row) if row else None

        if (
            admin is not None
            and admin.is_active
            and _check_admin_password(admin.password_hash, password)
        ):
            login_user(admin, remember=False, fresh=True)
            next_page = request.args.get("next", "")
            if next_page and _safe_next(next_page):
                return redirect(next_page)
            flash("Login successful!", "success")
            return redirect(url_for("admin.dashboard"))

        flash("Invalid username/email or password.", "error")

    return render_template("admin/login.html")


@admin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


@admin_bp.route("/", methods=["GET"])
@admin_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        funding = request.form.get("funding_secured", "").strip()
        if not funding:
            flash("Enter a funding amount or value.", "error")
            return redirect(url_for("admin.dashboard"))
        if len(funding) > 100:
            flash("Funding value must be 100 characters or fewer.", "error")
            return redirect(url_for("admin.dashboard"))

        d1.run(
            """INSERT INTO site_settings (key, value, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = CURRENT_TIMESTAMP""",
            ("funding_secured", funding),
        )
        flash("Homepage funding metric updated.", "success")
        return redirect(url_for("admin.dashboard"))

    setting = d1.fetch_one(
        "SELECT key, value, updated_at FROM site_settings WHERE key = ?",
        ("funding_secured",),
    )
    funding_secured = setting.value if setting else "$90m"

    stats = {
        "services": d1.table_count("services"),
        "active_services": _count("SELECT COUNT(*) AS value FROM services WHERE is_active = 1"),
        "projects": d1.table_count("projects"),
        "active_projects": _count("SELECT COUNT(*) AS value FROM projects WHERE is_active = 1"),
        "enquiries": d1.table_count("contact_enquiries"),
        "new_enquiries": _count("SELECT COUNT(*) AS value FROM contact_enquiries WHERE status = ?", ("new",)),
        "jobs": d1.table_count("jobs"),
        "active_jobs": _count("SELECT COUNT(*) AS value FROM jobs WHERE is_active = 1"),
        "applications": d1.table_count("job_applications"),
        "new_applications": _count("SELECT COUNT(*) AS value FROM job_applications WHERE status = ?", ("new",)),
    }

    recent_enquiries = ContactEnquiry.from_rows(
        d1.fetch_all(
            "SELECT * FROM contact_enquiries ORDER BY created_at DESC LIMIT 5"
        )
    )
    recent_applications = JobApplication.from_rows(
        d1.fetch_all(
            "SELECT * FROM job_applications ORDER BY created_at DESC LIMIT 5"
        )
    )

    response = make_response(
        render_template(
            "admin/dashboard.html",
            stats=stats,
            service_count=stats["services"],
            project_count=stats["projects"],
            enquiry_count=stats["enquiries"],
            new_enquiry_count=stats["new_enquiries"],
            job_count=stats["jobs"],
            application_count=stats["applications"],
            funding_secured=funding_secured,
            recent_enquiries=recent_enquiries,
            recent_applications=recent_applications,
        )
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


# ---------------------------------------------------------------------------
# Customer enquiries - Cloudflare D1
# ---------------------------------------------------------------------------

@admin_bp.route("/enquiries", methods=["GET"])
@login_required
def enquiries():
    search = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "").strip().lower()

    allowed_statuses = {"new", "read", "replied", "closed"}

    conditions = []
    parameters = []

    if status in allowed_statuses:
        conditions.append("status = ?")
        parameters.append(status)
    else:
        status = ""

    if search:
        conditions.append(
            "(name LIKE ? OR email LIKE ? OR company LIKE ? OR subject LIKE ?)"
        )
        pattern = f"%{search}%"
        parameters.extend([pattern, pattern, pattern, pattern])

    sql = "SELECT * FROM contact_enquiries"

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY created_at DESC, id DESC LIMIT 200"

    enquiry_rows = d1.fetch_all(sql, tuple(parameters))
    enquiry_items = ContactEnquiry.from_rows(enquiry_rows)

    response = make_response(
        render_template(
            "admin/enquiries.html",
            enquiries=enquiry_items,
            search=search,
            selected_status=status,
        )
    )

    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


@admin_bp.route("/enquiries/<int:item_id>/status", methods=["POST"])
@login_required
def enquiry_status(item_id):
    new_status = request.form.get("status", "").strip().lower()

    allowed_statuses = {"new", "read", "replied", "closed"}

    if new_status not in allowed_statuses:
        flash("Invalid enquiry status.", "error")
        return redirect(url_for("admin.enquiries"))

    existing = d1.fetch_one(
        "SELECT id FROM contact_enquiries WHERE id = ?",
        (item_id,),
    )

    if existing is None:
        flash("Enquiry not found.", "error")
        return redirect(url_for("admin.enquiries"))

    d1.run(
        """UPDATE contact_enquiries
           SET status = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (new_status, item_id),
    )

    flash("Enquiry status updated successfully.", "success")
    return redirect(url_for("admin.enquiries"))


@admin_bp.route("/enquiries/<int:enquiry_id>/update", methods=["POST"])
@login_required
def enquiry_update(enquiry_id):
    admin_notes = request.form.get("admin_notes", "").strip()

    if len(admin_notes) > 5000:
        flash("Admin notes cannot exceed 5000 characters.", "error")
        return redirect(url_for("admin.enquiries"))

    existing = d1.fetch_one(
        "SELECT id FROM contact_enquiries WHERE id = ?",
        (enquiry_id,),
    )

    if existing is None:
        flash("Enquiry not found.", "error")
        return redirect(url_for("admin.enquiries"))

    d1.run(
        """UPDATE contact_enquiries
           SET admin_notes = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (admin_notes or None, enquiry_id),
    )

    flash("Admin notes updated successfully.", "success")
    return redirect(url_for("admin.enquiries"))


@admin_bp.route("/enquiries/<int:enquiry_id>/delete", methods=["POST"])
@login_required
def enquiry_delete(enquiry_id):
    existing = d1.fetch_one(
        "SELECT id FROM contact_enquiries WHERE id = ?",
        (enquiry_id,),
    )

    if existing is None:
        flash("Enquiry not found.", "error")
        return redirect(url_for("admin.enquiries"))

    d1.run(
        "DELETE FROM contact_enquiries WHERE id = ?",
        (enquiry_id,),
    )

    flash("Enquiry deleted successfully.", "success")
    return redirect(url_for("admin.enquiries"))


# ---------------------------------------------------------------------------
# Services management - Cloudflare D1
# ---------------------------------------------------------------------------

_SERVICE_ICONS = {
    "brain-circuit",
    "code-2",
    "cloud",
    "workflow",
    "shield-check",
    "settings",
    "layers",
    "sparkles",
}


def _unique_service_slug(title: str, exclude_id: int | None = None) -> str:
    """Generate a URL-safe slug that is unique in the services table."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    base = base or "service"
    candidate = base
    suffix = 2

    while True:
        if exclude_id is None:
            existing = d1.fetch_one(
                "SELECT id FROM services WHERE slug = ? LIMIT 1",
                (candidate,),
            )
        else:
            existing = d1.fetch_one(
                "SELECT id FROM services WHERE slug = ? AND id != ? LIMIT 1",
                (candidate, exclude_id),
            )

        if existing is None:
            return candidate

        candidate = f"{base}-{suffix}"
        suffix += 1


def _service_form_data():
    """Validate and normalize fields shared by create and edit forms."""
    title = request.form.get("title", "").strip()
    short_description = request.form.get("short_description", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "settings").strip()
    order_value = request.form.get("display_order", "0").strip()

    if not title:
        return None, "Service title is required."

    if len(title) > 150:
        return None, "Service title cannot exceed 150 characters."

    if len(short_description) > 500:
        return None, "Short description cannot exceed 500 characters."

    if not description:
        return None, "Full description is required."

    if len(description) > 20000:
        return None, "Description cannot exceed 20000 characters."

    if icon not in _SERVICE_ICONS:
        icon = "settings"

    try:
        display_order = int(order_value or "0")
    except ValueError:
        return None, "Display order must be a whole number."

    if not 0 <= display_order <= 9999:
        return None, "Display order must be between 0 and 9999."

    values = {
        "title": title,
        "short_description": short_description,
        "description": description,
        "icon": icon,
        "display_order": display_order,
        "is_active": 1 if _as_bool(request.form.get("is_active")) else 0,
    }
    return values, None


@admin_bp.route("/services", methods=["GET", "POST"])
@login_required
def services():
    if request.method == "POST":
        values, error = _service_form_data()

        if error:
            flash(error, "error")
            return redirect(url_for("admin.services"))

        slug = _unique_service_slug(values["title"])

        d1.run(
            """INSERT INTO services (
                   title, slug, short_description, description, icon,
                   image_url, is_active, display_order,
                   created_at, updated_at
               )
               VALUES (?, ?, ?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP,
                       CURRENT_TIMESTAMP)""",
            (
                values["title"],
                slug,
                values["short_description"],
                values["description"],
                values["icon"],
                values["is_active"],
                values["display_order"],
            ),
        )

        flash("Service created successfully.", "success")
        return redirect(url_for("admin.services"))

    rows = d1.fetch_all(
        """SELECT * FROM services
           ORDER BY display_order ASC, id DESC"""
    )

    response = make_response(
        render_template("admin/services.html", services=Service.from_rows(rows))
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


@admin_bp.route("/services/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_service(item_id):
    existing = d1.fetch_one(
        "SELECT * FROM services WHERE id = ?",
        (item_id,),
    )

    if existing is None:
        flash("Service not found.", "error")
        return redirect(url_for("admin.services"))

    if request.method == "POST":
        values, error = _service_form_data()

        if error:
            flash(error, "error")
            return redirect(url_for("admin.edit_service", item_id=item_id))

        slug = _unique_service_slug(values["title"], exclude_id=item_id)

        d1.run(
            """UPDATE services
               SET title = ?,
                   slug = ?,
                   short_description = ?,
                   description = ?,
                   icon = ?,
                   is_active = ?,
                   display_order = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                values["title"],
                slug,
                values["short_description"],
                values["description"],
                values["icon"],
                values["is_active"],
                values["display_order"],
                item_id,
            ),
        )

        flash("Service updated successfully.", "success")
        return redirect(url_for("admin.services"))

    response = make_response(
        render_template(
            "admin/service_edit.html",
            item=Service.from_row(existing),
        )
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


@admin_bp.route("/services/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_service(item_id):
    existing = d1.fetch_one(
        "SELECT id, is_active FROM services WHERE id = ?",
        (item_id,),
    )

    if existing is None:
        flash("Service not found.", "error")
        return redirect(url_for("admin.services"))

    new_status = 0 if _as_bool(existing.get("is_active")) else 1

    d1.run(
        """UPDATE services
           SET is_active = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (new_status, item_id),
    )

    flash(
        "Service activated successfully."
        if new_status
        else "Service hidden successfully.",
        "success",
    )
    return redirect(url_for("admin.services"))


@admin_bp.route("/services/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_service(item_id):
    existing = d1.fetch_one(
        "SELECT id FROM services WHERE id = ?",
        (item_id,),
    )

    if existing is None:
        flash("Service not found.", "error")
        return redirect(url_for("admin.services"))

    d1.run(
        "DELETE FROM services WHERE id = ?",
        (item_id,),
    )

    flash("Service deleted successfully.", "success")
    return redirect(url_for("admin.services"))



# ---------------------------------------------------------------------------
# Projects management - Cloudflare D1
# ---------------------------------------------------------------------------

def _unique_project_slug(title: str, exclude_id: int | None = None) -> str:
    """Generate a unique URL-safe project slug."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    base = base or "project"
    candidate = base
    suffix = 2

    while True:
        if exclude_id is None:
            existing = d1.fetch_one(
                "SELECT id FROM projects WHERE slug = ? LIMIT 1",
                (candidate,),
            )
        else:
            existing = d1.fetch_one(
                "SELECT id FROM projects WHERE slug = ? AND id != ? LIMIT 1",
                (candidate, exclude_id),
            )

        if existing is None:
            return candidate

        candidate = f"{base}-{suffix}"
        suffix += 1


def _project_form_data():
    """Validate project form fields."""
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "").strip()
    short_description = request.form.get("short_description", "").strip()
    description = request.form.get("description", "").strip()
    technologies = request.form.get("technologies", "").strip()
    image_url = request.form.get("image_url", "").strip()
    project_url = request.form.get("project_url", "").strip()
    order_value = request.form.get("display_order", "0").strip()

    if not title:
        return None, "Project title is required."

    if len(title) > 150:
        return None, "Project title cannot exceed 150 characters."

    if len(category) > 100:
        return None, "Category cannot exceed 100 characters."

    if len(short_description) > 300:
        return None, "Short description cannot exceed 300 characters."

    if len(description) > 20000:
        return None, "Description cannot exceed 20000 characters."

    if len(technologies) > 500:
        return None, "Technologies cannot exceed 500 characters."

    for field_name, value in (
        ("Image URL", image_url),
        ("Project URL", project_url),
    ):
        if len(value) > 500:
            return None, f"{field_name} cannot exceed 500 characters."

        if value and not re.match(r"^https?://", value, re.IGNORECASE):
            return None, f"{field_name} must start with http:// or https://."

    try:
        display_order = int(order_value or "0")
    except ValueError:
        return None, "Display order must be a whole number."

    if not 0 <= display_order <= 9999:
        return None, "Display order must be between 0 and 9999."

    values = {
        "title": title,
        "category": category or None,
        "short_description": short_description or None,
        "description": description or None,
        "technologies": technologies or None,
        "image_url": image_url or None,
        "project_url": project_url or None,
        "display_order": display_order,
        "is_active": 1 if _as_bool(request.form.get("is_active")) else 0,
        "is_featured": 1 if _as_bool(request.form.get("is_featured")) else 0,
    }

    return values, None


@admin_bp.route("/projects", methods=["GET", "POST"], endpoint="projects")
@login_required
def admin_projects():
    if request.method == "POST":
        values, error = _project_form_data()

        if error:
            flash(error, "error")
            return redirect(url_for("admin.projects"))

        slug = _unique_project_slug(values["title"])

        d1.run(
            """INSERT INTO projects (
                   title, slug, category, short_description, description,
                   image_url, project_url, technologies, is_featured,
                   is_active, display_order, created_at, updated_at
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            (
                values["title"],
                slug,
                values["category"],
                values["short_description"],
                values["description"],
                values["image_url"],
                values["project_url"],
                values["technologies"],
                values["is_featured"],
                values["is_active"],
                values["display_order"],
            ),
        )

        flash("Project created successfully.", "success")
        return redirect(url_for("admin.projects"))

    rows = d1.fetch_all(
        """SELECT * FROM projects
           ORDER BY display_order ASC, id DESC"""
    )

    response = make_response(
        render_template("admin/projects.html", projects=Project.from_rows(rows))
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


@admin_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def project_edit(project_id):
    existing = d1.fetch_one(
        "SELECT * FROM projects WHERE id = ?",
        (project_id,),
    )

    if existing is None:
        flash("Project not found.", "error")
        return redirect(url_for("admin.projects"))

    if request.method == "POST":
        values, error = _project_form_data()

        if error:
            flash(error, "error")
            return redirect(
                url_for("admin.project_edit", project_id=project_id)
            )

        slug = _unique_project_slug(
            values["title"],
            exclude_id=project_id,
        )

        d1.run(
            """UPDATE projects
               SET title = ?,
                   slug = ?,
                   category = ?,
                   short_description = ?,
                   description = ?,
                   image_url = ?,
                   project_url = ?,
                   technologies = ?,
                   is_featured = ?,
                   is_active = ?,
                   display_order = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                values["title"],
                slug,
                values["category"],
                values["short_description"],
                values["description"],
                values["image_url"],
                values["project_url"],
                values["technologies"],
                values["is_featured"],
                values["is_active"],
                values["display_order"],
                project_id,
            ),
        )

        flash("Project updated successfully.", "success")
        return redirect(url_for("admin.projects"))

    response = make_response(
        render_template(
            "admin/project_edit.html",
            item=Project.from_row(existing),
        )
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response


@admin_bp.route("/projects/<int:item_id>/toggle", methods=["POST"])
@login_required
def toggle_project(item_id):
    existing = d1.fetch_one(
        "SELECT id, is_active FROM projects WHERE id = ?",
        (item_id,),
    )

    if existing is None:
        flash("Project not found.", "error")
        return redirect(url_for("admin.projects"))

    new_status = 0 if _as_bool(existing.get("is_active")) else 1

    d1.run(
        """UPDATE projects
           SET is_active = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (new_status, item_id),
    )

    flash(
        "Project activated successfully."
        if new_status
        else "Project hidden successfully.",
        "success",
    )
    return redirect(url_for("admin.projects"))


@admin_bp.route("/projects/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_project(item_id):
    existing = d1.fetch_one(
        "SELECT id FROM projects WHERE id = ?",
        (item_id,),
    )

    if existing is None:
        flash("Project not found.", "error")
        return redirect(url_for("admin.projects"))

    d1.run(
        "DELETE FROM projects WHERE id = ?",
        (item_id,),
    )

    flash("Project deleted successfully.", "success")
    return redirect(url_for("admin.projects"))


# ---------------------------------------------------------------------------
# Jobs management - D1
# ---------------------------------------------------------------------------

def _unique_job_slug(title, exclude_id=None):
    base = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    base = base or "job"
    slug = base
    counter = 2

    while True:
        if exclude_id is None:
            row = d1.fetch_one(
                "SELECT id FROM jobs WHERE slug = ? LIMIT 1",
                (slug,),
            )
        else:
            row = d1.fetch_one(
                "SELECT id FROM jobs WHERE slug = ? AND id != ? LIMIT 1",
                (slug, exclude_id),
            )

        if row is None:
            return slug

        slug = f"{base}-{counter}"
        counter += 1


def _job_form_data():
    from datetime import date

    title = (request.form.get("title") or "").strip()

    if not title:
        return None, "Job title is required."

    if len(title) > 150:
        return None, "Job title cannot exceed 150 characters."

    closing_date = (request.form.get("closing_date") or "").strip() or None

    if closing_date:
        try:
            date.fromisoformat(closing_date)
        except ValueError:
            return None, "Enter a valid closing date."

    return {
        "title": title,
        "department": (request.form.get("department") or "").strip() or None,
        "location": (request.form.get("location") or "").strip() or None,
        "employment_type": (request.form.get("employment_type") or "").strip() or None,
        "experience": (request.form.get("experience") or "").strip() or None,
        "salary_range": (request.form.get("salary_range") or "").strip() or None,
        "short_description": (request.form.get("short_description") or "").strip() or None,
        "description": (request.form.get("description") or "").strip() or None,
        "requirements": (request.form.get("requirements") or "").strip() or None,
        "is_active": 1 if _as_bool(request.form.get("is_active")) else 0,
        "closing_date": closing_date,
    }, None


def _load_jobs():
    return Job.from_rows(
        d1.fetch_all("SELECT * FROM jobs ORDER BY id DESC")
    )


@admin_bp.route("/jobs", methods=["GET", "POST"], endpoint="jobs")
@login_required
def admin_jobs():
    if request.method == "POST":
        values, error = _job_form_data()

        if error:
            flash(error, "error")
        else:
            values["slug"] = _unique_job_slug(values["title"])
            d1.run(
                """
                INSERT INTO jobs (
                    title, slug, department, location, employment_type,
                    experience, salary_range, short_description, description,
                    requirements, is_active, closing_date, created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """,
                (
                    values["title"],
                    values["slug"],
                    values["department"],
                    values["location"],
                    values["employment_type"],
                    values["experience"],
                    values["salary_range"],
                    values["short_description"],
                    values["description"],
                    values["requirements"],
                    values["is_active"],
                    values["closing_date"],
                ),
            )
            flash("Job created successfully.", "success")
            return redirect(url_for("admin.jobs"))

    response = make_response(
        render_template(
            "admin/jobs.html",
            jobs=_load_jobs(),
            edit_job=None,
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@admin_bp.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
def job_edit(job_id):
    existing = d1.fetch_one(
        "SELECT * FROM jobs WHERE id = ?",
        (job_id,),
    )

    if existing is None:
        abort(404)

    job = Job.from_row(existing)

    if request.method == "POST":
        values, error = _job_form_data()

        if error:
            flash(error, "error")
        else:
            values["slug"] = _unique_job_slug(
                values["title"],
                exclude_id=job_id,
            )
            d1.run(
                """
                UPDATE jobs
                SET title = ?,
                    slug = ?,
                    department = ?,
                    location = ?,
                    employment_type = ?,
                    experience = ?,
                    salary_range = ?,
                    short_description = ?,
                    description = ?,
                    requirements = ?,
                    is_active = ?,
                    closing_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    values["title"],
                    values["slug"],
                    values["department"],
                    values["location"],
                    values["employment_type"],
                    values["experience"],
                    values["salary_range"],
                    values["short_description"],
                    values["description"],
                    values["requirements"],
                    values["is_active"],
                    values["closing_date"],
                    job_id,
                ),
            )
            flash("Job updated successfully.", "success")
            return redirect(url_for("admin.jobs"))

    response = make_response(
        render_template(
            "admin/jobs.html",
            jobs=_load_jobs(),
            edit_job=job,
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@admin_bp.post("/jobs/<int:item_id>/toggle")
@login_required
def toggle_job(item_id):
    existing = d1.fetch_one(
        "SELECT id, is_active FROM jobs WHERE id = ?",
        (item_id,),
    )

    if existing is None:
        abort(404)

    new_status = 0 if _as_bool(existing.get("is_active")) else 1

    d1.run(
        """
        UPDATE jobs
        SET is_active = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_status, item_id),
    )

    flash("Job status updated.", "success")
    return redirect(url_for("admin.jobs"))


@admin_bp.post("/jobs/<int:job_id>/delete")
@login_required
def job_delete(job_id):
    existing = d1.fetch_one(
        "SELECT id FROM jobs WHERE id = ?",
        (job_id,),
    )

    if existing is None:
        abort(404)

    application_count = d1.scalar(
        "SELECT COUNT(*) AS value FROM job_applications WHERE job_id = ?",
        (job_id,),
        default=0,
    )

    application_count = int(application_count or 0)
    if application_count > 0:
        d1.run(
            """
            UPDATE jobs
            SET is_active = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (job_id,),
        )
        flash(
            f"This job has {application_count} application(s). "
            "It has been deactivated instead of deleted. "
            "Existing applications have been preserved.",
            "warning",
        )
        return redirect(url_for("admin.jobs"))

    d1.run(
        "DELETE FROM jobs WHERE id = ?",
        (job_id,),
    )

    flash("Job deleted successfully.", "success")
    return redirect(url_for("admin.jobs"))


# ---------------------------------------------------------------------------
# Applications management - D1
# ---------------------------------------------------------------------------

@admin_bp.get("/applications")
@login_required
def applications():
    search = (request.args.get("search") or "").strip()
    status = (request.args.get("status") or "").strip()

    sql = """
        SELECT a.*, j.title AS job_title
        FROM job_applications AS a
        LEFT JOIN jobs AS j ON j.id = a.job_id
        WHERE 1 = 1
    """
    params = []

    if search:
        pattern = f"%{search}%"
        sql += """
            AND (
                a.full_name LIKE ?
                OR a.email LIKE ?
                OR a.phone LIKE ?
                OR j.title LIKE ?
            )
        """
        params.extend([pattern, pattern, pattern, pattern])

    if status:
        sql += " AND a.status = ?"
        params.append(status)

    sql += " ORDER BY a.id DESC"

    rows = d1.fetch_all(sql, tuple(params))
    application_items = []

    for row in rows:
        item = JobApplication.from_row(row)
        item.job = SimpleNamespace(title=row.get("job_title") or "Role unavailable")
        application_items.append(item)

    response = make_response(
        render_template(
            "admin/applications.html",
            applications=application_items,
            search=search,
            selected_status=status,
        )
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@admin_bp.post("/applications/<int:application_id>/update")
@login_required
def application_update(application_id):
    existing = d1.fetch_one(
        "SELECT id FROM job_applications WHERE id = ?",
        (application_id,),
    )

    if existing is None:
        abort(404)

    allowed_statuses = {
        "new",
        "reviewing",
        "shortlisted",
        "rejected",
        "hired",
    }

    status = (request.form.get("status") or "").strip()
    admin_notes = (request.form.get("admin_notes") or "").strip()

    if status not in allowed_statuses:
        flash("Invalid application status.", "error")
        return redirect(url_for("admin.applications"))

    d1.run(
        """
        UPDATE job_applications
        SET status = ?,
            admin_notes = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, admin_notes or None, application_id),
    )

    flash("Application updated successfully.", "success")
    return redirect(url_for("admin.applications"))


@admin_bp.get("/applications/<int:application_id>/resume")
@login_required
def application_resume(application_id):
    existing = d1.fetch_one(
        "SELECT resume_filename FROM job_applications WHERE id = ?",
        (application_id,),
    )

    if existing is None:
        abort(404)

    object_key = existing.get("resume_filename")
    if not object_key:
        abort(404)

    extension = object_key.rsplit(".", 1)[-1].lower()
    if extension not in _ALLOWED_RESUME_TYPES:
        abort(404)

    try:
        resume_response = _supabase_storage_request("GET", object_key)
        contents = run_sync(resume_response.arrayBuffer())
        resume_bytes = bytes(Uint8Array.new(contents))
    except (RuntimeError, JsException):
        current_app.logger.exception(
            "Supabase resume download failed for application %s",
            application_id,
        )
        abort(503, description="Resume storage is temporarily unavailable.")

    content_type = _ALLOWED_RESUME_TYPES[extension][0]
    response = Response(
        resume_bytes,
        mimetype=content_type,
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="resume.{extension}"'
    )
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# Public pages backed by D1 where applicable
# ---------------------------------------------------------------------------

@main_bp.get("/")
def index():
    services = Service.from_rows(
        d1.fetch_all(
            """SELECT * FROM services WHERE is_active = 1
               ORDER BY display_order ASC, id DESC LIMIT 6"""
        )
    )
    projects = Project.from_rows(
        d1.fetch_all(
            """SELECT * FROM projects
               WHERE is_active = 1 AND is_featured = 1
               ORDER BY display_order ASC, id DESC LIMIT 6"""
        )
    )
    if not projects:
        projects = Project.from_rows(
            d1.fetch_all(
                """SELECT * FROM projects WHERE is_active = 1
                   ORDER BY display_order ASC, id DESC LIMIT 6"""
            )
        )
    funding = d1.fetch_one(
        "SELECT value FROM site_settings WHERE key = ?", ("funding_secured",)
    )
    return render_template(
        "main/index.html",
        services=services,
        projects=projects,
        project_count=_count("SELECT COUNT(*) AS value FROM projects WHERE is_active = 1"),
        open_job_count=_count(
            """SELECT COUNT(*) AS value FROM jobs
               WHERE is_active = 1
                 AND (closing_date IS NULL OR closing_date >= date('now'))"""
        ),
        funding_secured=funding.value if funding else "$90m",
    )


@main_bp.get("/about")
def about():
    return render_template("main/about.html")


@main_bp.get("/privacy-policy")
def privacy_policy():
    return render_template("main/privacy_policy.html")


@main_bp.get("/services")
def services():
    rows = d1.fetch_all(
        """SELECT * FROM services WHERE is_active = 1
           ORDER BY display_order ASC, id DESC"""
    )
    return render_template("main/services.html", services=Service.from_rows(rows))


@main_bp.get("/projects")
def projects():
    rows = d1.fetch_all(
        """SELECT * FROM projects WHERE is_active = 1
           ORDER BY is_featured DESC, display_order ASC, id DESC"""
    )
    return render_template("main/projects.html", projects=Project.from_rows(rows))


@main_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if not all((name, email, subject, message)):
            flash("Please fill in all required fields.", "error")
            return render_template("main/contact.html"), 400
        if len(name) > 120 or len(email) > 254 or "@" not in email:
            flash("Please enter valid contact details.", "error")
            return render_template("main/contact.html"), 400
        if len(phone) > 25 or len(company) > 150 or len(subject) > 200 or len(message) > 10000:
            flash("One or more fields exceed the allowed length.", "error")
            return render_template("main/contact.html"), 400

        d1.run(
            """INSERT INTO contact_enquiries
               (name, email, phone, company, subject, message, status)
               VALUES (?, ?, ?, ?, ?, ?, 'new')""",
            (name, email, phone or None, company or None, subject, message),
        )
        flash(
            "Your enquiry has been submitted successfully. Our team will contact you soon.",
            "success",
        )
        return redirect(url_for("main.contact"))
    return render_template("main/contact.html")


@main_bp.get("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return render_template(
            "main/search.html", query="", results=[], services=[], projects=[]
        )
    if len(query) > 100:
        flash("Your search must be 100 characters or fewer.", "error")
        return render_template(
            "main/search.html", query="", results=[], services=[], projects=[]
        ), 400

    term = f"%{query}%"
    service_rows = d1.fetch_all(
        """SELECT * FROM services WHERE is_active = 1
           AND (title LIKE ? OR short_description LIKE ? OR description LIKE ?)
           ORDER BY display_order ASC, id DESC""",
        (term, term, term),
    )
    project_rows = d1.fetch_all(
        """SELECT * FROM projects WHERE is_active = 1
           AND (title LIKE ? OR category LIKE ? OR short_description LIKE ?
                OR description LIKE ? OR technologies LIKE ?)
           ORDER BY display_order ASC, id DESC""",
        (term, term, term, term, term),
    )
    services_found = Service.from_rows(service_rows)
    projects_found = Project.from_rows(project_rows)
    results = [
        {
            "title": item.title,
            "url": url_for("main.services"),
            "description": item.short_description or item.description or "",
            "category": "Service",
        }
        for item in services_found
    ]
    results.extend(
        {
            "title": item.title,
            "url": url_for("main.projects"),
            "description": item.short_description or item.description or "",
            "category": item.category or "Project",
        }
        for item in projects_found
    )
    results.sort(key=lambda item: (item["title"] or "").casefold())
    return render_template(
        "main/search.html",
        query=query,
        results=results,
        services=services_found,
        projects=projects_found,
    )


# ---------------------------------------------------------------------------
# Careers and applications - D1 and private R2 resume storage.
# ---------------------------------------------------------------------------

@careers_bp.get("/careers")
def careers():
    query = request.args.get("q", "").strip()[:100]
    if query:
        term = f"%{query}%"
        rows = d1.fetch_all(
            """SELECT * FROM jobs WHERE is_active = 1
               AND (closing_date IS NULL OR closing_date >= date('now'))
               AND (title LIKE ? OR department LIKE ? OR location LIKE ?)
               ORDER BY id DESC""",
            (term, term, term),
        )
    else:
        rows = d1.fetch_all(
            """SELECT * FROM jobs WHERE is_active = 1
               AND (closing_date IS NULL OR closing_date >= date('now'))
               ORDER BY id DESC"""
        )
    return render_template("main/careers.html", jobs=Job.from_rows(rows), query=query)


@careers_bp.get("/careers/<slug>")
def job_detail(slug):
    job = d1.fetch_one(
        "SELECT * FROM jobs WHERE slug = ? AND is_active = 1 LIMIT 1", (slug,)
    )
    if not job:
        abort(404)
    return redirect(url_for("careers.apply", slug=slug))


@careers_bp.route("/careers/<slug>/apply", methods=["GET", "POST"])
def apply(slug):
    job_row = d1.fetch_one(
        """SELECT * FROM jobs
           WHERE slug = ? AND is_active = 1
             AND (closing_date IS NULL OR closing_date >= date('now'))
           LIMIT 1""",
        (slug,),
    )
    if job_row is None:
        abort(404)

    job = Job.from_row(job_row)
    if request.method == "GET":
        return render_template("main/apply.html", job=job)

    full_name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    location = (request.form.get("location") or "").strip()
    skills = (request.form.get("skills") or "").strip()
    portfolio_url = (request.form.get("portfolio_url") or "").strip()
    cover_letter = (request.form.get("cover_letter") or "").strip()

    error = None
    if not full_name or len(full_name) > 120:
        error = "Enter your name (up to 120 characters)."
    elif (
        len(email) > 254
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        error = "Enter a valid email address."
    elif len(phone) > 30 or len(location) > 120:
        error = "Phone or location exceeds the allowed length."
    elif len(skills) > 500 or len(cover_letter) > 3000:
        error = "Skills or introduction exceeds the allowed length."
    elif len(portfolio_url) > 500:
        error = "Portfolio URL cannot exceed 500 characters."
    elif portfolio_url:
        try:
            parsed_url = urlsplit(portfolio_url)
        except ValueError:
            error = "Enter a valid HTTP or HTTPS portfolio URL."
        else:
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                error = "Enter a valid HTTP or HTTPS portfolio URL."

    if error is None and request.form.get("consent") != "yes":
        error = "Please confirm your consent before submitting."

    resume = request.files.get("resume")
    extension = (
        (resume.filename or "").rsplit(".", 1)[-1].lower()
        if resume and "." in (resume.filename or "")
        else ""
    )
    if error is None and (resume is None or not resume.filename):
        error = "Please attach your resume."
    elif error is None and extension not in _ALLOWED_RESUME_TYPES:
        error = "Resume must be a PDF, DOC, or DOCX file."

    resume_content = b""
    if error is None:
        resume_content = resume.stream.read(_MAX_RESUME_BYTES + 1)
        if not resume_content:
            error = "The selected resume file is empty."
        elif len(resume_content) > _MAX_RESUME_BYTES:
            error = "Resume files must be 5 MB or smaller."
        elif not resume_content.startswith(_ALLOWED_RESUME_TYPES[extension][1]):
            error = "The selected file does not match its file type."

    if error:
        flash(error, "error")
        return render_template("main/apply.html", job=job), 400

    object_key = f"applications/{uuid.uuid4().hex}.{extension}"
    try:
        _supabase_storage_request(
            "POST",
            object_key,
            body=resume_content,
            content_type=_ALLOWED_RESUME_TYPES[extension][0],
        )
    except RuntimeError:
        current_app.logger.exception("Supabase resume upload failed")
        flash(
            "Resume storage is temporarily unavailable. Please try again.",
            "error",
        )
        return render_template("main/apply.html", job=job), 503

    application_cover_letter = cover_letter
    if portfolio_url:
        application_cover_letter = (
            f"{application_cover_letter}\n\n" if application_cover_letter else ""
        ) + f"Portfolio / LinkedIn: {portfolio_url}"

    try:
        d1.run(
            """
            INSERT INTO job_applications (
                job_id, full_name, email, phone, current_location,
                experience, cover_letter, resume_filename, status,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                job.id,
                full_name,
                email,
                phone,
                location,
                skills or None,
                application_cover_letter or None,
                object_key,
            ),
        )
    except D1QueryError:
        try:
            _supabase_storage_request("DELETE", object_key)
        except RuntimeError:
            current_app.logger.exception(
                "Failed to clean up resume after D1 insertion failure"
            )
        raise

    flash("Your application was submitted successfully.", "success")
    return redirect(url_for("careers.careers"))


# ---------------------------------------------------------------------------
# Health, assets, and application factory
# ---------------------------------------------------------------------------


def _serve_static(filename: str):
    # Static assets are normally served directly by Cloudflare before the
    # Worker. This binding-backed fallback preserves Flask's static endpoint.
    if ".." in filename.replace("\\", "/").split("/"):
        abort(404)
    worker_env = request.environ.get("workers.env")
    assets = _get_member(worker_env, "ASSETS")
    if assets is None:
        abort(404)
    response = run_sync(
        assets.fetch(f"https://assets.local/static/{quote(filename, safe='/')}")
    )
    status = int(_get_member(response, "status", 404))
    if status >= 400:
        abort(status)
    body = run_sync(response.bytes())
    headers = {}
    response_headers = _get_member(response, "headers")
    for header in ("content-type", "cache-control", "etag", "last-modified"):
        value = _get_member(response_headers, "get", None)
        if callable(value):
            header_value = value(header)
        else:
            header_value = None
        if header_value:
            headers[header] = str(header_value)
    return Response(body, status=status, headers=headers)


def create_app() -> Flask:
    app = Flask("vrtech_d1_worker", static_folder=None)
    app.config.update(
        SECRET_KEY=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE="Lax",
        REMEMBER_COOKIE_SECURE=False,
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=3600,
        PERMANENT_SESSION_LIFETIME=8 * 60 * 60,
        MAX_CONTENT_LENGTH=_MAX_RESUME_BYTES + 128 * 1024,
    )

    app.jinja_loader = DictLoader(TEMPLATES)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "admin.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "error"

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            admin_id = int(user_id)
        except (TypeError, ValueError):
            return None
        try:
            row = d1.fetch_one(
                "SELECT * FROM admins WHERE id = ? LIMIT 1", (admin_id,)
            )
            admin = Admin.from_row(row) if row else None
            if admin is None or not admin.is_active:
                return None
            return admin
        except Exception:
            app.logger.exception("Unable to load the D1 admin session user.")
            return None

    # The existing HTML uses url_for('static', filename=...). Cloudflare
    # normally serves these assets directly from the ASSETS collection.
    app.add_url_rule(
        "/static/<path:filename>",
        endpoint="static",
        view_func=_serve_static,
        methods=["GET"],
    )

    app.register_blueprint(main_bp)
    app.register_blueprint(careers_bp)
    app.register_blueprint(admin_bp)

    @app.get("/health")
    def health():
        return jsonify({"success": True, "application": "VR Tech Solutions", "database": "Cloudflare D1"})

    @app.errorhandler(404)
    def page_not_found(error):
        try:
            return render_template("404.html"), 404
        except Exception:
            return "Page not found", 404

    @app.errorhandler(500)
    def internal_server_error(error):
        app.logger.exception("Unhandled D1 Worker application error.")
        try:
            return render_template("500.html"), 500
        except Exception:
            return "Internal server error", 500

    # Worker bindings must be read from the WSGI environ before Flask opens
    # its session, so install this middleware last.
    app.wsgi_app = WorkerEnvironmentMiddleware(app.wsgi_app, app)
    return app
