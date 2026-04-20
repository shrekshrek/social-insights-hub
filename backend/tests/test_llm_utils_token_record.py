"""llm/utils.py 中 Research Agent 共享 token 工具的单元测试"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from src.config import settings
from src.llm.utils import build_flat_token_record, sum_cost_from_flat_records


def _mock_response(
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cache_hit: int | None = None,
    cache_miss: int | None = None,
) -> MagicMock:
    """构造一个具有 usage_metadata + 可选 response_metadata 的 mock 响应"""
    resp = MagicMock(spec=AIMessage)
    resp.usage_metadata = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    # DeepSeek 原生字段(模拟)
    raw_usage: dict = {}
    if cache_hit is not None:
        raw_usage["prompt_cache_hit_tokens"] = cache_hit
    if cache_miss is not None:
        raw_usage["prompt_cache_miss_tokens"] = cache_miss
    resp.response_metadata = {"token_usage": raw_usage} if raw_usage else {}
    return resp


class TestBuildFlatTokenRecord:
    def test_basic_response_no_cache(self):
        resp = _mock_response(input_tokens=1000, output_tokens=500, total_tokens=1500)
        record = build_flat_token_record(resp)
        assert record == {
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
            "cache_hit_tokens": 0,
            "cache_miss_tokens": 0,
        }

    def test_response_with_cache_fields(self):
        """DeepSeek 命中缓存时,cache_hit/miss 应正确提取"""
        resp = _mock_response(
            input_tokens=1000, output_tokens=500, total_tokens=1500,
            cache_hit=800, cache_miss=200,
        )
        record = build_flat_token_record(resp)
        assert record["cache_hit_tokens"] == 800
        assert record["cache_miss_tokens"] == 200

    def test_empty_response_returns_empty_dict(self):
        """空响应返回 {}, 方便 `[token_rec] if token_rec else []` 模式"""
        resp = MagicMock(spec=AIMessage)
        resp.usage_metadata = None
        resp.response_metadata = {}
        record = build_flat_token_record(resp)
        assert record == {}

    def test_zero_tokens_returns_empty(self):
        """usage_metadata 存在但全 0 也视为空响应"""
        resp = _mock_response(0, 0, 0)
        record = build_flat_token_record(resp)
        assert record == {}


class TestSumCostFromFlatRecords:
    """成本计算从 settings 读定价(避免与 .env 覆盖值冲突)"""

    def test_empty_records(self):
        assert sum_cost_from_flat_records([]) == 0.0

    def test_no_cache_fields_falls_back_to_miss_price(self):
        """旧记录(无 cache 字段): 全部按 miss 价计算,保持向前兼容"""
        records = [
            {"input_tokens": 1_000_000, "output_tokens": 500_000, "total_tokens": 1_500_000},
        ]
        in_price = settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION
        out_price = settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION
        expected = 1.0 * in_price + 0.5 * out_price
        cost = sum_cost_from_flat_records(records, llm_type="chat")
        assert abs(cost - expected) < 1e-6

    def test_with_cache_fields_uses_split_pricing(self):
        """有 cache 字段: hit/miss 按不同价计算"""
        records = [
            {
                "input_tokens": 1_000_000,
                "output_tokens": 500_000,
                "total_tokens": 1_500_000,
                "cache_hit_tokens": 800_000,
                "cache_miss_tokens": 200_000,
            },
        ]
        hit_price = settings.DEEPSEEK_CHAT_INPUT_CACHE_HIT_PRICE_PER_MILLION
        miss_price = settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION
        out_price = settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION
        expected = 0.8 * hit_price + 0.2 * miss_price + 0.5 * out_price
        cost = sum_cost_from_flat_records(records, llm_type="chat")
        assert abs(cost - expected) < 1e-6

    def test_hit_price_cheaper_than_miss(self):
        """关键约束: cache hit 价必须严格便宜于 miss 价"""
        hit_price = settings.DEEPSEEK_CHAT_INPUT_CACHE_HIT_PRICE_PER_MILLION
        miss_price = settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION
        assert hit_price < miss_price
        # 对比两个等量输入的成本
        all_hit = [{"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000,
                    "cache_hit_tokens": 1_000_000, "cache_miss_tokens": 0}]
        all_miss = [{"input_tokens": 1_000_000, "output_tokens": 0, "total_tokens": 1_000_000,
                     "cache_hit_tokens": 0, "cache_miss_tokens": 1_000_000}]
        assert sum_cost_from_flat_records(all_hit) < sum_cost_from_flat_records(all_miss)

    def test_multi_records_accumulate(self):
        """多条记录汇总应简单累加"""
        records = [
            {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500,
             "cache_hit_tokens": 0, "cache_miss_tokens": 1000},
            {"input_tokens": 2000, "output_tokens": 1000, "total_tokens": 3000,
             "cache_hit_tokens": 1500, "cache_miss_tokens": 500},
        ]
        hit_price = settings.DEEPSEEK_CHAT_INPUT_CACHE_HIT_PRICE_PER_MILLION
        miss_price = settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION
        out_price = settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION
        expected = (1500 * hit_price + 1500 * miss_price + 1500 * out_price) / 1_000_000
        cost = sum_cost_from_flat_records(records, llm_type="chat")
        assert abs(cost - expected) < 1e-6
