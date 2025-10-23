"""XiaoHongShu client - v2 with MediaCrawlerPro request() logic."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Dict, List, Union

import httpx
from httpx import Response

from src.resources.service import ProxyEndpoint

from .sign_client import SignServerClient
from .sign_models import XhsSignRequest

logger = logging.getLogger(__name__)


def _base36_encode(
    number: int, alphabet: str = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
) -> str:
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


class XhsClientV2:
    """XHS client with MediaCrawlerPro's request() logic."""

    BASE_URL = "https://edith.xiaohongshu.com"
    SEARCH_ENDPOINT = "/api/sns/web/v1/search/notes"

    def __init__(
        self,
        cookies: str | None = None,
        proxy: ProxyEndpoint | None = None,
        timeout: int = 10,
        sign_service_url: str = "http://localhost:8989",
    ) -> None:
        """Initialize XHS client."""
        self._cookie_str = cookies.strip() if cookies else ""
        self._proxy = self._build_proxy_url(proxy) if proxy else None
        self.timeout = timeout
        self._sign_client = SignServerClient(endpoint=sign_service_url, timeout=60)

    @staticmethod
    def _build_proxy_url(proxy: ProxyEndpoint) -> str:
        """Build proxy URL from ProxyEndpoint."""
        if proxy.username and proxy.password:
            return f"{proxy.protocol}://{proxy.username}:{proxy.password}@{proxy.host}:{proxy.port}"
        return f"{proxy.protocol}://{proxy.host}:{proxy.port}"

    @property
    def headers(self):
        """Base headers (matching MediaCrawlerPro)."""
        return {
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/json;charset=UTF-8",
            "origin": "https://www.xiaohongshu.com",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://www.xiaohongshu.com/",
            "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "cookie": self._cookie_str,
        }

    async def _pre_headers(self, uri: str, data=None) -> Dict:
        """
        Generate signature headers (matching MediaCrawlerPro).

        Args:
            uri: Request URI
            data: Request body data (dict or None)

        Returns:
            Complete headers with signature
        """
        sign_req = XhsSignRequest(uri=uri, data=data, cookies=self._cookie_str)
        xhs_sign_resp = await self._sign_client.xiaohongshu_sign(sign_req)

        xmns = xhs_sign_resp.data.x_mns
        signature_headers = {
            "X-s": xhs_sign_resp.data.x_s,
            "X-t": xhs_sign_resp.data.x_t,
            "x-s-common": xhs_sign_resp.data.x_s_common,
            "X-B3-Traceid": xhs_sign_resp.data.x_b3_traceid,
            "X-Mns": xmns,
        }

        headers = self.headers.copy()
        headers.update(signature_headers)
        return headers

    async def request(self, method, url, **kwargs) -> Union[Response, Dict]:
        """
        HTTP request wrapper (matching MediaCrawlerPro exactly).

        Args:
            method: HTTP method
            url: Request URL
            **kwargs: Additional request parameters

        Returns:
            Response dict or httpx.Response object
        """
        need_return_ori_response = kwargs.get("return_response", False)
        if "return_response" in kwargs:
            del kwargs["return_response"]

        # Create httpx client (matching MediaCrawlerPro)
        client_kwargs = {}
        if self._proxy:
            client_kwargs["proxies"] = self._proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.request(method, url, timeout=self.timeout, **kwargs)

        if need_return_ori_response:
            return response

        try:
            data = response.json()
        except json.decoder.JSONDecodeError:
            return response

        # Handle error codes (matching MediaCrawlerPro logic)
        if response.status_code == 471 or response.status_code == 461:
            verify_type = response.headers.get("Verifytype", "")
            verify_uuid = response.headers.get("Verifyuuid", "")
            raise Exception(
                f"出现验证码，请求失败，Verifytype: {verify_type}，Verifyuuid: {verify_uuid}"
            )

        # ⭐ Log full API response for debugging
        print(f"[request] Raw API response: {json.dumps(data, ensure_ascii=False)[:500]}")
        logger.info(f"[request] Raw API response: {json.dumps(data, ensure_ascii=False)[:500]}")

        # ⭐ CRITICAL: MediaCrawlerPro's response handling logic
        if data.get("success"):
            print(f"[request] Response has 'success' field, returning inner data")
            logger.info(f"[request] Response has 'success' field, returning inner data")
            return data.get("data", data.get("success"))  # Return inner "data" object!

        # Handle error codes
        elif data.get("code") == -510:
            raise Exception("IP blocked")
        elif data.get("code") == -500:
            raise Exception("Sign fault")
        elif data.get("code") == -1:
            logger.error("[request] 访问频次异常，延时...")
            await asyncio.sleep(random.uniform(2, 10))
            raise Exception("Access frequency error")
        else:
            # Log the error response
            logger.warning(f"[request] Unexpected response (no 'success' field): {data}")
            raise Exception(f"Request failed: {data}")

    async def post(self, uri: str, data: dict, **kwargs) -> Union[Dict, Response]:
        """
        POST request with signature (matching MediaCrawlerPro).

        Args:
            uri: Request URI (e.g., "/api/sns/web/v1/search/notes")
            data: Request body as dict
            **kwargs: Additional parameters

        Returns:
            Response data
        """
        json_str = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        headers = await self._pre_headers(uri, data)  # Pass dict to signature!

        res = await self.request(
            method="POST",
            url=f"{self.BASE_URL}{uri}",
            data=json_str,  # Send as string
            headers=headers,
            **kwargs,
        )
        return res

    async def search_notes(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        sort_type: str = "general",
        note_type: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Search notes by keyword.

        Args:
            keyword: Search keyword
            page: Page number
            page_size: Results per page
            sort_type: Sort type
            note_type: Note type (0=all, 1=video, 2=image)

        Returns:
            List of note dicts
        """
        search_data = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": _generate_search_id(),
            "sort": sort_type,
            "note_type": note_type,
        }

        print(f"🔍 [search_notes] Searching for '{keyword}' (page={page}, page_size={page_size})")
        logger.info(f"🔍 Searching for '{keyword}' (page={page}, page_size={page_size})")

        # Call post() which will use MediaCrawlerPro's request() logic
        result = await self.post(self.SEARCH_ENDPOINT, search_data)

        print(f"📊 [search_notes] API response type: {type(result)}")
        print(f"📊 [search_notes] API response: {json.dumps(result, ensure_ascii=False)[:500] if isinstance(result, dict) else str(result)[:500]}")
        logger.info(f"📊 API response type: {type(result)}")
        logger.info(f"📊 API response keys: {result.keys() if isinstance(result, dict) else 'N/A'}")

        # Parse response
        if isinstance(result, dict):
            items = result.get("items", [])
            logger.info(f"✅ Found {len(items)} items")

            notes = []
            for item in items:
                note_data = item.get("note_card") or item.get("data") or item

                if note_data and isinstance(note_data, dict) and note_data.get("note_id"):
                    try:
                        notes.append(self._parse_note_card(note_data))
                    except Exception as e:
                        logger.warning(f"Failed to parse note {note_data.get('note_id')}: {e}")
                        continue

            logger.info(f"✅ Parsed {len(notes)} notes from {len(items)} items")
            return notes
        else:
            logger.warning(f"Unexpected response type: {type(result)}")
            return []

    async def query_self(self) -> Dict[str, Any] | None:
        """Query current user info (for cookie verification)."""
        uri = "/api/sns/web/v1/user/selfinfo"
        headers = await self._pre_headers(uri)

        # Build client kwargs (only add proxies if not None)
        client_kwargs = {}
        if self._proxy:
            client_kwargs["proxies"] = self._proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.get(
                f"{self.BASE_URL}{uri}", headers=headers, timeout=10.0
            )
            if response.status_code == 200:
                return response.json()
        return None

    async def verify_cookie(self) -> tuple[bool, str]:
        """Verify if the cookie is valid."""
        logger.info("开始验证 Cookie 有效性...")

        if not self._cookie_str:
            return False, "Cookie 为空"

        try:
            self_info = await self.query_self()

            if not self_info:
                return False, "无法获取用户信息"

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

    @staticmethod
    def _parse_note_card(note_card: Dict[str, Any]) -> Dict[str, Any]:
        """Parse note card data."""
        user = note_card.get("user", {})
        interact_info = note_card.get("interact_info", {})

        return {
            "note_id": note_card.get("note_id", ""),
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
        }

    async def close(self) -> None:
        """Close client (placeholder for compatibility)."""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
