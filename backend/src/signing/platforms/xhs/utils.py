"""Utility helpers for XiaoHongShu signing implementations."""

from __future__ import annotations

from typing import Dict


def parse_cookie_string(cookie_str: str | None) -> Dict[str, str]:
    if not cookie_str:
        return {}
    result: Dict[str, str] = {}
    for item in cookie_str.split(";"):
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        result[name.strip()] = value.strip()
    return result
