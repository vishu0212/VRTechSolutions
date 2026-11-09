"""Cloudflare Worker entry point for VR Tech Solutions."""

from workers import WorkerEntrypoint, wsgi

from vrtech_site.app import create_app

app = create_app()


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        return await wsgi.fetch(app, request, self.env)