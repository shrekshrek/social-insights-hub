#!/usr/bin/env python3
"""策略 insight 产出评估 CLI

对比不同架构(Path A pipeline vs Path B 一把梭)在同一 strategy 上的
insight 产出质量,5 维打分。

## 使用方法

**默认场景(评估 Path A,即数据库里 strategies.insight_result)**

```bash
docker-compose exec backend uv run python /tmp/eval.py \\
    --strategy-id 18
```

**对比 Path A vs Path B(外部 JSON 文件作为 Path B)**

```bash
# 先把 Path B 的 insight JSON 复制进容器
docker cp /tmp/path_b_experiment/path_b_insight.json \\
    crawler-backend-1:/tmp/path_b_18.json

docker-compose exec backend uv run python /tmp/eval.py \\
    --strategy-id 18 \\
    --path-b-json /tmp/path_b_18.json
```

## 输出

JSON 形式的单边/对比评分,打印到 stdout。

## 参考

- docs/adr/001-analysis-architecture.md § 评估标准
- backend/src/strategies/evaluator.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from src.database import AsyncSessionLocal

# 预先 import 所有与 Strategy relationship 相关的模型,
# 保证 SQLAlchemy mapper 能解析跨模块关系(否则 select(Strategy) 会报
# `Module 'src' has no mapped classes registered under the name 'xxx'`)
from src.news_media.monitors.models import NewsMonitor  # noqa: F401
from src.news_media.tasks.models import NewsTask  # noqa: F401
from src.news_media.analysis.models import NewsSlice  # noqa: F401
from src.social_media.monitors.models import SocialMonitor  # noqa: F401
from src.social_media.analysis.models import SocialSlice  # noqa: F401
from src.auth.models import User  # noqa: F401
from src.research_agent.models import ResearchTask  # noqa: F401

from src.strategies.evaluator import (
    EvaluationResult,
    evaluate_insight_output,
)
from src.strategies.models import Strategy

logger = logging.getLogger(__name__)


def _load_json_file(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"{path} 不存在")
    return json.loads(p.read_text(encoding="utf-8"))


def _format_result(result: EvaluationResult) -> str:
    lines = [
        f"=== {result.architecture_label} (strategy={result.strategy_id}, "
        f"subject={result.subject!r}) ==="
    ]
    lines.append(
        f"Overall: {result.overall_score:.4f}  "
        f"(tensions={result.meta.get('tension_count')}, "
        f"opps={result.meta.get('opportunity_count')})"
    )
    lines.append("")
    for d in result.dimensions:
        lines.append(
            f"  {d.name:25s} score={d.score:.3f} "
            f"(weight={d.weight:.2f}, contrib={d.score * d.weight:.3f})"
        )
        for k, v in d.details.items():
            if isinstance(v, (dict, list)) and len(str(v)) > 100:
                v = f"<{type(v).__name__} len={len(v)}>"
            lines.append(f"      {k}: {v}")
    return "\n".join(lines)


async def _run(strategy_id: int, path_b_json: str | None) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(Strategy).where(Strategy.id == strategy_id)
        result = await db.execute(stmt)
        strategy = result.scalar_one_or_none()
        if strategy is None:
            print(f"ERROR: strategy {strategy_id} 不存在", file=sys.stderr)
            return 1

        # Path A: 数据库里的 insight_result
        if not strategy.insight_result:
            print(
                f"ERROR: strategy {strategy_id} 没有 insight_result,跳过 Path A",
                file=sys.stderr,
            )
            path_a_eval: EvaluationResult | None = None
        else:
            path_a_eval = await evaluate_insight_output(
                db, strategy, strategy.insight_result, "path_a_pipeline"
            )

        # Path B: 外部 JSON(可选)
        path_b_eval: EvaluationResult | None = None
        if path_b_json:
            path_b_output = _load_json_file(path_b_json)
            path_b_eval = await evaluate_insight_output(
                db, strategy, path_b_output, "path_b_oneshot"
            )

    # 输出
    if path_a_eval:
        print(_format_result(path_a_eval))
        print()
    if path_b_eval:
        print(_format_result(path_b_eval))
        print()

    # 对比总结
    if path_a_eval and path_b_eval:
        print("=" * 60)
        print("对比总结")
        print("=" * 60)
        print(
            f"Overall Score: Path A = {path_a_eval.overall_score:.4f}, "
            f"Path B = {path_b_eval.overall_score:.4f}, "
            f"Δ = {path_b_eval.overall_score - path_a_eval.overall_score:+.4f}"
        )
        print(f"\n{'Dimension':<25s} {'Path A':>10s} {'Path B':>10s} {'Δ':>10s}")
        print("-" * 60)
        for da, db_ in zip(path_a_eval.dimensions, path_b_eval.dimensions):
            delta = db_.score - da.score
            print(
                f"{da.name:<25s} {da.score:>10.3f} {db_.score:>10.3f} "
                f"{delta:>+10.3f}"
            )

    # 机器可读输出
    print("\n--- JSON ---")
    out = {}
    if path_a_eval:
        out["path_a"] = path_a_eval.to_dict()
    if path_b_eval:
        out["path_b"] = path_b_eval.to_dict()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="策略 insight 产出评估")
    parser.add_argument(
        "--strategy-id", type=int, required=True, help="目标 strategy ID"
    )
    parser.add_argument(
        "--path-b-json",
        type=str,
        default=None,
        help="Path B insight JSON 文件路径(容器内路径);省略则只评估 Path A",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    return asyncio.run(_run(args.strategy_id, args.path_b_json))


if __name__ == "__main__":
    sys.exit(main())
