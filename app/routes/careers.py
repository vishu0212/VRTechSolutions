
"""Career and job application routes for VR Tech Solutions."""

import os
import re
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from pymongo.errors import PyMongoError
from werkzeug.utils import secure_filename

from app.models import Job, JobApplication


careers_bp = Blueprint("careers", __name__)

ALLOWED_RESUME_EXTENSIONS = {"pdf", "doc", "docx"}
MAX_RESUME_SIZE = 5 * 1024 * 1024  # 5 MB


# =========================================================
# RESUME HELPERS
# =========================================================

def allowed_resume(filename):
    """Check whether a resume uses an allowed file extension."""

    if not filename or "." not in filename:
        return False

    extension = filename.rsplit(".", 1)[1].lower()
    return extension in ALLOWED_RESUME_EXTENSIONS


def get_resume_upload_folder():
    """Create and return the private resume upload directory."""

    upload_folder = current_app.config.get(
        "RESUME_UPLOAD_FOLDER",
        os.path.join(current_app.instance_path, "resumes"),
    )

    Path(upload_folder).mkdir(parents=True, exist_ok=True)

    return upload_folder


def get_form_value(*names):
    """Support both old and new application-form field names."""

    for name in names:
        value = request.form.get(name)

        if value is not None:
            return value.strip()

    return ""


def render_application(job, status=200):
    """Render the application template with the selected job."""

    return render_template(
        "main/apply.html",
        job=job,
    ), status


def application_error(job, message, status=400):
    """Show a validation message and redisplay the form."""

    flash(message, "error")
    return render_application(job, status)


def get_active_job(slug):
    """Find an active job by its slug in MongoDB."""

    document = Job.collection().find_one({
        "slug": slug,
        "is_active": True,
    })

    return Job.from_document(document) if document else None


def job_deadline_passed(closing_date):
    """Check whether a job's closing date has passed."""

    if not closing_date:
        return False

    if isinstance(closing_date, datetime):
        closing_date = closing_date.date()

    if isinstance(closing_date, date):
        return closing_date < date.today()

    return False


def active_jobs_filter():
    """Return MongoDB filter for active, non-expired jobs."""

    today_start = datetime.combine(
        date.today(),
        time.min,
        tzinfo=timezone.utc,
    )

    return {
        "is_active": True,
        "$or": [
            {"closing_date": None},
            {"closing_date": {"$gte": today_start}},
        ],
    }


# =========================================================
# CAREERS LISTING
# =========================================================

@careers_bp.route("/careers")
def careers():
    """Display active job vacancies with optional searching."""

    query = request.args.get("q", "").strip()

    if len(query) > 100:
        flash(
            "Your job search must be 100 characters or fewer.",
            "error",
        )
        query = query[:100]

    filters = active_jobs_filter()

    if query:
        search_pattern = re.compile(
            re.escape(query),
            re.IGNORECASE,
        )

        filters["$and"] = [
            {
                "$or": [
                    {"title": search_pattern},
                    {"department": search_pattern},
                    {"location": search_pattern},
                ]
            }
        ]

    jobs = Job.all(
        filters=filters,
        sort=[("_id", -1)],
    )

    return render_template(
        "main/careers.html",
        jobs=jobs,
        query=query,
    )


# =========================================================
# JOB DETAIL
# =========================================================

@careers_bp.route("/careers/<slug>")
def job_detail(slug):
    """Redirect a vacancy URL to its application form."""

    job = get_active_job(slug)

    if not job:
        return render_template("404.html"), 404

    if job_deadline_passed(job.closing_date):
        flash(
            "The application deadline for this job has passed.",
            "error",
        )
        return redirect(url_for("careers.careers"))

    return redirect(
        url_for("careers.apply", slug=job.slug)
    )


# =========================================================
# JOB APPLICATION
# =========================================================

@careers_bp.route(
    "/careers/<slug>/apply",
    methods=["GET", "POST"],
)
def apply(slug):
    """Display the form and process job application submissions."""

    job = get_active_job(slug)

    if not job:
        return render_template("404.html"), 404

    # Do not accept applications after the closing date.
    if job_deadline_passed(job.closing_date):
        flash(
            "The application deadline for this job has passed.",
            "error",
        )
        return redirect(url_for("careers.careers"))

    if request.method == "GET":
        return render_application(job)

    # Accept existing field names and the current apply.html names.
    full_name = get_form_value("full_name", "name")
    email = get_form_value("email").lower()
    phone = get_form_value("phone")

    current_location = get_form_value(
        "current_location",
        "location",
    )

    experience = get_form_value("experience")
    skills = get_form_value("skills")
    portfolio_url = get_form_value("portfolio_url")
    cover_letter = get_form_value("cover_letter")
    consent = get_form_value("consent")

    resume = request.files.get("resume")

    # -----------------------------------------------------
    # REQUIRED FIELD VALIDATION
    # -----------------------------------------------------

    if not full_name or not email or not phone:
        return application_error(
            job,
            "Please provide your full name, email address, and phone number.",
        )

    if len(full_name) > 150:
        return application_error(
            job,
            "Name must be 150 characters or fewer.",
        )

    if (
        len(email) > 150
        or "@" not in email
        or email.startswith("@")
        or email.endswith("@")
        or "." not in email.rsplit("@", 1)[-1]
    ):
        return application_error(
            job,
            "Please enter a valid email address.",
        )

    if len(phone) > 30:
        return application_error(
            job,
            "Phone must be 30 characters or fewer.",
        )

    if len(current_location) > 150:
        return application_error(
            job,
            "Location must be 150 characters or fewer.",
        )

    if len(experience) > 100:
        return application_error(
            job,
            "Experience must be 100 characters or fewer.",
        )

    if len(skills) > 500:
        return application_error(
            job,
            "Skills must be 500 characters or fewer.",
        )

    if len(portfolio_url) > 500:
        return application_error(
            job,
            "Portfolio URL must be 500 characters or fewer.",
        )

    if portfolio_url and not portfolio_url.lower().startswith(
        ("https://", "http://")
    ):
        return application_error(
            job,
            "Portfolio URL must begin with http:// or https://.",
        )

    if len(cover_letter) > 10000:
        return application_error(
            job,
            "Cover letter must be 10,000 characters or fewer.",
        )

    if consent != "yes":
        return application_error(
            job,
            "Please confirm that your information may be used "
            "to respond to your application.",
        )

    # -----------------------------------------------------
    # RESUME VALIDATION
    # -----------------------------------------------------

    if not resume or not resume.filename:
        return application_error(
            job,
            "Please upload your resume.",
        )

    original_filename = secure_filename(resume.filename)

    if not original_filename or not allowed_resume(original_filename):
        return application_error(
            job,
            "Upload your resume as a PDF, DOC, or DOCX file.",
        )

    try:
        resume.stream.seek(0, os.SEEK_END)
        resume_size = resume.stream.tell()
        resume.stream.seek(0)

    except (OSError, AttributeError):
        return application_error(
            job,
            "We could not read the uploaded resume. Please try again.",
        )

    if resume_size == 0:
        return application_error(
            job,
            "The uploaded resume is empty.",
        )

    if resume_size > MAX_RESUME_SIZE:
        return application_error(
            job,
            "Resume size must not exceed 5 MB.",
        )

    extension = original_filename.rsplit(".", 1)[1].lower()
    stored_filename = f"{uuid.uuid4().hex}.{extension}"

    # -----------------------------------------------------
    # SUPPLEMENTAL APPLICATION DETAILS
    # -----------------------------------------------------

    supplemental_details = []

    if skills:
        supplemental_details.append(f"Skills: {skills}")

    if portfolio_url:
        supplemental_details.append(
            f"Portfolio / LinkedIn: {portfolio_url}"
        )

    stored_cover_letter = cover_letter

    if supplemental_details:
        extra_details = "\n\n".join(supplemental_details)

        if stored_cover_letter:
            stored_cover_letter = (
                f"{stored_cover_letter}\n\n{extra_details}"
            )
        else:
            stored_cover_letter = extra_details

    if len(stored_cover_letter) > 10000:
        return application_error(
            job,
            "Your introduction, skills, and portfolio details are too long "
            "when combined.",
        )

    # -----------------------------------------------------
    # SAVE RESUME AND MONGODB DOCUMENT
    # -----------------------------------------------------

    resume_path = None

    try:
        upload_folder = get_resume_upload_folder()

        resume_path = os.path.join(
            upload_folder,
            stored_filename,
        )

        resume.save(resume_path)

        application = JobApplication(
            job_id=job.id,
            full_name=full_name,
            email=email,
            phone=phone,
            current_location=current_location or None,
            experience=experience or None,
            cover_letter=stored_cover_letter or None,
            resume_filename=stored_filename,
            status="new",
        )

        application.save()

        flash(
            "Your application has been submitted successfully!",
            "success",
        )

        return redirect(url_for("careers.careers"))

    except (PyMongoError, OSError):
        # Remove the uploaded file if the database operation failed.
        if resume_path and os.path.exists(resume_path):
            try:
                os.remove(resume_path)
            except OSError:
                current_app.logger.exception(
                    "Could not remove an incomplete resume upload."
                )

        current_app.logger.exception(
            "Failed to process a job application."
        )

        flash(
            "We could not submit your application. Please try again later.",
            "error",
        )

        return render_application(job, 500)
