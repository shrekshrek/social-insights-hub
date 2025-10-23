"""MediaCrawlerPro sign service client (copied from MediaCrawlerPro-Python).

This implementation uses aiohttp to call the sign service, exactly matching
MediaCrawlerPro-Python's implementation which has been verified to work.
"""

import logging
from typing import Any, Dict, Union

import aiohttp

from .mediacrawler_models import XhsSignRequest, XhsSignResponse

logger = logging.getLogger(__name__)


class SignServerClient:
    """Client for MediaCrawlerPro sign service (using aiohttp, matching MediaCrawlerPro-Python)."""

    def __init__(self, endpoint: str = "http://localhost:8989", timeout: int = 60):
        """
        SignServerClient constructor.

        Args:
            endpoint: sign server endpoint (e.g., "http://localhost:8989")
            timeout: request timeout in seconds
        """
        self._endpoint = endpoint
        self._timeout = timeout

    async def request(self, method: str, uri: str, **kwargs) -> Union[Dict, Any]:
        """
        Send request to sign server.

        Args:
            method: request method (GET, POST)
            uri: request uri (e.g., "/signsrv/v1/xhs/sign")
            **kwargs: other request params (e.g., json=...)

        Returns:
            Response JSON data

        Raises:
            Exception: If request fails
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout)
            ) as session:
                async with session.request(
                    method, self._endpoint + uri, **kwargs
                ) as response:
                    if response.status != 200:
                        response_text = await response.text()
                        logger.error(
                            f"[SignServerClient.request] response status code {response.status} "
                            f"response content: {response_text}"
                        )
                        raise Exception(f"请求签名服务器失败，状态码：{response.status}")

                    data = await response.json()
                    return data
        except Exception as e:
            raise Exception(f"请求签名服务器失败, error: {e}")

    async def xiaohongshu_sign(self, sign_req: XhsSignRequest) -> XhsSignResponse:
        """
        XiaoHongShu sign request to sign server.

        Args:
            sign_req: XhsSignRequest object

        Returns:
            XhsSignResponse object

        Raises:
            Exception: If signing fails
        """
        sign_server_uri = "/signsrv/v1/xhs/sign"

        # Use model_dump() to convert Pydantic model to dict (matching MediaCrawlerPro)
        res_json = await self.request(
            method="POST", uri=sign_server_uri, json=sign_req.model_dump()
        )

        if not res_json:
            raise Exception(
                f"从签名服务器:{self._endpoint}{sign_server_uri} 获取签名失败"
            )

        xhs_sign_response = XhsSignResponse(**res_json)
        if xhs_sign_response.isok:
            return xhs_sign_response

        raise Exception(
            f"从签名服务器:{self._endpoint}{sign_server_uri} 获取签名失败，"
            f"原因：{xhs_sign_response.msg}, sign response: {xhs_sign_response}"
        )

    async def pong_sign_server(self) -> None:
        """
        Test if sign server is alive.

        Raises:
            Exception: If sign server is not reachable
        """
        logger.info(
            "[SignServerClient.pong_sign_server] test sign server is alive"
        )
        await self.request(method="GET", uri="/signsrv/pong")
        logger.info("[SignServerClient.pong_sign_server] sign server is alive")
