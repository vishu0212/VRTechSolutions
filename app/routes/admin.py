import os
import re
import uuid
from datetime import date
from pathlib import Path

from bson.errors import InvalidId
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from app.models import (
    Admin,
    Service,
    Project,
    ContactEnquiry,
    Job,
    JobApplication,
    SiteSetting,
)


admin_bp = Blueprint("admin", __name__)

ALLOWED_RESUME_EXTENSIONS = {"pdf", "doc", "docx"}
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


# =========================================================
# GENERAL HELPERS
# =========================================================

def get_form_value(name, default=""):
    return request.form.get(name, default).strip()


def parse_integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_boolean(value):
    return value in {"1", "true", "True", "yes", "on"}


def parse_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def save_model(model, success_message=None):
    """Save a MongoDB model and handle database errors."""
    try:
        model.save()

        if success_message:
            flash(success_message, "success")

        return True

    except PyMongoError:
        current_app.logger.exception("MongoDB save operation failed.")
        flash("A database error occurred. Please try again.", "error")
        return False

    except Exception:
        current_app.logger.exception("Unexpected model save error.")
        flash("Unable to save the record. Please try again.", "error")
        return False


def delete_model(model, success_message=None):
    """Delete a MongoDB model and handle database errors."""
    try:
        model.delete()

        if success_message:
            flash(success_message, "success")

        return True

    except PyMongoError:
        current_app.logger.exception("MongoDB delete operation failed.")
        flash("A database error occurred. Please try again.", "error")
        return False

    except Exception:
        current_app.logger.exception("Unexpected model delete error.")
        flash("Unable to delete the record.", "error")
        return False


def get_record_or_404(model, record_id):
    """Load a MongoDB record using its string ObjectId."""
    try:
        record = model.get(record_id)
    except (InvalidId, TypeError, ValueError):
        abort(404)

    if record is None:
        abort(404)

    return record


# =========================================================
# SLUG HELPERS
# =========================================================

def generate_slug(title):
    slug = "-".join(title.lower().split())

    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
    slug = "".join(char for char in slug if char in allowed)

    return slug.strip("-")


def unique_slug(model, title, record_id=None):
    base_slug = generate_slug(title) or "item"
    slug = base_slug
    counter = 2

    while True:
        existing = model.collection().find_one({"slug": slug})

        if existing is None:
            return slug

        existing_id = str(existing.get("_id", ""))

        if record_id is not None and existing_id == str(record_id):
            return slug

        slug = f"{base_slug}-{counter}"
        counter += 1


# =========================================================
# FILE UPLOAD HELPERS
# =========================================================

def save_uploaded_image(field_name="image"):
    uploaded_file = request.files.get(field_name)

    if not uploaded_file or not uploaded_file.filename:
        return None

    filename = secure_filename(uploaded_file.filename)

    if not filename or "." not in filename:
        flash("Please select a valid image file.", "error")
        return False

    extension = filename.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        flash("Images must be JPG, JPEG, PNG, or WEBP files.", "error")
        return False

    uploaded_file.stream.seek(0, os.SEEK_END)
    file_size = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0)

    if file_size <= 0 or file_size > MAX_IMAGE_SIZE:
        flash("Image must be between 1 byte and 5 MB.", "error")
        return False

    upload_folder = os.path.join(
        current_app.static_folder,
        "uploads",
        "images",
    )

    Path(upload_folder).mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}.{extension}"
    uploaded_file.save(os.path.join(upload_folder, stored_filename))

    return stored_filename


# =========================================================
# ADMIN AUTHENTICATION
# =========================================================

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard"))

    if request.method == "POST":
        username_or_email = get_form_value("username")
        password = request.form.get("password", "")

        if not username_or_email or not password:
            flash("Please enter your username/email and password.", "error")
            return render_template("admin/login.html")

        admin = Admin.find_by_username(username_or_email)

        if admin is None:
            admin = Admin.find_by_email(username_or_email.lower())

        if (
            admin
            and admin.is_active
            and check_password_hash(admin.password_hash, password)
        ):
            login_user(admin)

            next_page = request.args.get("next", "")

            # Only allow safe local redirects.
            if (
                next_page.startswith("/")
                and not next_page.startswith("//")
                and "\\" not in next_page
            ):
                return redirect(next_page)

            flash("Login successful.", "success")
            return redirect(url_for("admin.dashboard"))

        flash("Invalid username/email or password.", "error")

    return render_template("admin/login.html")


@admin_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@admin_bp.route("/")
@admin_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():

    if request.method == "POST":
        funding_secured = get_form_value("funding_secured")

        if not funding_secured:
            flash("Enter a funding amount or value.", "error")
            return redirect(url_for("admin.dashboard"))

        if len(funding_secured) > 100:
            flash("Funding value must be 100 characters or fewer.", "error")
            return redirect(url_for("admin.dashboard"))

        try:
            SiteSetting.set_value("funding_secured", funding_secured)
            flash("Homepage funding metric updated.", "success")
        except PyMongoError:
            current_app.logger.exception("Unable to update funding setting.")
            flash("Unable to update the funding metric.", "error")

        return redirect(url_for("admin.dashboard"))

    funding_secured = SiteSetting.get_value(
        "funding_secured",
        "$90m",
    )

    stats = {
        "services": Service.count({}),
        "active_services": Service.count({"is_active": True}),
        "projects": Project.count({}),
        "active_projects": Project.count({"is_active": True}),
        "enquiries": ContactEnquiry.count({}),
        "new_enquiries": ContactEnquiry.count({"status": "new"}),
        "jobs": Job.count({}),
        "active_jobs": Job.count({"is_active": True}),
        "applications": JobApplication.count({}),
        "new_applications": JobApplication.count({"status": "new"}),
    }

    recent_enquiries = ContactEnquiry.all(
        sort=[("created_at", -1)],
        limit=5,
    )

    recent_applications = JobApplication.all(
        sort=[("created_at", -1)],
        limit=5,
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


# =========================================================
# SERVICE MANAGEMENT
# =========================================================

@admin_bp.route("/services", methods=["GET", "POST"])
@login_required
def services():

    if request.method == "POST":
        title = get_form_value("title")

        if not title:
            flash("Service title is required.", "error")
            return redirect(url_for("admin.services"))

        if len(title) > 150:
            flash("Service title must be 150 characters or fewer.", "error")
            return redirect(url_for("admin.services"))

        uploaded_image = save_uploaded_image()

        if uploaded_image is False:
            return redirect(url_for("admin.services"))

        image_url = get_form_value("image_url")

        if uploaded_image:
            image_url = f"/static/uploads/images/{uploaded_image}"

        service = Service(
            title=title,
            slug=unique_slug(Service, title),
            short_description=get_form_value("short_description"),
            description=get_form_value("description"),
            icon=get_form_value("icon"),
            image_url=image_url,
            is_active=parse_boolean(request.form.get("is_active")),
            display_order=parse_integer(
                request.form.get("display_order")
            ),
        )

        save_model(service, "Service created successfully.")
        return redirect(url_for("admin.services"))

    all_services = Service.all(
        sort=[("display_order", 1), ("created_at", -1)]
    )

    return render_template(
        "admin/services.html",
        services=all_services,
    )


@admin_bp.route("/services/<item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_service(item_id):

    service = get_record_or_404(Service, item_id)

    if request.method == "POST":
        title = get_form_value("title")

        if not title:
            flash("Service title is required.", "error")
            return render_template(
                "admin/service_edit.html",
                service=service,
            )

        if len(title) > 150:
            flash("Service title must be 150 characters or fewer.", "error")
            return render_template(
                "admin/service_edit.html",
                service=service,
            )

        uploaded_image = save_uploaded_image()

        if uploaded_image is False:
            return render_template(
                "admin/service_edit.html",
                service=service,
            )

        service.title = title
        service.slug = unique_slug(Service, title, service.id)
        service.short_description = get_form_value("short_description")
        service.description = get_form_value("description")
        service.icon = get_form_value("icon")
        service.is_active = parse_boolean(request.form.get("is_active"))
        service.display_order = parse_integer(
            request.form.get("display_order")
        )

        if uploaded_image:
            service.image_url = f"/static/uploads/images/{uploaded_image}"
        else:
            service.image_url = get_form_value("image_url")

        if save_model(service, "Service updated successfully."):
            return redirect(url_for("admin.services"))

    return render_template(
        "admin/service_edit.html",
        service=service,
    )


# FIX: This endpoint is required by admin/services.html.
@admin_bp.route("/services/<item_id>/toggle", methods=["POST"])
@login_required
def toggle_service(item_id):

    service = get_record_or_404(Service, item_id)

    service.is_active = not service.is_active

    message = (
        "Service activated."
        if service.is_active
        else "Service deactivated."
    )

    save_model(service, message)

    return redirect(url_for("admin.services"))


@admin_bp.route("/services/<item_id>/delete", methods=["POST"])
@login_required
def delete_service(item_id):

    service = get_record_or_404(Service, item_id)

    delete_model(service, "Service deleted successfully.")

    return redirect(url_for("admin.services"))


# =========================================================
# PROJECT MANAGEMENT
# =========================================================

@admin_bp.route("/projects", methods=["GET", "POST"])
@login_required
def projects():

    if request.method == "POST":
        title = get_form_value("title")

        if not title:
            flash("Project title is required.", "error")
            return redirect(url_for("admin.projects"))

        if len(title) > 150:
            flash("Project title must be 150 characters or fewer.", "error")
            return redirect(url_for("admin.projects"))

        uploaded_image = save_uploaded_image()

        if uploaded_image is False:
            return redirect(url_for("admin.projects"))

        image_url = get_form_value("image_url")

        if uploaded_image:
            image_url = f"/static/uploads/images/{uploaded_image}"

        project = Project(
            title=title,
            slug=unique_slug(Project, title),
            category=get_form_value("category"),
            short_description=get_form_value("short_description"),
            description=get_form_value("description"),
            image_url=image_url,
            project_url=get_form_value("project_url"),
            technologies=get_form_value("technologies"),
            is_featured=parse_boolean(request.form.get("is_featured")),
            is_active=parse_boolean(request.form.get("is_active")),
            display_order=parse_integer(
                request.form.get("display_order")
            ),
        )

        save_model(project, "Project created successfully.")
        return redirect(url_for("admin.projects"))

    all_projects = Project.all(
        sort=[("display_order", 1), ("created_at", -1)]
    )

    return render_template(
        "admin/projects.html",
        projects=all_projects,
    )


@admin_bp.route("/projects/<project_id>/edit", methods=["GET", "POST"])
@login_required
def project_edit(project_id):

    project = get_record_or_404(Project, project_id)

    if request.method == "POST":
        title = get_form_value("title")

        if not title:
            flash("Project title is required.", "error")
            return redirect(url_for("admin.projects"))

        if len(title) > 150:
            flash("Project title must be 150 characters or fewer.", "error")
            return redirect(url_for("admin.projects"))

        uploaded_image = save_uploaded_image()

        if uploaded_image is False:
            return redirect(url_for("admin.projects"))

        project.title = title
        project.slug = unique_slug(Project, title, project.id)
        project.category = get_form_value("category")
        project.short_description = get_form_value("short_description")
        project.description = get_form_value("description")
        project.project_url = get_form_value("project_url")
        project.technologies = get_form_value("technologies")
        project.is_featured = parse_boolean(
            request.form.get("is_featured")
        )
        project.is_active = parse_boolean(
            request.form.get("is_active")
        )
        project.display_order = parse_integer(
            request.form.get("display_order")
        )

        if uploaded_image:
            project.image_url = f"/static/uploads/images/{uploaded_image}"
        else:
            project.image_url = get_form_value("image_url")

        save_model(project, "Project updated successfully.")
        return redirect(url_for("admin.projects"))

    all_projects = Project.all(sort=[("created_at", -1)])

    return render_template(
        "admin/projects.html",
        projects=all_projects,
        edit_project=project,
    )


@admin_bp.route("/projects/<item_id>/toggle", methods=["POST"])
@login_required
def toggle_project(item_id):

    project = get_record_or_404(Project, item_id)
    project.is_active = not project.is_active

    message = (
        "Project activated."
        if project.is_active
        else "Project hidden."
    )

    save_model(project, message)

    return redirect(url_for("admin.projects"))


@admin_bp.route("/projects/<item_id>/delete", methods=["POST"])
@login_required
def delete_project(item_id):

    project = get_record_or_404(Project, item_id)

    delete_model(project, "Project deleted successfully.")

    return redirect(url_for("admin.projects"))


# =========================================================
# CONTACT ENQUIRIES
# =========================================================

ENQUIRY_STATUS_ALIASES = {
    "new": "new",
    "pending": "new",
    "read": "read",
    "in_progress": "read",
    "contacted": "replied",
    "replied": "replied",
    "resolved": "closed",
    "closed": "closed",
}


@admin_bp.route("/enquiries", methods=["GET"])
@login_required
def enquiries():

    search = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "").strip()

    filters = {}

    if search:
        pattern = re.compile(re.escape(search), re.IGNORECASE)

        filters["$or"] = [
            {"name": pattern},
            {"email": pattern},
            {"subject": pattern},
            {"company": pattern},
        ]

    if status in {"new", "read", "replied", "closed"}:
        filters["status"] = status

    all_enquiries = ContactEnquiry.all(
        filters=filters,
        sort=[("created_at", -1)],
    )

    return render_template(
        "admin/enquiries.html",
        enquiries=all_enquiries,
        search=search,
        selected_status=status,
    )


@admin_bp.route("/enquiries/<item_id>/status", methods=["POST"])
@login_required
def enquiry_status(item_id):

    enquiry = get_record_or_404(ContactEnquiry, item_id)

    submitted_status = get_form_value("status").lower()
    status = ENQUIRY_STATUS_ALIASES.get(submitted_status)
    if status is None:
        current_app.logger.warning(
            "Invalid enquiry status submitted: %r",
            submitted_status,
        )
        flash("Invalid enquiry status.", "error")
        return redirect(url_for("admin.enquiries"))

    enquiry.status = status
    if "admin_notes" in request.form:
        enquiry.admin_notes = get_form_value("admin_notes")

    save_model(enquiry, "Enquiry status updated successfully.")

    return redirect(url_for("admin.enquiries"))


@admin_bp.route("/enquiries/<enquiry_id>/update", methods=["POST"])
@login_required
def enquiry_update(enquiry_id):

    enquiry = get_record_or_404(ContactEnquiry, enquiry_id)

    status = None
    if "status" in request.form:
        submitted_status = get_form_value("status").lower()
        status = ENQUIRY_STATUS_ALIASES.get(submitted_status)
        if status is None:
            current_app.logger.warning(
                "Invalid enquiry status submitted: %r",
                submitted_status,
            )
            flash("Invalid enquiry status.", "error")
            return redirect(url_for("admin.enquiries"))

    enquiry.admin_notes = get_form_value("admin_notes")
    if status is not None:
        enquiry.status = status

    save_model(enquiry, "Enquiry updated successfully.")

    return redirect(url_for("admin.enquiries"))


@admin_bp.route("/enquiries/<enquiry_id>/delete", methods=["POST"])
@login_required
def enquiry_delete(enquiry_id):

    enquiry = get_record_or_404(ContactEnquiry, enquiry_id)

    delete_model(enquiry, "Enquiry deleted successfully.")

    return redirect(url_for("admin.enquiries"))


# =========================================================
# JOB VACANCY MANAGEMENT
# =========================================================

@admin_bp.route("/jobs", methods=["GET", "POST"])
@login_required
def jobs():

    if request.method == "POST":
        title = get_form_value("title")

        if not title:
            flash("Job title is required.", "error")
            return redirect(url_for("admin.jobs"))

        if len(title) > 150:
            flash("Job title must be 150 characters or fewer.", "error")
            return redirect(url_for("admin.jobs"))

        job = Job(
            title=title,
            slug=unique_slug(Job, title),
            department=get_form_value("department"),
            location=get_form_value("location"),
            employment_type=get_form_value("employment_type"),
            experience=get_form_value("experience"),
            salary_range=get_form_value("salary_range"),
            short_description=get_form_value("short_description"),
            description=get_form_value("description"),
            requirements=get_form_value("requirements"),
            is_active=parse_boolean(request.form.get("is_active")),
            closing_date=parse_date(request.form.get("closing_date")),
        )

        save_model(job, "Job vacancy created successfully.")

        return redirect(url_for("admin.jobs"))

    all_jobs = Job.all(sort=[("created_at", -1)])

    return render_template(
        "admin/jobs.html",
        jobs=all_jobs,
    )


@admin_bp.route("/jobs/<job_id>/edit", methods=["GET", "POST"])
@login_required
def job_edit(job_id):

    job = get_record_or_404(Job, job_id)

    if request.method == "POST":
        title = get_form_value("title")

        if not title:
            flash("Job title is required.", "error")
            return redirect(url_for("admin.jobs"))

        if len(title) > 150:
            flash("Job title must be 150 characters or fewer.", "error")
            return redirect(url_for("admin.jobs"))

        closing_date_value = get_form_value("closing_date")
        closing_date = parse_date(closing_date_value)

        if closing_date_value and closing_date is None:
            flash("Please enter a valid closing date.", "error")
            return redirect(url_for("admin.jobs"))

        job.title = title
        job.slug = unique_slug(Job, title, job.id)
        job.department = get_form_value("department")
        job.location = get_form_value("location")
        job.employment_type = get_form_value("employment_type")
        job.experience = get_form_value("experience")
        job.salary_range = get_form_value("salary_range")
        job.short_description = get_form_value("short_description")
        job.description = get_form_value("description")
        job.requirements = get_form_value("requirements")
        job.is_active = parse_boolean(request.form.get("is_active"))
        job.closing_date = closing_date

        save_model(job, "Job vacancy updated successfully.")

        return redirect(url_for("admin.jobs"))

    return render_template(
        "admin/jobs.html",
        jobs=Job.all(sort=[("created_at", -1)]),
        edit_job=job,
    )


@admin_bp.route("/jobs/<item_id>/toggle", methods=["POST"])
@login_required
def toggle_job(item_id):

    job = get_record_or_404(Job, item_id)
    job.is_active = not job.is_active

    message = (
        "Job listing reopened."
        if job.is_active
        else "Job listing closed."
    )

    save_model(job, message)

    return redirect(url_for("admin.jobs"))


@admin_bp.route("/jobs/<job_id>/delete", methods=["POST"])
@login_required
def job_delete(job_id):

    job = get_record_or_404(Job, job_id)

    # Preserve submitted applications.
    if job.applications:
        flash(
            "This job has applications. Deactivate it instead of deleting it.",
            "error",
        )
        return redirect(url_for("admin.jobs"))

    delete_model(job, "Job vacancy deleted successfully.")

    return redirect(url_for("admin.jobs"))


# =========================================================
# JOB APPLICATION MANAGEMENT
# =========================================================

@admin_bp.route("/applications", methods=["GET"])
@login_required
def applications():

    status = request.args.get("status", "").strip()
    search = request.args.get("q", "").strip()[:100]

    filters = {}

    if status in {
        "new",
        "reviewing",
        "shortlisted",
        "rejected",
        "hired",
    }:
        filters["status"] = status

    if search:
        pattern = re.compile(re.escape(search), re.IGNORECASE)

        search_filter = {
            "$or": [
                {"full_name": pattern},
                {"email": pattern},
                {"phone": pattern},
            ]
        }

        if filters:
            filters = {"$and": [filters, search_filter]}
        else:
            filters = search_filter

    all_applications = JobApplication.all(
        filters=filters,
        sort=[("created_at", -1)],
    )

    return render_template(
        "admin/applications.html",
        applications=all_applications,
        selected_status=status,
        search=search,
    )


@admin_bp.route("/applications/<application_id>/update", methods=["POST"])
@login_required
def application_update(application_id):

    application = get_record_or_404(
        JobApplication,
        application_id,
    )

    status = get_form_value("status")

    allowed_statuses = {
        "new",
        "reviewing",
        "shortlisted",
        "rejected",
        "hired",
    }

    if status not in allowed_statuses:
        flash("Invalid application status.", "error")
        return redirect(url_for("admin.applications"))

    application.status = status
    application.admin_notes = get_form_value("admin_notes")

    save_model(application, "Application updated successfully.")

    return redirect(url_for("admin.applications"))


@admin_bp.route("/applications/<application_id>/delete", methods=["POST"])
@login_required
def application_delete(application_id):

    application = get_record_or_404(
        JobApplication,
        application_id,
    )
    resume_filename = application.resume_filename

    if not delete_model(
        application,
        "Applicant application deleted successfully.",
    ):
        return redirect(url_for("admin.applications"))

    if (
        resume_filename
        and secure_filename(resume_filename) == resume_filename
        and "." in resume_filename
        and resume_filename.rsplit(".", 1)[1].lower()
        in ALLOWED_RESUME_EXTENSIONS
    ):
        upload_folder = current_app.config.get(
            "RESUME_UPLOAD_FOLDER",
            os.path.join(current_app.instance_path, "resumes"),
        )
        resume_path = Path(upload_folder) / resume_filename

        try:
            if resume_path.is_file():
                resume_path.unlink()
        except OSError:
            current_app.logger.exception(
                "Unable to delete resume file for application %s",
                application_id,
            )
            flash(
                "Application deleted, but its resume file could not be removed.",
                "warning",
            )

    return redirect(url_for("admin.applications"))


@admin_bp.route("/applications/<application_id>/resume", methods=["GET"])
@login_required
def application_resume(application_id):

    application = get_record_or_404(
        JobApplication,
        application_id,
    )

    filename = application.resume_filename

    if (
        not filename
        or secure_filename(filename) != filename
        or "." not in filename
        or filename.rsplit(".", 1)[1].lower()
        not in ALLOWED_RESUME_EXTENSIONS
    ):
        abort(404)

    upload_folder = current_app.config.get(
        "RESUME_UPLOAD_FOLDER",
        os.path.join(current_app.instance_path, "resumes"),
    )

    file_path = os.path.join(upload_folder, filename)

    if not os.path.isfile(file_path):
        abort(404)

    is_pdf = filename.rsplit(".", 1)[1].lower() == "pdf"

    response = send_from_directory(
        upload_folder,
        filename,
        as_attachment=not is_pdf,
        download_name=filename,
    )

    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"

    return response