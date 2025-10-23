"""XiaoHongShu crawler client implementation."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Dict, List

import httpx

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
        sign_service_url: str = "http://localhost:8989",
    ) -> None:
        """
        Initialize XHS client.

        Args:
            cookies: Cookie string for authentication (format: "key1=value1; key2=value2")
            proxy: Proxy endpoint configuration
            timeout: Request timeout in seconds
            sign_service_url: MediaCrawlerPro sign service URL
        """
        self._cookies = self._parse_cookies(cookies) if cookies else {}
        # Clean cookie string: strip whitespace and newlines to avoid "Illegal header value" errors
        self._cookie_str = cookies.strip() if cookies else ""
        self._proxy = self._build_proxy_url(proxy) if proxy else None
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

        # ⭐ Use MediaCrawlerPro's SignServerClient (with aiohttp, matching working implementation)
        self._sign_client = SignServerClient(endpoint=sign_service_url, timeout=60)

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
            # NOTE: 不在这里设置 cookies，而是在每个请求中手动添加 Cookie header
            # 这样可以确保 Cookie 和签名的一致性
            client_kwargs = {
                "timeout": self._timeout,
                "follow_redirects": True,
                "http2": False,  # ⚠️ 使用HTTP/1.1（虽然此方法已不再用于搜索）
                "trust_env": False,  # 不信任环境变量的代理设置
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
        # ⚠️ 不使用 self._get_client()，而是为每个请求创建新的客户端
        # 这样可以避免连接池/HTTP2状态复用被小红书反爬识别
        # 参考 MediaCrawlerPro-Python 的实现方式

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

        # ⭐ Get signature using MediaCrawlerPro's SignServerClient (with aiohttp)
        signature_headers = {}
        try:
            # Create sign request (matching MediaCrawlerPro-Python exactly)
            sign_req = XhsSignRequest(
                uri=self.SEARCH_ENDPOINT,
                data=search_data,  # Pass dict object directly (will be converted by model_dump())
                cookies=self._cookie_str,
            )

            # Call sign service using aiohttp (matching MediaCrawlerPro-Python)
            xhs_sign_resp = await self._sign_client.xiaohongshu_sign(sign_req)

            # Extract signature headers (matching MediaCrawlerPro-Python's format)
            xmns = xhs_sign_resp.data.x_mns
            signature_headers = {
                "X-s": xhs_sign_resp.data.x_s,
                "X-t": xhs_sign_resp.data.x_t,
                "x-s-common": xhs_sign_resp.data.x_s_common,
                "X-B3-Traceid": xhs_sign_resp.data.x_b3_traceid,
                "X-Mns": xmns,
            }

            logger.info("✅ Generated signature using MediaCrawlerPro SignServerClient")
        except Exception as e:
            logger.error(f"❌ Failed to generate signature: {e}")
            raise

        try:
            # 添加随机延时，避免频繁请求触发反爬 (5-10秒，增加延时以避免反爬)
            import asyncio

            delay = random.uniform(5, 10)
            logger.info(f"延时 {delay:.2f} 秒后发起搜索请求...")
            await asyncio.sleep(delay)

            # Serialize data to JSON string (same format used for signature)
            json_str = json.dumps(
                search_data, separators=(",", ":"), ensure_ascii=False
            )

            # 打印请求详情用于调试
            logger.info(f"请求 URL: {url}")
            logger.info(f"请求数据: {json_str}")
            logger.info(f"Cookie (前50字符): {self._cookie_str[:50]}...")
            logger.info(
                f"签名头: X-s={signature_headers.get('X-s', '')[:20]}..., X-t={signature_headers.get('X-t', '')}"
            )

            # 构建完整的请求头（包含签名头） - 完全匹配 MediaCrawlerPro
            request_headers = {
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
                "sec-ch-ua-platform": '"Windows"',  # 匹配 MediaCrawlerPro
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",  # 匹配 MediaCrawlerPro
                "cookie": self._cookie_str,
            }
            # 添加签名头
            request_headers.update(signature_headers)

            # 🔍 调试: 打印完整Cookie
            logger.info(f"🔍 完整Cookie长度: {len(self._cookie_str)}")
            logger.info(f"🔍 完整Cookie内容: {self._cookie_str}")

            # 打印所有将要发送的请求头（调试用）
            logger.info(
                f"所有请求头: {json.dumps({k: v[:100] + '...' if len(str(v)) > 100 else v for k, v in request_headers.items()}, ensure_ascii=False, indent=2)}"
            )

            # ✅ 关键修改: 为每个请求创建新的 AsyncClient (完全模仿 MediaCrawlerPro)
            # MediaCrawlerPro 只设置 proxies，其他参数使用httpx默认值！
            client_kwargs = {}
            if self._proxy:
                client_kwargs["proxies"] = self._proxy  # MediaCrawlerPro使用复数形式

            async with httpx.AsyncClient(**client_kwargs) as fresh_client:
                # Use data= with JSON string instead of json= to match signature
                # MediaCrawlerPro在request调用时传入timeout=10（见client.py第210行）
                response = await fresh_client.post(url, data=json_str, headers=request_headers, timeout=10.0)
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
                    # Handle multiple response structure formats:
                    # 1. item.note_card (wrapped format)
                    # 2. item.data (alternative wrapper)
                    # 3. item itself (direct format)
                    note_data = item.get("note_card") or item.get("data") or item

                    # Validate we have valid note data (must have note_id)
                    if note_data and isinstance(note_data, dict) and note_data.get("note_id"):
                        try:
                            notes.append(self._parse_note_card(note_data))
                        except Exception as e:
                            logger.warning(f"Failed to parse note {note_data.get('note_id')}: {e}")
                            continue

                logger.info(f"Successfully parsed {len(notes)} notes from {len(items)} items")
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
        uri = "/api/sns/web/v1/user/selfinfo"
        url = f"{self.BASE_URL}{uri}"

        try:
            # ⭐ Generate signature using MediaCrawlerPro's SignServerClient
            signature_headers = {}
            try:
                sign_req = XhsSignRequest(
                    uri=uri,
                    data=None,
                    cookies=self._cookie_str,
                )
                xhs_sign_resp = await self._sign_client.xiaohongshu_sign(sign_req)

                xmns = xhs_sign_resp.data.x_mns
                signature_headers = {
                    "X-s": xhs_sign_resp.data.x_s,
                    "X-t": xhs_sign_resp.data.x_t,
                    "x-s-common": xhs_sign_resp.data.x_s_common,
                    "X-B3-Traceid": xhs_sign_resp.data.x_b3_traceid,
                    "X-Mns": xmns,
                }
            except Exception as e:
                logger.warning(f"Failed to generate signature for selfinfo: {e}")

            # 构建完整的请求头
            request_headers = {
                "accept": "application/json, text/plain, */*",
                "accept-language": "zh-CN,zh;q=0.9",
                "cache-control": "no-cache",
                "origin": "https://www.xiaohongshu.com",
                "pragma": "no-cache",
                "referer": "https://www.xiaohongshu.com/",
                "sec-ch-ua": '"Chromium";v="131", "Google Chrome";v="131", "Not.A/Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site",
                "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "cookie": self._cookie_str,
            }
            request_headers.update(signature_headers)

            # ✅ 使用新客户端实例（完全使用httpx默认配置，匹配MediaCrawlerPro）
            client_kwargs = {}
            if self._proxy:
                client_kwargs["proxies"] = self._proxy

            async with httpx.AsyncClient(**client_kwargs) as fresh_client:
                response = await fresh_client.get(url, headers=request_headers, timeout=10.0)
                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"User selfinfo response: {json.dumps(data, ensure_ascii=False)[:200]}"
                    )
                    return data
                else:
                    logger.warning(
                        f"Query selfinfo failed with status {response.status_code}"
                    )
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

    async def fetch_comments(
        self,
        note_id: str,
        cursor: str = "",
        max_count: int = 30,
        x_s: str = "",
        x_t: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Fetch comments for a note.

        Args:
            note_id: Note ID to fetch comments from
            cursor: Pagination cursor (empty for first page)
            max_count: Maximum number of comments to fetch
            x_s: Signature parameter
            x_t: Timestamp parameter

        Returns:
            List of comment dicts
        """
        client = self._get_client()
        uri = "/api/sns/web/v2/comment/page"
        url = f"{self.BASE_URL}{uri}"

        params = {
            "note_id": note_id,
            "cursor": cursor,
            "top_comment_id": "",
            "image_formats": "jpg,webp,avif",
        }

        headers = {}
        if x_s:
            headers["X-s"] = x_s
        if x_t:
            headers["X-t"] = str(x_t)

        try:
            logger.info(f"Fetching comments for note {note_id}, cursor={cursor}")
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()
            logger.debug(
                f"Comments API response: {json.dumps(data, ensure_ascii=False)[:300]}"
            )

            # Parse response
            if data.get("code") == 0 or data.get("success"):
                comments_data = data.get("data", {}).get("comments", [])
                has_more = data.get("data", {}).get("has_more", False)
                next_cursor = data.get("data", {}).get("cursor", "")

                parsed_comments = []
                for comment_dict in comments_data:
                    parsed = self._parse_comment(comment_dict, note_id)
                    if parsed:
                        parsed_comments.append(parsed)

                        # Parse sub-comments if exist
                        sub_comments = comment_dict.get("sub_comments", [])
                        for sub_comment in sub_comments:
                            sub_parsed = self._parse_comment(
                                sub_comment, note_id, parent_id=parsed["comment_id"]
                            )
                            if sub_parsed:
                                parsed_comments.append(sub_parsed)

                logger.info(
                    f"Fetched {len(parsed_comments)} comments for note {note_id}"
                )

                # Fetch next page if needed and not reached max_count
                if has_more and next_cursor and len(parsed_comments) < max_count:
                    remaining = max_count - len(parsed_comments)
                    if remaining > 0:
                        next_page = await self.fetch_comments(
                            note_id=note_id,
                            cursor=next_cursor,
                            max_count=remaining,
                            x_s=x_s,
                            x_t=x_t,
                        )
                        parsed_comments.extend(next_page)

                return parsed_comments[:max_count]
            else:
                error_msg = data.get("msg", "Unknown error")
                logger.warning(f"Comments API returned error: {error_msg}")
                return []

        except httpx.HTTPStatusError as exc:
            logger.error(f"HTTP error {exc.response.status_code}: {exc.response.text}")
            return []
        except Exception as exc:
            logger.error(f"Fetch comments request failed: {exc}")
            return []

    def _parse_comment(
        self,
        comment_dict: Dict[str, Any],
        note_id: str,
        parent_id: str | None = None,
    ) -> Dict[str, Any] | None:
        """
        Parse comment data from API response.

        Args:
            comment_dict: Raw comment data from API
            note_id: Note ID this comment belongs to
            parent_id: Parent comment ID (for sub-comments)

        Returns:
            Parsed comment dict or None if invalid
        """
        try:
            user_info = comment_dict.get("user_info", {})

            parsed = {
                "comment_id": comment_dict.get("id", ""),
                "content": comment_dict.get("content", ""),
                "note_id": note_id,
                "parent_comment_id": parent_id,
                "sub_comment_count": comment_dict.get("sub_comment_count", 0),
                "user_id": user_info.get("user_id", ""),
                "user_name": user_info.get("nickname", ""),
                "avatar": user_info.get("avatar", ""),
                "liked_count": comment_dict.get("like_count", 0),
                "ip_location": comment_dict.get("ip_location", ""),
                "create_time": comment_dict.get("create_time", 0),  # Timestamp in ms
            }

            return parsed
        except Exception as exc:
            logger.warning(f"Failed to parse comment: {exc}")
            return None

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
