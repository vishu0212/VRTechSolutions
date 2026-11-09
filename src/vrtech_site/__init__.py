"""VR Tech Solutions application running on Cloudflare Python Workers."""

from .app import create_app

__all__ = ["create_app"]
