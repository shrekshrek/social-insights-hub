"""JavaScript-based signature generator for XiaoHongShu."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import logging
import random
import urllib.parse
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

    def sign(
        self, uri: str, data: Dict[str, Any] | None, cookies: str
    ) -> Dict[str, Any]:
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

    # Default b1 value from MediaCrawlerPro-SignSrv (hardcoded localStorage b1)
    DEFAULT_B1 = "I38rHdgsjopgIvesdVwgIC+oIELmBZ5e3VwXLgFTIxS3bqwErFeexd0ekncAzMFYnqthIhJeSnMDKutRI3KsYorWHPtGrbV0P9WfIi/eWc6eYqtyQApPI37ekmR1QL+5Ii6sdnoeSfqYHqwl2qt5B0DoIvMzOZQqZVw7IxOeTqwr4qtiIkrOIi/skccxICLdI3Oe0utl2ADZsLveDSKsSPw5IEvsiutJOqw8BVwfPpdeTDWOIx4VIiu6ZPwbPut5IvlaLbgs3qtxIxes1VwHIkumIkIyejgsY/WTge7sjutKrZgedWI9gfKeYWZGI36eWPwyIEJefut0ocVAPBLLI3Aeiqt3cZ7sVom4IESyIhEqQd4AICY24F4gIiifpVwAICZVJo3sWWJs1qwiIvdef97e0ekKIi/e1piS8qwUIE7s1fds6WAeiVwqed5sdut3IxILbd6sdqtDbgKs0PwgIv8aI3z5rqwGBVtwzfTsKD7sdBdskut+Iioed/As1SiiIkKs0F6s3nVuIkge1Pt0IkVkwPwwNVtMI3/e1qtdIkKs1VwVIEesdutA+qwKsuw7IvrRIxDgJfIj2IJexVtVIhiKIi6eDVw/bz4zLadsYjmfIkWo4VtPmVw5IvAe3qtk+LJeTl5sTSEyIEJekdgs3PtsnPwqI35sSPt0Ih/sV04TIk0ejjNsfqw7Iv3sVut04B8qIkWyIvKsxFOekzNsdAKsYPtKIiMFI3MurVtKIvzjIh6s6lFut//sWqtaI3IYbuwl"

    uri = payload.get("uri")
    cookies = payload.get("cookies")
    data = payload.get("data")
    b1 = payload.get("b1", "") or DEFAULT_B1  # Use default if empty

    if not isinstance(uri, str) or not uri:
        raise ValueError("payload.uri is required for XHS javascript strategy")
    if not isinstance(cookies, str) or not cookies:
        raise ValueError("payload.cookies is required for XHS javascript strategy")
    if data is not None and not isinstance(data, dict):
        raise ValueError("payload.data must be a JSON object")

    context = _ensure_context()

    def _run() -> Dict[str, Any]:
        return context.sign(uri, data, cookies)

    # Step 1: Get primary signature from JS
    primary_sig = await asyncio.to_thread(_run)

    # Step 2: Extract a1 from cookies
    a1 = ""
    for cookie_part in cookies.split(";"):
        cookie_part = cookie_part.strip()
        if cookie_part.startswith("a1="):
            a1 = cookie_part.split("=", 1)[1]
            break

    # Log b1 value for debugging
    _LOGGER.info(f"[XHS Signature] a1={a1[:20] if a1 else '(empty)'}..., b1={'(有值)' if b1 else '(空)'} (长度: {len(b1) if b1 else 0})")

    # Step 3: Apply secondary signature to generate x-s-common
    final_sig = apply_secondary_signature(
        x_s=primary_sig.get("x-s", ""),
        x_t=str(primary_sig.get("x-t", "")),
        a1=a1,
        b1=b1,
    )

    # Step 4: Add x-mns from primary signature (important!)
    # Only add if x-mns exists and is not empty
    x_mns_value = primary_sig.get("x-mns", "")
    if x_mns_value:
        final_sig["x-mns"] = x_mns_value
    else:
        _LOGGER.warning("[XHS Signature] x-mns is empty or missing from primary signature")

    # Ensure all keys are str for downstream consumers
    return {str(key): value for key, value in final_sig.items()}


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
        _LOGGER.debug(
            "javascript signer unavailable: runtime lookup failed", exc_info=True
        )
        return False
    return True


# ============================================================================
# Secondary signature functions (from MediaCrawler project)
# ============================================================================

# Custom base64 lookup table for XHS
_XHS_LOOKUP = [
    "Z",
    "m",
    "s",
    "e",
    "r",
    "b",
    "B",
    "o",
    "H",
    "Q",
    "t",
    "N",
    "P",
    "+",
    "w",
    "O",
    "c",
    "z",
    "a",
    "/",
    "L",
    "p",
    "n",
    "g",
    "G",
    "8",
    "y",
    "J",
    "q",
    "4",
    "2",
    "K",
    "W",
    "Y",
    "j",
    "0",
    "D",
    "S",
    "f",
    "d",
    "i",
    "k",
    "x",
    "3",
    "V",
    "T",
    "1",
    "6",
    "I",
    "l",
    "U",
    "A",
    "F",
    "M",
    "9",
    "7",
    "h",
    "E",
    "C",
    "v",
    "u",
    "R",
    "X",
    "5",
]


def _mrc(e: str) -> int:
    """CRC32-like checksum function for XHS."""
    ie = [
        0,
        1996959894,
        3993919788,
        2567524794,
        124634137,
        1886057615,
        3915621685,
        2657392035,
        249268274,
        2044508324,
        3772115230,
        2547177864,
        162941995,
        2125561021,
        3887607047,
        2428444049,
        498536548,
        1789927666,
        4089016648,
        2227061214,
        450548861,
        1843258603,
        4107580753,
        2211677639,
        325883990,
        1684777152,
        4251122042,
        2321926636,
        335633487,
        1661365465,
        4195302755,
        2366115317,
        997073096,
        1281953886,
        3579855332,
        2724688242,
        1006888145,
        1258607687,
        3524101629,
        2768942443,
        901097722,
        1119000684,
        3686517206,
        2898065728,
        853044451,
        1172266101,
        3705015759,
        2882616665,
        651767980,
        1373503546,
        3369554304,
        3218104598,
        565507253,
        1454621731,
        3485111705,
        3099436303,
        671266974,
        1594198024,
        3322730930,
        2970347812,
        795835527,
        1483230225,
        3244367275,
        3060149565,
        1994146192,
        31158534,
        2563907772,
        4023717930,
        1907459465,
        112637215,
        2680153253,
        3904427059,
        2013776290,
        251722036,
        2517215374,
        3775830040,
        2137656763,
        141376813,
        2439277719,
        3865271297,
        1802195444,
        476864866,
        2238001368,
        4066508878,
        1812370925,
        453092731,
        2181625025,
        4111451223,
        1706088902,
        314042704,
        2344532202,
        4240017532,
        1658658271,
        366619977,
        2362670323,
        4224994405,
        1303535960,
        984961486,
        2747007092,
        3569037538,
        1256170817,
        1037604311,
        2765210733,
        3554079995,
        1131014506,
        879679996,
        2909243462,
        3663771856,
        1141124467,
        855842277,
        2852801631,
        3708648649,
        1342533948,
        654459306,
        3188396048,
        3373015174,
        1466479909,
        544179635,
        3110523913,
        3462522015,
        1591671054,
        702138776,
        2966460450,
        3352799412,
        1504918807,
        783551873,
        3082640443,
        3233442989,
        3988292384,
        2596254646,
        62317068,
        1957810842,
        3939845945,
        2647816111,
        81470997,
        1943803523,
        3814918930,
        2489596804,
        225274430,
        2053790376,
        3826175755,
        2466906013,
        167816743,
        2097651377,
        4027552580,
        2265490386,
        503444072,
        1762050814,
        4150417245,
        2154129355,
        426522225,
        1852507879,
        4275313526,
        2312317920,
        282753626,
        1742555852,
        4189708143,
        2394877945,
        397917763,
        1622183637,
        3604390888,
        2714866558,
        953729732,
        1340076626,
        3518719985,
        2797360999,
        1068828381,
        1219638859,
        3624741850,
        2936675148,
        906185462,
        1090812512,
        3747672003,
        2825379669,
        829329135,
        1181335161,
        3412177804,
        3160834842,
        628085408,
        1382605366,
        3423369109,
        3138078467,
        570562233,
        1426400815,
        3317316542,
        2998733608,
        733239954,
        1555261956,
        3268935591,
        3050360625,
        752459403,
        1541320221,
        2607071920,
        3965973030,
        1969922972,
        40735498,
        2617837225,
        3943577151,
        1913087877,
        83908371,
        2512341634,
        3803740692,
        2075208622,
        213261112,
        2463272603,
        3855990285,
        2094854071,
        198958881,
        2262029012,
        4057260610,
        1759359992,
        534414190,
        2176718541,
        4139329115,
        1873836001,
        414664567,
        2282248934,
        4279200368,
        1711684554,
        285281116,
        2405801727,
        4167216745,
        1634467795,
        376229701,
        2685067896,
        3608007406,
        1308918612,
        956543938,
        2808555105,
        3495958263,
        1231636301,
        1047427035,
        2932959818,
        3654703836,
        1088359270,
        936918000,
        2847714899,
        3736837829,
        1202900863,
        817233897,
        3183342108,
        3401237130,
        1404277552,
        615818150,
        3134207493,
        3453421203,
        1423857449,
        601450431,
        3009837614,
        3294710456,
        1567103746,
        711928724,
        3020668471,
        3272380065,
        1510334235,
        755167117,
    ]
    o = -1

    def right_without_sign(num: int, bit: int = 0) -> int:
        val = ctypes.c_uint32(num).value >> bit
        MAX32INT = 4294967295
        return (val + (MAX32INT + 1)) % (2 * (MAX32INT + 1)) - MAX32INT - 1

    for n in range(len(e)):
        o = ie[(o & 255) ^ ord(e[n])] ^ right_without_sign(o, 8)
    return o ^ -1 ^ 3988292384


def _triplet_to_base64(e: int) -> str:
    """Convert a 24-bit triplet to 4 base64 characters."""
    return (
        _XHS_LOOKUP[63 & (e >> 18)]
        + _XHS_LOOKUP[63 & (e >> 12)]
        + _XHS_LOOKUP[(e >> 6) & 63]
        + _XHS_LOOKUP[e & 63]
    )


def _encode_chunk(e: list, t: int, r: int) -> str:
    """Encode a chunk of bytes to base64."""
    m = []
    for b in range(t, r, 3):
        n = (16711680 & (e[b] << 16)) + ((e[b + 1] << 8) & 65280) + (e[b + 2] & 255)
        m.append(_triplet_to_base64(n))
    return "".join(m)


def _b64_encode(e: list) -> str:
    """Custom base64 encoding using XHS lookup table."""
    P = len(e)
    W = P % 3
    U = []
    z = 16383
    H = 0
    Z = P - W
    while H < Z:
        U.append(_encode_chunk(e, H, Z if H + z > Z else H + z))
        H += z
    if 1 == W:
        F = e[P - 1]
        U.append(_XHS_LOOKUP[F >> 2] + _XHS_LOOKUP[(F << 4) & 63] + "==")
    elif 2 == W:
        F = (e[P - 2] << 8) + e[P - 1]
        U.append(
            _XHS_LOOKUP[F >> 10]
            + _XHS_LOOKUP[63 & (F >> 4)]
            + _XHS_LOOKUP[(F << 2) & 63]
            + "="
        )
    return "".join(U)


def _encode_utf8(e: str) -> list:
    """Encode string to UTF-8 byte array."""
    b = []
    m = urllib.parse.quote(e, safe="~()*!.'")
    w = 0
    while w < len(m):
        T = m[w]
        if T == "%":
            E = m[w + 1] + m[w + 2]
            S = int(E, 16)
            b.append(S)
            w += 2
        else:
            b.append(ord(T[0]))
        w += 1
    return b


def _get_b3_trace_id() -> str:
    """Generate a random b3 trace ID."""
    re = "abcdef0123456789"
    return "".join(random.choice(re) for _ in range(16))


def apply_secondary_signature(
    x_s: str, x_t: str, a1: str = "", b1: str = ""
) -> Dict[str, str]:
    """
    Apply secondary signature to generate x-s-common header.

    This is the critical second layer of signing that XHS requires.
    Based on MediaCrawler project's sign() function.

    Args:
        x_s: X-s value from primary signature
        x_t: X-t value from primary signature
        a1: Cookie a1 value
        b1: LocalStorage b1 value

    Returns:
        Dict with x-s, x-t, x-s-common, and x-b3-traceid
    """
    common = {
        "s0": 3,  # getPlatformCode
        "s1": "",
        "x0": "1",  # localStorage.getItem("b1b1")
        "x1": "3.7.8-2",  # version
        "x2": "Mac OS",
        "x3": "xhs-pc-web",
        "x4": "4.27.2",
        "x5": a1,  # cookie of a1
        "x6": x_t,
        "x7": x_s,
        "x8": b1,  # localStorage.getItem("b1")
        "x9": _mrc(x_t + x_s + b1),
        "x10": 154,  # getSigCount
    }

    encode_str = _encode_utf8(json.dumps(common, separators=(",", ":")))
    x_s_common = _b64_encode(encode_str)
    x_b3_traceid = _get_b3_trace_id()

    return {
        "x-s": x_s,
        "x-t": x_t,
        "x-s-common": x_s_common,
        "x-b3-traceid": x_b3_traceid,
    }
