"""Insight 产出质量评估器（rule-based MVP）

用途:
- 自动化对比不同分析架构(Pipeline vs LLM-native)在同一 strategy 上的产出
- 提供可复用的 5 维评分,作为后续重构决策的量化依据
- 支持 CI/监控场景(未来可扩展)

评估维度(5 维,权重总和 = 1.0):
1. citation_validity  (0.20) - 引用 post_id 真实性
2. thematic_engagement(0.30) - 引用覆盖了 monitor 多少真实 engagement
3. evidence_density   (0.15) - 每条 tension/opp 的证据数量
4. subject_focus      (0.20) - 结论是否围绕 Brief subject
5. completeness       (0.15) - 必要字段是否完整

MVP 范围: 仅评估 insight_result 结构(social_tensions + brand_opportunities)。
其他产出类型(brand_role / big_idea / agenda_map / landscape / strategic_brief)
后续按需扩展。

参考: docs/adr/001-analysis-architecture.md § 评估标准
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.social_media.tasks.models import SocialPost, SocialTask
from src.strategies.models import Strategy

logger = logging.getLogger(__name__)

# ======================================================================
# 数据类
# ======================================================================


@dataclass
class DimensionScore:
    """单维度得分"""

    name: str
    score: float  # 0.0 - 1.0; None(用 NaN)表示不适用
    weight: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """insight 产出评估结果"""

    strategy_id: int
    subject: str | None
    architecture_label: str  # 如 "path_a_pipeline" / "path_b_oneshot"
    dimensions: list[DimensionScore] = field(default_factory=list)
    overall_score: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "subject": self.subject,
            "architecture_label": self.architecture_label,
            "overall_score": round(self.overall_score, 4),
            "dimensions": [
                {
                    "name": d.name,
                    "score": round(d.score, 4),
                    "weight": d.weight,
                    "details": d.details,
                }
                for d in self.dimensions
            ],
            "meta": self.meta,
        }


# ======================================================================
# 工具函数
# ======================================================================

_POST_ID_PATTERN = re.compile(r"post_id[=:\s]*(\d+)", re.IGNORECASE)

# 评估配置
DIMENSION_WEIGHTS: dict[str, float] = {
    "citation_validity": 0.20,
    "thematic_engagement": 0.30,
    "evidence_density": 0.15,
    "subject_focus": 0.20,
    "completeness": 0.15,
}


def extract_post_ids(text: str) -> list[int]:
    """从任意文本(通常是 evidence.source 或 description)中提取 post_id"""
    if not text:
        return []
    return [int(m.group(1)) for m in _POST_ID_PATTERN.finditer(text)]


def iter_insight_claims(output: dict[str, Any]) -> list[dict[str, Any]]:
    """统一遍历 insight_result 的 tensions + opportunities 条目。

    返回每条结论的扁平化字典:
    - kind: "tension" | "opportunity"
    - statement: str
    - evidence: list[dict]
    - extra: 原字段(rationale / confidence / etc)
    """
    claims: list[dict[str, Any]] = []
    for t in output.get("social_tensions") or []:
        claims.append(
            {
                "kind": "tension",
                "statement": t.get("statement", "") or "",
                "evidence": t.get("evidence") or [],
                "extra": {
                    k: v
                    for k, v in t.items()
                    if k not in {"statement", "evidence"}
                },
            }
        )
    for o in output.get("brand_opportunities") or []:
        claims.append(
            {
                "kind": "opportunity",
                "statement": o.get("statement", "") or "",
                "evidence": o.get("evidence") or [],
                "extra": {
                    k: v
                    for k, v in o.items()
                    if k not in {"statement", "evidence"}
                },
            }
        )
    return claims


def collect_evidence_text(claim: dict[str, Any]) -> str:
    """把一条结论的所有 evidence 合并为一段文本,方便提 post_id"""
    parts: list[str] = [claim.get("statement", "")]
    for ev in claim.get("evidence") or []:
        if isinstance(ev, dict):
            parts.append(str(ev.get("source", "")))
            parts.append(str(ev.get("description", "")))
        else:
            parts.append(str(ev))
    return "\n".join(parts)


# ======================================================================
# 维度评分
# ======================================================================


async def _score_citation_validity(
    db: AsyncSession,
    claims: list[dict[str, Any]],
    social_monitor_id: int | None,
) -> DimensionScore:
    """引用 post_id 真实性:在 monitor 的帖子里有多少能被找到"""
    all_ids: set[int] = set()
    for c in claims:
        all_ids.update(extract_post_ids(collect_evidence_text(c)))

    details: dict[str, Any] = {
        "total_cited_ids": len(all_ids),
        "cited_ids_sample": sorted(all_ids)[:10],
    }

    if not all_ids:
        # 未引用 post_id(Path A 典型情况),得分 0——可追溯性为零
        details["reason"] = "no post_id citations found"
        return DimensionScore(
            "citation_validity", 0.0, DIMENSION_WEIGHTS["citation_validity"], details
        )

    if social_monitor_id is None:
        details["reason"] = "strategy has no social_monitor_id"
        return DimensionScore(
            "citation_validity", 0.0, DIMENSION_WEIGHTS["citation_validity"], details
        )

    stmt = (
        select(SocialPost.id)
        .join(SocialTask, SocialPost.task_id == SocialTask.id)
        .where(
            SocialTask.monitor_id == social_monitor_id,
            SocialPost.is_deleted.is_(False),
            SocialPost.id.in_(all_ids),
        )
    )
    result = await db.execute(stmt)
    valid_ids = {row[0] for row in result.all()}

    score = len(valid_ids) / len(all_ids)
    details["valid_count"] = len(valid_ids)
    details["invalid_ids"] = sorted(all_ids - valid_ids)[:10]
    return DimensionScore(
        "citation_validity", score, DIMENSION_WEIGHTS["citation_validity"], details
    )


async def _score_thematic_engagement(
    db: AsyncSession,
    claims: list[dict[str, Any]],
    social_monitor_id: int | None,
) -> DimensionScore:
    """议题 engagement 覆盖度:引用帖子的互动量 vs monitor 总互动量

    以 (likes + 2*comments) 作为 engagement 权重(与采样脚本一致)。
    得分 = cited_engagement / total_top_engagement,clamp[0,1]。
    top_engagement 取 monitor 全量的 80 分位数以上总和,避免头部爆款稀释小结论。
    """
    details: dict[str, Any] = {}
    if social_monitor_id is None:
        details["reason"] = "no social_monitor_id"
        return DimensionScore(
            "thematic_engagement",
            0.0,
            DIMENSION_WEIGHTS["thematic_engagement"],
            details,
        )

    all_ids: set[int] = set()
    for c in claims:
        all_ids.update(extract_post_ids(collect_evidence_text(c)))

    if not all_ids:
        details["reason"] = "no post_id citations found"
        return DimensionScore(
            "thematic_engagement",
            0.0,
            DIMENSION_WEIGHTS["thematic_engagement"],
            details,
        )

    cited_stmt = (
        select(
            func.coalesce(
                func.sum(SocialPost.likes_count + SocialPost.comments_count * 2),
                0,
            )
        )
        .join(SocialTask, SocialPost.task_id == SocialTask.id)
        .where(
            SocialTask.monitor_id == social_monitor_id,
            SocialPost.is_deleted.is_(False),
            SocialPost.id.in_(all_ids),
        )
    )
    total_stmt = (
        select(
            func.coalesce(
                func.sum(SocialPost.likes_count + SocialPost.comments_count * 2),
                0,
            )
        )
        .join(SocialTask, SocialPost.task_id == SocialTask.id)
        .where(
            SocialTask.monitor_id == social_monitor_id,
            SocialPost.is_deleted.is_(False),
        )
    )

    cited_engagement = int((await db.execute(cited_stmt)).scalar() or 0)
    total_engagement = int((await db.execute(total_stmt)).scalar() or 0)

    details["cited_engagement"] = cited_engagement
    details["monitor_total_engagement"] = total_engagement

    if total_engagement <= 0:
        details["reason"] = "monitor total engagement is 0"
        return DimensionScore(
            "thematic_engagement",
            0.0,
            DIMENSION_WEIGHTS["thematic_engagement"],
            details,
        )

    # 目标参考值:引用应至少触达 monitor 总 engagement 的 30%(参考 ADR § 评估标准)
    target_ratio = 0.30
    ratio = cited_engagement / total_engagement
    score = min(ratio / target_ratio, 1.0)
    details["engagement_ratio"] = round(ratio, 4)
    details["target_ratio"] = target_ratio
    return DimensionScore(
        "thematic_engagement",
        score,
        DIMENSION_WEIGHTS["thematic_engagement"],
        details,
    )


def _score_evidence_density(claims: list[dict[str, Any]]) -> DimensionScore:
    """证据密度:每条结论的 evidence 数量,≥2 条满分"""
    if not claims:
        return DimensionScore(
            "evidence_density",
            0.0,
            DIMENSION_WEIGHTS["evidence_density"],
            {"reason": "no claims"},
        )
    counts = [len(c.get("evidence") or []) for c in claims]
    per_claim_scores = [min(n / 2.0, 1.0) for n in counts]
    score = sum(per_claim_scores) / len(per_claim_scores)
    details = {
        "total_claims": len(claims),
        "avg_evidence_per_claim": round(sum(counts) / len(counts), 2),
        "claims_with_2plus": sum(1 for n in counts if n >= 2),
    }
    return DimensionScore(
        "evidence_density", score, DIMENSION_WEIGHTS["evidence_density"], details
    )


def _score_subject_focus(
    claims: list[dict[str, Any]], subject: str | None
) -> DimensionScore:
    """主体聚焦度:结论 statement/evidence 中是否提到 subject

    品牌聚焦场景下 ≥60% 结论应围绕 subject(参考 ADR § 评估标准)。
    若 subject 为空或 claims 为空,得分按 0 处理(无法判定)。
    """
    details: dict[str, Any] = {"subject": subject}
    if not subject or not claims:
        details["reason"] = "no subject or no claims"
        return DimensionScore(
            "subject_focus", 0.0, DIMENSION_WEIGHTS["subject_focus"], details
        )

    focused = 0
    for c in claims:
        text = collect_evidence_text(c)
        if subject in text:
            focused += 1

    target_ratio = 0.60
    ratio = focused / len(claims)
    score = min(ratio / target_ratio, 1.0)
    details["focused_count"] = focused
    details["total_claims"] = len(claims)
    details["focus_ratio"] = round(ratio, 4)
    details["target_ratio"] = target_ratio
    return DimensionScore(
        "subject_focus", score, DIMENSION_WEIGHTS["subject_focus"], details
    )


def _score_completeness(claims: list[dict[str, Any]]) -> DimensionScore:
    """完整度:必要字段填充率

    - tension 要求:conventional_wisdom / data_reality / evidence
    - opportunity 要求:rationale(或 why_non_obvious)/ evidence
    - 两者共同:statement / confidence
    """
    if not claims:
        return DimensionScore(
            "completeness",
            0.0,
            DIMENSION_WEIGHTS["completeness"],
            {"reason": "no claims"},
        )

    filled_flags: list[float] = []
    tension_required = {"conventional_wisdom", "data_reality"}
    opp_required = {"rationale", "why_non_obvious"}  # 二选一

    for c in claims:
        extra = c.get("extra") or {}
        total = 0
        filled = 0

        # 共同字段
        total += 1
        if c.get("statement"):
            filled += 1
        total += 1
        if extra.get("confidence"):
            filled += 1
        total += 1
        if c.get("evidence"):
            filled += 1

        if c["kind"] == "tension":
            for key in tension_required:
                total += 1
                if extra.get(key):
                    filled += 1
        else:  # opportunity
            total += 1
            if any(extra.get(k) for k in opp_required):
                filled += 1

        filled_flags.append(filled / total if total else 0.0)

    score = sum(filled_flags) / len(filled_flags)
    details = {
        "per_claim_fill_rate": [round(x, 2) for x in filled_flags],
        "avg_fill_rate": round(score, 4),
    }
    return DimensionScore(
        "completeness", score, DIMENSION_WEIGHTS["completeness"], details
    )


# ======================================================================
# 主入口
# ======================================================================


async def evaluate_insight_output(
    db: AsyncSession,
    strategy: Strategy,
    output: dict[str, Any],
    architecture_label: str,
) -> EvaluationResult:
    """对 insight 产出做 5 维评分。

    Args:
        db: AsyncSession
        strategy: 已加载的 Strategy 实例(需 brand_brief + social_monitor_id)
        output: insight_result JSON(含 social_tensions + brand_opportunities)
        architecture_label: 架构标签(如 "path_a_pipeline" / "path_b_oneshot")

    Returns:
        EvaluationResult
    """
    subject = None
    if isinstance(strategy.brand_brief, dict):
        subject = strategy.brand_brief.get("subject")

    claims = iter_insight_claims(output)
    logger.info(
        "评估 strategy=%s label=%s claims=%d",
        strategy.id,
        architecture_label,
        len(claims),
    )

    dims = [
        await _score_citation_validity(db, claims, strategy.social_monitor_id),
        await _score_thematic_engagement(db, claims, strategy.social_monitor_id),
        _score_evidence_density(claims),
        _score_subject_focus(claims, subject),
        _score_completeness(claims),
    ]

    overall = sum(d.score * d.weight for d in dims)

    return EvaluationResult(
        strategy_id=strategy.id,
        subject=subject,
        architecture_label=architecture_label,
        dimensions=dims,
        overall_score=overall,
        meta={
            "tension_count": len(output.get("social_tensions") or []),
            "opportunity_count": len(output.get("brand_opportunities") or []),
            "total_claims": len(claims),
        },
    )
