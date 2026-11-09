
"""Application factory for VR Tech Solutions."""

import os

from flask import Flask
from flask_login import LoginManager
from flask_wtf import CSRFProtect

from config import Config


# =========================================================
# INITIALIZE FLASK EXTENSIONS
# =========================================================

login_manager = LoginManager()
csrf = CSRFProtect()


# =========================================================
# APPLICATION FACTORY
# =========================================================

def create_app(config_object=None):
    """Create and configure the Flask application."""

    # -----------------------------------------------------
    # CREATE FLASK APPLICATION
    # -----------------------------------------------------

    if os.environ.get("VERCEL"):
        app = Flask(
            __name__,
            instance_path="/tmp/vr_tech_solutions_instance",
            instance_relative_config=True,
        )
    else:
        app = Flask(
            __name__,
            instance_relative_config=True,
        )

    # -----------------------------------------------------
    # LOAD CONFIGURATION
    # -----------------------------------------------------

    app.config.from_object(Config)

    if config_object is not None:
        app.config.from_object(config_object)

    # -----------------------------------------------------
    # VALIDATE REQUIRED CONFIGURATION
    # -----------------------------------------------------

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY is missing. Configure it in your environment."
        )

    if not os.getenv("MONGODB_URI"):
        raise RuntimeError(
            "MONGODB_URI is missing. Configure MongoDB Atlas."
        )

    # -----------------------------------------------------
    # CREATE INSTANCE DIRECTORY
    # -----------------------------------------------------

    os.makedirs(app.instance_path, exist_ok=True)

    # -----------------------------------------------------
    # INITIALIZE FLASK EXTENSIONS
    # -----------------------------------------------------

    login_manager.init_app(app)
    csrf.init_app(app)

    # -----------------------------------------------------
    # LOGIN CONFIGURATION
    # -----------------------------------------------------

    login_manager.login_view = "admin.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "error"

    # -----------------------------------------------------
    # MONGODB CONNECTION AND INDEXES
    # -----------------------------------------------------

    from app.mongo import get_mongo_client

    try:
        get_mongo_client().admin.command("ping")

        from app.models import create_mongodb_indexes

        create_mongodb_indexes()

        app.logger.info(
            "MongoDB Atlas connected and indexes initialized."
        )

    except Exception as exc:
        app.logger.exception("MongoDB initialization failed.")

        raise RuntimeError(
            "Could not initialize MongoDB Atlas. "
            "Check MONGODB_URI and Atlas network access."
        ) from exc

    # -----------------------------------------------------
    # FLASK-LOGIN USER LOADER
    # -----------------------------------------------------

    from app.models import Admin

    @login_manager.user_loader
    def load_user(user_id):
        try:
            admin = Admin.get(user_id)

            if admin and admin.is_active:
                return admin

            return None

        except Exception:
            app.logger.exception(
                "Failed to load authenticated admin."
            )
            return None

    # -----------------------------------------------------
    # REGISTER BLUEPRINTS
    # -----------------------------------------------------

    from app.routes.main import main_bp
    from app.routes.careers import careers_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(careers_bp)

    app.register_blueprint(
        admin_bp,
        url_prefix="/admin",
    )

    # -----------------------------------------------------
    # RETURN APPLICATION
    # -----------------------------------------------------

    return app
