
"""Public routes for VR Tech Solutions."""

import re
from datetime import date, datetime, time, timezone

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
from pymongo.errors import PyMongoError

from app.models import (
    Job,
    Project,
    Service,
    SiteSetting,
    ContactEnquiry,
)

main_bp = Blueprint("main", __name__)


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _active_jobs_filter():
    """Return MongoDB filter for active jobs that have not expired."""

    today = date.today()
    today_start = datetime.combine(
        today,
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


def _service_sort():
    """Match the previous SQL ordering."""
    return [
        ("display_order", 1),
        ("_id", -1),
    ]


def _project_sort():
    """Match the previous SQL ordering."""
    return [
        ("display_order", 1),
        ("_id", -1),
    ]


# =========================================================
# HOMEPAGE
# =========================================================

@main_bp.route("/")
def index():
    """Display homepage with active services and projects."""

    db = Service.collection().database

    project_count = db["projects"].count_documents(
        {"is_active": True}
    )

    open_job_count = db["jobs"].count_documents(
        _active_jobs_filter()
    )

    funding_secured = SiteSetting.get_value(
        "funding_secured",
        "$90m",
    )

    services = Service.all(
        filters={"is_active": True},
        sort=_service_sort(),
    )[:6]

    projects = Project.all(
        filters={
            "is_active": True,
            "is_featured": True,
        },
        sort=_project_sort(),
    )[:6]

    # Fall back to recent active projects if none are featured.
    if not projects:
        projects = Project.all(
            filters={"is_active": True},
            sort=_project_sort(),
        )[:6]

    return render_template(
        "main/index.html",
        services=services,
        projects=projects,
        project_count=project_count,
        open_job_count=open_job_count,
        funding_secured=funding_secured,
    )


# =========================================================
# ABOUT
# =========================================================

@main_bp.route("/about")
def about():
    """Display the company information page."""
    return render_template("main/about.html")


# =========================================================
# PRIVACY POLICY
# =========================================================

@main_bp.route("/privacy-policy")
def privacy_policy():
    """Display the website privacy policy."""
    return render_template("main/privacy_policy.html")


# =========================================================
# SERVICES
# =========================================================

@main_bp.route("/services")
def services():
    """Display all active services."""

    all_services = Service.all(
        filters={"is_active": True},
        sort=_service_sort(),
    )

    return render_template(
        "main/services.html",
        services=all_services,
    )


# =========================================================
# PROJECTS
# =========================================================

@main_bp.route("/projects")
def projects():
    """Display the company portfolio."""

    all_projects = Project.all(
        filters={"is_active": True},
        sort=[
            ("is_featured", -1),
            ("display_order", 1),
            ("_id", -1),
        ],
    )

    return render_template(
        "main/projects.html",
        projects=all_projects,
    )


# =========================================================
# CONTACT
# =========================================================

@main_bp.route("/contact", methods=["GET", "POST"])
def contact():
    """Display and process the contact form."""

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        company = request.form.get("company", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        # Validate required fields.
        if not all([name, email, subject, message]):
            flash("Please fill in all required fields.", "error")
            return render_template("main/contact.html"), 400

        if len(name) > 120:
            flash(
                "Name must be 120 characters or fewer.",
                "error",
            )
            return render_template("main/contact.html"), 400

        # Basic email validation.
        if (
            len(email) > 150
            or "@" not in email
            or email.startswith("@")
            or email.endswith("@")
        ):
            flash("Please enter a valid email address.", "error")
            return render_template("main/contact.html"), 400

        if len(phone) > 30 or len(company) > 150:
            flash(
                "Phone or company information is too long.",
                "error",
            )
            return render_template("main/contact.html"), 400

        if len(subject) > 200:
            flash(
                "Subject must be 200 characters or fewer.",
                "error",
            )
            return render_template("main/contact.html"), 400

        if len(message) > 10000:
            flash(
                "Your message must be 10,000 characters or fewer.",
                "error",
            )
            return render_template("main/contact.html"), 400

        enquiry = ContactEnquiry(
            name=name,
            email=email,
            phone=phone or None,
            company=company or None,
            subject=subject,
            message=message,
            status="new",
        )

        try:
            enquiry.save()

            flash(
                "Your enquiry has been submitted successfully. "
                "Our team will contact you soon.",
                "success",
            )

            return redirect(url_for("main.contact"))

        except PyMongoError:
            current_app.logger.exception(
                "Failed to save a contact enquiry."
            )

            flash(
                "We could not submit your enquiry. "
                "Please try again later.",
                "error",
            )

            return render_template("main/contact.html"), 500

    return render_template("main/contact.html")


# =========================================================
# SEARCH RESULT HELPERS
# =========================================================

def _service_result(service):
    """Convert a Service model to the structure expected by search.html."""

    description = (
        getattr(service, "short_description", None)
        or getattr(service, "description", None)
        or "Explore this service to learn more."
    )

    return {
        "title": service.title,
        "url": url_for("main.services"),
        "description": description,
        "category": "Service",
    }


def _project_result(project):
    """Convert a Project model to the structure expected by search.html."""

    description = (
        getattr(project, "short_description", None)
        or getattr(project, "description", None)
        or "Explore this project to learn more."
    )

    return {
        "title": project.title,
        "url": url_for("main.projects"),
        "description": description,
        "category": getattr(project, "category", None) or "Project",
    }


# =========================================================
# SEARCH
# =========================================================

@main_bp.route("/search")
def search():
    """Search active services and projects."""

    query = request.args.get("q", "").strip()

    if not query:
        return render_template(
            "main/search.html",
            query="",
            results=[],
            services=[],
            projects=[],
        )

    if len(query) > 100:
        flash(
            "Your search must be 100 characters or fewer.",
            "error",
        )

        return render_template(
            "main/search.html",
            query="",
            results=[],
            services=[],
            projects=[],
        ), 400

    # Escape regex special characters so search input is treated
    # as ordinary text rather than a regular expression.
    search_pattern = re.compile(
        re.escape(query),
        re.IGNORECASE,
    )

    # Search active services.
    services_found = Service.all(
        filters={
            "is_active": True,
            "$or": [
                {"title": search_pattern},
                {"short_description": search_pattern},
                {"description": search_pattern},
            ],
        },
        sort=_service_sort(),
    )

    # Search active projects.
    projects_found = Project.all(
        filters={
            "is_active": True,
            "$or": [
                {"title": search_pattern},
                {"category": search_pattern},
                {"short_description": search_pattern},
                {"description": search_pattern},
                {"technologies": search_pattern},
            ],
        },
        sort=_project_sort(),
    )

    # search.html expects one combined list of dictionaries.
    results = [
        _service_result(service)
        for service in services_found
    ]

    results.extend(
        _project_result(project)
        for project in projects_found
    )

    # Sort all matching results alphabetically.
    results.sort(
        key=lambda item: (item["title"] or "").casefold()
    )

    return render_template(
        "main/search.html",
        query=query,
        results=results,
        services=services_found,
        projects=projects_found,
    )


# =========================================================
# ERROR HANDLERS
# =========================================================

@main_bp.app_errorhandler(404)
def page_not_found(error):
    """Display the custom 404 page."""
    return render_template("404.html"), 404


@main_bp.app_errorhandler(500)
def internal_server_error(error):
    """Display the custom 500 page."""
    return render_template("500.html"), 500
