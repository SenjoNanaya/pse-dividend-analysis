"""Serve the Vite production build from frontend/dist (same origin as /api/)."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse


def _dist_dir() -> Path:
    return Path(settings.BASE_DIR) / "frontend" / "dist"


def frontend_file(request, path=""):
    dist = _dist_dir().resolve()
    if not dist.is_dir():
        return HttpResponse(
            "Frontend not built. From the repo root: cd frontend && npm run build\n",
            status=503,
            content_type="text/plain",
        )

    if path:
        candidate = (dist / path).resolve()
        try:
            candidate.relative_to(dist)
        except ValueError as exc:
            raise Http404() from exc
        if candidate.is_file():
            content_type, _ = mimetypes.guess_type(str(candidate))
            return FileResponse(
                candidate.open("rb"),
                content_type=content_type or "application/octet-stream",
            )

    index = dist / "index.html"
    if not index.is_file():
        return HttpResponse(
            "frontend/dist/index.html missing. Run: cd frontend && npm run build\n",
            status=503,
            content_type="text/plain",
        )
    return FileResponse(index.open("rb"), content_type="text/html")
