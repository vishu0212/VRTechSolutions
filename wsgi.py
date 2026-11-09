"""WSGI entrypoint for deployment platforms."""

import os

if not os.getenv("VERCEL"):
    from dotenv import load_dotenv

    load_dotenv()

from app import create_app

app = create_app()