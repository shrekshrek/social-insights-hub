"""策略定义业务逻辑"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status

if TYPE_CHECKING:
    from src.news_media.analysis.models import NewsSlice
from sqlalchemy import select, func, update, and_, delete
from sqlalchemy.exc import IntegrityError
from src.utils import run_cpu_bound_task
from src.knowledge_base.service import parse_text as _extract_text_from_bytes
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from src.llm.chains.strategy.research_design_chain import (
    create_research_design_chain,
    format_research_design_inputs,
    parse_research_design_response,
)
from src.llm.chains.strategy.social_probe_review_chain import (
    create_single_task_probe_review_chain,
    format_single_task_probe_review_inputs,
    parse_single_task_probe_review_response,
)
from src.llm.chains.strategy.coverage_check_chain import (
    create_coverage_check_chain,
    format_coverage_check_inputs,
    parse_coverage_check_response,
)
from src.llm.chains.strategy.brand_strategy.insight_chain import (
    create_insight_chain,
    format_slice_data_for_insight,
    parse_insight_response,
)
from src.llm.chains.strategy.brand_strategy.brand_role_chain import (
    create_brand_role_chain,
    format_data_for_brand_role,
    parse_brand_role_response,
)
from src.llm.chains.strategy.brand_strategy.big_idea_chain import (
    create_big_idea_chain,
    format_data_for_big_idea,
    parse_big_idea_response,
)
from src.llm.chains.strategy.market_report.agenda_map_chain import (
    create_agenda_map_chain,
    format_inputs_for_agenda_map,
    parse_agenda_map_response,
)
from src.llm.chains.strategy.market_report.landscape_chain import (
    create_landscape_chain,
    format_inputs_for_landscape,
    parse_landscape_response,
)
from src.llm.chains.strategy.market_report.strategic_brief_chain import (
    create_strategic_brief_chain,
    format_inputs_for_strategic_brief,
    parse_strategic_brief_response,
)
from src.llm.chains.strategy.brief_parser_chain import (
    create_brief_parser_chain,
    parse_brief_parser_response,
)
from src.database import AsyncSessionLocal
from src.llm import extract_token_usage
from src.llm.utils import merge_token_usage_stats
from src.jobs.factory import create_analysis_job_async
from src.jobs.models import AnalysisType
from src.feishu.client import fire_notification
from src.feishu import templates as feishu_tmpl
from src.social_media.analysis.models import SocialSlice
from src.social_media.tasks.models import SocialTask as SocialTask
from .models import Strategy
from .schemas import (
    ApproveProbeResponse,
    CollectionStatusResponse,
    CollectionTaskStatus,
    NewsCollectionTaskStatus,
    ConfirmResearchResponse,
    DataOverviewResponse,
    DesignResearchResponse,
    ParseBriefResponse,
    ProbeStatusResponse,
    SocialProbeTaskStatus,
    RefineProbeRequest,
    RefineProbeResponse,
    ResearchAgentStatus,
    StrategyCreate,
    StrategyUpdate,
    StrategyRead,
    StrategyListItem,
    SliceSummary,
)

_MAX_BRIEF_TEXT_CHARS = 10000


async def _load_strategy_slice_summaries(
    db: AsyncSession, strategy: Strategy
) -> list[SliceSummary]:
    """加载策略关联的全部切片（社媒 + 新闻），合并成统一 SliceSummary 列表。

    - 社媒：`SocialSlice.monitor_id == strategy.social_monitor_id`，channel="social"
    - 新闻：`NewsSlice.monitor_id == strategy.news_monitor_id`，channel="news"
    - 顺序：先社媒再新闻，同 channel 内按 id 升序

    前端 DataOverviewPanel 按 channel 分组显示并路由到不同详情页。
    """
    from src.news_media.analysis.models import NewsSlice as _NewsSlice

    summaries: list[SliceSummary] = []

    if strategy.social_monitor_id:
        stmt = (
            select(SocialSlice)
            .where(SocialSlice.monitor_id == strategy.social_monitor_id)
            .order_by(SocialSlice.id)
        )
        result = await db.execute(stmt)
        for s in result.scalars().all():
            summaries.append(
                SliceSummary(
                    slice_id=s.id,
                    slice_name=s.name,
                    monitor_id=s.monitor_id,
                    monitor_name=s.monitor.name if s.monitor else "",
                    channel="social",
                    status=s.status or "",
                )
            )

    if strategy.news_monitor_id:
        stmt = (
            select(_NewsSlice)
            .where(_NewsSlice.monitor_id == strategy.news_monitor_id)
            .order_by(_NewsSlice.id)
        )
        result = await db.execute(stmt)
        for s in result.scalars().all():
            summaries.append(
                SliceSummary(
                    slice_id=s.id,
                    slice_name=s.name,
                    monitor_id=s.monitor_id,
                    monitor_name=s.monitor.name if s.monitor else "",
                    channel="news",
                    status=s.status or "",
                )
            )

    return summaries


async def _count_strategy_slices(db: AsyncSession, strategy: Strategy) -> int:
    """统计策略关联的全部切片数量（社媒 + 新闻）。"""
    from src.news_media.analysis.models import NewsSlice as _NewsSlice

    total = 0
    if strategy.social_monitor_id:
        stmt = (
            select(func.count())
            .select_from(SocialSlice)
            .where(SocialSlice.monitor_id == strategy.social_monitor_id)
        )
        total += int((await db.execute(stmt)).scalar() or 0)

    if strategy.news_monitor_id:
        stmt = (
            select(func.count())
            .select_from(_NewsSlice)
            .where(_NewsSlice.monitor_id == strategy.news_monitor_id)
        )
        total += int((await db.execute(stmt)).scalar() or 0)

    return total


async def _strategy_read(db: AsyncSession, strategy: Strategy) -> StrategyRead:
    slices = await _load_strategy_slice_summaries(db, strategy)
    return StrategyRead.from_orm_full(strategy, slices=slices)


async def _strategy_list_item(db: AsyncSession, strategy: Strategy) -> StrategyListItem:
    slice_count = await _count_strategy_slices(db, strategy)
    return StrategyListItem.from_orm_full(strategy, slice_count=slice_count)


logger = logging.getLogger(__name__)


def _strategy_open_ids(strategy: Strategy) -> list[str]:
    """收集策略创建者 + 参与者的飞书 open_id（去重，跳过未绑定用户）。"""
    ids: list[str] = []
    if strategy.user and strategy.user.oauth_open_id:
        ids.append(strategy.user.oauth_open_id)
    for p in strategy.participants:
        if p.oauth_open_id and p.oauth_open_id not in ids:
            ids.append(p.oauth_open_id)
    return ids


async def create_strategy(
    db: AsyncSession, data: StrategyCreate, user_id: int
) -> Strategy:
    """创建策略（仅基础字段，切片由后续 design-research → confirm-research 自动建）。"""
    brief_dict = data.brand_brief.model_dump() if data.brand_brief else None
    strategy = Strategy(
        name=data.name,
        user_id=user_id,
        brand_brief=brief_dict,
    )
    db.add(strategy)
    await db.flush()

    if data.participant_ids:
        from src.auth.models import User as UserModel

        filtered_ids = [uid for uid in data.participant_ids if uid != user_id]
        if filtered_ids:
            users = await db.execute(
                select(UserModel).where(UserModel.id.in_(filtered_ids))
            )
            for u in users.scalars().all():
                strategy.participants.append(u)

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def get_strategies(
    db: AsyncSession,
    user_id: int,
    is_admin: bool,
    skip: int,
    limit: int,
    search: str | None = None,
) -> tuple[list[Strategy], int]:
    """获取策略列表

    admin 看全部，普通用户看自己创建或参与的。
    """
    from src.strategies.models import strategy_participants

    query = select(Strategy)

    if not is_admin:
        participated_subq = (
            select(strategy_participants.c.strategy_id)
            .where(strategy_participants.c.user_id == user_id)
            .scalar_subquery()
        )
        query = query.where(
            (Strategy.user_id == user_id) | Strategy.id.in_(participated_subq)
        )

    if search:
        query = query.where(Strategy.name.ilike(f"%{search}%"))

    # 计数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页 + 排序
    query = query.order_by(Strategy.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_strategy_by_id(db: AsyncSession, strategy_id: int) -> Strategy | None:
    """按 ID 获取策略（含关系）。

    切片通过 social_monitor_id / news_monitor_id 隐式关联，由 loader 按需加载。
    """
    query = (
        select(Strategy)
        .where(Strategy.id == strategy_id)
        .options(
            selectinload(Strategy.user),
            selectinload(Strategy.participants),
        )
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_strategy(
    db: AsyncSession, strategy: Strategy, data: StrategyUpdate
) -> Strategy:
    """更新策略基本信息"""
    if data.name is not None:
        strategy.name = data.name
    if data.brand_brief is not None:
        strategy.brand_brief = data.brand_brief

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def delete_strategy(db: AsyncSession, strategy: Strategy) -> None:
    """删除策略及所有系统自动创建的关联资源。

    清理顺序：
    1. SocialMonitor（策略专属，级联删其下所有 SocialTask + SocialSlice）
    2. NewsMonitor（策略专属，级联删其下所有 NewsTask + NewsArticle）
    3. Strategy（ORM cascade 自动删 ResearchTask）
    """
    social_monitor = None
    news_monitor = None

    if strategy.social_monitor_id:
        from src.social_media.monitors.crud import get_social_monitor_by_id

        social_monitor = await get_social_monitor_by_id(
            db, strategy.social_monitor_id, load_relations=False
        )

    if strategy.news_monitor_id:
        from src.news_media.monitors.crud import (
            get_monitor_by_id as get_news_monitor_by_id,
        )

        news_monitor = await get_news_monitor_by_id(
            db, strategy.news_monitor_id, load_relations=False
        )

    strategy.social_monitor_id = None
    strategy.news_monitor_id = None
    await db.flush()

    if social_monitor:
        await db.delete(social_monitor)
    if news_monitor:
        await db.delete(news_monitor)
    await db.flush()

    await db.delete(strategy)
    await db.commit()


async def add_participants_to_strategy(
    db: AsyncSession, strategy: Strategy, user_ids: list[int]
) -> Strategy:
    """为策略添加参与者，并同步到关联的 SocialMonitor / NewsMonitor"""
    from src.auth.models import User

    # 过滤 owner 自身
    filtered_ids = [uid for uid in user_ids if uid != strategy.user_id]
    if not filtered_ids:
        return strategy

    users = await db.execute(select(User).where(User.id.in_(filtered_ids)))
    new_participants = users.scalars().all()
    existing_ids = {u.id for u in strategy.participants}
    for user in new_participants:
        if user.id not in existing_ids:
            strategy.participants.append(user)

    await db.flush()
    await _sync_participants_to_associated_resources(db, strategy)
    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def remove_participant_from_strategy(
    db: AsyncSession, strategy: Strategy, user_id: int
) -> Strategy:
    """从策略移除参与者，并同步到关联的 SocialMonitor / NewsMonitor"""
    if user_id == strategy.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能移除策略创建者",
        )
    if user_id not in {p.id for p in strategy.participants}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户 {user_id} 不是该策略的参与者",
        )
    strategy.participants = [p for p in strategy.participants if p.id != user_id]
    await db.flush()
    await _sync_participants_to_associated_resources(db, strategy)
    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def _sync_participants_to_associated_resources(
    db: AsyncSession, strategy: Strategy
) -> None:
    """将策略 participants 同步（覆盖）到关联的 SocialMonitor / NewsMonitor / ResearchTask。

    只同步由策略创建/关联的资源（通过 social_monitor_id / news_monitor_id / strategy_id 判断）。
    独立创建的资源不受此影响。
    覆盖式语义：策略 participants 是关联资源 participants 的单一来源——任何额外加在
    资源上的协作者都会在策略 participants 变更时被覆盖。
    """
    from src.auth.models import User
    from src.research_agent.models import ResearchTask

    participant_ids = [p.id for p in strategy.participants]

    if strategy.social_monitor_id:
        from src.social_media.monitors.crud import get_social_monitor_by_id

        monitor = await get_social_monitor_by_id(
            db, strategy.social_monitor_id, load_relations=True
        )
        if monitor:
            users = await db.execute(select(User).where(User.id.in_(participant_ids)))
            new_participants = [
                u for u in users.scalars().all() if u.id != monitor.user_id
            ]
            monitor.participants = new_participants
            await db.flush()

    if strategy.news_monitor_id:
        from src.news_media.monitors.crud import (
            get_monitor_by_id as get_news_monitor_by_id,
        )

        news_monitor = await get_news_monitor_by_id(
            db, strategy.news_monitor_id, load_relations=True
        )
        if news_monitor:
            users2 = await db.execute(select(User).where(User.id.in_(participant_ids)))
            new_participants2 = [
                u for u in users2.scalars().all() if u.id != news_monitor.user_id
            ]
            news_monitor.participants = new_participants2
            await db.flush()

    # 同步到该策略关联的所有 ResearchTask（行业研究 / 创意研究）
    research_tasks_stmt = (
        select(ResearchTask)
        .where(ResearchTask.strategy_id == strategy.id)
        .options(selectinload(ResearchTask.participants))
    )
    research_tasks = (await db.execute(research_tasks_stmt)).scalars().all()
    if research_tasks:
        users_for_research = (
            (await db.execute(select(User).where(User.id.in_(participant_ids))))
            .scalars()
            .all()
            if participant_ids
            else []
        )
        for rtask in research_tasks:
            new_rparticipants = [u for u in users_for_research if u.id != rtask.user_id]
            rtask.participants = new_rparticipants
        await db.flush()


async def load_strategy_inputs(db: AsyncSession, strategy: Strategy) -> list[dict]:
    """加载策略社媒切片数据（SocialSlice.result_data）。按 social_monitor_id 查询。

    只返回 Stage2 完成后置为 `status=completed` 的切片（与 NewsSlice 过滤对称）。
    Stage2 failed/skipped 的切片 result_data 可能不完整，下游 chain 消费会产生
    质量问题，此处直接过滤。
    """
    if not strategy.social_monitor_id:
        return []

    query = select(SocialSlice).where(
        SocialSlice.monitor_id == strategy.social_monitor_id,
        SocialSlice.status == "completed",
    )
    result = await db.execute(query)
    slices = result.scalars().all()
    return [s.result_data for s in slices if s.result_data]


async def load_strategy_news_inputs(db: AsyncSession, strategy: Strategy) -> list[dict]:
    """加载策略关联的 NewsSlice 数据，供 Phase chains 使用。

    通过 strategy.news_monitor_id → NewsSlice.monitor_id 隐式关联。
    """
    if not strategy.news_monitor_id:
        return []

    from src.news_media.analysis.models import NewsSlice

    stmt = (
        select(NewsSlice)
        .where(
            NewsSlice.monitor_id == strategy.news_monitor_id,
            NewsSlice.status == "completed",
        )
        .order_by(NewsSlice.created_at)
    )
    result = await db.execute(stmt)
    slices = result.scalars().all()
    return [
        {"name": s.name, "result_data": s.result_data, "stats": s.stats}
        for s in slices
        if s.result_data
    ]


async def load_strategy_inputs_with_names(
    db: AsyncSession, strategy: Strategy
) -> list[tuple[str | None, dict]]:
    """加载策略输入数据（含切片名），用于覆盖度验证链。按 social_monitor_id 查询。

    与 load_strategy_inputs 一致，只返回 Stage2 完成的切片（status=completed）。
    """
    if not strategy.social_monitor_id:
        return []

    query = select(SocialSlice).where(
        SocialSlice.monitor_id == strategy.social_monitor_id,
        SocialSlice.status == "completed",
    )
    result = await db.execute(query)
    slices = result.scalars().all()
    return [(s.name, s.result_data) for s in slices if s.result_data]


async def _load_social_slice_refs(db: AsyncSession, strategy: Strategy) -> list[dict]:
    """加载策略社媒切片的 (id, name, monitor_id)，与 `load_strategy_inputs` 同序同过滤。

    用于 chain_inputs 元数据：记录本次 chain prompt 实际消费了哪些 SocialSlice，
    供前端 section 级"查看原始数据"drawer 使用。
    """
    if not strategy.social_monitor_id:
        return []

    query = select(SocialSlice.id, SocialSlice.name, SocialSlice.monitor_id).where(
        SocialSlice.monitor_id == strategy.social_monitor_id,
        SocialSlice.status == "completed",
    )
    result = await db.execute(query)
    return [
        {"id": row.id, "name": row.name, "monitor_id": row.monitor_id}
        for row in result.all()
    ]


async def _load_news_slice_refs(db: AsyncSession, strategy: Strategy) -> list[dict]:
    """加载策略新闻切片的 (id, name, monitor_id)，与 `load_strategy_news_inputs` 同序同过滤。"""
    if not strategy.news_monitor_id:
        return []

    from src.news_media.analysis.models import NewsSlice as _NewsSlice

    stmt = (
        select(_NewsSlice.id, _NewsSlice.name, _NewsSlice.monitor_id)
        .where(
            _NewsSlice.monitor_id == strategy.news_monitor_id,
            _NewsSlice.status == "completed",
        )
        .order_by(_NewsSlice.created_at)
    )
    result = await db.execute(stmt)
    return [
        {"id": row.id, "name": row.name, "monitor_id": row.monitor_id}
        for row in result.all()
    ]


async def _load_social_dapan(
    db: AsyncSession, strategy: Strategy
) -> tuple[dict | None, dict | None]:
    """加载策略的社媒【大盘】切片（meta.subject 空 + 有 sov_ranking）的 result_data 及溯源 ref。

    供 market_report 第 1/2 层做媒体 × 消费者交叉：
    - Landscape 用 result_data 投影（sov organic/promo + group_share + overview）做竞争交叉；
    - Agenda Map 用其话题（见 `_project_consumer_interest`）验证 attention_gaps。
    设计：媒体 SoV 可被 PR/投放放大，社媒大盘的 organic/promo 拆分揭示买不动的真实口碑。选**大盘**
    （对称采集、SoV/organic 公平），**不用聚焦**（单品牌深挖致 SoV 虚高）。按 id 升序取首个，确定性。
    返回的 ref（id/name/monitor_id）写入 chain_inputs，让前端"数据来源/查看证据"显示该社媒切片。
    无（纯 market_report / 无大盘社媒切片）时返回 (None, None)，调用方降级为媒体纯。
    """
    if not strategy.social_monitor_id:
        return None, None
    result = await db.execute(
        select(SocialSlice)
        .where(
            SocialSlice.monitor_id == strategy.social_monitor_id,
            SocialSlice.status == "completed",
        )
        .order_by(SocialSlice.id)
    )
    for s in result.scalars().all():
        # 用表列 s.subject 判定大盘/聚焦（权威，与 result_data 解耦；meta.subject 可能为空而误判）
        if (s.subject or "").strip():
            continue  # 跳过聚焦切片（SoV 因单品牌深挖虚高，不做基准）
        rd = s.result_data
        if not isinstance(rd, dict):
            continue
        if ((rd.get("layers") or {}).get("landscape") or {}).get("sov_ranking"):
            return rd, {"id": s.id, "name": s.name, "monitor_id": s.monitor_id}
    return None, None


def _project_consumer_interest(dapan: dict | None) -> dict | None:
    """从社媒大盘 result_data 投影消费者关注信号（话题 + 未满足需求），供 Agenda Map 的
    attention_gaps 验证。

    用 `organic_heat`（自然讨论）衡量"消费者真在意"——总热度可被推广刷高，会把软广炒热的话题
    误判成真实盲区；`organic_sentiment` 定 risk(负) vs opportunity(正)。无有效话题/需求时返回 None。
    """
    if not isinstance(dapan, dict):
        return None
    intent = (dapan.get("layers") or {}).get("intent") or {}
    topic_radar = intent.get("topic_radar") or {}
    top_topics: list[dict] = []
    for bucket in ("pains", "gains", "controversies"):
        for t in (topic_radar.get(bucket) or [])[:5]:
            if isinstance(t, dict) and t.get("name"):
                top_topics.append(
                    {
                        "name": t.get("name"),
                        "type": bucket,
                        "organic_heat": t.get("organic_heat"),
                        "organic_sentiment": t.get("organic_sentiment"),
                    }
                )
    unmet = [
        {
            "name": u.get("name"),
            "organic_heat": u.get("organic_heat"),
            "organic_sentiment": u.get("organic_sentiment"),
        }
        for u in (intent.get("unmet_needs") or [])[:8]
        if isinstance(u, dict) and u.get("name")
    ]
    if not top_topics and not unmet:
        return None
    return {"top_topics": top_topics, "unmet_needs": unmet}


def _build_chain_inputs(
    *,
    social_slice_refs: list[dict],
    news_slice_refs: list[dict],
    research_task_id: int | None,
    creative_task_id: int | None = None,
) -> dict[str, Any]:
    """构造 chain_inputs 元数据：本次 LLM 调用 prompt 中实际注入的上游数据 ID 清单。

    与 LLM 输出无关，纯由 orchestrator 在调用前确定，不存在幻觉风险。
    供前端 section 级"查看原始数据"drawer 反查上游切片 / 研究产出。
    """
    inputs: dict[str, Any] = {
        "social_slices": [
            {"id": r["id"], "name": r.get("name"), "monitor_id": r.get("monitor_id")}
            for r in social_slice_refs
        ],
        "news_slices": [
            {"id": r["id"], "name": r.get("name"), "monitor_id": r.get("monitor_id")}
            for r in news_slice_refs
        ],
        "research_findings": (
            [{"id": research_task_id, "profile": "industry"}]
            if research_task_id
            else []
        ),
        "creative_references": (
            [{"id": creative_task_id, "profile": "creative"}]
            if creative_task_id
            else []
        ),
    }
    return inputs


# ==================== 生成 + 编辑 ====================

# 状态流转顺序（含两条产出路径）
#
# campaign_strategy 路径：ready → insight_done → brand_role_done → completed
# market_report 路径：  ready → agenda_map_done → landscape_done → completed
#
# 同层级共享 order，使 "至少完成某步" 的比较仍然有效：
# insight_done ≡ agenda_map_done（两条路径的第 1 层），
# brand_role_done ≡ landscape_done（两条路径的第 2 层）。
STATUS_ORDER = {
    "draft": 0,
    "planned": 1,
    "probing": 2,
    "collecting": 3,
    "ready": 4,
    "insight_done": 5,
    "brand_role_done": 6,
    "agenda_map_done": 5,
    "landscape_done": 6,
    "completed": 7,
}


async def _validate_has_slices(db: AsyncSession, strategy: Strategy) -> None:
    """校验策略已关联社媒切片（insight 层前置条件）。按 social_monitor_id 查询。"""
    if not strategy.social_monitor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先关联分析切片",
        )
    stmt = (
        select(SocialSlice.id)
        .where(SocialSlice.monitor_id == strategy.social_monitor_id)
        .limit(1)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先关联分析切片",
        )


async def _get_research_agent_status(
    db: AsyncSession, strategy_id: int, profile_name: str
) -> ResearchAgentStatus:
    """查询策略关联的指定 profile Research Agent 任务状态。"""
    try:
        from src.research_agent.models import ResearchTask as RT

        stmt = (
            select(RT)
            .where(RT.strategy_id == strategy_id, RT.profile_name == profile_name)
            .order_by(RT.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()
        if task:
            return ResearchAgentStatus(
                has_task=True, status=task.status or "", task_id=task.id
            )
    except Exception:
        pass
    return ResearchAgentStatus()


async def _retrieve_research_findings(
    db: AsyncSession, strategy: Strategy, stage_label: str
) -> tuple[int | None, dict | None]:
    """加载策略关联的最新已完成 industry profile ResearchTask。

    返回 (task_id, result_data) 元组：
    - 无任务/未完成 / 失败时返回 (None, None)
    - chain_inputs 元数据需要 task_id 反查，因此始终携带

    失败时优雅降级，不中断主流程。
    """
    try:
        from src.research_agent.models import ResearchTask

        stmt = (
            select(ResearchTask)
            .where(
                ResearchTask.strategy_id == strategy.id,
                ResearchTask.status == "completed",
                ResearchTask.profile_name == "industry",
            )
            .order_by(ResearchTask.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()

        if not task or not task.result_data:
            return (None, None)

        logger.info(
            "%s 加载行业研究发现: strategy=%d, research_task=%d",
            stage_label,
            strategy.id,
            task.id,
        )
        return (task.id, task.result_data)
    except Exception as e:
        logger.warning("%s 行业研究数据加载失败，降级为空: %s", stage_label, e)
        return (None, None)


async def _retrieve_creative_research_findings(
    db: AsyncSession, strategy: Strategy, stage_label: str
) -> tuple[int | None, dict | None]:
    """加载策略关联的最新已完成 creative profile ResearchTask。

    返回 (task_id, result_data) 元组，语义同 _retrieve_research_findings。
    仅 brand_strategy/full_strategy 路径的 Brand Role / Big Idea 层使用。
    """
    try:
        from src.research_agent.models import ResearchTask

        stmt = (
            select(ResearchTask)
            .where(
                ResearchTask.strategy_id == strategy.id,
                ResearchTask.status == "completed",
                ResearchTask.profile_name == "creative",
            )
            .order_by(ResearchTask.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()

        if not task or not task.result_data:
            return (None, None)

        logger.info(
            "%s 加载创意研究发现: strategy=%d, research_task=%d",
            stage_label,
            strategy.id,
            task.id,
        )
        return (task.id, task.result_data)
    except Exception as e:
        logger.warning("%s 创意研究数据加载失败，降级为空: %s", stage_label, e)
        return (None, None)


def _validate_slices_have_data(
    slices_data: list[dict],
    strategy: Strategy,
    news_slices_data: list[dict] | None = None,
) -> None:
    """校验切片是否有可供下游消费的分析数据

    campaign_strategy 路径强制要求 social_media 作为主源——insight/brand_role/big_idea 的 prompt
    结构性依赖消费者声音（KOL/topic_aspects/pains/gains 等），纯新闻数据跑不出
    Tension / Brand Social Role / Big Idea。news_media 只作为补充视角存在。

    market_report 路径以 news_media 为主源，social_media 为可选补充。

    注意：slices_data / news_slices_data 由 load_strategy_inputs / load_strategy_news_inputs
    加载，两者均只返回 status=completed 的切片。因此此处"为空"的语义是
    "切片聚合分析尚未就绪或已失败"，而非"切片根本不存在"——提示文案按此口径。
    """
    social_msg = "社媒切片聚合分析尚未就绪（Stage2 未完成或失败），请在数据就绪后重试。"
    news_msg = "新闻切片分析尚未就绪或已失败，请在数据就绪后重试。"

    output_type = strategy.output_type or "campaign_strategy"

    if output_type == "campaign_strategy":
        if not slices_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"campaign_strategy 产出路径依赖社媒切片作为消费者声音主源：{social_msg}",
            )
        return

    if output_type == "market_report":
        if not news_slices_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"market_report 产出路径依赖新闻切片作为主源：{news_msg}",
            )
        return

    if output_type == "full_strategy":
        if not slices_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"full_strategy 产出路径依赖社媒切片作为消费者声音主源：{social_msg}",
            )
        if not news_slices_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"full_strategy 产出路径依赖新闻切片作为竞争格局主源：{news_msg}",
            )
        return

    # 未知 output_type：按旧的宽松校验兜底
    if not slices_data and not news_slices_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略关联的切片尚未完成分析",
        )


def _build_data_provenance(
    slices_data: list[dict],
    news_slices_data: list[dict],
    *,
    primary_channel: str,
    research_findings: str = "",
) -> dict[str, Any]:
    """构造本次 Phase 生成的数据来源记录，采用两层结构：

    - primary: 驱动产出路径的主数据通道（社媒切片 or 新闻切片）
    - research: 行业研究视角（Research Agent 自动搜索分析，与主通道平权的第三视角）

    primary 决定"走哪条产出路径"，research 提供"行业事实校验"，
    两者在分析权重上平等，但在数据流水线上角色不同。
    """
    primary: dict[str, Any] = {
        "channel": primary_channel,
        "social_media_slice_count": len(slices_data),
        "news_media_slice_count": len(news_slices_data),
    }
    research: dict[str, Any] = {
        "industry_research": bool(research_findings and research_findings.strip()),
    }
    return {"primary": primary, "research": research}


async def generate_insight(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 campaign_strategy 第 1 层 (洞察): Social Tension + Brand Opportunity"""
    await _validate_has_slices(db, strategy)

    # full_strategy 路径：Insight 在 Landscape 完成后运行，需先验证 Landscape 结果已存在
    if strategy.output_type == "full_strategy" and strategy.landscape_result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="full_strategy 路径：请先完成 Landscape（竞争格局）分析，再生成 Insight 层",
        )

    # 校验切片 Stage2 流水线已完成（campaign_strategy 三层都依赖 intent/focus 层数据）
    if strategy.social_monitor_id:
        stage2_check = await db.execute(
            select(SocialSlice.result_data).where(
                SocialSlice.monitor_id == strategy.social_monitor_id
            )
        )
        for rd in stage2_check.scalars().all():
            pipeline = (rd or {}).get("pipeline") or {}
            stage2 = pipeline.get("stage2") or {}
            if stage2.get("status") and stage2["status"] != "completed":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="切片分析流水线尚未完成，请稍后再生成洞察层",
                )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)
    social_slice_refs = await _load_social_slice_refs(db, strategy)
    news_slice_refs = await _load_news_slice_refs(db, strategy)

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "Insight"
    )
    from src.llm.chains.strategy.research_findings import format_research_for_insight

    research_findings_text = format_research_for_insight(research_result)

    chain = create_insight_chain()
    inputs = format_slice_data_for_insight(
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
        news_slices=news_slices_data,  # 原始新闻切片始终注入（一阶事实信号）
        slice_refs=social_slice_refs,
        news_slice_refs=news_slice_refs,
        research_findings=research_findings_text,
        coverage_check_result=strategy.coverage_check_result,
    )
    # full_strategy 路径：在原始新闻数据基础上，**额外**注入 Landscape 已结构化的
    # 竞争格局作为对标参考。Landscape 是二阶 LLM 解读（players / positioning_map /
    # discourse_battles），原始新闻是一阶事实信号（entities / quotes / event_clusters
    # 时序），两者互为补充而非替代——避免一阶信号被二阶过滤削弱。
    if strategy.output_type == "full_strategy" and strategy.landscape_result:
        inputs["landscape_context_section"] = (
            "## 竞争格局对标参考（Landscape 分析产出，full_strategy 模式）\n\n"
            "**说明**：以下是 Landscape chain 已生成的竞争格局结构化解读。请将其与上方"
            "原始新闻切片（news_media_section）和社媒切片（slice_data）共同使用——\n"
            "原始新闻是**一阶事实信号**（识别消费者-媒体分歧的依据），\n"
            "Landscape 是**已结构化的二阶解读**（提供「竞品已占据 / 未占据的位置」对标）。\n\n"
            "### 使用指引\n\n"
            "1. **消费者-媒体分歧识别**：基于原始新闻 + 社媒切片识别（不要直接用 Landscape，"
            "因为它已经过 LLM 二次过滤）\n"
            "2. **Brand Opportunity 验证**：识别出消费者机会后，对标 Landscape 的 "
            "positioning_map 和 attention_gaps——如果该位置在 Landscape 上是空白区，"
            "则为高置信度机会\n"
            "3. **evidence.source 引用规则**：原始信号引用 `news_media:...` / "
            "`social_slice:...`；对标 Landscape 时引用 `landscape:players[X]` 或 "
            "`landscape:positioning_map`，明确标注信号的二阶性质\n\n"
            "### Landscape 数据\n\n"
            + json.dumps(strategy.landscape_result, ensure_ascii=False, indent=2)
        )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_INSIGHT.value,
        source_count=len(slices_data) + len(news_slices_data),
        status="running",
        analysis_config={"strategy_id": strategy.id},
    )

    try:
        start = time.time()
        response = await chain.ainvoke(inputs)
        duration = time.time() - start

        result = parse_insight_response(response.content)
        result["data_provenance"] = _build_data_provenance(
            slices_data,
            news_slices_data,
            primary_channel="social_media",
            research_findings=research_findings_text,
        )
        result["chain_inputs"] = _build_chain_inputs(
            social_slice_refs=social_slice_refs,
            news_slice_refs=news_slice_refs,
            research_task_id=research_task_id,
        )
        logger.info("Strategy %d Insight 生成完成 (%.1fs)", strategy.id, duration)

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.insight_result = result
        # 重新生成 insight 后，tensions 可能变化，下游所有分支作废
        strategy.brand_strategy_branches = None
        # 立即按新 tensions 初始化 pending 骨架（让前端能展示 tension 列表 + 多选 UI）
        strategy.brand_strategy_branches = _ensure_branches_skeleton(strategy)
        # full_strategy：Insight 是 Landscape 之后的子阶段，status 保持 landscape_done
        # 避免从 landscape_done(6) 回退到 insight_done(5) 引发后续状态校验混乱
        if strategy.output_type != "full_strategy":
            strategy.status = "insight_done"

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error(
            "Strategy %d Insight 生成失败: %s", strategy.id, exc, exc_info=True
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


def _build_tension_summary(tension: dict) -> str:
    """从 tension 构造一句话摘要（≤80 字符），用于 UI 快速参考。"""
    statement = (tension.get("statement") or "").strip()
    if len(statement) <= 80:
        return statement
    return statement[:77] + "..."


def _ensure_branches_skeleton(strategy: Strategy) -> list[dict]:
    """从 insight_result 初始化或刷新 branches 骨架。

    - tensions 数量增加（refine 后）：补齐缺失 branches
    - tensions 数量减少：保留所有现有 branches（不删旧产出，用户可手动删）
    - 已存在的 branch 不动（保留 brand_role / big_idea 已生成结果）
    """
    insight = strategy.insight_result or {}
    tensions = insight.get("social_tensions") or []
    branches = list(strategy.brand_strategy_branches or [])
    existing_ids = {b.get("tension_id") for b in branches if isinstance(b, dict)}

    for idx, tension in enumerate(tensions):
        if idx in existing_ids:
            continue
        branches.append(
            {
                "tension_id": idx,
                "tension_summary": _build_tension_summary(tension),
                "brand_role": None,
                "big_idea": None,
                "selected": False,
                "status": "pending",
            }
        )
    # 按 tension_id 排序保持稳定顺序
    branches.sort(key=lambda b: b.get("tension_id", 0))
    return branches


async def _run_brand_role_for_one_branch(
    branch_idx: int,
    selected_tension_id: int,
    insight_result: dict,
    slices_data: list[dict],
    news_slices_data: list[dict],
    brief: dict | None,
    research_design: dict | None,
    research_findings_text: str,
    creative_references_text: str,
    chain_inputs: dict[str, Any],
    slice_refs: list[dict] | None = None,
    news_slice_refs: list[dict] | None = None,
) -> tuple[int, dict | None, dict | None, float, Exception | None]:
    """单分支 brand_role 调用 worker（不碰 DB session）。

    Returns:
        (branch_idx, result, token_usage, duration, error)
    """
    chain = create_brand_role_chain()
    inputs = format_data_for_brand_role(
        insight_result,
        selected_tension_id=selected_tension_id,
        slices=slices_data,
        brief=brief,
        research_design=research_design,
        news_slices=news_slices_data,
        slice_refs=slice_refs,
        news_slice_refs=news_slice_refs,
        research_findings=research_findings_text,
        creative_references=creative_references_text,
    )
    start = time.time()
    try:
        response = await chain.ainvoke(inputs)
        duration = time.time() - start
        result = parse_brand_role_response(response.content)
        result["data_provenance"] = _build_data_provenance(
            slices_data,
            news_slices_data,
            primary_channel="social_media",
            research_findings=research_findings_text,
        )
        result["chain_inputs"] = chain_inputs
        return (
            branch_idx,
            result,
            extract_token_usage(response, duration_seconds=duration),
            duration,
            None,
        )
    except Exception as exc:
        return (branch_idx, None, None, time.time() - start, exc)


async def _run_big_idea_for_one_branch(
    branch_idx: int,
    selected_tension_id: int,
    branch_brand_role: dict,
    insight_result: dict,
    slices_data: list[dict],
    news_slices_data: list[dict],
    brief: dict | None,
    research_design: dict | None,
    research_findings_text: str,
    creative_references_text: str,
    chain_inputs: dict[str, Any],
    slice_refs: list[dict] | None = None,
    news_slice_refs: list[dict] | None = None,
) -> tuple[int, dict | None, dict | None, float, Exception | None]:
    """单分支 big_idea 调用 worker（不碰 DB session）。"""
    chain = create_big_idea_chain()
    inputs = format_data_for_big_idea(
        insight_result,
        selected_tension_id=selected_tension_id,
        branch_brand_role=branch_brand_role,
        slices=slices_data,
        brief=brief,
        research_design=research_design,
        news_slices=news_slices_data,
        slice_refs=slice_refs,
        news_slice_refs=news_slice_refs,
        research_findings=research_findings_text,
        creative_references=creative_references_text,
    )
    start = time.time()
    try:
        response = await chain.ainvoke(inputs)
        duration = time.time() - start
        result = parse_big_idea_response(response.content)
        result["data_provenance"] = _build_data_provenance(
            slices_data,
            news_slices_data,
            primary_channel="social_media",
            research_findings=research_findings_text,
        )
        result["chain_inputs"] = chain_inputs
        return (
            branch_idx,
            result,
            extract_token_usage(response, duration_seconds=duration),
            duration,
            None,
        )
    except Exception as exc:
        return (branch_idx, None, None, time.time() - start, exc)


async def generate_brand_role(
    db: AsyncSession,
    strategy: Strategy,
    *,
    tension_ids: list[int] | None = None,
) -> Strategy:
    """生成 campaign_strategy 第 2 层 (策略): 多分支 Brand Role 并行生成

    两种模式：
    - tension_ids=None：**全跑模式**——重置所有分支 brand_role/big_idea/selected/status，
      然后并行跑全部分支（"重新全跑"语义）
    - tension_ids=[...]：**子集模式**——仅清空指定分支的 brand_role + big_idea + status，
      并仅对它们并行跑；未指定的分支保留当前状态（含已生成的 brand_role / big_idea / selected）

    单分支失败不影响其他分支（独立 try/except，failed branch 写 error_message 仍 commit）。
    """
    # full_strategy：status 在 landscape_done(6) 之后不经过 insight_done(5)，
    # 用 insight_result 存在性代替 status 校验
    if strategy.output_type == "full_strategy":
        if not strategy.insight_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="full_strategy 路径：请先完成 Insight（洞察层）分析，再生成 Brand Role",
            )
    elif STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["insight_done"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成并确认洞察层",
        )

    tensions = (strategy.insight_result or {}).get("social_tensions") or []
    if not tensions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Insight 阶段未产出任何 tensions，无法推导 brand_role",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)
    social_slice_refs = await _load_social_slice_refs(db, strategy)
    news_slice_refs = await _load_news_slice_refs(db, strategy)

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "BrandRole"
    )
    from src.llm.chains.strategy.research_findings import (
        format_research_for_brand_role,
        format_creative_for_brand_role,
    )

    research_findings_text = format_research_for_brand_role(research_result)

    creative_task_id, creative_result = await _retrieve_creative_research_findings(
        db, strategy, "BrandRole"
    )
    creative_references_text = format_creative_for_brand_role(creative_result)

    chain_inputs = _build_chain_inputs(
        social_slice_refs=social_slice_refs,
        news_slice_refs=news_slice_refs,
        research_task_id=research_task_id,
        creative_task_id=creative_task_id,
    )

    # 初始化/补齐分支骨架（覆盖所有 insight tensions）
    branches = _ensure_branches_skeleton(strategy)

    if tension_ids is None:
        # 全跑模式：重置所有分支
        for b in branches:
            b["brand_role"] = None
            b["big_idea"] = None
            b["selected"] = False
            b["status"] = "pending"
        branches_to_run = branches
    else:
        # 子集模式：严格校验所有 tension_ids 都存在；仅清空指定分支，保留其他（不动 selected）
        existing_ids = {b.get("tension_id") for b in branches}
        target_ids = set(tension_ids)
        unknown_ids = sorted(target_ids - existing_ids)
        if unknown_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tension_ids 包含不存在的分支: {unknown_ids}（已有分支 tension_id={sorted(existing_ids)}）",
            )
        branches_to_run = [b for b in branches if b.get("tension_id") in target_ids]
        if not branches_to_run:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tension_ids 不能为空",
            )
        for b in branches_to_run:
            b["brand_role"] = None
            b["big_idea"] = None
            b["status"] = "pending"

    # 创建跨分支 AnalysisJob（一次记录所有运行分支的总成本）
    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_BRAND_ROLE.value,
        source_count=len(slices_data) + len(news_slices_data),
        status="running",
        analysis_config={
            "strategy_id": strategy.id,
            "branch_count": len(branches_to_run),
            "subset_mode": tension_ids is not None,
            "target_tension_ids": tension_ids,
        },
    )

    overall_start = time.time()
    try:
        # 所有要跑的分支并行调用 LLM（不共享 DB session，纯外部 API 调用）
        results = await asyncio.gather(
            *[
                _run_brand_role_for_one_branch(
                    branch_idx=b["tension_id"],
                    selected_tension_id=b["tension_id"],
                    insight_result=strategy.insight_result,
                    slices_data=slices_data,
                    news_slices_data=news_slices_data,
                    brief=strategy.brand_brief,
                    research_design=strategy.research_design,
                    research_findings_text=research_findings_text,
                    creative_references_text=creative_references_text,
                    chain_inputs=chain_inputs,
                    slice_refs=social_slice_refs,
                    news_slice_refs=news_slice_refs,
                )
                for b in branches_to_run
            ]
        )

        # 写回 branches + 聚合 token usage（merge_token_usage_stats 处理嵌套
        # {summary, call_details} schema：summary 数字累加 + call_details 拼接，
        # 否则前端按总和读到的就是第一个分支的 summary，多分支统计漏算）
        success_count = 0
        failed_count = 0
        total_token_usage: dict | None = None
        for branch_idx, result, token_usage, duration, error in results:
            target = next(
                (b for b in branches if b.get("tension_id") == branch_idx), None
            )
            if target is None:
                continue
            if error is not None:
                target["status"] = "failed"
                target["brand_role"] = None
                target["error_message"] = str(error)[:500]
                failed_count += 1
                logger.error(
                    "Strategy %d branch %d brand_role 失败: %s",
                    strategy.id,
                    branch_idx,
                    error,
                )
            else:
                target["status"] = "brand_role_done"
                target["brand_role"] = result
                target.pop("error_message", None)
                success_count += 1
                if token_usage:
                    total_token_usage = merge_token_usage_stats(
                        total_token_usage, token_usage
                    )
                logger.info(
                    "Strategy %d branch %d brand_role 完成 (%.1fs)",
                    strategy.id,
                    branch_idx,
                    duration,
                )

        if success_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"所有 {len(branches_to_run)} 个分支的 brand_role 生成都失败",
            )

        strategy.brand_strategy_branches = branches
        flag_modified(strategy, "brand_strategy_branches")
        # 任一分支成功即推进 status；full_strategy 路径保持 landscape_done
        if strategy.output_type != "full_strategy":
            strategy.status = "brand_role_done"

        # 更新 AnalysisJob
        overall_duration = time.time() - overall_start
        job.status = (
            "completed" if failed_count == 0 else "completed"
        )  # 部分失败也算完成
        job.completed_at = datetime.now(timezone.utc)
        job.analyzed_count = success_count
        job.processing_time = int(overall_duration)
        job.token_usage = total_token_usage
        job.error_message = (
            f"{failed_count}/{len(branches_to_run)} 分支生成失败"
            if failed_count
            else None
        )

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error(
            "Strategy %d Brand Role 多分支生成失败: %s", strategy.id, exc, exc_info=True
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - overall_start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


async def generate_big_idea(
    db: AsyncSession,
    strategy: Strategy,
    *,
    tension_ids: list[int] | None = None,
) -> Strategy:
    """生成 campaign_strategy 第 3 层 (创意): 多分支 Big Idea 并行生成

    两种模式：
    - tension_ids=None：**全跑模式**——对所有 `brand_role` 已生成的分支并行跑 big_idea
    - tension_ids=[...]：**子集模式**——仅对指定的「且 brand_role 已生成」的分支跑

    无论哪种模式，都跳过 brand_role 未生成 / failed / pending 的分支（big_idea 依赖 brand_role）。
    单分支失败不影响其他分支。
    """
    # full_strategy：status 在 landscape_done(6) 之后不经过 brand_role_done(6)，
    # 用 brand_strategy_branches 是否含 brand_role 代替 status 校验
    branches = list(strategy.brand_strategy_branches or [])
    all_with_brand_role = [
        b for b in branches if isinstance(b, dict) and b.get("brand_role")
    ]

    if strategy.output_type == "full_strategy":
        if not all_with_brand_role:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="full_strategy 路径：请先完成 Brand Role（策略层）分析，再生成 Big Idea",
            )
    elif STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["brand_role_done"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成并确认策略层",
        )

    if not all_with_brand_role:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="所有分支的 brand_role 都未生成，无法推导 big_idea",
        )

    # 子集模式：严格校验所有 tension_ids 都对应「存在 + 已生成 brand_role」的分支
    if tension_ids is None:
        branches_to_run = all_with_brand_role
    else:
        existing_ids = {b.get("tension_id") for b in branches}
        ready_ids = {b.get("tension_id") for b in all_with_brand_role}
        target_ids = set(tension_ids)
        unknown_ids = sorted(target_ids - existing_ids)
        if unknown_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"tension_ids 包含不存在的分支: {unknown_ids}",
            )
        not_ready_ids = sorted(target_ids - ready_ids)
        if not_ready_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"以下分支尚未生成 brand_role，无法推导 big_idea: {not_ready_ids}"
                ),
            )
        if not target_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tension_ids 不能为空",
            )
        branches_to_run = [
            b for b in all_with_brand_role if b.get("tension_id") in target_ids
        ]

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)
    social_slice_refs = await _load_social_slice_refs(db, strategy)
    news_slice_refs = await _load_news_slice_refs(db, strategy)

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "BigIdea"
    )
    from src.llm.chains.strategy.research_findings import (
        format_research_for_big_idea,
        format_creative_for_big_idea,
    )

    research_findings_text = format_research_for_big_idea(research_result)

    creative_task_id, creative_result = await _retrieve_creative_research_findings(
        db, strategy, "BigIdea"
    )
    creative_references_text = format_creative_for_big_idea(creative_result)

    chain_inputs = _build_chain_inputs(
        social_slice_refs=social_slice_refs,
        news_slice_refs=news_slice_refs,
        research_task_id=research_task_id,
        creative_task_id=creative_task_id,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_BIG_IDEA.value,
        source_count=len(slices_data) + len(news_slices_data),
        status="running",
        analysis_config={
            "strategy_id": strategy.id,
            "branch_count": len(branches_to_run),
            "subset_mode": tension_ids is not None,
            "target_tension_ids": tension_ids,
        },
    )

    overall_start = time.time()
    try:
        # 对要跑的分支并行生成 big_idea
        results = await asyncio.gather(
            *[
                _run_big_idea_for_one_branch(
                    branch_idx=b["tension_id"],
                    selected_tension_id=b["tension_id"],
                    branch_brand_role=b["brand_role"],
                    insight_result=strategy.insight_result,
                    slices_data=slices_data,
                    news_slices_data=news_slices_data,
                    brief=strategy.brand_brief,
                    research_design=strategy.research_design,
                    research_findings_text=research_findings_text,
                    creative_references_text=creative_references_text,
                    chain_inputs=chain_inputs,
                    slice_refs=social_slice_refs,
                    news_slice_refs=news_slice_refs,
                )
                for b in branches_to_run
            ]
        )

        success_count = 0
        failed_count = 0
        # merge_token_usage_stats 处理嵌套 {summary, call_details} schema，
        # 详见 generate_brand_role 同位置注释
        total_token_usage: dict | None = None
        for branch_idx, result, token_usage, duration, error in results:
            target = next(
                (b for b in branches if b.get("tension_id") == branch_idx), None
            )
            if target is None:
                continue
            if error is not None:
                target["status"] = "failed"
                target["big_idea"] = None
                target["error_message"] = str(error)[:500]
                failed_count += 1
                logger.error(
                    "Strategy %d branch %d big_idea 失败: %s",
                    strategy.id,
                    branch_idx,
                    error,
                )
            else:
                target["status"] = "big_idea_done"
                target["big_idea"] = result
                target.pop("error_message", None)
                success_count += 1
                if token_usage:
                    total_token_usage = merge_token_usage_stats(
                        total_token_usage, token_usage
                    )
                logger.info(
                    "Strategy %d branch %d big_idea 完成 (%.1fs)",
                    strategy.id,
                    branch_idx,
                    duration,
                )

        if success_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"所有 {len(branches_to_run)} 个分支的 big_idea 生成都失败",
            )

        strategy.brand_strategy_branches = branches
        flag_modified(strategy, "brand_strategy_branches")
        strategy.status = "completed"

        overall_duration = time.time() - overall_start
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.analyzed_count = success_count
        job.processing_time = int(overall_duration)
        job.token_usage = total_token_usage
        job.error_message = (
            f"{failed_count}/{len(branches_to_run)} 分支生成失败"
            if failed_count
            else None
        )

        await db.commit()
        fire_notification(
            feishu_tmpl.big_idea_done_card(strategy.name, strategy.id),
            _strategy_open_ids(strategy),
        )
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error(
            "Strategy %d Big Idea 多分支生成失败: %s", strategy.id, exc, exc_info=True
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - overall_start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


async def select_branch(
    db: AsyncSession,
    strategy: Strategy,
    *,
    tension_id: int,
) -> Strategy:
    """将指定分支标记为 selected=true，其他分支 selected=false。

    selected 标志影响导出（仅导出 selected 分支）和 UI 默认展示。
    分支必须存在；selected 不要求该分支已完成 big_idea（允许用户选定一条进行中的方向）。
    """
    branches = list(strategy.brand_strategy_branches or [])
    target = next(
        (
            b
            for b in branches
            if isinstance(b, dict) and b.get("tension_id") == tension_id
        ),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"分支 tension_id={tension_id} 不存在",
        )
    for b in branches:
        if isinstance(b, dict):
            b["selected"] = b.get("tension_id") == tension_id

    strategy.brand_strategy_branches = branches
    flag_modified(strategy, "brand_strategy_branches")
    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def regenerate_brand_role_branch(
    db: AsyncSession,
    strategy: Strategy,
    *,
    tension_id: int,
) -> Strategy:
    """单分支重生成 brand_role：仅刷新指定 tension 的 brand_role + 清空其 big_idea。"""
    if strategy.output_type and strategy.output_type not in (
        "campaign_strategy",
        "full_strategy",
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"当前策略产出路径为 {strategy.output_type}，无法生成 brand_role",
        )
    if not strategy.insight_result:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成 Insight（洞察层）分析，再生成 Brand Role",
        )

    branches = list(strategy.brand_strategy_branches or [])
    target = next(
        (
            b
            for b in branches
            if isinstance(b, dict) and b.get("tension_id") == tension_id
        ),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"分支 tension_id={tension_id} 不存在",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)
    social_slice_refs = await _load_social_slice_refs(db, strategy)
    news_slice_refs = await _load_news_slice_refs(db, strategy)

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "BrandRole"
    )
    from src.llm.chains.strategy.research_findings import (
        format_creative_for_brand_role,
        format_research_for_brand_role,
    )

    research_findings_text = format_research_for_brand_role(research_result)

    creative_task_id, creative_result = await _retrieve_creative_research_findings(
        db, strategy, "BrandRole"
    )
    creative_references_text = format_creative_for_brand_role(creative_result)

    chain_inputs = _build_chain_inputs(
        social_slice_refs=social_slice_refs,
        news_slice_refs=news_slice_refs,
        research_task_id=research_task_id,
        creative_task_id=creative_task_id,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_BRAND_ROLE.value,
        source_count=len(slices_data) + len(news_slices_data),
        status="running",
        analysis_config={
            "strategy_id": strategy.id,
            "branch_count": 1,
            "tension_id": tension_id,
        },
    )

    overall_start = time.time()
    try:
        (
            branch_idx,
            result,
            token_usage,
            duration,
            error,
        ) = await _run_brand_role_for_one_branch(
            branch_idx=tension_id,
            selected_tension_id=tension_id,
            insight_result=strategy.insight_result,
            slices_data=slices_data,
            news_slices_data=news_slices_data,
            brief=strategy.brand_brief,
            research_design=strategy.research_design,
            research_findings_text=research_findings_text,
            creative_references_text=creative_references_text,
            chain_inputs=chain_inputs,
            slice_refs=social_slice_refs,
            news_slice_refs=news_slice_refs,
        )

        if error is not None:
            target["status"] = "failed"
            target["brand_role"] = None
            target["error_message"] = str(error)[:500]
            job.status = "failed"
            job.error_message = str(error)[:500]
        else:
            target["brand_role"] = result
            target["big_idea"] = None  # 上游变更，下游作废
            target["status"] = "brand_role_done"
            target.pop("error_message", None)
            job.status = "completed"
            job.analyzed_count = 1
            job.token_usage = token_usage or None

        job.completed_at = datetime.now(timezone.utc)
        job.processing_time = int(time.time() - overall_start)

        strategy.brand_strategy_branches = branches
        flag_modified(strategy, "brand_strategy_branches")
        if error is None and strategy.output_type != "full_strategy":
            strategy.status = "brand_role_done"

        await db.commit()
        if error is not None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"分支 tension_id={tension_id} brand_role 生成失败: {error}",
            )
        logger.info(
            "Strategy %d branch %d brand_role 单分支重生成完成 (%.1fs)",
            strategy.id,
            tension_id,
            duration,
        )
        return await get_strategy_by_id(db, strategy.id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Strategy %d branch %d brand_role 单分支重生成失败: %s",
            strategy.id,
            tension_id,
            exc,
            exc_info=True,
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - overall_start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


async def regenerate_big_idea_branch(
    db: AsyncSession,
    strategy: Strategy,
    *,
    tension_id: int,
) -> Strategy:
    """单分支重生成 big_idea：仅刷新指定 tension 的 big_idea。"""
    if strategy.output_type and strategy.output_type not in (
        "campaign_strategy",
        "full_strategy",
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"当前策略产出路径为 {strategy.output_type}，无法生成 big_idea",
        )

    branches = list(strategy.brand_strategy_branches or [])
    target = next(
        (
            b
            for b in branches
            if isinstance(b, dict) and b.get("tension_id") == tension_id
        ),
        None,
    )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"分支 tension_id={tension_id} 不存在",
        )
    if not target.get("brand_role"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"分支 tension_id={tension_id} 尚未生成 brand_role，无法推导 big_idea",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)
    social_slice_refs = await _load_social_slice_refs(db, strategy)
    news_slice_refs = await _load_news_slice_refs(db, strategy)

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "BigIdea"
    )
    from src.llm.chains.strategy.research_findings import (
        format_creative_for_big_idea,
        format_research_for_big_idea,
    )

    research_findings_text = format_research_for_big_idea(research_result)

    creative_task_id, creative_result = await _retrieve_creative_research_findings(
        db, strategy, "BigIdea"
    )
    creative_references_text = format_creative_for_big_idea(creative_result)

    chain_inputs = _build_chain_inputs(
        social_slice_refs=social_slice_refs,
        news_slice_refs=news_slice_refs,
        research_task_id=research_task_id,
        creative_task_id=creative_task_id,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_BIG_IDEA.value,
        source_count=len(slices_data) + len(news_slices_data),
        status="running",
        analysis_config={
            "strategy_id": strategy.id,
            "branch_count": 1,
            "tension_id": tension_id,
        },
    )

    overall_start = time.time()
    try:
        (
            branch_idx,
            result,
            token_usage,
            duration,
            error,
        ) = await _run_big_idea_for_one_branch(
            branch_idx=tension_id,
            selected_tension_id=tension_id,
            branch_brand_role=target["brand_role"],
            insight_result=strategy.insight_result,
            slices_data=slices_data,
            news_slices_data=news_slices_data,
            brief=strategy.brand_brief,
            research_design=strategy.research_design,
            research_findings_text=research_findings_text,
            creative_references_text=creative_references_text,
            chain_inputs=chain_inputs,
            slice_refs=social_slice_refs,
            news_slice_refs=news_slice_refs,
        )

        if error is not None:
            target["status"] = "failed"
            target["big_idea"] = None
            target["error_message"] = str(error)[:500]
            job.status = "failed"
            job.error_message = str(error)[:500]
        else:
            target["big_idea"] = result
            target["status"] = "big_idea_done"
            target.pop("error_message", None)
            job.status = "completed"
            job.analyzed_count = 1
            job.token_usage = token_usage or None

        job.completed_at = datetime.now(timezone.utc)
        job.processing_time = int(time.time() - overall_start)

        strategy.brand_strategy_branches = branches
        flag_modified(strategy, "brand_strategy_branches")
        if error is None and strategy.output_type != "full_strategy":
            strategy.status = "completed"

        await db.commit()
        if error is not None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"分支 tension_id={tension_id} big_idea 生成失败: {error}",
            )
        logger.info(
            "Strategy %d branch %d big_idea 单分支重生成完成 (%.1fs)",
            strategy.id,
            tension_id,
            duration,
        )
        return await get_strategy_by_id(db, strategy.id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Strategy %d branch %d big_idea 单分支重生成失败: %s",
            strategy.id,
            tension_id,
            exc,
            exc_info=True,
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - overall_start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


# Token 累加统一走 src.llm.utils.merge_token_usage_stats（处理嵌套
# {summary, call_details} schema）。早期 _merge_token_usage_dicts 用 shallow
# 数字累加，碰到 dict / list 字段会保留首个值——summary 累加失效，
# 多分支统计实际只反映第一个分支。已移除。


# ==================== market_report 路径 agenda_map / landscape / strategic_brief ====================


def _validate_market_report_output_type(strategy: Strategy) -> None:
    """防御性校验：market_report 层只能在 output_type=market_report/full_strategy 的策略上生成"""
    if strategy.output_type not in ("market_report", "full_strategy"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"当前策略产出路径为 {strategy.output_type or 'campaign_strategy'}，"
                "无法生成 market_report 层。请在研究计划确认时选择 market_report 或 full_strategy 路径。"
            ),
        )


_BRAND_STRATEGY_STAGES: tuple[str, ...] = ("insight", "brand_role", "big_idea")
_MARKET_REPORT_STAGES: tuple[str, ...] = ("agenda_map", "landscape", "strategic_brief")


async def edit_brand_strategy_result(
    db: AsyncSession,
    strategy: Strategy,
    *,
    stage: str,
    result: dict[str, Any],
    tension_id: int | None = None,
) -> Strategy:
    """编辑 campaign_strategy 路径的 insight / brand_role / big_idea 结果。

    - insight: 单一结果。编辑会让所有分支作废（tensions 可能变化），
      下次生成 brand_role 时会按新 tensions 重建分支骨架。
    - brand_role / big_idea: 多分支，必须传 tension_id 指定要编辑的分支；
      编辑 brand_role 会清空该分支的 big_idea。
    """
    if strategy.output_type and strategy.output_type not in (
        "campaign_strategy",
        "full_strategy",
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"当前策略产出路径为 {strategy.output_type}，"
                "无法编辑 campaign_strategy 结果"
            ),
        )

    if stage not in _BRAND_STRATEGY_STAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"stage 必须为 insight/brand_role/big_idea，收到 {stage}",
        )

    is_full = strategy.output_type == "full_strategy"

    if stage == "insight":
        if not strategy.insight_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="insight 层尚未生成，无法编辑",
            )
        strategy.insight_result = result
        # 编辑 insight 后 tensions 可能变化，下游所有分支作废 + 按新 tensions 重建 pending 骨架
        strategy.brand_strategy_branches = None
        strategy.brand_strategy_branches = _ensure_branches_skeleton(strategy)
        # full_strategy：insight 是 landscape 之后的子阶段，保持 landscape_done
        if not is_full:
            strategy.status = "insight_done"
        flag_modified(strategy, "insight_result")
    else:
        # brand_role / big_idea：按分支编辑
        if tension_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"编辑 {stage} 必须指定 tension_id",
            )
        branches = list(strategy.brand_strategy_branches or [])
        target = next(
            (
                b
                for b in branches
                if isinstance(b, dict) and b.get("tension_id") == tension_id
            ),
            None,
        )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"分支 tension_id={tension_id} 不存在",
            )

        if stage == "brand_role":
            if not target.get("brand_role"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"分支 tension_id={tension_id} 的 brand_role 尚未生成，无法编辑",
                )
            target["brand_role"] = result
            # 清空该分支下游 big_idea
            target["big_idea"] = None
            target["status"] = "brand_role_done"
            if not is_full:
                # 任何分支有 brand_role 即视为推进到 brand_role_done
                strategy.status = "brand_role_done"
        else:  # stage == "big_idea"
            if not target.get("big_idea"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"分支 tension_id={tension_id} 的 big_idea 尚未生成，无法编辑",
                )
            target["big_idea"] = result
            target["status"] = "big_idea_done"
            if not is_full:
                strategy.status = "completed"

        strategy.brand_strategy_branches = branches
        flag_modified(strategy, "brand_strategy_branches")

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def edit_market_report_result(
    db: AsyncSession,
    strategy: Strategy,
    *,
    stage: str,
    result: dict[str, Any],
) -> Strategy:
    """编辑 market_report 路径的 agenda_map / landscape / strategic_brief 结果
    （级联清除下游）。"""
    if strategy.output_type not in ("market_report", "full_strategy"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"当前策略产出路径为 {strategy.output_type or 'campaign_strategy'}，"
                "无法编辑 market_report 结果"
            ),
        )

    if stage not in _MARKET_REPORT_STAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(f"stage 必须为 agenda_map/landscape/strategic_brief，收到 {stage}"),
        )

    is_full = strategy.output_type == "full_strategy"

    if stage == "agenda_map":
        if not strategy.agenda_map_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="agenda_map 层尚未生成，无法编辑",
            )
        strategy.agenda_map_result = result
        strategy.landscape_result = None
        strategy.strategic_brief_result = None
        # full_strategy：清空依赖 landscape 的 insight/brand_role/big_idea
        if is_full:
            strategy.insight_result = None
            strategy.brand_strategy_branches = None
        strategy.status = "agenda_map_done"
    elif stage == "landscape":
        if not strategy.landscape_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="landscape 层尚未生成，无法编辑",
            )
        strategy.landscape_result = result
        strategy.strategic_brief_result = None
        # full_strategy：清空依赖 landscape 的 insight/brand_role/big_idea
        if is_full:
            strategy.insight_result = None
            strategy.brand_strategy_branches = None
        strategy.status = "landscape_done"
    else:  # stage == "strategic_brief"
        if not strategy.strategic_brief_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="strategic_brief 层尚未生成，无法编辑",
            )
        strategy.strategic_brief_result = result
        strategy.status = "completed"

    flag_modified(strategy, f"{stage}_result")
    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def generate_agenda_map(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 Market Report 第 1 层：媒体议程图 (Agenda Map)"""
    _validate_market_report_output_type(strategy)

    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["ready"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="数据尚未就绪，无法生成媒体议程图",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)
    news_slice_refs = await _load_news_slice_refs(db, strategy)

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "AgendaMap"
    )
    from src.llm.chains.strategy.research_findings import format_research_for_agenda_map

    research_findings_text = format_research_for_agenda_map(research_result)

    # full_strategy：载入社媒大盘切片，用其消费者自然讨论话题验证 attention_gaps。
    # ref 写入 chain_inputs 作数据来源；market_report / 无社媒大盘 → (None, None) → 降级媒体纯。
    dapan_result, dapan_ref = (
        await _load_social_dapan(db, strategy)
        if strategy.output_type == "full_strategy"
        else (None, None)
    )

    chain = create_agenda_map_chain()
    inputs = format_inputs_for_agenda_map(
        news_slices=news_slices_data,
        brief=strategy.brand_brief,
        research_design=strategy.research_design,
        news_slice_refs=news_slice_refs,
        research_findings=research_findings_text,
        coverage_check_result=strategy.coverage_check_result,
        consumer_interest=_project_consumer_interest(dapan_result),
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_AGENDA_MAP.value,
        source_count=len(news_slices_data),
        status="running",
        analysis_config={"strategy_id": strategy.id},
    )

    try:
        start = time.time()
        response = await chain.ainvoke(inputs)
        duration = time.time() - start

        result = parse_agenda_map_response(response.content)
        # 社媒计数按实际交叉的大盘切片记（0/1），与 chain_inputs 一致——不计入未被消费的
        # 其余社媒切片（如聚焦切片），避免高估社媒在媒体侧产出的角色。
        result["data_provenance"] = _build_data_provenance(
            [dapan_result] if dapan_result else [],
            news_slices_data,
            primary_channel="news_media",
            research_findings=research_findings_text,
        )
        # full_strategy 下 agenda 交叉了社媒大盘切片做 attention_gaps 验证 → 写入数据来源；
        # market_report 无社媒切片则为空。
        result["chain_inputs"] = _build_chain_inputs(
            social_slice_refs=[dapan_ref] if dapan_ref else [],
            news_slice_refs=news_slice_refs,
            research_task_id=research_task_id,
        )
        logger.info("Strategy %d Agenda Map 生成完成 (%.1fs)", strategy.id, duration)

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.agenda_map_result = result
        # 重新生成 agenda_map 时，下游所有结果必须作废
        strategy.landscape_result = None
        strategy.strategic_brief_result = None
        # full_strategy：insight/brand_role/big_idea 依赖 landscape，需同步清空
        if strategy.output_type == "full_strategy":
            strategy.insight_result = None
            strategy.brand_strategy_branches = None
        strategy.status = "agenda_map_done"

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error(
            "Strategy %d Agenda Map 生成失败: %s", strategy.id, exc, exc_info=True
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


async def generate_landscape(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 Market Report 第 2 层：竞争格局 (Landscape)"""
    _validate_market_report_output_type(strategy)

    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["agenda_map_done"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成并确认 Agenda Map",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)
    news_slice_refs = await _load_news_slice_refs(db, strategy)

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "Landscape"
    )
    from src.llm.chains.strategy.research_findings import format_research_for_landscape

    research_findings_text = format_research_for_landscape(research_result)

    # full_strategy：载入社媒大盘切片做媒体 × 消费者竞争交叉（organic/promo 揭示买不动的真实
    # 口碑）。ref 写入 chain_inputs 作数据来源；market_report / 无社媒大盘 → (None, None) → 媒体纯。
    dapan_result, dapan_ref = (
        await _load_social_dapan(db, strategy)
        if strategy.output_type == "full_strategy"
        else (None, None)
    )

    chain = create_landscape_chain()
    inputs = format_inputs_for_landscape(
        agenda_map_result=strategy.agenda_map_result,
        news_slices=news_slices_data,
        brief=strategy.brand_brief,
        research_design=strategy.research_design,
        news_slice_refs=news_slice_refs,
        research_findings=research_findings_text,
        social_dapan=dapan_result,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_LANDSCAPE.value,
        source_count=len(news_slices_data),
        status="running",
        analysis_config={"strategy_id": strategy.id},
    )

    try:
        start = time.time()
        response = await chain.ainvoke(inputs)
        duration = time.time() - start

        result = parse_landscape_response(response.content)
        # 社媒计数按实际交叉的大盘切片记（0/1），与 chain_inputs 一致——不计入未被消费的
        # 其余社媒切片（如聚焦切片），避免高估社媒在媒体侧产出的角色。
        result["data_provenance"] = _build_data_provenance(
            [dapan_result] if dapan_result else [],
            news_slices_data,
            primary_channel="news_media",
            research_findings=research_findings_text,
        )
        # full_strategy 下 landscape 交叉了社媒大盘切片做消费者竞争对照 → 写入数据来源；
        # market_report 无社媒切片则为空。
        result["chain_inputs"] = _build_chain_inputs(
            social_slice_refs=[dapan_ref] if dapan_ref else [],
            news_slice_refs=news_slice_refs,
            research_task_id=research_task_id,
        )
        logger.info("Strategy %d Landscape 生成完成 (%.1fs)", strategy.id, duration)

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.landscape_result = result
        strategy.strategic_brief_result = None
        # full_strategy：insight/brand_role/big_idea 依赖 landscape，重新生成时需清空
        if strategy.output_type == "full_strategy":
            strategy.insight_result = None
            strategy.brand_strategy_branches = None
        strategy.status = "landscape_done"

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error(
            "Strategy %d Landscape 生成失败: %s", strategy.id, exc, exc_info=True
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


async def generate_strategic_brief(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 Strategic Brief 战略简报 (双模式终层)。

    - **market_report 路径** (media_only 模式)：基于 Agenda Map + Landscape 输出
      聚焦媒体战略 / PR 焦点的战略简报。前置条件：Landscape 已完成。

    - **full_strategy 路径** (comprehensive 模式)：除媒体侧外，还注入 Insight +
      已完成的 brand_strategy_branches + creative_references，输出综合战略简报。
      前置条件：至少有一个分支的 big_idea 已生成（确保下游消费者侧分析就绪）。

    **可选触发**：full_strategy 路径下，Strategic Brief 不自动跑——用户在所有上游层
    完成后主动触发。market_report 路径下，Strategic Brief 是终层（必跑才算 completed）。
    """
    _validate_market_report_output_type(strategy)

    is_full = strategy.output_type == "full_strategy"

    # 前置条件分模式校验
    if is_full:
        # comprehensive 模式：需要 Big Idea 至少一个分支完成（保证 brand_strategy_branches 有内容可综合）
        branches = strategy.brand_strategy_branches or []
        has_big_idea = any(isinstance(b, dict) and b.get("big_idea") for b in branches)
        if not has_big_idea:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="full_strategy 路径生成 Strategic Brief 需先完成至少一个分支的 Big Idea",
            )
    else:
        # media_only 模式：需要 Landscape 完成
        if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["landscape_done"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="请先完成并确认 Landscape",
            )

    # 加载切片数据（不直接喂给 chain，仅用于 data_provenance + chain_inputs 透传 + 校验）
    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    # Strategic Brief 不直接消费切片，但 chain_inputs 透传上游切片（agenda_map / landscape
    # / insight 各层的输入），便于前端 drawer 反查"本节最终基于哪些切片"
    news_slice_refs = await _load_news_slice_refs(db, strategy)
    social_slice_refs = await _load_social_slice_refs(db, strategy) if is_full else []

    research_task_id, research_result = await _retrieve_research_findings(
        db, strategy, "StrategicBrief"
    )
    from src.llm.chains.strategy.research_findings import (
        format_research_for_strategic_brief,
    )

    research_findings_text = format_research_for_strategic_brief(research_result)

    # comprehensive 模式：额外拉取 creative_references（与 Big Idea 阶段同源）
    creative_references_text = ""
    creative_task_id: int | None = None
    if is_full:
        creative_task_id, creative_result = await _retrieve_creative_research_findings(
            db, strategy, "StrategicBrief"
        )
        from src.llm.chains.strategy.research_findings import (
            format_creative_for_big_idea,
        )

        creative_references_text = format_creative_for_big_idea(creative_result)

    chain = create_strategic_brief_chain()
    inputs = format_inputs_for_strategic_brief(
        agenda_map_result=strategy.agenda_map_result,
        landscape_result=strategy.landscape_result,
        brief=strategy.brand_brief,
        research_design=strategy.research_design,
        research_findings=research_findings_text,
        coverage_check_result=strategy.coverage_check_result,
        # comprehensive 模式：注入消费者侧 + 多分支 + 创意；media_only 模式留空
        insight_result=strategy.insight_result if is_full else None,
        brand_strategy_branches=strategy.brand_strategy_branches if is_full else None,
        creative_references=creative_references_text,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_STRATEGIC_BRIEF.value,
        source_count=len(news_slices_data) + (len(slices_data) if is_full else 0),
        status="running",
        analysis_config={
            "strategy_id": strategy.id,
            "mode": "comprehensive" if is_full else "media_only",
        },
    )

    try:
        start = time.time()
        response = await chain.ainvoke(inputs)
        duration = time.time() - start

        result = parse_strategic_brief_response(response.content)
        # comprehensive 模式 primary 标 mixed（消费者+媒体），media_only 标 news_media
        result["data_provenance"] = _build_data_provenance(
            slices_data,
            news_slices_data,
            primary_channel="news_media",
            research_findings=research_findings_text,
        )
        # Strategic Brief chain_inputs：透传上游各层切片（media_only 仅新闻；
        # comprehensive 加入社媒）+ research / creative 任务 ID
        result["chain_inputs"] = _build_chain_inputs(
            social_slice_refs=social_slice_refs,
            news_slice_refs=news_slice_refs,
            research_task_id=research_task_id,
            creative_task_id=creative_task_id,
        )
        # 标记生成模式（前端展示「媒体视角」vs「综合视角」标签依据）
        result["generation_mode"] = "comprehensive" if is_full else "media_only"

        priorities = result.get("strategic_priorities") or []
        total_refs = sum(len(sp.get("evidence_refs") or []) for sp in priorities)
        logger.info(
            "Strategy %d Strategic Brief (%s 模式) 生成完成 (%.1fs): %d priorities, %d evidence_refs",
            strategy.id,
            "comprehensive" if is_full else "media_only",
            duration,
            len(priorities),
            total_refs,
        )

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.strategic_brief_result = result
        # full_strategy 路径 status 已经在 big_idea 完成时置为 "completed"，无需再改
        # market_report 路径 SB 是终层，必须置 status
        if not is_full:
            strategy.status = "completed"

        await db.commit()
        fire_notification(
            feishu_tmpl.strategic_brief_done_card(strategy.name, strategy.id),
            _strategy_open_ids(strategy),
        )
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error(
            "Strategy %d Strategic Brief 生成失败: %s", strategy.id, exc, exc_info=True
        )
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


PLATFORM_NAME_TO_CODE = {
    "douyin": "dy",
    "weibo": "wb",
    "bilibili": "bili",
    "xiaohongshu": "xhs",
    "kuaishou": "ks",
    "zhihu": "zhihu",
    "tieba": "tieba",
}


# ==================== ① 研究设计 ====================


def _extract_channel_brief(brand_brief: dict | None, channel_type: str) -> str:
    """从 brand_brief 中提取指定渠道的 channel_brief"""
    if not brand_brief:
        return ""
    channel_plan = brand_brief.get("channel_plan") or []
    for item in channel_plan:
        if item.get("type") == channel_type:
            return item.get("channel_brief", "")
    return ""


async def _dispatch_strategy_research_tasks(
    db: AsyncSession,
    strategy: Strategy,
    user_id: int,
) -> None:
    """探测通过、进入 collecting 时启动 Research Agent 任务（行业 + 创意）。

    与全量采集并行；探测通过后才启动是为了避免方向被 probe review 否决时浪费 Tavily 调用，
    并保证研究主题基于 probe review 后稳定的 brief。

    创建条件：
    - 行业研究：`brand_brief.channel_plan` 含 `industry_research` 渠道
    - 创意研究：`output_type ∈ {campaign_strategy, full_strategy}` 且 `channel_plan` 含 `creative_research`

    失败仅日志告警，不阻塞 collecting 推进（产出阶段 _retrieve_research_findings
    找不到已完成 ResearchTask 时优雅降级为空注入）。幂等性由调用方 approve_probe
    入口的 status>=collecting 早返回守卫保证。
    """
    from src.research_agent.service import create_research_task

    brief = strategy.brand_brief or {}
    industry_channel_brief = _extract_channel_brief(brief, "industry_research")
    if industry_channel_brief:
        try:
            analysis_goal = brief.get("analysis_goal", "")
            search_config = {"context": analysis_goal} if analysis_goal else {}
            await create_research_task(
                db,
                user_id=user_id,
                analysis_goal=industry_channel_brief,
                title=brief.get("subject", "") or "行业研究",
                search_config=search_config,
                strategy_id=strategy.id,
                profile_name="industry",
            )
            logger.info("策略 %d: 进入 collecting，创建行业研究任务", strategy.id)
        except Exception as e:
            logger.warning(
                "策略 %d: 创建行业研究任务失败（不阻塞主流程）: %s", strategy.id, e
            )

    if strategy.output_type in ("campaign_strategy", "full_strategy"):
        creative_channel_brief = _extract_channel_brief(brief, "creative_research")
        if creative_channel_brief:
            try:
                analysis_goal = brief.get("analysis_goal", "")
                search_config = {"context": analysis_goal} if analysis_goal else {}
                subject = brief.get("subject", "") or "品牌"
                await create_research_task(
                    db,
                    user_id=user_id,
                    analysis_goal=creative_channel_brief,
                    title=f"{subject} 竞品创意研究",
                    search_config=search_config,
                    strategy_id=strategy.id,
                    profile_name="creative",
                )
                logger.info("策略 %d: 进入 collecting，创建创意研究任务", strategy.id)
            except Exception as e:
                logger.warning(
                    "策略 %d: 创建创意研究任务失败（不阻塞主流程）: %s",
                    strategy.id,
                    e,
                )


# ==================== 研究计划 advisory ====================
#
# 非阻塞软提示，在 design_research 返回时计算，附带在 DesignResearchResponse.advisories。
# 设计原则：
# - 只检测 brief 显性化诉求与 data_plan 的覆盖盲区，不替用户决策
# - 规则判断（不调 LLM），单一信号词，召回明确、漏报可接受
# - 信号词为简体中文专有名词，不做正则、不做语义匹配（避免误报）

# 用于检测竞品对比诉求的单一信号词（兜底字面 grep）。"竞品" 在 brand brief 中几乎无歧义；
# "对比/差异化/横向" 等词太宽泛（"消费者对比场景"/"产品差异化升级"/"用户横向调研"
# 都不必然意味着 brand-vs-brand 的竞品分析），不纳入触发集。
# 当 brand_brief.competitors 字段非空时优先使用结构化字段，字面 grep 退化为兜底。
_COMPETITIVE_SIGNAL_TOKEN = "竞品"


def _check_missing_competitive_social_dimension(
    research_design: dict,
    brand_brief: dict,
) -> dict | None:
    """检测 brief 提及竞品但 data_plan 缺 competitive 社媒维度的覆盖盲区。

    所有触发条件全部满足时返回 advisory dict，否则 None：
    1. data_plan 含 social_media 维度（纯新闻 brief 不适用）
    2. data_plan 不含 competitive 类型维度（通过 RQ.dimension 反查）
    3. 竞品诉求成立——优先看结构化字段 `brand_brief.competitors` 非空；为空时兜底
       字面 grep `constraints / analysis_goal / channel_plan[social_media].solvable`
       任一字段含信号词「竞品」
    """
    data_plan = research_design.get("data_plan") or []
    research_questions = research_design.get("research_questions") or []

    has_social = any(
        (dp.get("channel") or "social_media") == "social_media" for dp in data_plan
    )
    if not has_social:
        return None

    rq_dim_map = {rq.get("id"): rq.get("dimension") for rq in research_questions}
    has_competitive = any(
        rq_dim_map.get(qid) == "competitive"
        for dp in data_plan
        for qid in (dp.get("question_ids") or [])
    )
    if has_competitive:
        return None

    # 优先：结构化字段——brief_parser 抽到的明确竞品列表
    structured_competitors = brand_brief.get("competitors") or []
    competitor_signal = bool([c for c in structured_competitors if c])

    # 兜底：字面 grep 历史 brief（未升级 schema 时仍可工作）
    if not competitor_signal:
        constraints = brand_brief.get("constraints") or ""
        analysis_goal = brand_brief.get("analysis_goal") or ""
        social_solvable: list[str] = []
        for ch in brand_brief.get("channel_plan") or []:
            if ch.get("type") == "social_media":
                social_solvable = ch.get("solvable") or []
                break
        text_pool = " ".join([constraints, analysis_goal, *social_solvable])
        competitor_signal = _COMPETITIVE_SIGNAL_TOKEN in text_pool

    if not competitor_signal:
        return None

    return {
        "code": "missing_competitive_social_dimension",
        "severity": "warning",
        "message": (
            "Brief 中提及「竞品」相关诉求，但研究计划未包含 competitive 类型的社媒维度。"
            "若需采集消费者对竞品的主观评价（社媒 UGC），建议补充一个 competitive 维度，"
            "关键词建议与主品 consumer_voice 共享同一主题锚（如「<竞品名> <主题锚>」）。"
            "若仅关注主品资产建设，或竞品诉求已由新闻媒体维度覆盖，可忽略此提示。"
        ),
    }


# Advisory 检测函数注册表——新增规则在此 append 即可，无需改 dispatcher
_ADVISORY_CHECKS = [
    _check_missing_competitive_social_dimension,
]


def _compute_research_design_advisories(
    research_design: dict,
    brand_brief: dict,
) -> list[dict]:
    """计算研究计划 advisory（非阻塞软提示）。

    每条 advisory 是独立函数，互不影响。新增规则在 _ADVISORY_CHECKS 列表追加即可。
    """
    advisories: list[dict] = []

    for check in _ADVISORY_CHECKS:
        try:
            result = check(research_design, brand_brief)
        except Exception as exc:  # 单条规则异常不应阻塞其他规则
            logger.warning("Advisory check %s 异常（已忽略）: %s", check.__name__, exc)
            continue
        if result:
            advisories.append(result)

    return advisories


async def design_research(
    db: AsyncSession,
    strategy: Strategy,
    user_input: str,
) -> DesignResearchResponse:
    """AI 研究设计：基于各渠道 channel_brief 生成结构化研究计划

    输出研究问题、数据采集方案（社媒+新闻）、切片蓝图、产出类型建议。
    每次调用覆盖上一次结果。
    LLM 解析失败时抛出 HTTPException(500)，strategy 不更新。
    """
    chain = create_research_design_chain()
    brand_brief = strategy.brand_brief or {}
    inputs = format_research_design_inputs(
        user_input=user_input,
        social_channel_brief=_extract_channel_brief(brand_brief, "social_media"),
        subject=brand_brief.get("subject", ""),
        constraints=brand_brief.get("constraints") or "",
        analysis_goal=brand_brief.get("analysis_goal") or "",
        news_channel_brief=_extract_channel_brief(brand_brief, "news_media"),
        research_channel_brief=_extract_channel_brief(brand_brief, "industry_research"),
        target_audiences=brand_brief.get("target_audiences"),
        audience_insights=brand_brief.get("audience_insights"),
        core_propositions=brand_brief.get("core_propositions"),
        competitors=brand_brief.get("competitors"),
    )

    start = time.time()
    llm_result = await chain.ainvoke(inputs)
    duration = time.time() - start

    try:
        parsed = parse_research_design_response(llm_result.content)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI 研究设计解析失败: {e}",
        ) from e

    advisories = _compute_research_design_advisories(parsed, brand_brief)
    parsed["advisories"] = advisories

    response = DesignResearchResponse(
        understanding_summary=parsed["understanding_summary"],
        research_questions=parsed["research_questions"],
        data_plan=parsed["data_plan"],
        slice_blueprint=parsed["slice_blueprint"],
        primary_sources=parsed.get("primary_sources", []),
        output_type=parsed["output_type"],
        output_type_rationale=parsed.get("output_type_rationale", ""),
        advisories=advisories,
    )
    logger.info(
        "Strategy %d 研究设计完成 (%.1fs, %d 个研究问题, %d 个数据维度)",
        strategy.id,
        duration,
        len(parsed["research_questions"]),
        len(parsed["data_plan"]),
    )

    strategy.research_design = parsed
    flag_modified(strategy, "research_design")
    strategy.output_type = parsed["output_type"]

    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["planned"]:
        strategy.status = "planned"

    await db.commit()
    return response


async def reset_to_design(
    db: AsyncSession,
    strategy: Strategy,
) -> StrategyRead:
    """重置策略到研究设计阶段，软删除已创建的任务

    允许用户从探测/采集阶段回退到 planned，重新编辑研究计划。
    保留 SocialMonitor（复用），保留 research_design（可重新编辑后确认）。
    """
    from src.social_media.tasks import crud as task_crud
    from src.social_media.tasks.models import SocialTask as SocialTask

    if STATUS_ORDER.get(strategy.status, 0) <= STATUS_ORDER["planned"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前状态无需重置",
        )

    # 软删除所有社媒任务
    tasks_to_delete = await db.execute(
        select(SocialTask).where(
            SocialTask.strategy_id == strategy.id,
            SocialTask.is_deleted.is_(False),
        )
    )
    deleted_social_tasks = list(tasks_to_delete.scalars().all())
    for task in deleted_social_tasks:
        await task_crud.delete_task(db, task)

    # 删除所有新闻任务
    deleted_news_count = 0
    if strategy.news_monitor_id:
        from src.news_media.tasks.service import (
            get_news_tasks_by_strategy,
            delete_news_task,
        )

        news_tasks = await get_news_tasks_by_strategy(db, strategy.id)
        for nt in news_tasks:
            await delete_news_task(db, nt)
            deleted_news_count += 1

    # 清除探测/采集阶段的数据，回退状态
    strategy.probe_review_result = None
    flag_modified(strategy, "probe_review_result")
    strategy.probe_round = 0
    strategy.coverage_check_result = None
    flag_modified(strategy, "coverage_check_result")
    strategy.status = "planned"

    # 清除自动创建的切片（按 monitor_id），否则重新 design-research 时
    # check_collecting_strategies 会判定"已有切片"而不再建新切片
    if strategy.social_monitor_id:
        await db.execute(
            delete(SocialSlice).where(
                SocialSlice.monitor_id == strategy.social_monitor_id
            )
        )
    if strategy.news_monitor_id:
        from src.news_media.analysis.models import NewsSlice as _NS

        await db.execute(delete(_NS).where(_NS.monitor_id == strategy.news_monitor_id))

    await db.commit()

    updated = await get_strategy_by_id(db, strategy.id)
    logger.info(
        "Strategy %d 重置到研究设计阶段 (删除 %d 社媒 + %d 新闻任务)",
        strategy.id,
        len(deleted_social_tasks),
        deleted_news_count,
    )
    return await _strategy_read(db, updated)


async def confirm_research(
    db: AsyncSession,
    strategy: Strategy,
    research_design: dict,
    current_user_id: int,
    *,
    output_type: str,
    notes_per_task: int = 50,
    probe_notes: int = 20,
) -> ConfirmResearchResponse:
    """确认研究计划，创建 SocialMonitor/NewsMonitor + 探测任务

    output_type 由用户在前端显式选择并回传，后端按决策表校验：
    - campaign_strategy 必须要求 data_plan 里至少一个 social_media 维度（否则 Insight/Brand Role/Big Idea 跑不通）
    - market_report 必须要求 data_plan 里至少一个 news_media 维度
    """
    from src.social_media.monitors.crud import get_monitor_by_name, get_platform_by_code
    from src.social_media.monitors.schemas import SocialMonitorCreate
    from src.social_media.monitors.service import create_monitor
    from src.social_media.tasks.schemas import SocialTaskCreate as SocialTaskCreate
    from src.social_media.tasks.service import create_task

    if STATUS_ORDER.get(strategy.status, 0) > STATUS_ORDER["probing"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="全量采集已启动，无法重新确认研究计划",
        )

    # 从 probing 状态重新确认：清理旧探测数据（社媒 + 新闻），重新创建任务
    if strategy.status == "probing":
        from src.social_media.tasks import crud as task_crud
        from src.social_media.tasks.models import SocialTask as _DataTask
        from src.news_media.tasks.models import NewsTask as _NewsTask

        old_tasks = await db.execute(
            select(_DataTask).where(
                _DataTask.strategy_id == strategy.id,
                _DataTask.is_deleted.is_(False),
            )
        )
        for _task in old_tasks.scalars().all():
            await task_crud.delete_task(db, _task)

        old_news = await db.execute(
            select(_NewsTask).where(
                _NewsTask.strategy_id == strategy.id,
                _NewsTask.phase == "probe",
            )
        )
        for _nt in old_news.scalars().all():
            await db.delete(_nt)

        strategy.probe_review_result = None
        flag_modified(strategy, "probe_review_result")
        strategy.probe_round = 0
        _probe_review_in_progress.discard(strategy.id)

    data_plan = research_design.get("data_plan") or []
    if not data_plan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="研究计划中无数据采集方案",
        )

    # 按决策表校验 output_type 与 data_plan 的匹配关系
    if output_type not in ("campaign_strategy", "market_report", "full_strategy"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法的 output_type: {output_type}",
        )
    has_social_dim = any(
        (dp.get("channel") or "social_media") == "social_media" for dp in data_plan
    )
    has_news_dim = any(dp.get("channel") == "news_media" for dp in data_plan)
    if output_type == "campaign_strategy" and not has_social_dim:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "campaign_strategy 产出路径依赖社媒作为主数据源，但研究计划中无 social_media 维度。"
                "请修改研究计划加入社媒维度，或将产出路径切换为 market_report。"
            ),
        )
    if output_type == "market_report" and not has_news_dim:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "market_report 产出路径依赖新闻作为主数据源，但研究计划中无 news_media 维度。"
                "请修改研究计划加入新闻维度，或将产出路径切换为 campaign_strategy。"
            ),
        )
    if output_type == "full_strategy" and not (has_social_dim and has_news_dim):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "full_strategy 产出路径同时依赖社媒和新闻作为双主源，"
                "但研究计划中缺少"
                + ("社媒维度" if not has_social_dim else "新闻维度")
                + "。请修改研究计划或切换产出路径。"
            ),
        )

    # 同步把 primary_sources 写入 research_design，供前端展示和下游读取
    primary_sources: list[str] = []
    if has_social_dim:
        primary_sources.append("social_media")
    if has_news_dim:
        primary_sources.append("news_media")
    research_design["primary_sources"] = primary_sources

    # 预估任务数，社媒和新闻分开校验（新闻任务轻量，不应与社媒共享预算）
    social_tasks = sum(
        len(dp.get("keywords") or []) * len(dp.get("platforms") or [])
        for dp in data_plan
        if (dp.get("channel") or "social_media") == "social_media"
    )
    news_tasks = sum(
        len(dp.get("keywords") or [])
        for dp in data_plan
        if dp.get("channel") == "news_media"
    )
    if social_tasks > 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"社媒采集任务数（{social_tasks}）过多，请精简关键词或平台（常规 brief 目标 12-20，明示 3 平台时可放宽至 18-30）",
        )
    if news_tasks > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"新闻采集任务数（{news_tasks}）过多，请精简关键词（建议 4-6 个）",
        )

    # 保存用户编辑后的研究计划 + 用户显式选择的 output_type（覆盖 LLM 建议值）
    research_design["output_type"] = output_type
    strategy.research_design = research_design
    flag_modified(strategy, "research_design")
    strategy.output_type = output_type

    # 复用已有 SocialMonitor 或创建新的
    if strategy.social_monitor_id:
        from src.social_media.monitors.models import SocialMonitor as SocialMonitor

        monitor = await db.get(SocialMonitor, strategy.social_monitor_id)
        if not monitor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"关联的监测项目 {strategy.social_monitor_id} 不存在",
            )
    else:
        base_name = strategy.name
        monitor_name = base_name
        suffix = 1
        while await get_monitor_by_name(db, monitor_name):
            suffix += 1
            monitor_name = f"{base_name}({suffix})"

        try:
            result = await create_monitor(
                db,
                SocialMonitorCreate(
                    name=monitor_name,
                    description=f"策略「{strategy.name}」的研究数据采集",
                    participant_ids=[p.id for p in strategy.participants],
                ),
                current_user_id,
            )
            monitor = result["monitor"]
        except HTTPException as e:
            raise HTTPException(
                status_code=e.status_code,
                detail=f"创建监测项目失败: {e.detail}",
            ) from e

    # 创建或复用 NewsMonitor（如果有新闻渠道）
    news_monitor = None
    has_news_channel = any(d.get("channel") == "news_media" for d in data_plan)

    if has_news_channel:
        if strategy.news_monitor_id:
            from src.news_media.monitors.models import NewsMonitor

            news_monitor = await db.get(NewsMonitor, strategy.news_monitor_id)
        else:
            from src.news_media.monitors.service import create_news_monitor
            from src.news_media.monitors.schemas import NewsMonitorCreate

            news_monitor = await create_news_monitor(
                db,
                NewsMonitorCreate(
                    name=f"{strategy.name} - 新闻监测",
                    description=f"策略「{strategy.name}」的新闻数据采集",
                    participant_ids=[p.id for p in strategy.participants],
                ),
                current_user_id,
            )
            strategy.news_monitor_id = news_monitor.id

    # 为每个维度×关键词×平台创建独立任务（每个关键词独立，便于探测审查逐词评估）
    created_task_ids: list[int] = []
    created_news_task_ids: list[int] = []
    task_dimension_map: dict[int, str] = {}  # task_id → dimension_name
    news_task_dimension_map: dict[int, str] = {}  # news_task_id → dimension_name
    partial_errors: list[str] = []

    for dimension in data_plan:
        channel = dimension.get("channel", "social_media")  # 默认社媒渠道
        dimension_name = dimension.get("dimension_name", "").strip()
        keywords = dimension.get("keywords") or []

        if not dimension_name or not keywords:
            partial_errors.append(f"跳过不完整的数据维度: {dimension_name}")
            continue

        clean_keywords = [kw.strip() for kw in keywords if kw.strip()]
        if not clean_keywords:
            continue

        # 根据渠道类型分别处理
        if channel == "news_media":
            # 新闻渠道：创建新闻任务并立即执行探测
            if not news_monitor:
                partial_errors.append(f"新闻渠道缺少 NewsMonitor: {dimension_name}")
                continue

            from src.news_media.tasks.service import create_news_task
            from src.news_media.tasks.schemas import NewsTaskCreate
            from src.news_media.tasks.tasks import run_news_probe_task

            enable_wechat_mp = dimension.get("enable_wechat_mp", False)
            news_channels = ["baidu", "sogou"]
            if enable_wechat_mp:
                news_channels.append("wechat_mp")

            for keyword in clean_keywords:
                try:
                    news_task = await create_news_task(
                        db,
                        news_monitor.id,
                        NewsTaskCreate(
                            name=f"{dimension_name} - {keyword}",
                            keywords=keyword,
                            search_params={"channels": news_channels},
                            auto_analyze=False,
                        ),
                        current_user_id,
                        strategy_id=strategy.id,
                        phase="probe",
                    )
                    # create_news_task 已 commit
                    news_task.status = "running"
                    await db.commit()
                    created_news_task_ids.append(news_task.id)
                    news_task_dimension_map[news_task.id] = dimension_name

                    # 异步派发 probe celery（纯搜索，无 LLM，秒级完成）
                    run_news_probe_task.delay(task_id=news_task.id)
                except Exception as e:
                    logger.error(f"创建新闻任务失败: {keyword} - {e}")
                    partial_errors.append(f"创建新闻任务「{keyword}」失败: {e}")

            continue

        # 社媒渠道：原有逻辑
        platforms = dimension.get("platforms") or []
        if not platforms:
            partial_errors.append(f"社媒维度缺少平台配置: {dimension_name}")
            continue

        # 探测任务：仅采 probe_notes 条，跳过评论（加快速度），下发给爬虫时直接用 max_notes_count
        probe_task_params = {
            "max_notes_count": probe_notes,
            "enable_comments": 0,
            "per_note_max_comments_count": 0,
        }

        for keyword in clean_keywords:
            for platform_name in platforms:
                code = PLATFORM_NAME_TO_CODE.get(platform_name, platform_name)
                try:
                    platform = await get_platform_by_code(db, code)
                    if not platform:
                        partial_errors.append(f"平台「{platform_name}」不存在，跳过")
                        continue

                    # max_pages 用于控制翻页数量：微博/贴吧 10 条/页限 2 页，其他平台 20 条/页限 1 页
                    max_pages = 2 if code in ("wb", "tieba") else 1

                    # 为每个平台单独设置 max_pages
                    probe_task_params["max_pages"] = max_pages

                    task = await create_task(
                        db,
                        monitor.id,
                        SocialTaskCreate(
                            name=f"{keyword}-{platform.name}",
                            platform_id=platform.id,
                            task_type="search",
                            keywords=keyword,
                            data_source="remote_crawler",
                            task_params=probe_task_params,
                            auto_analyze=True,
                            phase="probe",
                        ),
                        current_user_id,
                    )
                    task.strategy_id = strategy.id
                    created_task_ids.append(task.id)
                    task_dimension_map[task.id] = dimension_name
                except Exception as e:
                    logger.error(
                        "创建任务「%s-%s-%s」失败: %s",
                        keyword,
                        platform_name,
                        dimension_name,
                        e,
                    )
                    partial_errors.append(
                        f"创建任务「{keyword}-{platform_name}」失败: {e}"
                    )

    # 记录 task_id → dimension 映射到 research_design 中，供后续自动建切片使用
    research_design["_task_dimension_map"] = {
        str(tid): dim for tid, dim in task_dimension_map.items()
    }
    research_design["_news_task_dimension_map"] = {
        str(tid): dim for tid, dim in news_task_dimension_map.items()
    }
    strategy.research_design = research_design
    flag_modified(strategy, "research_design")

    strategy.social_monitor_id = monitor.id
    strategy.status = "probing"

    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)
    return ConfirmResearchResponse(
        created_monitor_id=monitor.id,
        created_task_count=len(created_task_ids),
        created_news_task_count=len(created_news_task_ids),
        partial_errors=partial_errors,
        strategy=await _strategy_read(db, updated),
    )


# ==================== ② 探测验证 ====================

# 防止多个并发请求同时触发同一策略的 LLM 审查
_probe_review_in_progress: set[int] = set()

# 防止同进程内多个并发请求/APScheduler tick 同时触发同一策略的自动建切片。
# 当前部署是 workers=1（见 scheduler.py docstring 硬约束）——此 set 即为主防线。
# DB 层 (monitor_id, name) 唯一约束（migration 2026052801 / 2026052802）
# + _create_auto_slices 的 IntegrityError 捕获作为永久纵深，
# 同时也为未来扩展到 multi-worker 留出 DB 层兜底（届时此 set 会失效，
# 需补 Redis 分布式锁或 leader election，详见 scheduler.py）。
_slice_creation_in_progress: set[int] = set()

# 防止多个并发请求同时触发同一策略的 coverage_check + ready 推进
_coverage_check_in_progress: set[int] = set()


async def _build_social_probe_summaries(
    db: AsyncSession,
    task_ids: list[int],
    research_design: dict | None = None,
) -> tuple[list[SocialProbeTaskStatus], list[dict]]:
    """查询探测任务状态和分析摘要

    Args:
        research_design: 可选，传入后会从 slice_blueprint 派生 expected_subjects /
            expected_competitors 注入 summary，让 probe review LLM 知道当前任务
            预期召回哪些主体/竞品实体（修正 entity_match bool 的语义模糊问题）。

    Returns:
        (task_statuses, analyzed_summaries)
        analyzed_summaries 只包含已有分析结果的任务摘要，供审查使用
    """
    from src.social_media.tasks.models import SocialTask as SocialTask

    if not task_ids:
        return [], []

    # 构造 dimension_name → (subjects, competitors) 映射
    # 来自 slice_blueprint：每个聚焦切片显式声明了 subject + competitors，
    # 通过 source_dimensions 关联到 data_plan 的 dimension_name
    task_dim_map: dict[str, str] = (research_design or {}).get(
        "_task_dimension_map"
    ) or {}
    slice_blueprint: list[dict] = (research_design or {}).get("slice_blueprint") or []
    dim_to_subjects: dict[str, set[str]] = {}
    dim_to_competitors: dict[str, set[str]] = {}
    for sb in slice_blueprint:
        subj = (sb.get("subject") or "").strip()
        comps = [c.strip() for c in (sb.get("competitors") or []) if c and c.strip()]
        for src_dim in sb.get("source_dimensions") or []:
            if subj:
                dim_to_subjects.setdefault(src_dim, set()).add(subj)
            for c in comps:
                dim_to_competitors.setdefault(src_dim, set()).add(c)

    query = select(SocialTask).where(
        SocialTask.id.in_(task_ids), SocialTask.is_deleted.is_(False)
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    # 社媒探测"成功完结"终态（爬虫结束 + 数据可信）。failed 不在此集合：
    # - agent 的 auto_retry 仅本地最多 2 次（MAX_AUTO_RETRY_COUNT），用完后 failed
    #   即为终态——agent 拉任务只查 status=pending，不会再主动碰 failed 行
    # - 因此 failed 任务**不会自动恢复**，需要外部介入：
    #   a) 前端策略页点失败卡片的"重试"图标（调 /social-media/tasks/{id}/clear-data
    #      把 status 重置为 pending，agent 下次轮询会重新认领）
    #   b) 用户去监测项目页删除该任务（永久放弃此关键词×平台组合）
    #   c) 账号问题时由运维在 agent UI 修好账号 + 点继续任务（人工出口）
    # 与新闻探测的非对称设计：新闻 Celery push 模型无 retry 机制，failed 在新闻侧
    # 仍按"保守 pass + 人工核查标注"处理（见 _NEWS_PROBE_TERMINAL）
    _PROBE_OK_TERMINAL_STATUSES = {"probe_ready", "approved", "completed"}

    statuses = []
    analyzed_summaries = []

    for task in tasks:
        is_failed = task.status == "failed"
        # 失败任务永远不算"已分析"——即便 analysis_result 在崩溃前部分写入也不算，
        # 强制等待 retry 或人工删除。这是方案 B "失败必须解决" 的核心保证。
        has_analysis_real = task.analysis_result is not None and not is_failed
        # 0 条数据 + 成功终态：爬虫已完成但无结果，无需 LLM 判断，视为已处理
        no_data = (
            task.posts_count or 0
        ) == 0 and task.status in _PROBE_OK_TERMINAL_STATUSES

        statuses.append(
            SocialProbeTaskStatus(
                task_id=task.id,
                keyword=task.keywords or "",
                platform=task.platform.code if task.platform else "",
                status=task.status,
                has_analysis=has_analysis_real or no_data,
                posts_count=task.posts_count or 0,
                last_updated_at=task.updated_at,
            )
        )

        if has_analysis_real:
            ar = task.analysis_result or {}
            insights = ar.get("insights") or {}
            metrics = ar.get("metrics") or {}
            marketing = metrics.get("marketing_analysis") or {}
            data_volume = (ar.get("meta") or {}).get("data_volume") or {}

            # entity_match: 从已分类的实体列表计算，不依赖 LLM 解析
            target_entities = insights.get("target_entities") or []
            competitor_entities = insights.get("competitor_entities") or []
            entity_match = bool(target_entities or competitor_entities)

            top_topics_raw = insights.get("top_topics") or []
            top_topics = [
                {
                    "name": t.get("name", ""),
                    "mentions": t.get("mentions", 0),
                    "post_source_count": t.get("post_source_count", 0),
                }
                for t in top_topics_raw[:20]
            ]

            # 实际识别到的实体名样本（前 20 个），让 LLM 看清是否匹配 expected_subjects/competitors
            # 取 20 而非 10：probe_lite 不做实体归一，主品名常见 3-5 种变体占位；
            # 强竞品对比场景下竞品品牌也常 10+ 个。20 能覆盖典型长尾，prompt 长度可控。
            target_entities_sample = [
                e.get("name", "") for e in target_entities[:20] if e.get("name")
            ]
            competitor_entities_sample = [
                e.get("name", "") for e in competitor_entities[:20] if e.get("name")
            ]

            # 来自 slice_blueprint 的预期主体/竞品（per-task，按 dimension_name 关联）
            # 防御性上限 50：实际场景不会触达，避免 slice_blueprint 异常时 prompt 爆炸
            dim_name = task_dim_map.get(str(task.id), "")
            expected_subjects = sorted(dim_to_subjects.get(dim_name, set()))[:50]
            expected_competitors = sorted(dim_to_competitors.get(dim_name, set()))[:50]

            summary = {
                "task_id": task.id,
                "keyword": task.keywords or "",
                "platform": task.platform.code if task.platform else "",
                "posts_count": task.posts_count,
                "screened": data_volume.get("screened", 0),
                "deep_analyzed": data_volume.get("deep_analyzed", 0),
                "entity_match": entity_match,
                "target_entities_sample": target_entities_sample,
                "competitor_entities_sample": competitor_entities_sample,
                "expected_subjects": expected_subjects,
                "expected_competitors": expected_competitors,
                "top_topics": top_topics,
                "promotion_ratio": marketing.get("promotion_ratio"),
            }
            analyzed_summaries.append(summary)
        elif no_data:
            # 0 条帖子：加入 summaries 供客观规则层直接 fail，不送 LLM
            analyzed_summaries.append(
                {
                    "task_id": task.id,
                    "keyword": task.keywords or "",
                    "platform": task.platform.code if task.platform else "",
                    "posts_count": 0,
                    "screened": 0,
                    "deep_analyzed": 0,
                    "entity_match": False,
                    "target_entities_sample": [],
                    "competitor_entities_sample": [],
                    "expected_subjects": [],
                    "expected_competitors": [],
                    "top_topics": [],
                    "promotion_ratio": None,
                }
            )

    return statuses, analyzed_summaries


async def _build_news_probe_summaries(
    db: AsyncSession,
    news_probe_tasks: list,
) -> list[dict]:
    """为已完成的新闻 probe 任务构造 LLM 审查所需的卡片摘要

    Returns:
        list[dict]，每条含 task_id / keyword / articles_total / source_tier_distribution
        / articles / channel。失败任务（status != completed 或无 analysis_result）跳过——
        审查链入参为空文章卡片无意义；失败任务由 _run_probe_review_bg_task 内部规则层补建议。
    """
    from src.news_media.tasks import crud as news_crud

    summaries: list[dict] = []
    for npt in news_probe_tasks:
        if not (npt.status == "completed" and npt.analysis_result):
            continue
        meta = (npt.analysis_result or {}).get("meta", {}) or {}
        articles, _ = await news_crud.get_articles_by_task(
            db, task_id=npt.id, skip=0, limit=40
        )
        summaries.append(
            {
                "task_id": npt.id,
                "keyword": npt.keywords or "",
                "articles_total": meta.get("articles_total", 0),
                "source_tier_distribution": meta.get("source_tier_distribution") or {},
                "articles": [
                    {
                        "title": a.title,
                        "source_name": a.source_name,
                        "source_tier": a.source_tier,
                        "snippet": a.snippet,
                    }
                    for a in articles
                ],
                "channel": "news_media",
            }
        )
    return summaries


def _build_channel_summary(assessments: list[dict]) -> dict[str, dict]:
    """按渠道聚合 probe verdict，生成渠道级摘要。

    当某渠道所有任务全部 fail 时，标记 channel_verdict="all_fail"，
    提示用户考虑移除该渠道（可能影响 output_type 路径选择）。
    """
    by_channel: dict[str, list[str]] = {}
    for a in assessments:
        platform = a.get("platform", "")
        channel = "news_media" if platform == "news_media" else "social_media"
        by_channel.setdefault(channel, []).append(a.get("verdict", "fail"))

    summary: dict[str, dict] = {}
    for channel, verdicts in by_channel.items():
        total = len(verdicts)
        fail_count = sum(1 for v in verdicts if v == "fail")
        if fail_count == 0:
            channel_verdict = "all_pass"
            note = ""
        elif fail_count == total:
            channel_verdict = "all_fail"
            channel_label = "社交媒体" if channel == "social_media" else "新闻媒体"
            note = (
                f"{channel_label}的 {total} 个探测任务全部未通过，"
                f"该渠道可能不适合当前研究主题，建议考虑移除相关维度"
            )
        else:
            channel_verdict = "partial_pass"
            note = ""
        summary[channel] = {
            "total": total,
            "fail_count": fail_count,
            "channel_verdict": channel_verdict,
            "note": note,
        }
    return summary


def _override_suggestions_for_all_fail_channels(
    suggestions: list[dict],
    channel_summary: dict[str, dict],
    probe_round: int,
) -> list[dict]:
    """当某渠道 channel_verdict=all_fail 且已经 refine 过至少一次时，覆盖该渠道所有换词建议为 null。

    区分两种 all_fail 场景：
    - 首轮 all_fail（probe_round=0）：多为关键词质量问题，LLM 换词建议往往有价值，不覆盖
    - 重复 all_fail（probe_round≥1，即至少 refine 过一次）：换词已经试过仍全失败，
      说明是结构性数据稀疏，继续换词无济于事，统一覆盖为 null（建议移除任务）
      避免决策层冲突：banner 提示"建议移除渠道"，底部还在给换词建议。
    """
    if probe_round < 1:
        return suggestions

    fail_channels = {
        ch
        for ch, info in channel_summary.items()
        if info.get("channel_verdict") == "all_fail"
    }
    if not fail_channels:
        return suggestions

    result: list[dict] = []
    for s in suggestions:
        platform = s.get("platform", "")
        channel = "news_media" if platform == "news_media" else "social_media"
        if channel in fail_channels:
            total = channel_summary[channel].get("total", 0)
            channel_label = "社交媒体" if channel == "social_media" else "新闻媒体"
            result.append(
                {
                    **s,
                    "suggested_keyword": None,
                    "reason": (
                        f"{channel_label}渠道已 refine 过仍 {total} 个任务全部未通过，"
                        f"判定为结构性数据稀疏，换词无法突破，建议移除该任务"
                    ),
                }
            )
        else:
            result.append(s)
    return result


def _auto_verdict_social_probe_task(summary: dict) -> tuple[str, str] | None:
    """客观规则层：根据量化指标直接判定，返回 (verdict, note) 或 None（交 LLM 判断）

    Hard FAIL：原始采集量极少 / 广告占比极高（LLM 也无法从中获取有效话题）
    其余（含深度分析样本不足）：交 LLM 判断——LLM 看 top_topics + entity_match
    后给出更细粒度的 pass+样本不足兜底 / fail+具体换词建议，统一走 SINGLE_TASK_SYSTEM_TEMPLATE
    的「判定规则」：deep_analyzed < 10 触发样本不足兜底 pass；>=10 严格按 30% 阈值。
    """
    posts = summary.get("posts_count") or 0
    promo = summary.get("promotion_ratio")

    # Hard FAIL
    if posts < 5:
        return "fail", f"平台内容极少（仅 {posts} 条），关键词在此平台可能无效"
    if promo is not None and promo > 0.85:
        return "fail", f"广告内容占比 {promo:.0%}，自然讨论极少"

    return None  # 交 LLM 判断话题相关性（含 deep_analyzed < 5 的低样本场景）


async def _run_news_probe_review_one(
    chain,
    research_design: dict,
    brief: dict | None,
    task_summary: dict,
) -> tuple[dict | None, dict | None, float]:
    """评估单个新闻 probe 任务，返回 (assessment, token_usage, duration_seconds)

    失败时 assessment 为 None，usage 可能为 None（若调用前抛出）。
    """
    from src.llm.chains.strategy.news_probe_review_chain import (
        format_single_news_probe_review_inputs,
        parse_single_news_probe_review_response,
    )

    inputs = format_single_news_probe_review_inputs(
        research_design=research_design, task=task_summary, brief=brief
    )
    t0 = time.time()
    try:
        resp = await chain.ainvoke(inputs)
        dur = time.time() - t0
        assessment = parse_single_news_probe_review_response(resp.content)
        assessment.setdefault("task_id", task_summary["task_id"])
        assessment.setdefault("keyword", task_summary.get("keyword", ""))
        assessment.setdefault("platform", "news_media")
        usage = extract_token_usage(resp, duration_seconds=dur)
        return assessment, usage, dur
    except Exception as exc:
        logger.warning(
            "News probe review failed for task #%s: %s",
            task_summary.get("task_id"),
            exc,
        )
        return None, None, time.time() - t0


async def _run_probe_review_bg_task(
    strategy_id: int,
    analyzed_summaries: list[dict],
    news_probe_summaries: list[dict] | None = None,
) -> None:
    """后台任务：运行探测审查，结果写入 DB（不阻塞 HTTP 响应）

    全量评估所有任务（不区分新旧轮次）：
    1. 客观规则层（_auto_verdict_social_probe_task）处理明确案例
    2. LLM 层处理模糊案例（话题相关性判断）
    temperature=0 保证相同数据重评结果不变。
    """
    try:
        async with AsyncSessionLocal() as db:
            strategy = await get_strategy_by_id(db, strategy_id)
            if strategy is None or strategy.probe_review_result:
                return  # 策略不存在或已有结果（并发任务已完成）

            # 客观规则层：分流（全量评估所有任务，temperature=0 保证相同数据相同结果）
            auto_assessments: list[dict] = []
            rule_suggestions: list[dict] = []  # auto-fail 任务的规则建议（无需 LLM）
            ambiguous_summaries: list[dict] = []

            for summary in analyzed_summaries:
                result = _auto_verdict_social_probe_task(summary)
                if result is not None:
                    verdict, note = result
                    auto_assessments.append(
                        {
                            "task_id": summary["task_id"],
                            "keyword": summary["keyword"],
                            "platform": summary["platform"],
                            "entity_match": summary.get("entity_match", False),
                            "verdict": verdict,
                            "note": note,
                        }
                    )
                    if verdict == "fail":
                        # 规则 fail：内容极少或几乎全是广告，LLM 无法从中获取有效话题
                        # 给出通用建议，具体关键词由用户根据研究方向决定
                        rule_suggestions.append(
                            {
                                "task_id": summary["task_id"],
                                "original_keyword": summary["keyword"],
                                "suggested_keyword": None,
                                "platform": summary["platform"],
                                "reason": note,
                            }
                        )
                else:
                    ambiguous_summaries.append(summary)

            # 加载所有新闻 probe 任务（含失败任务，用于后续补规则建议）
            from src.news_media.tasks.service import (
                get_news_tasks_by_strategy as _get_news_tasks,
            )

            news_probe_tasks = await _get_news_tasks(db, strategy.id, phase="probe")

            # 新闻 probe：LLM 审查（并行每任务一次调用），走 AnalysisJob 记录成本
            news_llm_assessments: list[dict] = []
            if news_probe_summaries:
                from src.llm.chains.strategy.news_probe_review_chain import (
                    create_single_news_probe_review_chain,
                )

                news_chain = create_single_news_probe_review_chain()
                research_design = strategy.research_design or {}
                brief = strategy.brand_brief

                news_job = await create_analysis_job_async(
                    db,
                    news_monitor_id=strategy.news_monitor_id,
                    user_id=strategy.user_id,
                    analysis_type=AnalysisType.STRATEGY_NEWS_PROBE_REVIEW.value,
                    source_count=len(news_probe_summaries),
                    status="running",
                    analysis_config={"strategy_id": strategy.id, "channel": "news"},
                )

                start_news = time.time()
                try:
                    news_results = await asyncio.gather(
                        *[
                            _run_news_probe_review_one(
                                news_chain, research_design, brief, nps
                            )
                            for nps in news_probe_summaries
                        ]
                    )
                    duration_news = time.time() - start_news

                    total_input = total_output = total_tokens = 0
                    total_cost = 0.0
                    call_details: list[dict] = []
                    failed_calls = 0

                    for idx, (nps, (assessment, usage, _dur)) in enumerate(
                        zip(news_probe_summaries, news_results)
                    ):
                        if usage:
                            s = usage.get("summary", {})
                            total_input += s.get("total_input_tokens", 0)
                            total_output += s.get("total_output_tokens", 0)
                            total_tokens += s.get("total_tokens", 0)
                            total_cost += s.get("total_cost_cny", 0.0)
                            for detail in usage.get("call_details", []):
                                call_details.append({**detail, "call_index": idx})

                        if assessment is None:
                            failed_calls += 1
                            # LLM 调用失败：保守判 pass 让用户人工把关（不阻塞流程）
                            auto_assessments.append(
                                {
                                    "task_id": nps["task_id"],
                                    "keyword": nps["keyword"],
                                    "platform": "news_media",
                                    "entity_match": False,
                                    "verdict": "pass",
                                    "note": "LLM 审查失败，已默认通过，请人工核查卡片后决定",
                                }
                            )
                            continue
                        news_llm_assessments.append(assessment)

                    news_total = len(news_probe_summaries)
                    news_job.token_usage = {
                        "summary": {
                            "total_calls": news_total,
                            "total_input_tokens": total_input,
                            "total_output_tokens": total_output,
                            "total_tokens": total_tokens,
                            "total_cost_cny": round(total_cost, 6),
                            "total_duration_seconds": round(duration_news, 2),
                            "avg_tokens_per_call": float(total_tokens) / news_total
                            if news_total
                            else 0.0,
                            "avg_cost_per_call": round(total_cost / news_total, 6)
                            if news_total
                            else 0.0,
                        },
                        "call_details": call_details,
                    }
                    news_job.analyzed_count = len(news_llm_assessments)
                    news_job.processing_time = int(duration_news)
                    news_job.completed_at = datetime.now(timezone.utc)
                    if failed_calls and failed_calls == news_total:
                        news_job.status = "failed"
                        news_job.error_message = (
                            f"全部 {failed_calls} 个新闻 probe LLM 调用失败"
                        )
                    else:
                        news_job.status = "completed"
                        if failed_calls:
                            news_job.error_message = (
                                f"{failed_calls} 个调用失败（已保守判 pass）"
                            )
                    await db.commit()
                except Exception as exc:
                    logger.error(
                        "Strategy %d news probe review 异常: %s",
                        strategy.id,
                        exc,
                        exc_info=True,
                    )
                    news_job.status = "failed"
                    news_job.error_message = str(exc)[:500]
                    news_job.completed_at = datetime.now(timezone.utc)
                    news_job.processing_time = int(time.time() - start_news)
                    await db.commit()
                    raise

                logger.info(
                    "Strategy %d news probe review 完成 (%.1fs, 任务=%d, 成功=%d, 失败=%d)",
                    strategy.id,
                    duration_news,
                    news_total,
                    len(news_llm_assessments),
                    failed_calls,
                )

            # 新闻 LLM 结果直接合入 auto_assessments（已是终态，不进二次 LLM）
            for a in news_llm_assessments:
                auto_assessments.append(
                    {
                        "task_id": a.get("task_id"),
                        "keyword": a.get("keyword", ""),
                        "platform": "news_media",
                        "entity_match": False,
                        "verdict": a.get("verdict", "pass"),
                        "note": a.get("note", ""),
                    }
                )
                if a.get("verdict") == "fail":
                    rule_suggestions.append(
                        {
                            "task_id": a.get("task_id"),
                            "original_keyword": a.get("keyword", ""),
                            "suggested_keyword": a.get("suggested_keyword"),
                            "platform": "news_media",
                            "reason": a.get("suggestion_reason") or a.get("note", ""),
                        }
                    )

            # 失败的新闻探测任务未进 LLM 审查（无文章数据可评估），补规则建议
            # `news_probe_summaries or []`：scheduler 路径在历史 bug 修复前可能传 None；
            # 现 scheduler 也构造摘要，理论不再为 None，但保留防御避免新调用方再踩坑
            reviewed_news_ids = {nps["task_id"] for nps in (news_probe_summaries or [])}
            for npt in news_probe_tasks:
                if npt.status == "failed" and npt.id not in reviewed_news_ids:
                    note = npt.error_message or "新闻探测任务失败，未能采集到搜索结果"
                    keyword = npt.keywords or ""
                    auto_assessments.append(
                        {
                            "task_id": npt.id,
                            "keyword": keyword,
                            "platform": "news_media",
                            "entity_match": False,
                            "verdict": "fail",
                            "note": note,
                        }
                    )
                    # suggested_keyword 与原词相同：应用建议时移除失败任务并以原词重新创建，
                    # 相当于重试；用户可在确认弹窗前手动改词
                    rule_suggestions.append(
                        {
                            "task_id": npt.id,
                            "original_keyword": keyword,
                            "suggested_keyword": keyword,
                            "platform": "news_media",
                            "reason": f"采集失败（{note}），已恢复原词重新探测。如需换词可在应用前修改。",
                        }
                    )

            # LLM 层：处理模糊案例（话题相关性判断）
            review_result = await _run_probe_review(
                db,
                strategy,
                ambiguous_summaries=ambiguous_summaries,
                auto_assessments=auto_assessments,
                rule_suggestions=rule_suggestions,
            )

            if review_result.get("overall_verdict") == "all_pass":
                await approve_probe(db, strategy, current_user_id=strategy.user_id)
    except Exception as e:
        logger.error(
            "Strategy %d probe review background task failed: %s",
            strategy_id,
            e,
            exc_info=True,
        )
    finally:
        _probe_review_in_progress.discard(strategy_id)


async def _run_probe_review(
    db: AsyncSession,
    strategy: Strategy,
    ambiguous_summaries: list[dict],
    auto_assessments: list[dict] | None = None,
    rule_suggestions: list[dict] | None = None,
) -> dict:
    """运行 probe_review_chain 并存储结果

    Args:
        ambiguous_summaries: 需要 LLM 判定 verdict 的任务（客观指标无法确定）
        auto_assessments: 已通过客观规则判定的评估结果（直接合并，不送 LLM）
        rule_suggestions: auto-fail 任务的规则建议（不送 LLM，直接合并）
    """
    llm_assessments: list[dict] = []
    llm_add_suggestions: list[dict] = []
    parse_error: str | None = None

    # 仅在有模糊案例时调用 LLM（每个任务独立并行评估，消除批量上下文干扰）
    if ambiguous_summaries:
        chain = create_single_task_probe_review_chain()
        research_design = strategy.research_design or {}
        brief = strategy.brand_brief

        # 查询当前 strategy 下所有活跃 probe task 的 (keyword, platform_code) 元组，
        # 供 LLM 校验建议词不与已有任务重复。必须查 DB 实际任务而非从 data_plan 派生
        # ——data_plan 在 refine_probe 时不更新，会 stale。
        # 使用 Platform.code（如 xhs/dy）而非 Platform.name（如 小红书/抖音），
        # 因为 task_summary 的 platform 字段是 .code（见 _build_social_probe_summaries
        # 第 3096 行 task.platform.code），三处都用 code 才能让 LLM 字符串比对生效。
        from src.social_media.monitors.models import Platform as _Platform

        active_tasks_rows = await db.execute(
            select(SocialTask.keywords, _Platform.code)
            .join(_Platform, SocialTask.platform_id == _Platform.id)
            .where(
                and_(
                    SocialTask.strategy_id == strategy.id,
                    SocialTask.phase == "probe",
                    SocialTask.is_deleted.is_(False),
                )
            )
        )
        existing_task_tuples: list[tuple[str, str]] = [
            (kw, plat) for kw, plat in active_tasks_rows.all() if kw and plat
        ]

        job = await create_analysis_job_async(
            db,
            social_monitor_id=strategy.social_monitor_id,
            news_monitor_id=strategy.news_monitor_id,
            user_id=strategy.user_id,
            analysis_type=AnalysisType.STRATEGY_SOCIAL_PROBE_REVIEW.value,
            source_count=len(ambiguous_summaries),
            status="running",
            analysis_config={"strategy_id": strategy.id},
        )

        async def _evaluate_one(
            task_summary: dict,
        ) -> tuple[dict | None, dict | None, float]:
            """评估单个任务，返回 (assessment, token_usage, duration)"""
            inputs = format_single_task_probe_review_inputs(
                research_design=research_design,
                task=task_summary,
                brief=brief,
                existing_task_tuples=existing_task_tuples,
            )
            t0 = time.time()
            try:
                resp = await chain.ainvoke(inputs)
                dur = time.time() - t0
                assessment = parse_single_task_probe_review_response(resp.content)
                usage = extract_token_usage(resp, duration_seconds=dur)
                return assessment, usage, dur
            except Exception as exc:
                logger.warning(
                    "Strategy %d task #%s probe review 失败: %s",
                    strategy.id,
                    task_summary.get("task_id"),
                    exc,
                )
                return None, None, time.time() - t0

        start = time.time()
        try:
            call_results = await asyncio.gather(
                *[_evaluate_one(t) for t in ambiguous_summaries]
            )
            duration = time.time() - start  # 并行总耗时

            # 合并结果和 token 统计
            total_input = total_output = total_tokens = 0
            total_cost = 0.0
            call_details = []
            failed_parses = 0

            for idx, (assessment, usage, dur) in enumerate(call_results):
                if assessment is None:
                    failed_parses += 1
                    continue
                llm_assessments.append(assessment)
                if usage:
                    s = usage.get("summary", {})
                    total_input += s.get("total_input_tokens", 0)
                    total_output += s.get("total_output_tokens", 0)
                    total_tokens += s.get("total_tokens", 0)
                    total_cost += s.get("total_cost_cny", 0.0)
                    for detail in usage.get("call_details", []):
                        call_details.append({**detail, "call_index": idx})

            if failed_parses:
                parse_error = f"{failed_parses} 个任务解析失败"

            merged_token_usage = {
                "summary": {
                    "total_calls": len(ambiguous_summaries),
                    "total_input_tokens": total_input,
                    "total_output_tokens": total_output,
                    "total_tokens": total_tokens,
                    "total_cost_cny": round(total_cost, 6),
                    "total_duration_seconds": round(duration, 2),
                    "avg_tokens_per_call": float(total_tokens)
                    / len(ambiguous_summaries)
                    if ambiguous_summaries
                    else 0.0,
                    "avg_cost_per_call": round(total_cost / len(ambiguous_summaries), 6)
                    if ambiguous_summaries
                    else 0.0,
                },
                "call_details": call_details,
            }

            now = datetime.now(timezone.utc)
            job.status = "completed" if not parse_error else "failed"
            job.completed_at = now
            job.analyzed_count = len(llm_assessments)
            job.processing_time = int(duration)
            job.token_usage = merged_token_usage
            if parse_error:
                job.error_message = parse_error

            logger.info(
                "Strategy %d probe review 并行 LLM 完成 (%.1fs, 模糊=%d, 成功=%d)",
                strategy.id,
                duration,
                len(ambiguous_summaries),
                len(llm_assessments),
            )
        except Exception as exc:
            logger.error(
                "Strategy %d social probe review 异常: %s",
                strategy.id,
                exc,
                exc_info=True,
            )
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
            raise
    else:
        logger.info("Strategy %d probe review 全部自动判定，跳过 LLM", strategy.id)

    # 合并所有评估结果
    all_assessments = (auto_assessments or []) + llm_assessments

    # 从合并后的 assessments 确定性计算 overall_verdict
    verdicts = [a.get("verdict", "fail") for a in all_assessments]
    fail_count = sum(1 for v in verdicts if v == "fail")
    if not verdicts:
        overall = "fail"
    elif fail_count == 0:
        overall = "all_pass"
    elif fail_count == len(verdicts):
        overall = "fail"
    else:
        overall = "partial_pass"

    # 合并建议：rule_suggestions（auto-fail） + LLM-fail assessments 中的 suggested_keyword
    all_suggestions: list[dict] = list(rule_suggestions or [])
    for a in llm_assessments:
        if a.get("verdict") == "fail" and a.get("suggested_keyword"):
            all_suggestions.append(
                {
                    "task_id": a["task_id"],
                    "original_keyword": a.get("keyword", ""),
                    "suggested_keyword": a["suggested_keyword"],
                    "platform": a.get("platform", ""),
                    "reason": a.get("suggestion_reason", ""),
                }
            )

    # 后处理：检测 consumer_voice / competitive 互补平台失败，替换为平台统一建议
    from src.llm.chains.strategy.social_probe_review_chain import (
        detect_and_replace_symmetry_suggestions,
    )

    all_suggestions = detect_and_replace_symmetry_suggestions(
        all_assessments=all_assessments,
        existing_suggestions=all_suggestions,
        research_design=strategy.research_design or {},
    )

    # 按渠道聚合 verdict，生成渠道级摘要
    channel_summary = _build_channel_summary(all_assessments)

    # 渠道 all_fail 覆盖（仅 probe_round≥1，即至少 refine 过一次）：
    # 首轮 all_fail 保留 LLM 换词建议（多为关键词质量问题）；重复 all_fail 才判定结构性稀疏，统一建议移除
    all_suggestions = _override_suggestions_for_all_fail_channels(
        all_suggestions,
        channel_summary,
        strategy.probe_round or 0,
    )

    logger.info(
        "Strategy %d probe review 完成 (verdict=%s, 规则自动=%d, LLM=%d)",
        strategy.id,
        overall,
        len(auto_assessments or []),
        len(llm_assessments),
    )

    result: dict = {
        "assessments": all_assessments,
        "overall_verdict": overall,
        "channel_summary": channel_summary,
        "refinement_suggestions": all_suggestions,
        "add_suggestions": llm_add_suggestions,
    }
    if parse_error:
        result["_parse_error"] = parse_error

    strategy.probe_review_result = result
    flag_modified(strategy, "probe_review_result")
    await db.commit()

    if overall != "all_pass":
        fire_notification(
            feishu_tmpl.probe_needs_review_card(
                strategy.name,
                strategy.id,
                overall_verdict=overall,
            ),
            _strategy_open_ids(strategy),
        )

    return result


async def parse_brief_from_file(content: bytes, filename: str) -> ParseBriefResponse:
    """从上传文档提取文本并用 LLM 解析为 BrandBrief 字段"""
    try:
        raw_text = await run_cpu_bound_task(_extract_text_from_bytes, content, filename)
    except Exception as exc:
        logger.error("Brief 文本提取失败 (%s): %s", filename, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"无法从文档提取文本，请检查文件是否损坏: {exc}",
        ) from exc

    if not raw_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文档内容为空，无法解析",
        )

    document_text = raw_text[:_MAX_BRIEF_TEXT_CHARS]

    chain = create_brief_parser_chain()
    try:
        response = await chain.ainvoke({"document_text": document_text})
        response_text = (
            response.content if hasattr(response, "content") else str(response)
        )
        parsed = parse_brief_parser_response(response_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Brief 解析 LLM 调用失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 解析失败，请稍后重试",
        ) from exc

    return ParseBriefResponse(**parsed)


async def parse_brief_from_text(text: str) -> ParseBriefResponse:
    """从纯文本用 LLM 解析为 BrandBrief 字段"""
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文本内容为空，无法解析",
        )

    document_text = text[:_MAX_BRIEF_TEXT_CHARS]

    chain = create_brief_parser_chain()
    try:
        response = await chain.ainvoke({"document_text": document_text})
        response_text = (
            response.content if hasattr(response, "content") else str(response)
        )
        parsed = parse_brief_parser_response(response_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Brief 解析 LLM 调用失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 解析失败，请稍后重试",
        ) from exc

    return ParseBriefResponse(**parsed)


async def check_probe_status(
    db: AsyncSession,
    strategy: Strategy,
) -> ProbeStatusResponse:
    """查询探测任务进度，全部分析完成后自动触发后台 LLM 审查。"""
    # 查询该策略的所有社媒 probe 任务
    probe_tasks_result = await db.execute(
        select(SocialTask).where(
            SocialTask.strategy_id == strategy.id,
            SocialTask.phase == "probe",
            SocialTask.is_deleted.is_(False),
        )
    )
    probe_tasks = list(probe_tasks_result.scalars().all())

    # 查询该策略的所有新闻 probe 任务
    from src.news_media.tasks.service import get_news_tasks_by_strategy

    news_probe_tasks = await get_news_tasks_by_strategy(db, strategy.id, phase="probe")

    if not probe_tasks and not news_probe_tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有探测任务，无法查询进度",
        )

    task_ids = [t.id for t in probe_tasks]
    task_statuses, analyzed_summaries = await _build_social_probe_summaries(
        db,
        task_ids,
        research_design=strategy.research_design,
    )

    # 新闻任务状态（进入终态即视为已处理，failed 不阻塞审查触发）
    _NEWS_PROBE_TERMINAL = {"completed", "failed"}
    news_all_analyzed = all(t.status in _NEWS_PROBE_TERMINAL for t in news_probe_tasks)
    news_analyzed_count = sum(
        1 for t in news_probe_tasks if t.status in _NEWS_PROBE_TERMINAL
    )

    # 构建新闻任务状态列表（供前端展示）
    from src.strategies.schemas import NewsProbeTaskStatus

    news_probe_dim_map: dict[str, str] = (strategy.research_design or {}).get(
        "_news_task_dimension_map"
    ) or {}
    news_task_statuses = [
        NewsProbeTaskStatus(
            task_id=npt.id,
            keyword=npt.keywords or "",
            dimension=news_probe_dim_map.get(str(npt.id), ""),
            status=npt.status,
            completed=npt.status == "completed" and bool(npt.analysis_result),
            failed=npt.status == "failed",
            articles_count=(npt.analysis_result or {})
            .get("meta", {})
            .get("articles_total", 0)
            if npt.analysis_result
            else 0,
        )
        for npt in news_probe_tasks
    ]

    # 新闻 probe 送 LLM 审查：加载每个任务的文章卡片（title/source/tier/snippet）
    # 由 strategy_news_probe_review_chain 基于搜索结果判断关键词相关性与信号质量
    news_probe_summaries = await _build_news_probe_summaries(db, news_probe_tasks)

    # 兼容纯新闻策略（无社媒任务时 task_statuses 为空）
    social_all_analyzed = not task_statuses or all(
        t.has_analysis for t in task_statuses
    )
    news_check = not news_probe_tasks or news_all_analyzed
    all_analyzed = bool(
        social_all_analyzed and news_check and (task_statuses or news_probe_tasks)
    )
    analyzed_count = (
        sum(1 for t in task_statuses if t.has_analysis) + news_analyzed_count
    )
    total_count = len(task_statuses) + len(news_probe_tasks)

    # 全部分析完成且尚无审查结果 → 触发后台 LLM 审查（仅针对社媒数据）
    if (
        all_analyzed
        and not strategy.probe_review_result
        and strategy.id not in _probe_review_in_progress
    ):
        _probe_review_in_progress.add(strategy.id)
        import asyncio

        asyncio.ensure_future(
            _run_probe_review_bg_task(
                strategy.id, analyzed_summaries, news_probe_summaries
            )
        )

    return ProbeStatusResponse(
        social_tasks=task_statuses,
        news_tasks=news_task_statuses,
        all_analyzed=all_analyzed,
        analyzed_count=analyzed_count,
        total_count=total_count,
        probe_review_result=strategy.probe_review_result,
        strategy=await _strategy_read(db, strategy),
    )


# ==================== 探测任务审批和调整 ====================


async def _advance_probe_task_to_collect(
    db: AsyncSession,
    task: "SocialTask",
    collect_task_params: dict,
) -> None:
    """把一条 SocialTask 从 probe 阶段原地推进到 collect 阶段。

    - phase: probe → collect
    - status: probe_ready → pending（重新进入 agent 认领队列）
    - task_params: 覆写为全量采集参数
    - 重置执行态字段（accepted/started/completed/error），供 agent 重新认领
    - 清除 Redis 自动分析锁 + 撤销进行中的 probe 分析作业
    - 保留 PostAnalysis：probe 阶段已分析的笔记结果可被 collect 阶段增量复用，省 LLM 成本
    - 保留 task.analysis_result（probe 的聚合）：作为 0-new-data 边缘场景的兜底；
      collect 抓到新数据时 auto_analysis 会覆写；抓不到新数据时（如 platform 总共
      就 20 条），probe 的聚合仍然是对"全部可见数据"的合法聚合，让 check_collecting
      scheduler 能正常筛到这个 task 进入建切片流程，避免策略永卡 collecting

    已采集的 posts/comments 保留在同一 task 下（它们是最终 40 条的一部分）。
    爬虫侧通过相同 cloud_task_id 的历史 checkpoint 自动续采，无需额外传参。
    """
    from src.social_media.analysis.service import reset_task_analysis_state

    task.phase = "collect"
    task.status = "pending"
    task.task_params = collect_task_params
    task.accepted_at = None
    task.accepted_by = None
    task.started_at = None
    task.completed_at = None
    task.error_message = None
    task.crawled_count = 0
    # posts_count / comments_count 保留：probe 阶段已入库的 20 条不能被遗忘
    flag_modified(task, "task_params")

    # 复用统一的分析状态重置逻辑：清 Redis 锁 + 撤销 Celery
    # delete_post_analysis=False：probe 已经做过的 per-post 分析保留，collect 完成后增量复用
    # delete_analysis_jobs=False：保留作业历史，便于追溯
    # clear_aggregated=False：保留 probe 聚合作为 0-new-data 边缘场景兜底（详见函数 docstring）
    await reset_task_analysis_state(
        db,
        task.id,
        task=task,
        delete_post_analysis=False,
        delete_analysis_jobs=False,
        clear_aggregated=False,
    )


async def approve_probe(
    db: AsyncSession,
    strategy: Strategy,
    current_user_id: int,
) -> ApproveProbeResponse:
    """手动确认探测，把每个社媒探测任务原地推进到全量采集阶段（phase 由 probe → collect）。

    单任务多阶段模型：同一条 SocialTask 记录承载探测与全量两个阶段，通过 phase 字段区分。
    `task_id` 在两个阶段保持不变，爬虫侧据此自动续采探测阶段产生的 checkpoint。

    幂等：若策略已进入 collecting 及以后阶段，直接返回当前 collect 任务数，
    避免网络重试 / 前端重复点击触发重复推进。

    新闻任务仍按旧模型（创建独立的 collect NewsTask），因为新闻走 Celery push 模型，
    不存在 checkpoint 复用需求。
    """
    from src.social_media.tasks.models import SocialTask as SocialTask

    # 入口幂等：已推进到 collecting/ready/产出阶段时，直接返回当前 collect 任务数
    if STATUS_ORDER.get(strategy.status, 0) >= STATUS_ORDER["collecting"]:
        existing = await db.execute(
            select(func.count())
            .select_from(SocialTask)
            .where(
                and_(
                    SocialTask.strategy_id == strategy.id,
                    SocialTask.phase == "collect",
                    SocialTask.is_deleted.is_(False),
                )
            )
        )
        social_count = int(existing.scalar() or 0)
        from src.news_media.tasks.service import get_news_tasks_by_strategy as _get_news

        existing_news = await _get_news(db, strategy.id, phase="collect")
        return ApproveProbeResponse(
            approved_task_count=social_count + len(existing_news),
            strategy=await _strategy_read(db, strategy),
        )

    # 获取当前所有社媒 probe 任务
    probe_tasks_stmt = select(SocialTask).where(
        and_(
            SocialTask.strategy_id == strategy.id,
            SocialTask.phase == "probe",
            SocialTask.is_deleted.is_(False),
        )
    )
    probe_tasks_result = await db.execute(probe_tasks_stmt)
    probe_tasks = list(probe_tasks_result.scalars().all())

    # 获取新闻 probe 任务
    from src.news_media.tasks.service import get_news_tasks_by_strategy

    news_probe_tasks = await get_news_tasks_by_strategy(db, strategy.id, phase="probe")

    if not probe_tasks and not news_probe_tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有探测任务，无法确认",
        )

    # 维度映射必须完整存在（社媒自动建切片的唯一依据）
    research_design = strategy.research_design or {}
    if not isinstance(research_design, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="研究计划数据异常：research_design 必须为对象",
        )

    probe_dim_map = research_design.get("_task_dimension_map")
    if not isinstance(probe_dim_map, dict) or not probe_dim_map:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="缺少任务维度映射，请重新确认研究计划后再批准探测",
        )

    # 原地推进社媒 probe 任务至 collect 阶段（task_id 保持不变）
    collect_task_ids: list[int] = []
    collect_dim_map: dict[str, str] = {}
    for pt in probe_tasks:
        dim = probe_dim_map.get(str(pt.id))
        if not dim:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"探测任务 {pt.id} 缺少维度映射，请重新确认研究计划",
            )

        # 构造 collect 阶段参数，保留原 probe 任务的平台专属参数（sort_type / publish_time_type 等）
        existing_params = dict(pt.task_params or {})
        # 移除仅探测阶段使用的参数
        existing_params.pop("probe_size", None)
        existing_params.pop("max_pages", None)
        # 覆写 collect 阶段默认参数（用户侧可通过配置页后续调整）
        collect_task_params = {
            **existing_params,
            "max_notes_count": 40,
            "enable_comments": 1,
            "per_note_max_comments_count": 20,
        }

        # 原地推进：phase → collect，status → pending（供 agent 重新认领），重置执行字段
        await _advance_probe_task_to_collect(db, pt, collect_task_params)

        collect_task_ids.append(pt.id)
        # task_id 不变，直接复用 probe 阶段的维度映射
        collect_dim_map[str(pt.id)] = dim

    # 为新闻 probe 任务创建全量采集任务
    news_collect_dim_map: dict[str, str] = {}
    news_collect_task_ids: list[int] = []
    if news_probe_tasks:
        from src.news_media.tasks.service import create_news_task
        from src.news_media.tasks.schemas import NewsTaskCreate

        news_probe_dim_map = research_design.get("_news_task_dimension_map") or {}

        for npt in news_probe_tasks:
            dim = news_probe_dim_map.get(str(npt.id))
            if not dim:
                continue

            news_collect_task = await create_news_task(
                db,
                npt.monitor_id,
                NewsTaskCreate(
                    name=f"{npt.name} - 全量",
                    keywords=npt.keywords,
                    # 继承 probe 阶段的 channels 选择（含用户勾选的 wechat_mp），避免全量阶段
                    # fallback 到 baidu+sogou 默认值导致公众号不被采集
                    search_params=npt.search_params,
                    auto_analyze=True,
                ),
                current_user_id,
                strategy_id=strategy.id,
                phase="collect",
            )
            news_collect_dim_map[str(news_collect_task.id)] = dim
            news_collect_task_ids.append(news_collect_task.id)

    # 更新策略
    strategy.status = "collecting"
    research_design["_task_dimension_map"] = collect_dim_map
    research_design["_news_task_dimension_map"] = news_collect_dim_map
    strategy.research_design = research_design
    flag_modified(strategy, "research_design")

    await _dispatch_strategy_research_tasks(db, strategy, current_user_id)

    # 新建的 ResearchTask 立即同步 participants，让协作者无需等下次手动 add/remove 就能看见
    await _sync_participants_to_associated_resources(db, strategy)

    await db.commit()

    # 新闻全量采集通过 celery 异步执行（与独立 news_media 流程统一）
    if news_collect_task_ids:
        from src.news_media.analysis.jobs import create_news_tagging_job
        from src.jobs import crud as jobs_crud
        from src.news_media.tasks import crud as news_crud
        from src.news_media.tasks.tasks import run_news_collect_task

        # 从 brand_brief.subject + slice_blueprint union competitors 提取 role 归类元数据
        # 供 tagging_chain 做 role 硬绑定（target=subject / competitor∈competitors / 其余=context）
        brand_brief = strategy.brand_brief or {}
        tagging_subject = (brand_brief.get("subject") or "").strip()
        blueprint = research_design.get("slice_blueprint") or []
        _comp_seen: set[str] = set()
        tagging_competitors: list[str] = []
        for bp in blueprint:
            for c in bp.get("competitors") or []:
                c_norm = (c or "").strip()
                if c_norm and c_norm.lower() not in _comp_seen:
                    _comp_seen.add(c_norm.lower())
                    tagging_competitors.append(c_norm)

        for tid in news_collect_task_ids:
            collect_task = await news_crud.get_task_by_id(db, tid, load_relations=False)
            if not collect_task:
                continue
            tagging_job = await create_news_tagging_job(
                db=db, task=collect_task, user_id=current_user_id
            )
            collect_task.status = "running"
            await db.commit()

            celery_result = run_news_collect_task.delay(
                task_id=collect_task.id,
                tagging_job_id=tagging_job.id,
                subject=tagging_subject,
                competitors=tagging_competitors,
            )
            await jobs_crud.set_celery_task_id(db, tagging_job.id, celery_result.id)
            await db.commit()

    updated = await get_strategy_by_id(db, strategy.id)
    return ApproveProbeResponse(
        approved_task_count=len(collect_task_ids),
        strategy=await _strategy_read(db, updated),
    )


async def refine_probe(
    db: AsyncSession,
    strategy: Strategy,
    data: RefineProbeRequest,
    current_user_id: int,
) -> RefineProbeResponse:
    """调整探测任务关键词，创建新的探测任务（phase="probe"），probe_round++"""
    from src.social_media.tasks.schemas import SocialTaskCreate as SocialTaskCreate
    from src.social_media.tasks.service import create_task
    from src.social_media.monitors.crud import get_platform_by_code

    if STATUS_ORDER.get(strategy.status, 0) > STATUS_ORDER["probing"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="全量采集已启动，无法调整探测任务",
        )

    # 加载现有 probe 任务（用于软删除）
    from sqlalchemy import select, and_
    from src.social_media.tasks.models import SocialTask as SocialTask

    old_tasks_result = await db.execute(
        select(SocialTask).where(
            and_(
                SocialTask.strategy_id == strategy.id,
                SocialTask.phase == "probe",
                SocialTask.is_deleted.is_(False),
            )
        )
    )
    old_tasks_map: dict[int, SocialTask] = {
        t.id: t for t in old_tasks_result.scalars().all()
    }

    # 加载现有 news probe 任务
    from src.news_media.tasks.models import NewsTask

    old_news_result = await db.execute(
        select(NewsTask).where(
            and_(
                NewsTask.strategy_id == strategy.id,
                NewsTask.phase == "probe",
            )
        )
    )
    old_news_map: dict[int, NewsTask] = {
        t.id: t for t in old_news_result.scalars().all()
    }

    if not old_tasks_map and not old_news_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有探测任务，无法调整",
        )

    if data.social_refinements and not old_tasks_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有社媒探测任务，无法调整",
        )
    if data.news_refinements and not old_news_map:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前没有新闻探测任务，无法调整",
        )

    # 继承现有维度映射，在此基础上增删改
    research_design = strategy.research_design or {}
    if not isinstance(research_design, dict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="研究计划数据异常：research_design 必须为对象",
        )
    old_dim_map: dict[str, str] = dict(research_design.get("_task_dimension_map") or {})

    # 以现有所有 probe 任务 ID 为基础逐项操作，未提及的任务自动保留
    current_task_ids = list(old_tasks_map.keys())
    new_task_dim_map = dict(old_dim_map)
    removed_social_task_ids: list[int] = []
    created_social_task_ids: list[int] = []

    for item in data.social_refinements:
        # 三种操作：
        #   替换：task_id + new_keyword  → 软删旧任务，继承维度，创建新任务
        #   移除：task_id + new_keyword=None → 仅软删旧任务
        #   新增：task_id=None + new_keyword + dimension → 仅创建新任务

        # 步骤 1：软删除旧任务（替换/移除时）
        if item.task_id is not None:
            old_task = old_tasks_map.get(item.task_id)
            if old_task:
                old_task.is_deleted = True
            if item.task_id in current_task_ids:
                current_task_ids.remove(item.task_id)
            new_task_dim_map.pop(str(item.task_id), None)
            removed_social_task_ids.append(item.task_id)

        # 步骤 2：创建新任务（替换/新增时）
        if item.new_keyword is not None:
            code = PLATFORM_NAME_TO_CODE.get(item.platform, item.platform)
            platform_obj = await get_platform_by_code(db, code)
            if not platform_obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"平台 {item.platform} 不存在",
                )

            # 维度：优先使用 item.dimension；替换时可继承旧任务维度
            dimension = item.dimension or old_dim_map.get(str(item.task_id), "")
            if not dimension:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="创建探测任务必须提供 dimension",
                )

            max_pages = 2 if code in ("wb", "tieba") else 1
            new_task = await create_task(
                db,
                strategy.social_monitor_id,
                SocialTaskCreate(
                    name=f"{item.new_keyword}-{platform_obj.name}",
                    platform_id=platform_obj.id,
                    task_type="search",
                    keywords=item.new_keyword,
                    data_source="remote_crawler",
                    task_params={
                        "max_notes_count": 20,
                        "enable_comments": 0,
                        "per_note_max_comments_count": 0,
                        "max_pages": max_pages,
                    },
                    auto_analyze=True,
                    phase="probe",
                ),
                current_user_id,
            )
            new_task.strategy_id = strategy.id
            current_task_ids.append(new_task.id)
            created_social_task_ids.append(new_task.id)
            new_task_dim_map[str(new_task.id)] = dimension

    # ---- 新闻 probe 调整分支 ----
    old_news_dim_map: dict[str, str] = dict(
        research_design.get("_news_task_dimension_map") or {}
    )
    new_news_dim_map = dict(old_news_dim_map)
    removed_news_task_ids: list[int] = []
    created_news_task_ids: list[int] = []

    if data.news_refinements:
        from src.news_media.tasks.crud import delete_task as delete_news_task_crud
        from src.news_media.tasks.schemas import NewsTaskCreate
        from src.news_media.tasks.service import (
            create_news_task as create_news_task_svc,
        )
        from src.news_media.tasks.tasks import run_news_probe_task

        if not strategy.news_monitor_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="策略未关联 NewsMonitor，无法调整新闻探测任务",
            )

        new_news_task_payloads: list[tuple[str, str]] = []  # (keyword, dimension)

        for item in data.news_refinements:
            # 步骤 1：删除旧任务（替换/移除时）
            if item.task_id is not None:
                old_news = old_news_map.get(item.task_id)
                if old_news:
                    await delete_news_task_crud(db, old_news)
                new_news_dim_map.pop(str(item.task_id), None)
                removed_news_task_ids.append(item.task_id)

            # 步骤 2：记录新任务待创建（替换/新增时）
            if item.new_keyword is not None:
                dimension = item.dimension or old_news_dim_map.get(
                    str(item.task_id) if item.task_id is not None else "", ""
                )
                if not dimension:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="创建新闻探测任务必须提供 dimension",
                    )
                new_news_task_payloads.append((item.new_keyword, dimension))

        # 先 commit 删除
        await db.flush()

        # 创建新任务（create_news_task 内部会 commit）
        for keyword, dimension in new_news_task_payloads:
            news_task = await create_news_task_svc(
                db,
                strategy.news_monitor_id,
                NewsTaskCreate(
                    name=f"{dimension} - {keyword}",
                    keywords=keyword,
                    search_params={"max_results": 25},
                    auto_analyze=False,
                ),
                current_user_id,
                strategy_id=strategy.id,
                phase="probe",
            )
            news_task.status = "running"
            await db.commit()
            created_news_task_ids.append(news_task.id)
            new_news_dim_map[str(news_task.id)] = dimension
            run_news_probe_task.delay(task_id=news_task.id)

    # 重置审查结果，确保新一轮探测完成后重新触发审查
    strategy.probe_review_result = None
    strategy.probe_round = (strategy.probe_round or 0) + 1
    research_design["_task_dimension_map"] = new_task_dim_map
    research_design["_news_task_dimension_map"] = new_news_dim_map
    strategy.research_design = research_design
    flag_modified(strategy, "probe_review_result")
    flag_modified(strategy, "research_design")

    await db.commit()

    updated = await get_strategy_by_id(db, strategy.id)
    return RefineProbeResponse(
        removed_social_task_ids=removed_social_task_ids,
        created_social_task_ids=created_social_task_ids,
        removed_news_task_ids=removed_news_task_ids,
        created_news_task_ids=created_news_task_ids,
        probe_round=updated.probe_round,
        strategy=await _strategy_read(db, updated),
    )


async def check_collection_status(
    db: AsyncSession,
    strategy: Strategy,
    current_user_id: int,
) -> CollectionStatusResponse:
    """查询全量采集进度，全部完成+分析后自动建切片并验证覆盖度。"""
    from src.social_media.tasks.models import SocialTask as SocialTask

    # 查询该策略的所有社媒 collect 任务
    stmt = select(SocialTask).where(
        and_(
            SocialTask.strategy_id == strategy.id,
            SocialTask.phase == "collect",
            SocialTask.is_deleted.is_(False),
        )
    )
    result = await db.execute(stmt)
    tasks = list(result.scalars().all())

    # 查询该策略的所有新闻 collect 任务
    from src.news_media.tasks.service import get_news_tasks_by_strategy

    news_tasks = await get_news_tasks_by_strategy(db, strategy.id, phase="collect")

    if not tasks and not news_tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到采集任务",
        )

    # failed 任务自动重置为 pending，让爬虫重试（利用本地 checkpoint 续采）
    failed_tasks = [t for t in tasks if t.status == "failed"]
    if failed_tasks:
        failed_ids = [t.id for t in failed_tasks]
        await db.execute(
            update(SocialTask)
            .where(SocialTask.id.in_(failed_ids))
            .values(status="pending", accepted_at=None, accepted_by=None)
        )
        await db.commit()
        for t in failed_tasks:
            t.status = "pending"
        logger.info(
            "Strategy %s: reset %d failed collect task(s) to pending for retry: %s",
            strategy.id,
            len(failed_ids),
            failed_ids,
        )

    # 终态判定：completed 或 failed 均视为终态（failed = 爬虫/Worker 故障，不应永久阻塞策略）
    _terminal = {"completed", "failed"}
    all_completed = all(task.status in _terminal for task in tasks) and all(
        t.status in _terminal for t in news_tasks
    )
    # 已分析判定：所有任务都终态 + 至少有 1 个 completed（非全失败） + 所有 completed 任务有 analysis_result
    # 注意：必须要求 all_completed 为前置，否则单个任务完成就会触发 all_analyzed=True，让前端进度条提前消失
    completed_social = [t for t in tasks if t.status == "completed"]
    completed_news = [t for t in news_tasks if t.status == "completed"]
    all_analyzed = (
        all_completed
        and bool(completed_social or completed_news)
        and all(t.analysis_result is not None for t in completed_social)
        and all(t.analysis_result is not None for t in completed_news)
    )

    task_statuses = [
        CollectionTaskStatus(
            task_id=task.id,
            keyword=task.keywords or "",
            platform=task.platform.code if task.platform else "",
            status=task.status,
            posts_count=task.posts_count,
            comments_count=task.comments_count or 0,
            has_analysis=task.analysis_result is not None,
        )
        for task in tasks
    ]

    news_task_dim_map: dict[str, str] = (strategy.research_design or {}).get(
        "_news_task_dimension_map"
    ) or {}
    news_task_statuses = [
        NewsCollectionTaskStatus(
            task_id=nt.id,
            keyword=nt.keywords or "",
            dimension=news_task_dim_map.get(str(nt.id), ""),
            status=nt.status,
            articles_count=nt.articles_count or 0,
            has_analysis=nt.analysis_result is not None,
        )
        for nt in news_tasks
    ]

    slices_created = False

    # 检查是否已有切片（社媒 + 新闻，均按 monitor_id 独立查询）
    has_social_slices = False
    if strategy.social_monitor_id:
        _ss_result = await db.execute(
            select(SocialSlice.id)
            .where(SocialSlice.monitor_id == strategy.social_monitor_id)
            .limit(1)
        )
        has_social_slices = _ss_result.scalar_one_or_none() is not None
    has_news_slices = False
    if strategy.news_monitor_id:
        from src.news_media.analysis.models import NewsSlice as _NS

        _ns_result = await db.execute(
            select(_NS.id).where(_NS.monitor_id == strategy.news_monitor_id).limit(1)
        )
        has_news_slices = _ns_result.scalar_one_or_none() is not None

    # 全部终态且已分析 → 自动建切片（若尚无任何切片且未在进行中）
    if all_completed and all_analyzed:
        if (
            not has_social_slices
            and not has_news_slices
            and strategy.id not in _slice_creation_in_progress
        ):
            _slice_creation_in_progress.add(strategy.id)
            logger.info(
                "Strategy %s: 所有任务完成且已分析，开始自动建切片", strategy.id
            )
            try:
                completed_tasks = [
                    t
                    for t in tasks
                    if t.status == "completed" and t.analysis_result is not None
                ]
                completed_news = [
                    t
                    for t in news_tasks
                    if t.status == "completed" and t.analysis_result is not None
                ]
                await _create_auto_slices(
                    db, strategy, completed_tasks, current_user_id, completed_news
                )
                slices_created = True
                logger.info("Strategy %s: 自动建切片完成", strategy.id)
            except Exception as e:
                logger.error(
                    "Strategy %s: 自动建切片失败: %s", strategy.id, e, exc_info=True
                )
            finally:
                _slice_creation_in_progress.discard(strategy.id)
        else:
            slices_created = True
    elif has_social_slices or has_news_slices:
        slices_created = True
    elif all_completed:
        logger.info("Strategy %s: 所有任务已完成，等待分析", strategy.id)

    # 切片已建、但 coverage_check 尚未跑 → 在 Stage2/新闻 insight 全完时主动推进到 ready
    # （利用前端 15s 轮询实现近实时推进，不依赖 APScheduler 2min tick）
    if (
        has_social_slices or has_news_slices
    ) and strategy.coverage_check_result is None:
        try:
            await _try_advance_to_ready(db, strategy)
        except Exception as e:
            logger.error(
                "Strategy %s: _try_advance_to_ready 失败: %s",
                strategy.id,
                e,
                exc_info=True,
            )

    completed_count = sum(1 for t in tasks if t.status == "completed") + sum(
        1 for t in news_tasks if t.status == "completed"
    )
    total_count = len(tasks) + len(news_tasks)

    industry_status = await _get_research_agent_status(db, strategy.id, "industry")
    creative_status = await _get_research_agent_status(db, strategy.id, "creative")

    return CollectionStatusResponse(
        tasks=task_statuses,
        news_tasks=news_task_statuses,
        all_completed=all_completed,
        all_analyzed=all_analyzed,
        slices_created=slices_created,
        completed_count=completed_count,
        total_count=total_count,
        coverage_check_result=strategy.coverage_check_result,
        industry_research=industry_status,
        creative_research=creative_status,
        strategy=await _strategy_read(db, strategy),
    )


async def _create_strategy_news_slice(
    db: AsyncSession,
    strategy: Strategy,
    name: str,
    news_task_ids: list[int],
    user_id: int,
    subject: str | None,
    competitors: list[str],
) -> "NewsSlice":
    """为策略创建 NewsSlice：同步落 stage1（subject/competitors 列 + descriptive + stats）。

    HTTP 立即返回 status=analyzing 的切片行（无文章则 completed），LLM stage2
    由调用方 commit 主事务后异步派发 `run_news_slice_insight_task`。这样避免长
    事务（LLM ~120s）持有 INSERT 不 commit，APScheduler / 轮询读得到该行；同时
    subject / competitors 写入 NewsSlice 表列（与 SocialSlice 列存储对齐），
    与分析产物 result_data 解耦。
    """
    from src.news_media.analysis.service import initialize_slice

    return await initialize_slice(
        db,
        monitor_id=strategy.news_monitor_id,
        name=name,
        included_task_ids=news_task_ids,
        user_id=user_id,
        subject=subject,
        competitors=competitors,
    )


async def _create_auto_slices(
    db: AsyncSession,
    strategy: Strategy,
    collect_tasks: list,
    current_user_id: int,
    news_tasks: list = None,
) -> None:
    """按 slice_blueprint 自动创建 SocialSlice + NewsSlice，并关联到策略。

    社媒维度 → SocialSlice（Stage1/2/3 流水线，create_monitor_slice 内部 inline commit）
    新闻维度 → NewsSlice 行 + 异步派发 run_news_slice_insight_task（Celery）

    每个 blueprint 条目可产生 0-1 个 SocialSlice + 0-1 个 NewsSlice。

    幂等性（按 monitor_id + name 跳过已存在切片）：调用方可能在 polling/scheduler
    并发或重试场景下多次调用，本函数保证不重复创建——已存在的切片直接跳过，
    支持"上轮部分失败 → 下轮补建"的合法重试。
    """
    from src.news_media.analysis.models import NewsSlice
    from src.social_media.analysis.service import create_monitor_slice

    # 已存在切片去重（按 monitor_id + name）
    existing_social_names: set[str] = set()
    if strategy.social_monitor_id:
        rows = await db.execute(
            select(SocialSlice.name).where(
                SocialSlice.monitor_id == strategy.social_monitor_id
            )
        )
        existing_social_names = {r[0] for r in rows.all() if r[0]}

    existing_news_names: set[str] = set()
    if strategy.news_monitor_id:
        rows = await db.execute(
            select(NewsSlice.name).where(
                NewsSlice.monitor_id == strategy.news_monitor_id
            )
        )
        existing_news_names = {r[0] for r in rows.all() if r[0]}

    blueprint: list[dict] = []
    research_design = strategy.research_design or {}
    if isinstance(research_design, dict):
        blueprint = research_design.get("slice_blueprint") or []

    slice_objs: list = []  # 本轮新建的社媒 SocialSlice
    # 本轮新建的新闻 NewsSlice 派发载荷：(slice_id, analysis_goal)
    # subject/competitors 已持久化到 NewsSlice 行，由 Celery task 直接读
    news_dispatch_payloads: list[tuple[int, str]] = []

    if blueprint:
        task_dim_map = research_design.get("_task_dimension_map") or {}
        news_task_dim_map = research_design.get("_news_task_dimension_map") or {}

        # 有社媒采集任务时必须有维度映射
        if collect_tasks and (not isinstance(task_dim_map, dict) or not task_dim_map):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="缺少 collect 任务维度映射，无法自动建切片",
            )

        # 社媒任务按维度分组
        dimension_to_social: dict[str, list] = {}
        for task in collect_tasks:
            dim = task_dim_map.get(str(task.id))
            if not dim:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"采集任务 {task.id} 缺少维度映射，无法自动建切片",
                )
            dimension_to_social.setdefault(dim, []).append(task)

        # 新闻任务按维度分组
        dimension_to_news: dict[str, list] = {}
        if news_tasks:
            for task in news_tasks:
                dim = news_task_dim_map.get(str(task.id))
                if dim:
                    dimension_to_news.setdefault(dim, []).append(task)

        # 新闻大盘切片去冗余：预计算每个聚焦 blueprint（subject 非空）覆盖的新闻任务集合。
        # 与社媒不同——新闻对称采集（无单品牌深挖），聚焦切片的 competitive.players 已含
        # 主品+竞品同框的公平 media_sov，无需单独大盘新闻切片做 SOV 基准。因此当某大盘
        # blueprint 的新闻任务集合与某聚焦 blueprint 完全相同时，其大盘新闻切片是纯冗余
        # （同一批数据再分析一遍、仅丢失角色），下方跳过创建。
        # 用「完全相同」而非「子集」判定：纯行业分析（无聚焦）保留大盘；万一新闻出现单品牌
        # 深挖（聚焦任务真多于大盘）则两者不等、保留大盘做公平基准。社媒不适用此去冗余。
        focus_news_task_sets: list[frozenset[int]] = []
        for bp_focus in blueprint:
            if not (bp_focus.get("subject") or "").strip():
                continue
            focus_dims = bp_focus.get("source_dimensions") or []
            focus_ids = {
                t.id
                for dim_key, dim_tasks in dimension_to_news.items()
                if (not focus_dims or dim_key in focus_dims)
                for t in dim_tasks
            }
            if focus_ids:
                focus_news_task_sets.append(frozenset(focus_ids))

        for bp in blueprint:
            bp_name: str = bp.get("name") or "综合分析"
            bp_dims: list[str] = bp.get("source_dimensions") or []
            bp_subject: str | None = bp.get("subject")
            bp_competitors: list[str] | None = bp.get("competitors")

            # 社媒任务匹配
            matched_task_ids: list[int] = []
            for dim_key, dim_tasks in dimension_to_social.items():
                if not bp_dims or dim_key in bp_dims:
                    matched_task_ids.extend(t.id for t in dim_tasks)

            # 新闻任务匹配
            matched_news_task_ids: list[int] = []
            matched_news_keywords: list[str] = []
            for dim_key, dim_tasks in dimension_to_news.items():
                if not bp_dims or dim_key in bp_dims:
                    matched_news_task_ids.extend(t.id for t in dim_tasks)
                    matched_news_keywords.extend(
                        t.keywords for t in dim_tasks if t.keywords
                    )

            social_already_exists = bp_name in existing_social_names
            news_already_exists = bp_name in existing_news_names

            # 大盘新闻切片去冗余：subject 为空（大盘）且其新闻任务集合与某聚焦切片完全相同时，
            # 该大盘新闻切片对策略链路是纯冗余（聚焦超集已覆盖议程层、且自带公平竞争层），跳过。
            # 社媒侧不受影响（此处只 gate 新闻创建，社媒大盘切片照常建）。
            news_redundant = (
                not (bp_subject or "").strip()
                and bool(matched_news_task_ids)
                and frozenset(matched_news_task_ids) in focus_news_task_sets
            )
            if news_redundant:
                logger.info(
                    "Strategy %s: 大盘 blueprint '%s' 的新闻任务与聚焦切片相同，跳过冗余新闻切片",
                    strategy.id,
                    bp_name,
                )

            # 该 blueprint 完全无任务可消费时：若已有任一侧切片视为历史已建，跳过；否则报错
            if not matched_task_ids and not matched_news_task_ids:
                if social_already_exists or news_already_exists:
                    continue
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"切片「{bp_name}」未匹配到任何任务，请检查 source_dimensions 配置",
                )

            # 创建社媒 SocialSlice（已存在则跳过）
            if matched_task_ids and not social_already_exists:
                try:
                    slice_obj = await create_monitor_slice(
                        db,
                        monitor_id=strategy.social_monitor_id,
                        task_ids=matched_task_ids,
                        current_user_id=current_user_id,
                        name=bp_name,
                        subject=bp_subject,
                        competitors=bp_competitors,
                    )
                    slice_objs.append(slice_obj)
                    existing_social_names.add(bp_name)
                except IntegrityError:
                    # 并发 INSERT 被数据库唯一约束拦截（另一个 uvicorn worker 抢先建完）
                    await db.rollback()
                    logger.info(
                        "Strategy %s: SocialSlice '%s' 已被其他 worker 创建，跳过",
                        strategy.id,
                        bp_name,
                    )
                    existing_social_names.add(bp_name)

            # 创建新闻 NewsSlice 行（已存在则检查是否需要补派 insight）
            if (
                matched_news_task_ids
                and strategy.news_monitor_id
                and not news_redundant
            ):
                goal = (
                    f"{bp_name}（关键词：{', '.join(matched_news_keywords)}）"
                    if matched_news_keywords
                    else bp_name
                )
                if not news_already_exists:
                    try:
                        ns = await _create_strategy_news_slice(
                            db,
                            strategy=strategy,
                            name=bp_name,
                            news_task_ids=matched_news_task_ids,
                            user_id=current_user_id,
                            subject=bp_subject or None,
                            competitors=bp_competitors or [],
                        )
                        news_dispatch_payloads.append((ns.id, goal))
                        existing_news_names.add(bp_name)
                    except IntegrityError:
                        await db.rollback()
                        logger.info(
                            "Strategy %s: NewsSlice '%s' 已被其他 worker 创建，检查是否需补派",
                            strategy.id,
                            bp_name,
                        )
                        existing_news_names.add(bp_name)
                        # 并发抢建成功的切片也要检查补派（下方统一处理）
                        news_already_exists = True

                if news_already_exists:
                    # 切片已存在：检查是否卡在 analyzing（上次派发丢失），若是则补派
                    stale = await db.execute(
                        select(NewsSlice).where(
                            NewsSlice.monitor_id == strategy.news_monitor_id,
                            NewsSlice.name == bp_name,
                            NewsSlice.status == "analyzing",
                        )
                    )
                    stale_ns = stale.scalar_one_or_none()
                    if stale_ns is not None:
                        news_dispatch_payloads.append((stale_ns.id, goal))
                        logger.info(
                            "Strategy %s: NewsSlice '%s' (id=%s) 处于 analyzing，补派 insight",
                            strategy.id,
                            bp_name,
                            stale_ns.id,
                        )
    else:
        # 无 blueprint：合并为综合切片
        if collect_tasks and "综合分析" not in existing_social_names:
            all_task_ids = [t.id for t in collect_tasks]
            try:
                slice_obj = await create_monitor_slice(
                    db,
                    monitor_id=strategy.social_monitor_id,
                    task_ids=all_task_ids,
                    current_user_id=current_user_id,
                    name="综合分析",
                )
                slice_objs.append(slice_obj)
            except IntegrityError:
                await db.rollback()
                logger.info(
                    "Strategy %s: 综合分析 SocialSlice 已被其他 worker 创建，跳过",
                    strategy.id,
                )

        if news_tasks and strategy.news_monitor_id:
            all_news_ids = [t.id for t in news_tasks]
            all_keywords = [t.keywords for t in news_tasks if t.keywords]
            goal = (
                f"综合分析（关键词：{', '.join(all_keywords)}）"
                if all_keywords
                else "综合分析"
            )
            general_already_exists = "综合分析" in existing_news_names
            if not general_already_exists:
                try:
                    ns = await _create_strategy_news_slice(
                        db,
                        strategy=strategy,
                        name="综合分析",
                        news_task_ids=all_news_ids,
                        user_id=current_user_id,
                        subject=None,
                        competitors=[],
                    )
                    news_dispatch_payloads.append((ns.id, goal))
                except IntegrityError:
                    await db.rollback()
                    logger.info(
                        "Strategy %s: 综合分析 NewsSlice 已被其他 worker 创建，检查是否需补派",
                        strategy.id,
                    )
                    general_already_exists = True

            if general_already_exists:
                stale = await db.execute(
                    select(NewsSlice).where(
                        NewsSlice.monitor_id == strategy.news_monitor_id,
                        NewsSlice.name == "综合分析",
                        NewsSlice.status == "analyzing",
                    )
                )
                stale_ns = stale.scalar_one_or_none()
                if stale_ns is not None:
                    news_dispatch_payloads.append((stale_ns.id, goal))
                    logger.info(
                        "Strategy %s: 综合分析 NewsSlice (id=%s) 处于 analyzing，补派 insight",
                        strategy.id,
                        stale_ns.id,
                    )

    # 社媒切片 Stage2/Stage3 pipeline 设置
    now_iso = datetime.now(timezone.utc).isoformat()
    pipeline_slice_ids: list[int] = []

    for s_obj in slice_objs:
        rd = s_obj.result_data
        if not isinstance(rd, dict):
            continue
        pipeline = rd.get("pipeline")
        if (
            not isinstance(pipeline, dict)
            or pipeline.get("stage1", {}).get("status") != "completed"
        ):
            continue

        rd = dict(rd)
        rd["pipeline"] = {
            **rd.get("pipeline", {}),
            "stage2": {
                "status": "pending",
                "updated_at": now_iso,
                "steps": {
                    "entity_normalization": {"status": "pending"},
                    "opinion_normalization": {"status": "pending"},
                    "derived_analysis": {"status": "pending"},
                },
            },
            "stage3": {
                "status": "pending",
                "updated_at": now_iso,
            },
        }
        s_obj.result_data = rd
        flag_modified(s_obj, "result_data")
        pipeline_slice_ids.append(s_obj.id)

    # 切片通过 monitor_id 隐式关联到策略，无需显式关联表
    await db.flush()
    await db.commit()

    # 策略保持 collecting 状态 —— 等所有社媒切片 Stage2 完成后，
    # 由 get_collection_status / APScheduler 主动调 _try_advance_to_ready
    # 跑 coverage_check 并推进到 ready。
    # 新闻切片 insight 分析是另外独立的 Celery 流水线，也一同等待。

    # commit 之后触发 Stage2/Stage3 celery 任务
    if pipeline_slice_ids:
        from src.social_media.analysis.celery_tasks.monitor_slice_tasks import (
            run_monitor_slice_task,
        )

        for sid in pipeline_slice_ids:
            run_monitor_slice_task.delay(slice_id=sid)
            logger.info(
                "Strategy %s: triggered Stage2/Stage3 pipeline for slice %s",
                strategy.id,
                sid,
            )

    # commit 之后异步派发新闻 insight（避免长事务窗口）
    if news_dispatch_payloads:
        from src.news_media.analysis.models import NewsSlice as _NewsSlice
        from src.news_media.tasks.tasks import run_news_slice_insight_task

        for slice_id, goal in news_dispatch_payloads:
            ns = await db.get(_NewsSlice, slice_id)
            if ns is None or ns.status != "analyzing":
                # 0 篇文章场景 initialize_slice 直接置 completed，无需派发 LLM
                continue
            run_news_slice_insight_task.delay(
                slice_id=slice_id,
                user_id=current_user_id,
                analysis_goal=goal,
            )
            logger.info(
                "Strategy %s: triggered news insight for slice %s",
                strategy.id,
                slice_id,
            )


# ==================== 覆盖度推进（Stage2 完成后 → ready） ====================

# SocialSlice Stage2 的终态集合：任意一个都意味着"不再 processing"
_SLICE_STAGE2_TERMINAL = {"completed", "failed", "skipped"}
# 新闻切片单流水线 status 的终态集合
_NEWS_SLICE_TERMINAL = {"completed", "failed"}


def _social_slice_stage2_terminal(slice_obj: SocialSlice) -> bool:
    """判断社媒切片 Stage2 是否已到终态（completed/failed/skipped）。

    Stage2 完成即代表切片对策略下游可用——Stage3 的 3 报告不参与策略 chain。
    """
    rd = slice_obj.result_data or {}
    if not isinstance(rd, dict):
        return False
    pipeline = rd.get("pipeline") or {}
    stage2 = pipeline.get("stage2") or {}
    return stage2.get("status") in _SLICE_STAGE2_TERMINAL


async def _try_advance_to_ready(
    db: AsyncSession,
    strategy: Strategy,
) -> bool:
    """所有切片 Stage2 到终态后跑 coverage_check，通过则置 ready。

    - 社媒切片：检查 `result_data.pipeline.stage2.status` ∈ {completed, failed, skipped}
    - 新闻切片：检查 `NewsSlice.status` ∈ {completed, failed}
    - 失败/跳过的切片：不阻塞 ready，coverage_check 会基于现有可用切片判定

    返回：是否成功推进到 ready（或 coverage 已跑过但未通过时仍返回 False）
    """
    if strategy.status != "collecting":
        return False
    if strategy.coverage_check_result is not None:
        # 已跑过 coverage（结果可能通过也可能未通过），不重复跑
        return False
    if strategy.id in _coverage_check_in_progress:
        return False

    # 收集关联切片
    social_slices: list[SocialSlice] = []
    if strategy.social_monitor_id:
        res = await db.execute(
            select(SocialSlice).where(
                SocialSlice.monitor_id == strategy.social_monitor_id
            )
        )
        social_slices = list(res.scalars().all())

    news_slices_list: list = []
    if strategy.news_monitor_id:
        from src.news_media.analysis.models import NewsSlice as _NS

        res = await db.execute(
            select(_NS).where(_NS.monitor_id == strategy.news_monitor_id)
        )
        news_slices_list = list(res.scalars().all())

    if not social_slices and not news_slices_list:
        return False  # 切片尚未建出

    # 等待所有切片 Stage2 / 新闻 insight 到终态
    social_all_done = all(_social_slice_stage2_terminal(s) for s in social_slices)
    news_all_done = all(ns.status in _NEWS_SLICE_TERMINAL for ns in news_slices_list)
    if not (social_all_done and news_all_done):
        return False

    _coverage_check_in_progress.add(strategy.id)
    try:
        research_design = strategy.research_design or {}
        research_questions = (
            research_design.get("research_questions") or []
            if isinstance(research_design, dict)
            else []
        )
        # 只把可供下游消费的切片喂给 coverage chain
        slices_data: list[tuple[str, dict]] = []
        for s in social_slices:
            if s.status == "completed" and s.result_data:
                slices_data.append((s.name or f"切片{s.id}", s.result_data))
        for ns in news_slices_list:
            if ns.status == "completed" and ns.result_data:
                slices_data.append((f"[新闻] {ns.name}", ns.result_data))

        if not slices_data:
            logger.warning(
                "Strategy %s: 所有切片 Stage2 均失败/跳过，无可用数据，保持 collecting",
                strategy.id,
            )
            return False

        try:
            chain = create_coverage_check_chain()
            inputs = format_coverage_check_inputs(
                brief=strategy.brand_brief,
                research_questions=research_questions,
                slices_data=slices_data,
            )
            raw = await chain.ainvoke(inputs)
            coverage_result = parse_coverage_check_response(
                raw.content if hasattr(raw, "content") else str(raw)
            )
            strategy.coverage_check_result = coverage_result
            flag_modified(strategy, "coverage_check_result")

            advanced = False
            if coverage_result.get("overall_ready"):
                strategy.status = "ready"
                advanced = True
                logger.info(
                    "Strategy %s: 覆盖度验证通过，状态推进到 ready", strategy.id
                )
            else:
                logger.info(
                    "Strategy %s: 覆盖度验证未通过，保持 collecting，建议调整切片",
                    strategy.id,
                )

            await db.commit()

            if advanced:
                fire_notification(
                    feishu_tmpl.data_ready_card(
                        strategy.name,
                        strategy.id,
                        slice_count=len(social_slices) + len(news_slices_list),
                    ),
                    _strategy_open_ids(strategy),
                )

            return advanced
        except Exception as e:
            logger.error(
                "Strategy %s: 覆盖度 LLM 验证失败: %s",
                strategy.id,
                e,
                exc_info=True,
            )
            return False
    finally:
        _coverage_check_in_progress.discard(strategy.id)


async def get_data_overview(
    db: AsyncSession,
    strategy: Strategy,
) -> "DataOverviewResponse":
    """数据全景：返回该策略已关联的切片列表 + 覆盖度验证结果。"""
    from .schemas import DataOverviewResponse

    slice_summaries = await _load_strategy_slice_summaries(db, strategy)

    return DataOverviewResponse(
        slices=slice_summaries,
        coverage_check_result=strategy.coverage_check_result,
        strategy=await _strategy_read(db, strategy),
    )


async def adjust_slices(
    db: AsyncSession,
    strategy: Strategy,
    adjustments: list[dict],
    current_user_id: int,
) -> Strategy:
    """微调社媒切片配置（名称/主体/竞品），调整后重新触发覆盖度验证。

    每个 adjustment 格式：{slice_id, name?, subject?, competitors?}

    注意：当前仅支持调整社媒切片。新闻切片的 subject/competitors 在 insight 阶段
    传入并影响实体 role 归类，调整后需要重跑 insight chain（暂未实现）。
    """
    from src.news_media.analysis.models import NewsSlice as _NewsSlice
    from src.social_media.analysis.models import SocialSlice

    # 校验 slice 归属：本策略 social_monitor 下的切片
    if strategy.social_monitor_id:
        ids_result = await db.execute(
            select(SocialSlice.id).where(
                SocialSlice.monitor_id == strategy.social_monitor_id
            )
        )
        strategy_slice_ids = set(ids_result.scalars().all())
    else:
        strategy_slice_ids = set()

    # 预查新闻切片 ID，用于把"传错 channel"的错误从泛化的"不属于该策略"
    # 提升为更明确的 409，引导前端禁用 news 切片的调整入口
    news_slice_ids: set[int] = set()
    if strategy.news_monitor_id:
        ns_result = await db.execute(
            select(_NewsSlice.id).where(
                _NewsSlice.monitor_id == strategy.news_monitor_id
            )
        )
        news_slice_ids = set(ns_result.scalars().all())

    for adj in adjustments:
        sid = adj.get("slice_id")
        if sid in news_slice_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"切片 {sid} 是新闻切片，当前仅支持调整社媒切片",
            )
        if sid not in strategy_slice_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"切片 {sid} 不属于该策略",
            )

        slice_obj = await db.get(SocialSlice, sid)
        if slice_obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"切片 {sid} 不存在",
            )

        if "name" in adj and adj["name"] is not None:
            slice_obj.name = adj["name"]

        # subject / competitors 是切片配置，写到表列上（与分析产物 result_data 解耦）
        if "subject" in adj and adj["subject"] is not None:
            slice_obj.subject = adj["subject"] or None
        if "competitors" in adj and adj["competitors"] is not None:
            slice_obj.competitors = list(adj["competitors"])

    await db.flush()

    # 重新触发覆盖度 LLM 验证
    try:
        research_design = strategy.research_design or {}
        research_questions = research_design.get("research_questions") or []

        # 重新加载所有切片
        slice_ids = list(strategy_slice_ids)
        stmt = select(SocialSlice).where(SocialSlice.id.in_(slice_ids))
        result = await db.execute(stmt)
        updated_slices = list(result.scalars().all())

        slices_data = [
            (s.name or f"切片{s.id}", s.result_data or {}) for s in updated_slices
        ]
        chain = create_coverage_check_chain()
        inputs = format_coverage_check_inputs(
            brief=strategy.brand_brief,
            research_questions=research_questions,
            slices_data=slices_data,
        )
        raw = await chain.ainvoke(inputs)
        coverage_result = parse_coverage_check_response(
            raw.content if hasattr(raw, "content") else str(raw)
        )
        strategy.coverage_check_result = coverage_result
        flag_modified(strategy, "coverage_check_result")

        if coverage_result.get("overall_ready") and strategy.status == "collecting":
            strategy.status = "ready"
            logger.info("Strategy %s: 调整后覆盖度通过，状态推进到 ready", strategy.id)
    except Exception as e:
        logger.error(
            "Strategy %s: 调整切片后覆盖度验证失败: %s", strategy.id, e, exc_info=True
        )

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)
