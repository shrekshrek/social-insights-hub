#!/usr/bin/env python3
"""验证 DeepSeek Prompt Caching 是否生效

目的：连续两次调用同一条 chain（SYSTEM_TEMPLATE 静态），观察第二次是否有
cache 命中。若 `cache_hit_tokens > 0`，则说明 caching 在工作。

运行：
    docker-compose exec backend uv run python scripts/experiments/verify_prompt_caching.py

参考：docs/adr/001-analysis-architecture.md P1 项"确认 DeepSeek prompt caching 生效"
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from src.llm.chains.social.entity_normalization_chain import (
    create_entity_clustering_chain,
)
from src.llm.chains.social.post_extraction_chain import create_post_extraction_chain
from src.llm.utils import extract_token_usage


SAMPLE_POST = """
# 标题
新出的无糖气泡水怎么样

# 正文
最近看到小红书上很多人在推元气森林的新款白桃口味,买了一箱试了下,
味道比想象中甜但不腻,据说零糖零卡,但我总怀疑添加了代糖。
有没有人知道这种代糖长期喝会不会对身体不好?听说赤藓糖醇不吸收,
但我的胃好像不太耐受,喝了有点胀。想听听大家的意见。
""".strip()

SAMPLE_ENTITIES = """
- 元气森林 (类型: 品牌, 重要度: 9.5)
- 白桃口味气泡水 (类型: 产品, 重要度: 8.0)
- 赤藓糖醇 (类型: 其他, 重要度: 6.0)
- 无糖气泡水 (类型: 产品, 重要度: 7.0)
- 代糖 (类型: 其他, 重要度: 5.5)
""".strip()


async def call_and_report(chain, inputs: dict, label: str) -> dict:
    """调用 chain 一次并打印 token 用量"""
    start = time.time()
    resp = await chain.ainvoke(inputs)
    elapsed = time.time() - start

    stats = extract_token_usage(resp, duration_seconds=elapsed, llm_type="chat")
    summary = stats["summary"]

    print(f"\n[{label}] 耗时 {elapsed:.2f}s")
    print(
        f"  tokens: input={summary['total_input_tokens']} "
        f"output={summary['total_output_tokens']} total={summary['total_tokens']}"
    )
    print(
        f"  cache:  hit={summary['total_cache_hit_tokens']} "
        f"miss={summary['total_cache_miss_tokens']}"
    )
    print(f"  cost:   ¥{summary['total_cost_cny']:.6f}")
    return stats


async def main():
    print("=" * 60)
    print("DeepSeek Prompt Caching 验证实验")
    print("=" * 60)

    # ===== 测试 1:post_extraction_chain (SYSTEM 原本就是静态) =====
    print("\n### 实验 1:post_extraction_chain (原有静态 SYSTEM)")
    chain_1 = create_post_extraction_chain()
    stats_1a = await call_and_report(
        chain_1, {"content": SAMPLE_POST}, "首次调用 (cold)"
    )
    # DeepSeek 缓存写入需要少量时间,等 2 秒
    await asyncio.sleep(2)
    stats_1b = await call_and_report(
        chain_1, {"content": SAMPLE_POST + "\n\n(轻微差异内容以强制输入变长)"},
        "二次调用 (warm)",
    )

    # ===== 测试 2:entity_clustering_chain (本次修复的链) =====
    print("\n### 实验 2:entity_clustering_chain (修复后 SYSTEM 静态)")
    chain_2 = create_entity_clustering_chain()
    stats_2a = await call_and_report(
        chain_2,
        {"entities": SAMPLE_ENTITIES, "task_keywords": "气泡水,元气森林"},
        "首次调用 (cold)",
    )
    await asyncio.sleep(2)
    stats_2b = await call_and_report(
        chain_2,
        {"entities": SAMPLE_ENTITIES + "\n- 冰红茶 (类型: 产品)", "task_keywords": "气泡水,元气森林"},
        "二次调用 (warm)",
    )

    # ===== 总结 =====
    print("\n" + "=" * 60)
    print("实验结论")
    print("=" * 60)

    def check(name: str, cold: dict, warm: dict) -> bool:
        warm_hit = warm["summary"]["total_cache_hit_tokens"]
        warm_input = warm["summary"]["total_input_tokens"]
        hit_ratio = warm_hit / warm_input if warm_input > 0 else 0
        status = "✓" if warm_hit > 0 else "✗"
        print(
            f"{status} [{name}] 二次调用 cache 命中 {warm_hit}/{warm_input} "
            f"({hit_ratio:.1%})"
        )
        return warm_hit > 0

    ok_1 = check("post_extraction", stats_1a, stats_1b)
    ok_2 = check("entity_clustering (fixed)", stats_2a, stats_2b)

    if ok_1 and ok_2:
        print("\n🎉 DeepSeek Prompt Caching 正常工作,修复后的 chain 能命中缓存")
        return 0
    else:
        print("\n⚠️  部分链未命中缓存,需进一步排查(可能 prefix 未稳定或 DeepSeek 侧延迟)")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
