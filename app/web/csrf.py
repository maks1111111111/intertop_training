"""Browser-level CSRF protection for server-rendered Web routes."""

from __future__ import annotations

from urllib.parse import SplitResult, urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class SameOriginCSRFMiddleware(BaseHTTPMiddleware):
    """Reject browser cross-site writes to cookie-authenticated Web routes."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if _requires_same_origin_check(request) and not _is_same_origin(request):
            return PlainTextResponse("Forbidden", status_code=403)

        return await call_next(request)


def _requires_same_origin_check(request: Request) -> bool:
    return request.method.upper() not in _SAFE_METHODS


def _is_same_origin(request: Request) -> bool:
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if fetch_site == "cross-site":
        return False

    origin = request.headers.get("origin")
    if origin is not None:
        return _matches_request_origin(request, origin)

    referer = request.headers.get("referer")
    if referer is not None:
        return _matches_request_origin(request, referer)

    if fetch_site and fetch_site != "same-origin":
        return False

    # Non-browser clients and existing internal tests do not send browser fetch
    # metadata. Browsers provide Origin or Sec-Fetch-Site for form submissions.
    return True


def _matches_request_origin(request: Request, supplied_url: str) -> bool:
    try:
        supplied = urlsplit(supplied_url)
        expected = urlsplit(str(request.base_url))
        return _origin_tuple(supplied) == _origin_tuple(expected)
    except ValueError:
        return False


def _origin_tuple(url: SplitResult) -> tuple[str, str, int] | None:
    scheme = url.scheme.lower()
    hostname = (url.hostname or "").lower()
    if scheme not in {"http", "https"} or not hostname:
        return None

    default_port = 443 if scheme == "https" else 80
    return scheme, hostname, url.port or default_port
