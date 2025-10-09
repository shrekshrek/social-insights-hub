"""JavaScript-based signature generator for XiaoHongShu."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict

try:  # pragma: no cover - optional dependency detection
    import execjs
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    execjs = None  # type: ignore

from importlib import resources

_LOGGER = logging.getLogger(__name__)


class XhsJavascriptSignerUnavailable(RuntimeError):
    """Raised when the JS runtime for XHS signing is unavailable."""


def _load_resource(filename: str) -> str:
    package = "src.signing.resources.xhs"
    with resources.files(package).joinpath(filename).open("r", encoding="utf-8") as fp:
        return fp.read()


@dataclass(slots=True)
class _XhsJavascriptContext:
    """Holds compiled JavaScript contexts for XHS signing."""

    xs_ctx: Any
    xmns_ctx: Any

    def sign(self, uri: str, data: Dict[str, Any] | None, cookies: str) -> Dict[str, Any]:
        sign_result: Dict[str, Any] = self.xs_ctx.call("sign", uri, data, cookies)
        md5_seed = self._make_md5_paramsd(uri, data)
        x_mns = self.xmns_ctx.call("window.getMnsToken", uri, data, md5_seed)
        sign_result = {k: v for k, v in sign_result.items()}
        sign_result["x-mns"] = x_mns
        return sign_result

    @staticmethod
    def _make_md5_paramsd(api: str, data: Dict[str, Any] | None) -> str:
        data_json = ""
        if data and isinstance(data, dict):
            data_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        return hashlib.md5(data_json.encode("utf-8")).hexdigest()


_context: _XhsJavascriptContext | None = None
_context_error: str | None = None


def _ensure_context() -> _XhsJavascriptContext:
    global _context, _context_error

    if _context:
        return _context

    if _context_error:
        raise XhsJavascriptSignerUnavailable(_context_error)

    if execjs is None:
        _context_error = "PyExecJS is not installed"
        raise XhsJavascriptSignerUnavailable(_context_error)

    try:
        runtime = execjs.get()
    except execjs.RuntimeUnavailableError as exc:  # type: ignore[attr-defined]
        _context_error = f"No JavaScript runtime available: {exc}"
        raise XhsJavascriptSignerUnavailable(_context_error) from exc

    try:
        xs_source = _load_resource("xhs_xs.js")
        xmns_source = _load_resource("xhs_xmns.js")
        xs_ctx = runtime.compile(xs_source)
        xmns_ctx = runtime.compile(xmns_source)
        _context = _XhsJavascriptContext(xs_ctx=xs_ctx, xmns_ctx=xmns_ctx)
        return _context
    except Exception as exc:  # pragma: no cover - runtime specific errors
        _context_error = f"Failed to compile XHS JavaScript signer: {exc}"
        raise XhsJavascriptSignerUnavailable(_context_error) from exc


async def generate_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate signature payload for XiaoHongShu using JavaScript implementation."""

    uri = payload.get("uri")
    cookies = payload.get("cookies")
    data = payload.get("data")

    if not isinstance(uri, str) or not uri:
        raise ValueError("payload.uri is required for XHS javascript strategy")
    if not isinstance(cookies, str) or not cookies:
        raise ValueError("payload.cookies is required for XHS javascript strategy")
    if data is not None and not isinstance(data, dict):
        raise ValueError("payload.data must be a JSON object")

    context = _ensure_context()

    def _run() -> Dict[str, Any]:
        return context.sign(uri, data, cookies)

    result = await asyncio.to_thread(_run)
    # Ensure all keys are str for downstream consumers
    return {str(key): value for key, value in result.items()}


def is_available() -> bool:
    if _context is not None:
        return True
    if _context_error:
        _LOGGER.debug("javascript signer unavailable cached error: %s", _context_error)
        return False
    if execjs is None:
        _LOGGER.debug("javascript signer unavailable: execjs missing")
        return False
    try:
        execjs.get()
    except Exception:  # pragma: no cover - runtime detection
        _LOGGER.debug("javascript signer unavailable: runtime lookup failed", exc_info=True)
        return False
    return True
