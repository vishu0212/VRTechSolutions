import os

from dotenv import load_dotenv

# Load environment variables before importing the Flask app
load_dotenv()

from app import create_app

# Create the Flask application
app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))

    app.run(
        host=host,
        port=port,
        debug=app.config.get("DEBUG", False),
    )