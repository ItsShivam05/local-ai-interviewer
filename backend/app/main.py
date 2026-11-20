"""FastAPI application factory: JSON API under /api, built React app served at /."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import Settings
from .deps import Container, build_container
from .errors import AppError
from .routers import ai, interviews, library, resumes, setup, speech, system

class SelectiveGZip:
    """Compress JSON, pages, scripts and styles for the browser; leave audio uploads/downloads untouched."""

    def __init__(self, app):
        self.plain = app
        self.gzip = GZipMiddleware(app, minimum_size=1024, compresslevel=5)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not scope["path"].startswith("/api/speech"):
            await self.gzip(scope, receive, send)
        else:
            await self.plain(scope, receive, send)


LOCAL_HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", re.I)
log = logging.getLogger("interviewer")


def _same_app(origin: str, host: str) -> bool:
    """Is this Origin the app's own page? A loopback name (localhost and 127.0.0.1 are the same machine) on the SAME port as the
    request's Host. A page served from any other localhost port belongs to some other program."""
    try:
        o = urlsplit(origin)
        o_port = o.port or (443 if o.scheme == "https" else 80)
    except ValueError:
        return False
    if o.scheme not in ("http", "https") or o.username or o.password or not LOCAL_HOST_RE.match(o.netloc):
        return False
    h = urlsplit("//" + host)
    try:
        h_port = h.port or 80
    except ValueError:
        return False
    return o_port == h_port


def create_app(settings: Optional[Settings] = None, container: Optional[Container] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs only, but keep logs quiet
    app = FastAPI(title="Local AI Interviewer", version=__version__, openapi_url="/api/openapi.json", redoc_url=None,
                  docs_url="/api/docs" if settings.api_docs else None)   # Swagger UI pulls JS/CSS from a CDN: developers opt in
    app.state.c = container or build_container(settings)

    @app.middleware("http")
    async def local_only_guard(request: Request, call_next):
        """Only this computer's own browser tab may use the API.

        * Host must be a loopback name (stops DNS rebinding).
        * A request that carries an Origin must come from THIS app: same host and port as the Host header. Another program's page on
          a different localhost port is a different site and is refused (it could otherwise end or pause an interview).
        * The browser's own Sec-Fetch-Site verdict is honoured for the API: "cross-site" and "same-site" (another port) are refused,
          so a foreign page cannot even trigger a download of the backup or a report. Requests without the header (curl, scripts,
          old browsers) are unaffected; "none" is the user typing or opening the address.
        * Responses may not be framed by another site and are never sniffed."""
        host = request.headers.get("host", "")
        if not LOCAL_HOST_RE.match(host):
            return JSONResponse({"error": {"code": "forbidden_host", "message": "Local access only."}}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and request.method not in ("GET", "HEAD", "OPTIONS"):
            if not _same_app(origin, host):
                return JSONResponse({"error": {"code": "forbidden_origin", "message": "Cross-site request blocked."}}, status_code=403)
        if request.url.path.startswith("/api/") and request.headers.get("sec-fetch-site", "same-origin").lower() not in ("same-origin", "none"):
            return JSONResponse({"error": {"code": "forbidden_origin", "message": "Cross-site request blocked."}}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")            # the app frames its own PDF preview; nobody else may frame it
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    @app.exception_handler(AppError)
    async def app_error(_: Request, e: AppError):
        return JSONResponse({"error": {"code": e.code, "message": e.message, **e.extra}}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        field = ".".join(str(x) for x in first.get("loc", ())[1:]) or "request"
        return JSONResponse({"error": {"code": "invalid_request", "message": f"Invalid {field}: {first.get('msg', 'bad value')}"}},
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, e: StarletteHTTPException):
        return JSONResponse({"error": {"code": "http_error", "message": str(e.detail)}}, status_code=e.status_code)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, e: Exception):
        log.exception("unhandled error")
        return JSONResponse({"error": {"code": "internal", "message": "Unexpected server error. See logs/backend.log."}}, status_code=500)

    for r in (system.router, library.router, interviews.router, speech.router, ai.router, setup.router, resumes.router):
        app.include_router(r)
    app.add_middleware(SelectiveGZip)

    dist: Path = settings.frontend_dist
    if dist.is_dir():
        index = dist / "index.html"

        @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)     # HEAD: uptime checks, curl -I
        def spa(path: str):
            if path.startswith("api/"):
                return JSONResponse({"error": {"code": "not_found", "message": "Unknown API route."}}, status_code=404)
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                # build output has content-hashed names: the browser may keep them for good; anything else is re-checked
                hashed = path.startswith("assets/")
                return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable" if hashed else "no-cache"})
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        def no_ui():
            return JSONResponse({"message": "Frontend not built. Run ./start.sh (builds it) or `npm run build` in frontend/."})

    return app


def app_factory() -> FastAPI:  # uvicorn --factory target
    return create_app()
