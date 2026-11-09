
"""SEO routes for Google and other search engines."""

from datetime import date
from xml.etree.ElementTree import Element, SubElement, tostring

from flask import Blueprint, Response, request, url_for

seo_bp = Blueprint("seo", __name__)

# Only include public pages that should appear in Google.
PUBLIC_ENDPOINTS = [
    "main.index",
    "main.about",
    "main.services",
    "main.projects",
    "main.careers",
    "main.contact",
    "main.privacy_policy",
]


@seo_bp.route("/sitemap.xml", methods=["GET"])
def sitemap():
    """Generate an XML sitemap of public website pages."""

    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"

    root = Element(
        "urlset",
        xmlns=namespace,
    )

    for endpoint in PUBLIC_ENDPOINTS:
        try:
            page_url = url_for(
                endpoint,
                _external=True,
                _scheme=request.scheme,
            )
        except Exception:
            continue

        url_element = SubElement(
            root,
            "url",
        )

        SubElement(
            url_element,
            "loc",
        ).text = page_url

    xml_content = tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
    )

    response = Response(
        xml_content,
        content_type="application/xml; charset=utf-8",
    )

    response.headers["Cache-Control"] = "public, max-age=3600"

    return response


@seo_bp.route("/robots.txt", methods=["GET"])
def robots():
    """Tell search engines which parts of the website they can crawl."""

    base_url = request.url_root.rstrip("/")

    robots_content = f"""User-agent: *
Allow: /

Disallow: /admin/
Disallow: /search
Disallow: /careers/*/apply

Sitemap: {base_url}/sitemap.xml
"""

    return Response(
        robots_content,
        content_type="text/plain; charset=utf-8",
    )
