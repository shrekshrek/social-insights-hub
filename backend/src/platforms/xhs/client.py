"""XiaoHongShu crawler client implementation."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Dict, List
from urllib.parse import urlencode

import httpx

from src.resources.service import ProxyEndpoint
from src.signing import generate_signature

logger = logging.getLogger(__name__)


def _base36_encode(number: int, alphabet: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") -> str:
    """Convert integer to base36 string."""
    if number == 0:
        return alphabet[0]

    base36 = ""
    sign = ""

    if number < 0:
        sign = "-"
        number = -number

    while number != 0:
        number, remainder = divmod(number, len(alphabet))
        base36 = alphabet[remainder] + base36

    return sign + base36


def _generate_search_id() -> str:
    """Generate search_id for XHS API."""
    timestamp_part = int(time.time() * 1000) << 64
    random_part = int(random.uniform(0, 2147483646))
    return _base36_encode(timestamp_part + random_part)


class XhsClient:
    """Real XiaoHongShu API client with authentication and proxy support."""

    BASE_URL = "https://edith.xiaohongshu.com"
    SEARCH_ENDPOINT = "/api/sns/web/v1/search/notes"
    NOTE_DETAIL_ENDPOINT = "/api/sns/web/v1/feed"

    def __init__(
        self,
        cookies: str | None = None,
        proxy: ProxyEndpoint | None = None,
        timeout: int = 30,
    ) -> None:
        """
        Initialize XHS client.

        Args:
            cookies: Cookie string for authentication (format: "key1=value1; key2=value2")
            proxy: Proxy endpoint configuration
            timeout: Request timeout in seconds
        """
        self._cookies = self._parse_cookies(cookies) if cookies else {}
        self._cookie_str = cookies or ""  # Keep original cookie string for signing
        self._proxy = self._build_proxy_url(proxy) if proxy else None
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _parse_cookies(cookie_str: str) -> Dict[str, str]:
        """Parse cookie string into dict."""
        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies

    @staticmethod
    def _build_proxy_url(proxy: ProxyEndpoint) -> str:
        """Build proxy URL from ProxyEndpoint."""
        if proxy.username and proxy.password:
            return f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
        return f"{proxy.protocol}://{proxy.host}:{proxy.port}"

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            # 构建 AsyncClient 参数（请求头需要完全模拟浏览器）
            client_kwargs = {
                "cookies": self._cookies,
                "timeout": self._timeout,
                "follow_redirects": True,
                "headers": {
                    "accept": "application/json, text/plain, */*",
                    "accept-language": "zh-CN,zh;q=0.9",
                    "cache-control": "no-cache",
                    "content-type": "application/json;charset=UTF-8",
                    "origin": "https://www.xiaohongshu.com",
                    "pragma": "no-cache",
                    "priority": "u=1, i",
                    "referer": "https://www.xiaohongshu.com/",
                    "sec-ch-ua": '"Chromium";v="131", "Google Chrome";v="131", "Not.A/Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-site",
                    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                },
            }
            # 如果有代理，添加 proxy 参数（注意是单数形式）
            if self._proxy:
                client_kwargs["proxy"] = self._proxy

            self._client = httpx.AsyncClient(**client_kwargs)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search_notes(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        sort_type: str = "general",
        note_type: int = 0,
        x_s: str = "",
        x_t: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Search notes by keyword.

        Args:
            keyword: Search keyword
            page: Page number (starts from 1)
            page_size: Results per page (max 20)
            sort_type: Sort type (general/popularity_descending/time_descending)
            note_type: Note type (0=all, 1=video, 2=image)
            x_s: Signature parameter (deprecated, will use sign service)
            x_t: Timestamp parameter (deprecated, will use sign service)

        Returns:
            List of note data dicts
        """
        client = self._get_client()

        # Build search data (POST body, not query params)
        search_data = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": _generate_search_id(),
            "sort": sort_type,
            "note_type": note_type,
        }

        # Build URL
        url = f"{self.BASE_URL}{self.SEARCH_ENDPOINT}"

        # Get signature using built-in signing module
        headers = {}
        try:
            sign_data = await generate_signature(
                platform="xhs",
                payload={
                    "uri": self.SEARCH_ENDPOINT,
                    "data": search_data,
                    "cookies": self._cookie_str,
                },
            )
            # Extract signature headers
            if sign_data:
                headers["X-s"] = sign_data.get("x-s", "")
                headers["X-t"] = sign_data.get("x-t", "")
                if "x-s-common" in sign_data:
                    headers["x-s-common"] = sign_data["x-s-common"]
                if "x-b3-traceid" in sign_data:
                    headers["X-B3-Traceid"] = sign_data["x-b3-traceid"]
                if "x-mns" in sign_data:
                    headers["X-Mns"] = sign_data["x-mns"]
                logger.info("Generated signature headers successfully")
        except Exception as e:
            logger.warning(f"Failed to generate signature, proceeding without: {e}")

        try:
            # 添加随机延时，避免频繁请求触发反爬 (2-5秒)
            import asyncio
            delay = random.uniform(2, 5)
            logger.info(f"延时 {delay:.2f} 秒后发起请求...")
            await asyncio.sleep(delay)

            # 打印请求详情用于调试
            logger.info(f"请求 URL: {url}")
            logger.info(f"请求数据: {json.dumps(search_data, ensure_ascii=False)}")
            logger.info(f"Cookie (前50字符): {self._cookie_str[:50]}...")
            logger.info(f"签名头: X-s={headers.get('X-s', '')[:20]}..., X-t={headers.get('X-t', '')}")

            response = await client.post(url, json=search_data, headers=headers)
            response.raise_for_status()

            data = response.json()
            logger.info(
                f"Search API response: {json.dumps(data, ensure_ascii=False)[:500]}"
            )

            # Parse response
            if data.get("code") == 0 or data.get("success"):
                items = data.get("data", {}).get("items", [])
                notes = []
                for item in items:
                    note_card = item.get("note_card", {})
                    if note_card:
                        notes.append(self._parse_note_card(note_card))
                return notes
            else:
                error_msg = data.get("msg", "Unknown error")
                logger.warning(f"Search API returned error: {error_msg}")
                return []

        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error {exc.response.status_code}: {exc.response.text}")
            raise
        except Exception as exc:
            logger.error(f"Search request failed: {exc}")
            raise

    async def query_self(self) -> Dict[str, Any] | None:
        """
        Query current user info to verify cookie validity.

        Returns:
            User info dict if successful, None otherwise
        """
        client = self._get_client()
        uri = "/api/sns/web/v1/user/selfinfo"
        url = f"{self.BASE_URL}{uri}"

        try:
            # Generate signature for this request
            headers = {}
            try:
                sign_data = await generate_signature(
                    platform="xhs",
                    payload={
                        "uri": uri,
                        "data": None,
                        "cookies": self._cookie_str,
                    },
                )
                if sign_data:
                    headers["X-s"] = sign_data.get("x-s", "")
                    headers["X-t"] = sign_data.get("x-t", "")
                    if "x-s-common" in sign_data:
                        headers["x-s-common"] = sign_data["x-s-common"]
                    if "x-b3-traceid" in sign_data:
                        headers["X-B3-Traceid"] = sign_data["x-b3-traceid"]
            except Exception as e:
                logger.warning(f"Failed to generate signature for selfinfo: {e}")

            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                logger.info(f"User selfinfo response: {json.dumps(data, ensure_ascii=False)[:200]}")
                return data
            else:
                logger.warning(f"Query selfinfo failed with status {response.status_code}")
                return None

        except Exception as exc:
            logger.error(f"Query selfinfo request failed: {exc}")
            return None

    async def verify_cookie(self) -> tuple[bool, str]:
        """
        Verify if the cookie is valid by querying user info.

        Returns:
            Tuple of (is_valid, message)
        """
        logger.info("开始验证 Cookie 有效性...")

        if not self._cookie_str:
            return False, "Cookie 为空"

        try:
            self_info = await self.query_self()

            if not self_info:
                return False, "无法获取用户信息（请求失败）"

            # Check response structure
            if self_info.get("code") == 0 or self_info.get("success"):
                result = self_info.get("data", {}).get("result", {})
                if result.get("success"):
                    user_info = result.get("user_info", {})
                    nickname = user_info.get("nickname", "未知")
                    user_id = user_info.get("user_id", "未知")
                    logger.info(f"✅ Cookie 验证成功！用户: {nickname} (ID: {user_id})")
                    return True, f"验证成功，用户: {nickname}"
                else:
                    return False, "用户信息返回失败"
            else:
                error_msg = self_info.get("msg", "未知错误")
                return False, f"API 返回错误: {error_msg}"

        except Exception as exc:
            logger.exception("Cookie 验证异常")
            return False, f"验证过程出错: {str(exc)}"

    async def get_note_detail(
        self,
        note_id: str,
        x_s: str = "",
        x_t: str = "",
    ) -> Dict[str, Any] | None:
        """
        Get note detail by note_id.

        Args:
            note_id: Note ID
            x_s: Signature parameter
            x_t: Timestamp parameter

        Returns:
            Note detail dict or None if not found
        """
        client = self._get_client()

        url = f"{self.BASE_URL}{self.NOTE_DETAIL_ENDPOINT}"
        params = {"source_note_id": note_id}

        headers = {}
        if x_s:
            headers["x-s"] = x_s
        if x_t:
            headers["x-t"] = str(x_t)

        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()
            if data.get("code") == 0 or data.get("success"):
                items = data.get("data", {}).get("items", [])
                if items:
                    note_card = items[0].get("note_card", {})
                    return self._parse_note_card(note_card, include_detail=True)
            return None

        except Exception as exc:
            logger.error(f"Get note detail failed: {exc}")
            raise

    @staticmethod
    def _parse_note_card(
        note_card: Dict[str, Any],
        include_detail: bool = False,
    ) -> Dict[str, Any]:
        """
        Parse note card data from API response.

        Args:
            note_card: Raw note card data
            include_detail: Include detailed fields

        Returns:
            Parsed note data
        """
        note_id = note_card.get("note_id", "")
        user = note_card.get("user", {})
        interact_info = note_card.get("interact_info", {})
        image_list = note_card.get("image_list", [])

        parsed = {
            "note_id": note_id,
            "type": note_card.get("type", "normal"),
            "title": note_card.get("title", ""),
            "desc": note_card.get("desc", ""),
            "user_id": user.get("user_id", ""),
            "nickname": user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
            "liked_count": interact_info.get("liked_count", 0),
            "collected_count": interact_info.get("collected_count", 0),
            "comment_count": interact_info.get("comment_count", 0),
            "share_count": interact_info.get("share_count", 0),
            "image_count": len(image_list),
            "last_update_time": note_card.get("last_update_time", 0),
        }

        if include_detail:
            parsed["video_url"] = (
                note_card.get("video", {})
                .get("media", {})
                .get("stream", {})
                .get("h264", [{}])[0]
                .get("master_url", "")
            )
            parsed["images"] = [img.get("url_default", "") for img in image_list]
            parsed["ip_location"] = note_card.get("ip_location", "")
            parsed["tag_list"] = [
                tag.get("name", "") for tag in note_card.get("tag_list", [])
            ]

        return parsed

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
