"""MediaCrawlerPro sign service models (copied from MediaCrawlerPro-Python)."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class XhsSignResult(BaseModel):
    """XHS signature result from MediaCrawlerPro-SignSrv."""

    x_s: str = Field(..., title="x_s", description="x_s")
    x_t: str = Field(..., title="x_t", description="x_t")
    x_s_common: str = Field(..., title="x_s_common", description="x_s_common")
    x_b3_traceid: str = Field(..., title="x_t_common", description="x_b3_trace_id")
    x_mns: str = Field(..., title="x_mns", description="x_mns")


class XhsSignRequest(BaseModel):
    """XHS signature request to MediaCrawlerPro-SignSrv."""

    uri: str = Field(..., title="uri", description="请求的uri")
    data: Optional[Any] = Field(None, title="data", description="请求body的数据")
    cookies: str = Field("", title="cookies", description="cookies")


class XhsSignResponse(BaseModel):
    """XHS signature response from MediaCrawlerPro-SignSrv."""

    biz_code: int = 0
    msg: str = "OK!"
    isok: bool = True
    data: Optional[XhsSignResult] = None
