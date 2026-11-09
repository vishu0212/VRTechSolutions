
"""MongoDB models for VR Tech Solutions."""

from datetime import date, datetime, timezone

from bson import ObjectId
from flask_login import UserMixin
from pymongo import ASCENDING, DESCENDING
from werkzeug.security import check_password_hash, generate_password_hash

from app.mongo import get_mongo_db


# =========================================================
# COMMON HELPERS
# =========================================================

def utc_now():
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


def serialize_document(document):
    """Convert MongoDB document into a Python dictionary."""

    if not document:
        return None

    result = dict(document)
    result["id"] = str(result.pop("_id"))

    return result


def normalize_closing_date(value):
    """Convert MongoDB datetime or Python date into a Python date."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return None


def convert_dates_to_bson(data):
    """Convert Python date values into MongoDB-compatible datetimes."""

    converted = {}

    for key, value in data.items():

        if isinstance(value, datetime):
            converted[key] = value

        elif isinstance(value, date):
            converted[key] = datetime(
                value.year,
                value.month,
                value.day,
                tzinfo=timezone.utc,
            )

        else:
            converted[key] = value

    return converted


# =========================================================
# BASE MONGODB MODEL
# =========================================================

class MongoModel:

    collection_name = None

    def __init__(self, **kwargs):
        self.id = kwargs.pop("id", None)

        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def collection(cls):
        """Return the MongoDB collection."""
        return get_mongo_db()[cls.collection_name]

    @classmethod
    def get(cls, document_id):
        """Find a document using its MongoDB ObjectId."""

        if not ObjectId.is_valid(str(document_id)):
            return None

        document = cls.collection().find_one({
            "_id": ObjectId(str(document_id))
        })

        return cls.from_document(document)

    @classmethod
    def from_document(cls, document):
        """Convert MongoDB document into a model instance."""

        if not document:
            return None

        return cls(**serialize_document(document))

    @classmethod
    def all(cls, filters=None, sort=None, limit=None):
        """Return matching documents."""

        cursor = cls.collection().find(filters or {})

        if sort:
            cursor = cursor.sort(sort)

        if limit is not None:
            cursor = cursor.limit(limit)

        return [
            cls.from_document(document)
            for document in cursor
        ]

    @classmethod
    def count(cls, filters=None):
        """Count matching documents."""
        return cls.collection().count_documents(filters or {})

    def to_document(self):
        """Convert model instance into a MongoDB document."""

        data = self.__dict__.copy()
        data.pop("id", None)

        return convert_dates_to_bson(data)

    def save(self):
        """Insert a new document or update an existing document."""

        data = self.to_document()
        data["updated_at"] = utc_now()

        if self.id and ObjectId.is_valid(str(self.id)):

            self.collection().update_one(
                {"_id": ObjectId(str(self.id))},
                {"$set": data},
            )

        else:

            data.setdefault("created_at", utc_now())

            result = self.collection().insert_one(data)

            self.id = str(result.inserted_id)

        self.updated_at = data["updated_at"]

        return self

    def delete(self):
        """Delete this document."""

        if self.id and ObjectId.is_valid(str(self.id)):

            self.collection().delete_one({
                "_id": ObjectId(str(self.id))
            })

# =========================================================
# ADMIN MODEL
# =========================================================

class Admin(UserMixin, MongoModel):

    collection_name = "admins"

    # Override UserMixin's read-only is_active property.
    is_active = True

    def __init__(
        self,
        username="",
        email="",
        password_hash="",
        is_active=True,
        created_at=None,
        updated_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.username = username.strip() if username else ""
        self.email = email.strip().lower() if email else ""
        self.password_hash = password_hash
        self.is_active = bool(is_active)
        self.created_at = created_at or utc_now()
        self.updated_at = updated_at or utc_now()

    def get_id(self):
        return str(self.id)

    @property
    def is_authenticated(self):
        return bool(self.is_active and self.id)

    @property
    def is_anonymous(self):
        return False

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False

        return check_password_hash(
            self.password_hash,
            password,
        )

    @classmethod
    def find_by_username(cls, username):
        document = cls.collection().find_one({
            "username": username.strip()
        })

        return cls.from_document(document)

    @classmethod
    def find_by_email(cls, email):
        document = cls.collection().find_one({
            "email": email.strip().lower()
        })

        return cls.from_document(document)
# =========================================================
# SITE SETTINGS MODEL
# =========================================================

class SiteSetting(MongoModel):

    collection_name = "site_settings"

    def __init__(
        self,
        key="",
        value="",
        updated_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.key = key
        self.value = value
        self.updated_at = updated_at or utc_now()

    @classmethod
    def get_value(cls, key, default=None):

        document = cls.collection().find_one({
            "key": key
        })

        return document.get("value", default) if document else default

    @classmethod
    def set_value(cls, key, value):

        cls.collection().update_one(
            {"key": key},
            {
                "$set": {
                    "value": value,
                    "updated_at": utc_now(),
                }
            },
            upsert=True,
        )


# =========================================================
# SERVICE MODEL
# =========================================================

class Service(MongoModel):

    collection_name = "services"

    def __init__(
        self,
        title="",
        slug="",
        short_description="",
        description="",
        icon="fa-solid fa-code",
        image_url=None,
        is_active=True,
        display_order=0,
        created_at=None,
        updated_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.title = title
        self.slug = slug
        self.short_description = short_description
        self.description = description
        self.icon = icon
        self.image_url = image_url
        self.is_active = is_active
        self.display_order = display_order
        self.created_at = created_at or utc_now()
        self.updated_at = updated_at or utc_now()


# =========================================================
# PROJECT MODEL
# =========================================================

class Project(MongoModel):

    collection_name = "projects"

    def __init__(
        self,
        title="",
        slug="",
        category=None,
        short_description=None,
        description="",
        image_url=None,
        project_url=None,
        technologies=None,
        is_featured=False,
        is_active=True,
        display_order=0,
        created_at=None,
        updated_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.title = title
        self.slug = slug
        self.category = category
        self.short_description = short_description
        self.description = description
        self.image_url = image_url
        self.project_url = project_url
        self.technologies = technologies
        self.is_featured = is_featured
        self.is_active = is_active
        self.display_order = display_order
        self.created_at = created_at or utc_now()
        self.updated_at = updated_at or utc_now()


# =========================================================
# CONTACT ENQUIRY MODEL
# =========================================================

class ContactEnquiry(MongoModel):

    collection_name = "contact_enquiries"

    def __init__(
        self,
        name="",
        email="",
        phone=None,
        company=None,
        subject="",
        message="",
        status="new",
        admin_notes=None,
        created_at=None,
        updated_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.name = name
        self.email = email
        self.phone = phone
        self.company = company
        self.subject = subject
        self.message = message
        self.status = status
        self.admin_notes = admin_notes
        self.created_at = created_at or utc_now()
        self.updated_at = updated_at or utc_now()


# =========================================================
# JOB MODEL
# =========================================================

class Job(MongoModel):

    collection_name = "jobs"

    def __init__(
        self,
        title="",
        slug="",
        department=None,
        location=None,
        employment_type=None,
        experience=None,
        salary_range=None,
        short_description=None,
        description="",
        requirements=None,
        is_active=True,
        closing_date=None,
        created_at=None,
        updated_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.title = title
        self.slug = slug
        self.department = department
        self.location = location
        self.employment_type = employment_type
        self.experience = experience
        self.salary_range = salary_range
        self.short_description = short_description
        self.description = description
        self.requirements = requirements
        self.is_active = is_active

        # Important: MongoDB datetime becomes Python date.
        self.closing_date = normalize_closing_date(closing_date)

        self.created_at = created_at or utc_now()
        self.updated_at = updated_at or utc_now()

    @property
    def applications(self):
        return JobApplication.all(
            filters={"job_id": str(self.id)},
            sort=[("_id", DESCENDING)],
        )


# =========================================================
# JOB APPLICATION MODEL
# =========================================================

class JobApplication(MongoModel):

    collection_name = "job_applications"

    def __init__(
        self,
        job_id=None,
        full_name="",
        email="",
        phone="",
        current_location=None,
        experience=None,
        cover_letter=None,
        resume_filename="",
        status="new",
        admin_notes=None,
        created_at=None,
        updated_at=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.job_id = (
            str(job_id)
            if job_id is not None
            else None
        )

        self.full_name = full_name
        self.email = email
        self.phone = phone
        self.current_location = current_location
        self.experience = experience
        self.cover_letter = cover_letter
        self.resume_filename = resume_filename
        self.status = status
        self.admin_notes = admin_notes
        self.created_at = created_at or utc_now()
        self.updated_at = updated_at or utc_now()

    @property
    def job(self):
        return Job.get(self.job_id)


# =========================================================
# MONGODB INDEX INITIALIZATION
# =========================================================

def create_mongodb_indexes():
    """Create indexes required by the application."""

    db = get_mongo_db()

    # Admin indexes.
    db.admins.create_index(
        [("username", ASCENDING)],
        unique=True,
        name="unique_admin_username",
    )

    db.admins.create_index(
        [("email", ASCENDING)],
        unique=True,
        name="unique_admin_email",
    )

    # Service indexes.
    db.services.create_index(
        [("slug", ASCENDING)],
        unique=True,
        name="unique_service_slug",
    )

    db.services.create_index(
        [
            ("is_active", ASCENDING),
            ("display_order", ASCENDING),
        ],
        name="active_services_order",
    )

    # Project indexes.
    db.projects.create_index(
        [("slug", ASCENDING)],
        unique=True,
        name="unique_project_slug",
    )

    db.projects.create_index(
        [
            ("is_active", ASCENDING),
            ("is_featured", DESCENDING),
            ("display_order", ASCENDING),
        ],
        name="active_projects_order",
    )

    # Job indexes.
    db.jobs.create_index(
        [("slug", ASCENDING)],
        unique=True,
        name="unique_job_slug",
    )

    db.jobs.create_index(
        [
            ("is_active", ASCENDING),
            ("closing_date", ASCENDING),
        ],
        name="active_jobs_closing_date",
    )

    # Contact enquiry indexes.
    db.contact_enquiries.create_index(
        [("email", ASCENDING)],
        name="contact_email",
    )

    db.contact_enquiries.create_index(
        [
            ("status", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="contact_status_created",
    )

    # Job application indexes.
    db.job_applications.create_index(
        [("job_id", ASCENDING)],
        name="applications_job_id",
    )

    db.job_applications.create_index(
        [
            ("status", ASCENDING),
            ("created_at", DESCENDING),
        ],
        name="applications_status_created",
    )

    db.job_applications.create_index(
        [("email", ASCENDING)],
        name="applications_email",
    )
