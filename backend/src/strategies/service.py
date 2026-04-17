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
from sqlalchemy import select, func, update, and_
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
from src.jobs.factory import create_analysis_job_async
from src.jobs.models import AnalysisType
from src.feishu.client import fire_notification
from src.feishu import templates as feishu_tmpl
from src.social_media.analysis.models import SocialSlice
from src.social_media.monitors.crud import assert_social_monitor_access as assert_monitor_access
from src.social_media.tasks.models import SocialTask as SocialTask
from .models import Strategy, StrategySlice
from .schemas import (
    ApproveProbeResponse,
    CollectionStatusResponse,
    CollectionTaskStatus,
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

# 便捷别名，service 内部直接用
_strategy_read = StrategyRead.from_orm_full
_strategy_list_item = StrategyListItem.from_orm_full

logger = logging.getLogger(__name__)


async def create_strategy(
    db: AsyncSession, data: StrategyCreate, user_id: int
) -> Strategy:
    """创建策略

    校验每个 slice_id 的存在性和项目访问权限，
    然后创建 Strategy + StrategySlice 记录。
    """
    # 校验每个 slice
    for sid in data.slice_ids:
        slice_obj = await db.get(SocialSlice, sid)
        if not slice_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"切片 {sid} 不存在",
            )
        await assert_monitor_access(db, slice_obj.monitor_id, user_id, detail=f"无权访问切片 {sid} 所属项目")

    # 创建 Strategy
    brief_dict = data.brand_brief.model_dump() if data.brand_brief else None
    strategy = Strategy(
        name=data.name,
        user_id=user_id,
        brand_brief=brief_dict,
    )
    db.add(strategy)
    await db.flush()

    # 添加参与者
    if data.participant_ids:
        from src.auth.models import User as UserModel

        filtered_ids = [uid for uid in data.participant_ids if uid != user_id]
        if filtered_ids:
            users = await db.execute(select(UserModel).where(UserModel.id.in_(filtered_ids)))
            for u in users.scalars().all():
                strategy.participants.append(u)

    # 创建关联
    for sid in data.slice_ids:
        db.add(StrategySlice(strategy_id=strategy.id, slice_id=sid))

    await db.commit()

    # 重新查询以加载关系
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
    """按 ID 获取策略（含关系）"""
    query = (
        select(Strategy)
        .where(Strategy.id == strategy_id)
        .options(
            selectinload(Strategy.user),
            selectinload(Strategy.participants),
            selectinload(Strategy.slices)
            .selectinload(StrategySlice.slice)
            .selectinload(SocialSlice.monitor),
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
    """删除策略（CASCADE 自动清理 strategy_slices）"""
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
    await _sync_participants_to_monitors(db, strategy)
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
    await _sync_participants_to_monitors(db, strategy)
    await db.commit()
    return await get_strategy_by_id(db, strategy.id)


async def _sync_participants_to_monitors(db: AsyncSession, strategy: Strategy) -> None:
    """将策略 participants 同步（覆盖）到关联的 SocialMonitor 和 NewsMonitor。

    只同步由策略创建/关联的 monitor（通过 social_monitor_id / news_monitor_id 判断）。
    独立创建的 monitor 不受此影响。
    """
    participant_ids = [p.id for p in strategy.participants]

    if strategy.social_monitor_id:
        from src.social_media.monitors.crud import get_social_monitor_by_id
        from src.auth.models import User

        monitor = await get_social_monitor_by_id(db, strategy.social_monitor_id, load_relations=True)
        if monitor:
            users = await db.execute(select(User).where(User.id.in_(participant_ids)))
            new_participants = [u for u in users.scalars().all() if u.id != monitor.user_id]
            monitor.participants = new_participants
            await db.flush()

    if strategy.news_monitor_id:
        from src.news_media.monitors.crud import get_monitor_by_id as get_news_monitor_by_id
        from src.auth.models import User

        news_monitor = await get_news_monitor_by_id(db, strategy.news_monitor_id, load_relations=True)
        if news_monitor:
            users2 = await db.execute(select(User).where(User.id.in_(participant_ids)))
            new_participants2 = [u for u in users2.scalars().all() if u.id != news_monitor.user_id]
            news_monitor.participants = new_participants2
            await db.flush()


async def load_strategy_inputs(db: AsyncSession, strategy: Strategy) -> list[dict]:
    """加载策略社媒切片数据（SocialSlice.result_data）"""
    slice_ids = [s.slice_id for s in strategy.slices]
    if not slice_ids:
        return []

    query = select(SocialSlice).where(SocialSlice.id.in_(slice_ids))
    result = await db.execute(query)
    slices = result.scalars().all()
    return [s.result_data for s in slices if s.result_data]


async def load_strategy_news_inputs(
    db: AsyncSession, strategy: Strategy
) -> list[dict]:
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
    """加载策略输入数据（含切片名），用于覆盖度验证链"""
    slice_ids = [s.slice_id for s in strategy.slices]
    if not slice_ids:
        return []

    query = select(SocialSlice).where(SocialSlice.id.in_(slice_ids))
    result = await db.execute(query)
    slices = result.scalars().all()
    return [(s.name, s.result_data) for s in slices if s.result_data]






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


def _validate_has_slices(strategy: Strategy) -> None:
    """校验策略已关联切片（insight 层前置条件）"""
    if not strategy.slices:
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
) -> dict | None:
    """加载策略关联的最新已完成 industry profile ResearchTask 的 result_data。

    返回 result_data dict 或 None（无研究任务/未完成），供 per-stage 格式化器使用。
    失败时优雅降级为 None，不中断主流程。
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
            return None

        logger.info(
            "%s 加载行业研究发现: strategy=%d, research_task=%d",
            stage_label, strategy.id, task.id,
        )
        return task.result_data
    except Exception as e:
        logger.warning("%s 行业研究数据加载失败，降级为空: %s", stage_label, e)
        return None


async def _retrieve_creative_research_findings(
    db: AsyncSession, strategy: Strategy, stage_label: str
) -> dict | None:
    """加载策略关联的最新已完成 creative profile ResearchTask 的 result_data。

    仅 brand_strategy/full_strategy 路径的 Brand Role / Big Idea 层使用。
    失败时优雅降级为 None，不中断主流程。
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
            return None

        logger.info(
            "%s 加载创意研究发现: strategy=%d, research_task=%d",
            stage_label, strategy.id, task.id,
        )
        return task.result_data
    except Exception as e:
        logger.warning("%s 创意研究数据加载失败，降级为空: %s", stage_label, e)
        return None


def _validate_slices_have_data(
    slices_data: list[dict],
    strategy: Strategy,
    news_slices_data: list[dict] | None = None,
) -> None:
    """校验切片是否有分析数据

    campaign_strategy 路径强制要求 social_media 作为主源——insight/brand_role/big_idea 的 prompt
    结构性依赖消费者声音（KOL/topic_aspects/pains/gains 等），纯新闻数据跑不出
    Tension / Brand Social Role / Big Idea。news_media 只作为补充视角存在。

    market_report 路径以 news_media 为主源，social_media 为可选补充。
    """
    output_type = strategy.output_type or "campaign_strategy"

    if output_type == "campaign_strategy":
        if not slices_data:
            slice_ids = [s.slice_id for s in strategy.slices]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"campaign_strategy 产出路径依赖社媒切片作为消费者声音主源，"
                    f"但切片 {slice_ids} 尚无社媒分析数据。"
                ),
            )
        return

    if output_type == "market_report":
        if not news_slices_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="market_report 产出路径依赖新闻切片作为主源，但新闻切片尚无分析数据。",
            )
        return

    if output_type == "full_strategy":
        if not slices_data:
            slice_ids = [s.slice_id for s in strategy.slices]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"full_strategy 产出路径依赖社媒切片作为消费者声音主源，"
                    f"但切片 {slice_ids} 尚无社媒分析数据。"
                ),
            )
        if not news_slices_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="full_strategy 产出路径依赖新闻切片作为竞争格局主源，但新闻切片尚无分析数据。",
            )
        return

    # 未知 output_type：按旧的宽松校验兜底
    if not slices_data and not news_slices_data:
        slice_ids = [s.slice_id for s in strategy.slices]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"切片 {slice_ids} 尚未完成分析",
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
    _validate_has_slices(strategy)

    # full_strategy 路径：Insight 在 Landscape 完成后运行，需先验证 Landscape 结果已存在
    if strategy.output_type == "full_strategy" and strategy.landscape_result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="full_strategy 路径：请先完成 Landscape（竞争格局）分析，再生成 Insight 层",
        )

    # 校验切片 Stage2 流水线已完成（campaign_strategy 三层都依赖 intent/focus 层数据）
    for ss in strategy.slices:
        rd = (ss.slice.result_data or {}) if ss.slice else {}
        pipeline = rd.get("pipeline") or {}
        stage2 = pipeline.get("stage2") or {}
        if stage2.get("status") and stage2["status"] != "completed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="切片分析流水线尚未完成，请稍后再生成洞察层",
            )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)

    research_result = await _retrieve_research_findings(db, strategy, "Insight")
    from src.llm.chains.strategy.research_findings import format_research_for_insight
    research_findings_text = format_research_for_insight(research_result)

    # full_strategy 路径：用 Landscape 结构化输出替代原始新闻切片注入 news_media_section，
    # 让 Insight 获得的不是零散新闻片段，而是已综合分析的竞争格局视角
    if strategy.output_type == "full_strategy" and strategy.landscape_result:
        landscape_as_news_section = (
            "## 竞争格局视角（来自 Landscape 分析，替代原始新闻切片）\n\n"
            "以下为已完成的竞争格局分析结果，包含品类玩家定位、媒体份额和议程战场，"
            "作为 Insight 分析的竞争背景参考（不是消费者声音，不要混淆）。\n\n"
            + json.dumps(strategy.landscape_result, ensure_ascii=False, indent=2)
        )
        effective_news_slices = []  # 原始新闻切片不再注入
    else:
        landscape_as_news_section = None
        effective_news_slices = news_slices_data

    chain = create_insight_chain()
    inputs = format_slice_data_for_insight(
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
        news_slices=effective_news_slices,
        research_findings=research_findings_text,
    )
    # full_strategy：覆盖 format_slice_data_for_insight 生成的 news_media_section
    if landscape_as_news_section is not None:
        inputs["news_media_section"] = landscape_as_news_section

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
            slices_data, news_slices_data,
            primary_channel="social_media",
            research_findings=research_findings_text,
        )
        logger.info("Strategy %d Insight 生成完成 (%.1fs)", strategy.id, duration)

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.insight_result = result
        strategy.brand_role_result = None
        strategy.big_idea_result = None
        # full_strategy：Insight 是 Landscape 之后的子阶段，status 保持 landscape_done
        # 避免从 landscape_done(6) 回退到 insight_done(5) 引发后续状态校验混乱
        if strategy.output_type != "full_strategy":
            strategy.status = "insight_done"

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error("Strategy %d Insight 生成失败: %s", strategy.id, exc, exc_info=True)
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


async def generate_brand_role(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 campaign_strategy 第 2 层 (策略): Brand Social Role + Social Strategy"""
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

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)

    research_result = await _retrieve_research_findings(db, strategy, "BrandRole")
    from src.llm.chains.strategy.research_findings import (
        format_research_for_brand_role,
        format_creative_for_brand_role,
    )
    research_findings_text = format_research_for_brand_role(research_result)

    creative_result = await _retrieve_creative_research_findings(db, strategy, "BrandRole")
    creative_references_text = format_creative_for_brand_role(creative_result)

    chain = create_brand_role_chain()
    inputs = format_data_for_brand_role(
        strategy.insight_result,
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
        news_slices=news_slices_data,
        research_findings=research_findings_text,
        creative_references=creative_references_text,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_BRAND_ROLE.value,
        source_count=len(slices_data) + len(news_slices_data),
        status="running",
        analysis_config={"strategy_id": strategy.id},
    )

    try:
        start = time.time()
        response = await chain.ainvoke(inputs)
        duration = time.time() - start

        result = parse_brand_role_response(response.content)
        result["data_provenance"] = _build_data_provenance(
            slices_data, news_slices_data,
            primary_channel="social_media",
            research_findings=research_findings_text,
        )
        logger.info("Strategy %d Brand Role 生成完成 (%.1fs)", strategy.id, duration)

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.brand_role_result = result
        strategy.big_idea_result = None
        # full_strategy：status 保持 landscape_done，不推进到 brand_role_done(6=landscape_done)
        # 防止 STATUS_ORDER 比较混乱（两者 order 相同，但避免歧义语义）
        if strategy.output_type != "full_strategy":
            strategy.status = "brand_role_done"

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error("Strategy %d Brand Role 生成失败: %s", strategy.id, exc, exc_info=True)
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


async def generate_big_idea(db: AsyncSession, strategy: Strategy) -> Strategy:
    """生成 campaign_strategy 第 3 层 (创意): Big Idea + Content Strategy"""
    # full_strategy：status 在 landscape_done(6) 之后不经过 brand_role_done(6)，
    # 用 brand_role_result 存在性代替 status 校验
    if strategy.output_type == "full_strategy":
        if not strategy.brand_role_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="full_strategy 路径：请先完成 Brand Role（策略层）分析，再生成 Big Idea",
            )
    elif STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["brand_role_done"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成并确认策略层",
        )

    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)
    _validate_slices_have_data(slices_data, strategy, news_slices_data)

    research_result = await _retrieve_research_findings(db, strategy, "BigIdea")
    from src.llm.chains.strategy.research_findings import (
        format_research_for_big_idea,
        format_creative_for_big_idea,
    )
    research_findings_text = format_research_for_big_idea(research_result)

    creative_result = await _retrieve_creative_research_findings(db, strategy, "BigIdea")
    creative_references_text = format_creative_for_big_idea(creative_result)

    chain = create_big_idea_chain()
    inputs = format_data_for_big_idea(
        strategy.insight_result,
        strategy.brand_role_result,
        slices_data,
        strategy.brand_brief,
        research_design=strategy.research_design,
        news_slices=news_slices_data,
        research_findings=research_findings_text,
        creative_references=creative_references_text,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_BIG_IDEA.value,
        source_count=len(slices_data) + len(news_slices_data),
        status="running",
        analysis_config={"strategy_id": strategy.id},
    )

    try:
        start = time.time()
        response = await chain.ainvoke(inputs)
        duration = time.time() - start

        result = parse_big_idea_response(response.content)
        result["data_provenance"] = _build_data_provenance(
            slices_data, news_slices_data,
            primary_channel="social_media",
            research_findings=research_findings_text,
        )
        logger.info("Strategy %d Big Idea 生成完成 (%.1fs)", strategy.id, duration)

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.big_idea_result = result
        strategy.status = "completed"

        await db.commit()
        fire_notification(feishu_tmpl.big_idea_done_card(strategy.name, strategy.id))
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error("Strategy %d Big Idea 生成失败: %s", strategy.id, exc, exc_info=True)
        try:
            job.status = "failed"
            job.error_message = str(exc)[:500]
            job.completed_at = datetime.now(timezone.utc)
            job.processing_time = int(time.time() - start)
            await db.commit()
        except Exception:
            await db.rollback()
        raise


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
) -> Strategy:
    """编辑 campaign_strategy 路径的 insight / brand_role / big_idea 结果。

    编辑上游层会级联清除下游层（避免陈旧结果与新修改冲突），
    并根据 stage 把 strategy.status 回退到对应节点。
    """
    if strategy.output_type and strategy.output_type not in ("campaign_strategy", "full_strategy"):
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
        strategy.brand_role_result = None
        strategy.big_idea_result = None
        # full_strategy：insight 是 landscape 之后的子阶段，保持 landscape_done
        if not is_full:
            strategy.status = "insight_done"
    elif stage == "brand_role":
        if not strategy.brand_role_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="brand_role 层尚未生成，无法编辑",
            )
        strategy.brand_role_result = result
        strategy.big_idea_result = None
        # full_strategy：brand_role 是 landscape 之后的子阶段，保持 landscape_done
        if not is_full:
            strategy.status = "brand_role_done"
    else:  # stage == "big_idea"
        if not strategy.big_idea_result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="big_idea 层尚未生成，无法编辑",
            )
        strategy.big_idea_result = result
        strategy.status = "completed"

    flag_modified(strategy, f"{stage}_result")
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
            detail=(
                f"stage 必须为 agenda_map/landscape/strategic_brief，收到 {stage}"
            ),
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
            strategy.brand_role_result = None
            strategy.big_idea_result = None
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
            strategy.brand_role_result = None
            strategy.big_idea_result = None
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

    research_result = await _retrieve_research_findings(db, strategy, "AgendaMap")
    from src.llm.chains.strategy.research_findings import format_research_for_agenda_map
    research_findings_text = format_research_for_agenda_map(research_result)

    chain = create_agenda_map_chain()
    inputs = format_inputs_for_agenda_map(
        news_slices=news_slices_data,
        brief=strategy.brand_brief,
        research_design=strategy.research_design,
        research_findings=research_findings_text,
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
        result["data_provenance"] = _build_data_provenance(
            slices_data, news_slices_data,
            primary_channel="news_media",
            research_findings=research_findings_text,
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
            strategy.brand_role_result = None
            strategy.big_idea_result = None
        strategy.status = "agenda_map_done"

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error("Strategy %d Agenda Map 生成失败: %s", strategy.id, exc, exc_info=True)
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

    research_result = await _retrieve_research_findings(db, strategy, "Landscape")
    from src.llm.chains.strategy.research_findings import format_research_for_landscape
    research_findings_text = format_research_for_landscape(research_result)

    chain = create_landscape_chain()
    inputs = format_inputs_for_landscape(
        agenda_map_result=strategy.agenda_map_result,
        news_slices=news_slices_data,
        brief=strategy.brand_brief,
        research_design=strategy.research_design,
        research_findings=research_findings_text,
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
        result["data_provenance"] = _build_data_provenance(
            slices_data, news_slices_data,
            primary_channel="news_media",
            research_findings=research_findings_text,
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
            strategy.brand_role_result = None
            strategy.big_idea_result = None
        strategy.status = "landscape_done"

        await db.commit()
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error("Strategy %d Landscape 生成失败: %s", strategy.id, exc, exc_info=True)
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
    """生成 Market Report 第 3 层（终层）：战略简报 (Strategic Brief)"""
    _validate_market_report_output_type(strategy)
    # strategic_brief 是 market_report 的终层；full_strategy 的终层是 big_idea，不生成 strategic_brief
    if strategy.output_type == "full_strategy":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="full_strategy 路径不生成 Strategic Brief；请继续生成 Insight → Brand Role → Big Idea",
        )

    if STATUS_ORDER.get(strategy.status, 0) < STATUS_ORDER["landscape_done"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先完成并确认 Landscape",
        )

    # strategic_brief 不加载切片数据（纯 agenda_map + landscape 合成），
    # 但仍记录 provenance 便于前端展示
    slices_data = await load_strategy_inputs(db, strategy)
    news_slices_data = await load_strategy_news_inputs(db, strategy)

    # strategic_brief 只注入高置信度研究要点作为证据锚点，不引入大量新数据
    research_result = await _retrieve_research_findings(db, strategy, "StrategicBrief")
    from src.llm.chains.strategy.research_findings import format_research_for_strategic_brief
    research_findings_text = format_research_for_strategic_brief(research_result)

    chain = create_strategic_brief_chain()
    inputs = format_inputs_for_strategic_brief(
        agenda_map_result=strategy.agenda_map_result,
        landscape_result=strategy.landscape_result,
        brief=strategy.brand_brief,
        research_design=strategy.research_design,
        research_findings=research_findings_text,
    )

    job = await create_analysis_job_async(
        db,
        social_monitor_id=strategy.social_monitor_id,
        news_monitor_id=strategy.news_monitor_id,
        user_id=strategy.user_id,
        analysis_type=AnalysisType.STRATEGY_STRATEGIC_BRIEF.value,
        source_count=len(news_slices_data),
        status="running",
        analysis_config={"strategy_id": strategy.id},
    )

    try:
        start = time.time()
        response = await chain.ainvoke(inputs)
        duration = time.time() - start

        result = parse_strategic_brief_response(response.content)
        result["data_provenance"] = _build_data_provenance(
            slices_data, news_slices_data,
            primary_channel="news_media",
            research_findings=research_findings_text,
        )
        # 埋点：观察 evidence_refs 实际产出规模，为后续决定是否需要路径校验提供数据
        priorities = result.get("strategic_priorities") or []
        total_refs = sum(len(sp.get("evidence_refs") or []) for sp in priorities)
        logger.info(
            "Strategy %d Strategic Brief 生成完成 (%.1fs): %d priorities, %d evidence_refs",
            strategy.id, duration, len(priorities), total_refs,
        )

        now = datetime.now(timezone.utc)
        job.status = "completed"
        job.completed_at = now
        job.analyzed_count = 1
        job.processing_time = int(duration)
        job.token_usage = extract_token_usage(response, duration_seconds=duration)

        strategy.strategic_brief_result = result
        strategy.status = "completed"

        await db.commit()
        fire_notification(feishu_tmpl.strategic_brief_done_card(strategy.name, strategy.id))
        return await get_strategy_by_id(db, strategy.id)
    except Exception as exc:
        logger.error("Strategy %d Strategic Brief 生成失败: %s", strategy.id, exc, exc_info=True)
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
        news_channel_brief=_extract_channel_brief(brand_brief, "news_media"),
        research_channel_brief=_extract_channel_brief(brand_brief, "industry_research"),
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

    response = DesignResearchResponse(
        understanding_summary=parsed["understanding_summary"],
        research_questions=parsed["research_questions"],
        data_plan=parsed["data_plan"],
        slice_blueprint=parsed["slice_blueprint"],
        primary_sources=parsed.get("primary_sources", []),
        output_type=parsed["output_type"],
        output_type_rationale=parsed.get("output_type_rationale", ""),
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
        from src.news_media.tasks.service import get_news_tasks_by_strategy, delete_news_task

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

    # 清除关联切片（自动创建的）
    for ss in list(strategy.slices):
        await db.delete(ss)

    await db.commit()

    updated = await get_strategy_by_id(db, strategy.id)
    logger.info(
        "Strategy %d 重置到研究设计阶段 (删除 %d 社媒 + %d 新闻任务)",
        strategy.id,
        len(deleted_social_tasks),
        deleted_news_count,
    )
    return _strategy_read(updated)


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

    # 从 probing 状态重新确认：清理旧探测数据，重新创建任务
    if strategy.status == "probing":
        from src.social_media.tasks import crud as task_crud
        from src.social_media.tasks.models import SocialTask as _DataTask

        old_tasks = await db.execute(
            select(_DataTask).where(
                _DataTask.strategy_id == strategy.id,
                _DataTask.is_deleted.is_(False),
            )
        )
        for _task in old_tasks.scalars().all():
            await task_crud.delete_task(db, _task)

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

    # 预估总任务数，超过 20 个视为异常（提示用户精简，而非静默创建大量任务）
    # 社媒: keywords × platforms；新闻: keywords（每个关键词 1 个任务，无 platforms）
    estimated_tasks = sum(
        len(dp.get("keywords") or []) * max(len(dp.get("platforms") or []), 1)
        for dp in data_plan
    )
    if estimated_tasks > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"研究计划预估任务数（{estimated_tasks}）过多，请精简关键词或平台（建议 6-10 个任务）",
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
            news_channels = ["baidu", "sogou", "duckduckgo"]
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

    # 条件创建 Research Agent 任务（仅 research_design 包含 industry_research 时）
    brief = strategy.brand_brief or {}
    ra_channel_brief = _extract_channel_brief(brief, "industry_research")
    if ra_channel_brief:
        try:
            from src.research_agent.service import create_research_task

            research_title = brief.get("subject", "") or "行业研究"
            # query = channel_brief（industry_research 渠道专属定制描述，Planner 的主锚点）
            # context = analysis_goal（整体策略背景，replan 各轮持续参考）
            analysis_goal = brief.get("analysis_goal", "")
            search_config = {"context": analysis_goal} if analysis_goal else {}
            # research_questions 不传：Planner 从 channel_brief 自行生成搜索优化的问题
            await create_research_task(
                db,
                user_id=current_user_id,
                analysis_goal=ra_channel_brief,
                title=research_title,
                search_config=search_config,
                strategy_id=strategy.id,
                profile_name="industry",
            )
            logger.info("策略 %d: 创建行业研究 Research Agent 任务", strategy.id)
        except Exception as e:
            logger.warning("策略 %d: 创建行业研究任务失败（不阻塞主流程）: %s", strategy.id, e)
            partial_errors.append(f"创建研究任务失败: {e}")

    # 条件创建创意研究任务（campaign_strategy/full_strategy + brief 含 creative_research 渠道时）
    # 创意研究搜集竞品 Campaign 案例，注入 Brand Role 和 Big Idea 层提供差异化起点
    if output_type in ("campaign_strategy", "full_strategy"):
        creative_channel_brief = _extract_channel_brief(brief, "creative_research")
        if creative_channel_brief:
            try:
                from src.research_agent.service import create_research_task  # noqa: F811

                subject = brief.get("subject", "") or "品牌"
                analysis_goal = brief.get("analysis_goal", "")
                search_config = {"context": analysis_goal} if analysis_goal else {}
                await create_research_task(
                    db,
                    user_id=current_user_id,
                    analysis_goal=creative_channel_brief,
                    title=f"{subject} 竞品创意研究",
                    search_config=search_config,
                    strategy_id=strategy.id,
                    profile_name="creative",
                )
                logger.info("策略 %d: 创建创意研究 Research Agent 任务", strategy.id)
            except Exception as e:
                logger.warning("策略 %d: 创建创意研究任务失败（不阻塞主流程）: %s", strategy.id, e)
                partial_errors.append(f"创建创意研究任务失败: {e}")

    await db.commit()
    updated = await get_strategy_by_id(db, strategy.id)
    return ConfirmResearchResponse(
        created_monitor_id=monitor.id,
        created_task_count=len(created_task_ids),
        created_news_task_count=len(created_news_task_ids),
        partial_errors=partial_errors,
        strategy=_strategy_read(updated),
    )


# ==================== ② 探测验证 ====================

# 防止多个并发请求同时触发同一策略的 LLM 审查
_probe_review_in_progress: set[int] = set()


async def _build_probe_task_summaries(
    db: AsyncSession,
    task_ids: list[int],
) -> tuple[list[SocialProbeTaskStatus], list[dict]]:
    """查询探测任务状态和分析摘要

    Returns:
        (task_statuses, analyzed_summaries)
        analyzed_summaries 只包含已有分析结果的任务摘要，供审查使用
    """
    from src.social_media.tasks.models import SocialTask as SocialTask

    if not task_ids:
        return [], []

    query = select(SocialTask).where(
        SocialTask.id.in_(task_ids), SocialTask.is_deleted.is_(False)
    )
    result = await db.execute(query)
    tasks = result.scalars().all()

    # 爬虫已完成（含 0 结果）的终态
    _PROBE_TERMINAL_STATUSES = {"probe_ready", "approved", "completed", "failed"}

    statuses = []
    analyzed_summaries = []

    for task in tasks:
        has_analysis = task.analysis_result is not None
        # 只有进入终态（爬虫已结束）且 0 条时才视为已处理，避免把仍在运行的任务提前计入
        no_data = (task.posts_count or 0) == 0 and task.status in _PROBE_TERMINAL_STATUSES

        # 0 条数据：爬虫已完成但无结果，无需 LLM 判断，直接视为已处理（客观规则层会自动 fail）
        statuses.append(
            SocialProbeTaskStatus(
                task_id=task.id,
                keyword=task.keywords or "",
                platform=task.platform.code if task.platform else "",
                status=task.status,
                has_analysis=has_analysis or no_data,
            )
        )

        if has_analysis:
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
                {"name": t.get("name", ""), "mentions": t.get("mentions", 0)}
                for t in top_topics_raw[:10]
            ]

            summary = {
                "task_id": task.id,
                "keyword": task.keywords or "",
                "platform": task.platform.code if task.platform else "",
                "posts_count": task.posts_count,
                "deep_analyzed": data_volume.get("deep_analyzed", 0),
                "entity_match": entity_match,
                "top_topics": top_topics,
                "promotion_ratio": marketing.get("promotion_ratio"),
            }
            analyzed_summaries.append(summary)
        elif no_data:
            # 0 条帖子：加入 summaries 供客观规则层直接 fail，不送 LLM
            analyzed_summaries.append({
                "task_id": task.id,
                "keyword": task.keywords or "",
                "platform": task.platform.code if task.platform else "",
                "posts_count": 0,
                "deep_analyzed": 0,
                "entity_match": False,
                "top_topics": [],
                "promotion_ratio": None,
            })

    return statuses, analyzed_summaries


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


def _auto_verdict_probe_task(summary: dict) -> tuple[str, str] | None:
    """客观规则层：根据量化指标直接判定，返回 (verdict, note) 或 None（交 LLM 判断）

    Hard FAIL：内容极少 / 广告占比极高
    数据门槛：深度分析样本不足，默认 pass 待全量后验证
    None：交 LLM 判断话题与研究问题的相关性
    """
    posts = summary.get("posts_count") or 0
    promo = summary.get("promotion_ratio")
    deep_analyzed = summary.get("deep_analyzed") or 0

    # Hard FAIL
    if posts < 5:
        return "fail", f"平台内容极少（仅 {posts} 条），关键词在此平台可能无效"
    if promo is not None and promo > 0.85:
        return "fail", f"广告内容占比 {promo:.0%}，自然讨论极少"

    # 数据门槛：深度分析样本不足，无法判断话题相关性，默认通过待全量后验证
    if deep_analyzed < 5:
        return "pass", f"深度分析样本较少（{deep_analyzed} 条），待全量采集后验证话题相关性"

    return None  # 交 LLM 判断话题相关性


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
            task_summary.get("task_id"), exc,
        )
        return None, None, time.time() - t0


async def _run_probe_review_bg_task(
    strategy_id: int,
    analyzed_summaries: list[dict],
    news_probe_summaries: list[dict] | None = None,
) -> None:
    """后台任务：运行探测审查，结果写入 DB（不阻塞 HTTP 响应）

    全量评估所有任务（不区分新旧轮次）：
    1. 客观规则层（_auto_verdict_probe_task）处理明确案例
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
                result = _auto_verdict_probe_task(summary)
                if result is not None:
                    verdict, note = result
                    auto_assessments.append({
                        "task_id": summary["task_id"],
                        "keyword": summary["keyword"],
                        "platform": summary["platform"],
                        "entity_match": summary.get("entity_match", False),
                        "verdict": verdict,
                        "note": note,
                    })
                    if verdict == "fail":
                        # 规则 fail：内容极少或几乎全是广告，LLM 无法从中获取有效话题
                        # 给出通用建议，具体关键词由用户根据研究方向决定
                        rule_suggestions.append({
                            "task_id": summary["task_id"],
                            "original_keyword": summary["keyword"],
                            "suggested_keyword": None,
                            "platform": summary["platform"],
                            "reason": note,
                        })
                else:
                    ambiguous_summaries.append(summary)

            # 加载所有新闻 probe 任务（含失败任务，用于后续补规则建议）
            from src.news_media.tasks.service import get_news_tasks_by_strategy as _get_news_tasks
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
                    news_results = await asyncio.gather(*[
                        _run_news_probe_review_one(news_chain, research_design, brief, nps)
                        for nps in news_probe_summaries
                    ])
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
                            auto_assessments.append({
                                "task_id": nps["task_id"],
                                "keyword": nps["keyword"],
                                "platform": "news_media",
                                "entity_match": False,
                                "verdict": "pass",
                                "note": "LLM 审查失败，已默认通过，请人工核查卡片后决定",
                            })
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
                            "avg_tokens_per_call": float(total_tokens) / news_total if news_total else 0.0,
                            "avg_cost_per_call": round(total_cost / news_total, 6) if news_total else 0.0,
                        },
                        "call_details": call_details,
                    }
                    news_job.analyzed_count = len(news_llm_assessments)
                    news_job.processing_time = int(duration_news)
                    news_job.completed_at = datetime.now(timezone.utc)
                    if failed_calls and failed_calls == news_total:
                        news_job.status = "failed"
                        news_job.error_message = f"全部 {failed_calls} 个新闻 probe LLM 调用失败"
                    else:
                        news_job.status = "completed"
                        if failed_calls:
                            news_job.error_message = f"{failed_calls} 个调用失败（已保守判 pass）"
                    await db.commit()
                except Exception as exc:
                    logger.error("Strategy %d news probe review 异常: %s", strategy.id, exc, exc_info=True)
                    news_job.status = "failed"
                    news_job.error_message = str(exc)[:500]
                    news_job.completed_at = datetime.now(timezone.utc)
                    news_job.processing_time = int(time.time() - start_news)
                    await db.commit()
                    raise

                logger.info(
                    "Strategy %d news probe review 完成 (%.1fs, 任务=%d, 成功=%d, 失败=%d)",
                    strategy.id, duration_news, news_total, len(news_llm_assessments), failed_calls,
                )

            # 新闻 LLM 结果直接合入 auto_assessments（已是终态，不进二次 LLM）
            for a in news_llm_assessments:
                auto_assessments.append({
                    "task_id": a.get("task_id"),
                    "keyword": a.get("keyword", ""),
                    "platform": "news_media",
                    "entity_match": False,
                    "verdict": a.get("verdict", "pass"),
                    "note": a.get("note", ""),
                })
                if a.get("verdict") == "fail":
                    rule_suggestions.append({
                        "task_id": a.get("task_id"),
                        "original_keyword": a.get("keyword", ""),
                        "suggested_keyword": a.get("suggested_keyword"),
                        "platform": "news_media",
                        "reason": a.get("suggestion_reason") or a.get("note", ""),
                    })

            # 失败的新闻探测任务未进 LLM 审查（无文章数据可评估），补规则建议
            reviewed_news_ids = {nps["task_id"] for nps in news_probe_summaries}
            for npt in news_probe_tasks:
                if npt.status == "failed" and npt.id not in reviewed_news_ids:
                    note = npt.error_message or "新闻探测任务失败，未能采集到搜索结果"
                    keyword = npt.keywords or ""
                    auto_assessments.append({
                        "task_id": npt.id,
                        "keyword": keyword,
                        "platform": "news_media",
                        "entity_match": False,
                        "verdict": "fail",
                        "note": note,
                    })
                    # suggested_keyword 与原词相同：应用建议时移除失败任务并以原词重新创建，
                    # 相当于重试；用户可在确认弹窗前手动改词
                    rule_suggestions.append({
                        "task_id": npt.id,
                        "original_keyword": keyword,
                        "suggested_keyword": keyword,
                        "platform": "news_media",
                        "reason": f"采集失败（{note}），已恢复原词重新探测。如需换词可在应用前修改。",
                    })

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
            "Strategy %d probe review background task failed: %s", strategy_id, e, exc_info=True
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

        async def _evaluate_one(task_summary: dict) -> tuple[dict | None, dict | None, float]:
            """评估单个任务，返回 (assessment, token_usage, duration)"""
            inputs = format_single_task_probe_review_inputs(
                research_design=research_design,
                task=task_summary,
                brief=brief,
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
                    strategy.id, task_summary.get("task_id"), exc,
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
                    "avg_tokens_per_call": float(total_tokens) / len(ambiguous_summaries) if ambiguous_summaries else 0.0,
                    "avg_cost_per_call": round(total_cost / len(ambiguous_summaries), 6) if ambiguous_summaries else 0.0,
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
                strategy.id, duration, len(ambiguous_summaries), len(llm_assessments),
            )
        except Exception as exc:
            logger.error("Strategy %d social probe review 异常: %s", strategy.id, exc, exc_info=True)
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
            all_suggestions.append({
                "task_id": a["task_id"],
                "original_keyword": a.get("keyword", ""),
                "suggested_keyword": a["suggested_keyword"],
                "platform": a.get("platform", ""),
                "reason": a.get("suggestion_reason", ""),
            })

    # 后处理：检测 brand_voice / competitive 互补平台失败，替换为平台统一建议
    from src.llm.chains.strategy.social_probe_review_chain import detect_and_replace_symmetry_suggestions
    all_suggestions = detect_and_replace_symmetry_suggestions(
        all_assessments=all_assessments,
        existing_suggestions=all_suggestions,
        research_design=strategy.research_design or {},
    )

    logger.info(
        "Strategy %d probe review 完成 (verdict=%s, 规则自动=%d, LLM=%d)",
        strategy.id, overall,
        len(auto_assessments or []), len(llm_assessments),
    )

    # 按渠道聚合 verdict，生成渠道级摘要
    channel_summary = _build_channel_summary(all_assessments)

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
        fire_notification(feishu_tmpl.probe_needs_review_card(
            strategy.name, strategy.id, overall_verdict=overall,
        ))

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
    task_statuses, analyzed_summaries = await _build_probe_task_summaries(db, task_ids)

    # 新闻任务状态（进入终态即视为已处理，failed 不阻塞审查触发）
    _NEWS_PROBE_TERMINAL = {"completed", "failed"}
    news_all_analyzed = all(t.status in _NEWS_PROBE_TERMINAL for t in news_probe_tasks)
    news_analyzed_count = sum(1 for t in news_probe_tasks if t.status in _NEWS_PROBE_TERMINAL)

    # 构建新闻任务状态列表（供前端展示）
    from src.strategies.schemas import NewsProbeTaskStatus
    news_probe_dim_map: dict[str, str] = (strategy.research_design or {}).get("_news_task_dimension_map") or {}
    news_task_statuses = [
        NewsProbeTaskStatus(
            task_id=npt.id,
            keyword=npt.keywords or "",
            dimension=news_probe_dim_map.get(str(npt.id), ""),
            status=npt.status,
            completed=npt.status == "completed" and bool(npt.analysis_result),
            failed=npt.status == "failed",
            articles_count=(npt.analysis_result or {}).get("meta", {}).get("articles_total", 0)
            if npt.analysis_result
            else 0,
        )
        for npt in news_probe_tasks
    ]

    # 新闻 probe 送 LLM 审查：加载每个任务的文章卡片（title/source/tier/snippet）
    # 由 strategy_news_probe_review_chain 基于搜索结果判断关键词相关性与信号质量
    from src.news_media.tasks import crud as news_crud

    news_probe_summaries: list[dict] = []
    for npt in news_probe_tasks:
        if not (npt.status == "completed" and npt.analysis_result):
            continue
        meta = (npt.analysis_result or {}).get("meta", {}) or {}
        articles, _ = await news_crud.get_articles_by_task(
            db, task_id=npt.id, skip=0, limit=40
        )
        news_probe_summaries.append({
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
        })

    # 兼容纯新闻策略（无社媒任务时 task_statuses 为空）
    social_all_analyzed = not task_statuses or all(t.has_analysis for t in task_statuses)
    news_check = not news_probe_tasks or news_all_analyzed
    all_analyzed = bool(social_all_analyzed and news_check and (task_statuses or news_probe_tasks))
    analyzed_count = sum(1 for t in task_statuses if t.has_analysis) + news_analyzed_count
    total_count = len(task_statuses) + len(news_probe_tasks)

    # 全部分析完成且尚无审查结果 → 触发后台 LLM 审查（仅针对社媒数据）
    if all_analyzed and not strategy.probe_review_result and strategy.id not in _probe_review_in_progress:
        _probe_review_in_progress.add(strategy.id)
        import asyncio
        asyncio.ensure_future(
            _run_probe_review_bg_task(strategy.id, analyzed_summaries, news_probe_summaries)
        )

    industry_status = await _get_research_agent_status(db, strategy.id, "industry")
    creative_status = await _get_research_agent_status(db, strategy.id, "creative")

    return ProbeStatusResponse(
        social_tasks=task_statuses,
        news_tasks=news_task_statuses,
        all_analyzed=all_analyzed,
        analyzed_count=analyzed_count,
        total_count=total_count,
        probe_review_result=strategy.probe_review_result,
        industry_research=industry_status,
        creative_research=creative_status,
        strategy=_strategy_read(strategy),
    )


# ==================== 探测任务审批和调整 ====================

async def approve_probe(
    db: AsyncSession,
    strategy: Strategy,
    current_user_id: int,
) -> ApproveProbeResponse:
    """手动确认探测，为每个探测任务创建独立的全量采集任务（phase="collect"）"""
    from src.social_media.tasks.models import SocialTask as SocialTask
    from src.social_media.tasks.schemas import SocialTaskCreate as SocialTaskCreate
    from src.social_media.tasks.service import create_task

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

    # 维度映射是自动建切片的唯一依据：必须完整存在
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

    # 创建全量采集任务，并同步重建 collect 阶段的 task_id -> dimension 映射
    collect_task_ids = []
    collect_dim_map: dict[str, str] = {}
    for pt in probe_tasks:
        # 构造任务参数
        collect_task_params = {
            "max_notes_count": 50,  # 全量采集默认 50 条
            "enable_comments": 1,  # 启用评论
            "per_note_max_comments_count": 20,  # 每帖最多 20 条评论
            # max_pages: 不设置，表示不限制翻页
        }

        dim = probe_dim_map.get(str(pt.id))
        if not dim:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"探测任务 {pt.id} 缺少维度映射，请重新确认研究计划",
            )

        collect_task = await create_task(
            db,
            strategy.social_monitor_id,
            SocialTaskCreate(
                name=f"{pt.keywords}-{pt.platform.name}",
                platform_id=pt.platform_id,
                task_type="search",
                keywords=pt.keywords,
                data_source="remote_crawler",
                task_params=collect_task_params,
                auto_analyze=True,
                phase="collect",  # 标记为全量采集任务
            ),
            current_user_id,
        )
        collect_task.strategy_id = strategy.id
        collect_task_ids.append(collect_task.id)
        collect_dim_map[str(collect_task.id)] = dim

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
                    search_params=None,
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

    await db.commit()

    # 新闻全量采集通过 celery 异步执行（与独立 news_media 流程统一）
    if news_collect_task_ids:
        from src.news_media.analysis.jobs import create_news_tagging_job
        from src.jobs import crud as jobs_crud
        from src.news_media.tasks import crud as news_crud
        from src.news_media.tasks.tasks import run_news_collect_task

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
            )
            await jobs_crud.set_celery_task_id(db, tagging_job.id, celery_result.id)
            await db.commit()

    updated = await get_strategy_by_id(db, strategy.id)
    return ApproveProbeResponse(
        approved_task_count=len(collect_task_ids),
        strategy=_strategy_read(updated),
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
    old_tasks_map: dict[int, SocialTask] = {t.id: t for t in old_tasks_result.scalars().all()}

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
    old_news_map: dict[int, NewsTask] = {t.id: t for t in old_news_result.scalars().all()}

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
        from src.news_media.tasks.service import create_news_task as create_news_task_svc
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
        strategy=_strategy_read(updated),
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

    all_completed = (
        all(task.status == "completed" for task in tasks)
        and all(t.status == "completed" for t in news_tasks)
    )
    all_analyzed = (
        all(task.analysis_result is not None for task in tasks)
        and all(t.analysis_result is not None for t in news_tasks)
    )

    task_statuses = [
        CollectionTaskStatus(
            task_id=task.id,
            keyword=task.keywords or "",
            platform=task.platform.code if task.platform else "",
            status=task.status,
            posts_count=task.posts_count,
            has_analysis=task.analysis_result is not None,
        )
        for task in tasks
    ]

    slices_created = False

    # 全部完成且全部已分析 → 自动建切片（若该策略尚未关联切片）
    if all_completed and all_analyzed:
        has_strategy_slices = bool(strategy.slices)
        if not has_strategy_slices:
            logger.info(
                "Strategy %s: 所有任务完成且已分析，开始自动建切片", strategy.id
            )
            try:
                await _create_auto_slices(db, strategy, tasks, current_user_id, news_tasks)
                slices_created = True
                logger.info("Strategy %s: 自动建切片完成", strategy.id)
            except Exception as e:
                logger.error(
                    "Strategy %s: 自动建切片失败: %s", strategy.id, e, exc_info=True
                )
        else:
            slices_created = True
    elif all_completed:
        logger.info("Strategy %s: 所有任务已完成，等待分析", strategy.id)

    completed_count = (
        sum(1 for t in tasks if t.status == "completed")
        + sum(1 for t in news_tasks if t.status == "completed")
    )
    total_count = len(tasks) + len(news_tasks)

    industry_status = await _get_research_agent_status(db, strategy.id, "industry")
    creative_status = await _get_research_agent_status(db, strategy.id, "creative")

    return CollectionStatusResponse(
        tasks=task_statuses,
        all_completed=all_completed,
        all_analyzed=all_analyzed,
        slices_created=slices_created,
        completed_count=completed_count,
        total_count=total_count,
        coverage_check_result=strategy.coverage_check_result,
        industry_research=industry_status,
        creative_research=creative_status,
        strategy=_strategy_read(strategy),
    )


async def _create_strategy_news_slice(
    db: AsyncSession,
    strategy: Strategy,
    name: str,
    news_task_ids: list[int],
    keywords: list[str],
    user_id: int,
) -> "NewsSlice | None":
    """为策略创建 NewsSlice 并运行 inline insight 分析。

    不调用 news_media.analysis.service.create_slice（它有中间 commit），
    改为 inline 创建 + 分析，与策略事务管理一致（最终由调用方统一 commit）。
    """
    from src.news_media.analysis.models import NewsSlice
    from src.news_media.analysis.service import _compute_stats
    from src.news_media.tasks.models import NewsArticle
    from src.news_media.tasks.service import _run_insight_analysis

    ns = NewsSlice(
        name=name,
        monitor_id=strategy.news_monitor_id,
        included_task_ids=news_task_ids,
        user_id=user_id,
    )
    db.add(ns)
    await db.flush()

    # 查询文章
    stmt = (
        select(NewsArticle)
        .where(NewsArticle.task_id.in_(news_task_ids))
        .order_by(NewsArticle.published_at.desc().nulls_last())
    )
    rows = await db.execute(stmt)
    all_articles = list(rows.scalars().all())

    # URL 去重
    seen_urls: set[str] = set()
    deduped: list = []
    for a in all_articles:
        if a.url not in seen_urls:
            seen_urls.add(a.url)
            deduped.append(a)

    # 过滤低相关
    filtered = [a for a in deduped if a.relevance != "low"]
    ns.stats = _compute_stats(filtered)

    if not filtered:
        ns.result_data = {"meta": {"articles_total": 0}}
        ns.status = "completed"
        logger.info("NewsSlice「%s」无有效文章，跳过 insight", name)
        return ns

    brand_brief = strategy.brand_brief or {}
    goal = f"{name}（关键词：{', '.join(keywords)}）" if keywords else name
    subj = brand_brief.get("subject", name)

    try:
        insights, _token_usage = await _run_insight_analysis(
            filtered, analysis_goal=goal, subject=subj,
        )
        ns.result_data = (
            insights
            if isinstance(insights, dict) and "error" not in insights
            else {"meta": ns.stats, "error": str(insights)}
        )
    except Exception as e:
        logger.error("NewsSlice「%s」insight 分析失败: %s", name, e, exc_info=True)
        ns.result_data = {"meta": ns.stats, "error": str(e)[:500]}
        ns.status = "failed"
        return ns

    ns.status = "completed"
    logger.info(
        "NewsSlice「%s」insight 完成：%d 篇文章（去重前 %d）",
        name, len(filtered), len(all_articles),
    )
    return ns


async def _create_auto_slices(
    db: AsyncSession,
    strategy: Strategy,
    collect_tasks: list,
    current_user_id: int,
    news_tasks: list = None,
) -> None:
    """按 slice_blueprint 自动创建 SocialSlice + NewsSlice，并关联到策略。

    社媒维度 → SocialSlice（Stage1/2/3 流水线）
    新闻维度 → NewsSlice（独立 insight 分析）

    每个 blueprint 条目可产生 0-1 个 SocialSlice + 0-1 个 NewsSlice。
    建完切片后立即触发 LLM 覆盖度验证并写入 strategy.coverage_check_result。
    """
    from src.social_media.analysis.service import create_monitor_slice

    blueprint: list[dict] = []
    research_design = strategy.research_design or {}
    if isinstance(research_design, dict):
        blueprint = research_design.get("slice_blueprint") or []

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

        slice_objs: list = []  # 社媒 SocialSlice
        news_slice_objs: list = []  # 新闻 NewsSlice

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

            if not matched_task_ids and not matched_news_task_ids:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"切片「{bp_name}」未匹配到任何任务，请检查 source_dimensions 配置",
                )

            # 创建社媒 SocialSlice
            if matched_task_ids:
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

            # 创建新闻 NewsSlice
            if matched_news_task_ids and strategy.news_monitor_id:
                ns = await _create_strategy_news_slice(
                    db,
                    strategy=strategy,
                    name=bp_name,
                    news_task_ids=matched_news_task_ids,
                    keywords=matched_news_keywords,
                    user_id=current_user_id,
                )
                if ns:
                    news_slice_objs.append(ns)
    else:
        # 无 blueprint：合并为综合切片
        slice_objs = []
        news_slice_objs = []

        if collect_tasks:
            all_task_ids = [t.id for t in collect_tasks]
            slice_obj = await create_monitor_slice(
                db,
                monitor_id=strategy.social_monitor_id,
                task_ids=all_task_ids,
                current_user_id=current_user_id,
                name="综合分析",
            )
            slice_objs = [slice_obj]

        if news_tasks and strategy.news_monitor_id:
            all_news_ids = [t.id for t in news_tasks]
            all_keywords = [t.keywords for t in news_tasks if t.keywords]
            ns = await _create_strategy_news_slice(
                db,
                strategy=strategy,
                name="综合分析",
                news_task_ids=all_news_ids,
                keywords=all_keywords,
                user_id=current_user_id,
            )
            if ns:
                news_slice_objs = [ns]

    # 社媒切片 Stage2/Stage3 pipeline 设置
    now_iso = datetime.now(timezone.utc).isoformat()
    pipeline_slice_ids: list[int] = []

    for s_obj in slice_objs:
        rd = s_obj.result_data
        if not isinstance(rd, dict):
            continue
        pipeline = rd.get("pipeline")
        if not isinstance(pipeline, dict) or pipeline.get("stage1", {}).get("status") != "completed":
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

    # 关联社媒切片到策略
    for s in slice_objs:
        existing = await db.get(StrategySlice, (strategy.id, s.id))
        if existing is None:
            db.add(StrategySlice(strategy_id=strategy.id, slice_id=s.id))
    await db.flush()

    # 覆盖度 LLM 验证（社媒 + 新闻切片）
    try:
        research_questions = research_design.get("research_questions") or []
        slices_data = [
            (s.name or f"切片{s.id}", s.result_data or {}) for s in slice_objs
        ]
        for ns in news_slice_objs:
            slices_data.append(
                (f"[新闻] {ns.name}", ns.result_data or {})
            )
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

        if coverage_result.get("overall_ready"):
            strategy.status = "ready"
            logger.info("Strategy %s: 覆盖度验证通过，状态推进到 ready", strategy.id)
        else:
            logger.info(
                "Strategy %s: 覆盖度验证未通过，保持 collecting，建议调整切片",
                strategy.id,
            )
    except Exception as e:
        logger.error(
            "Strategy %s: 覆盖度 LLM 验证失败: %s", strategy.id, e, exc_info=True
        )

    await db.commit()

    if strategy.status == "ready":
        fire_notification(feishu_tmpl.data_ready_card(
            strategy.name, strategy.id,
            slice_count=len(slice_objs) + len(news_slice_objs),
        ))

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


async def get_data_overview(
    db: AsyncSession,
    strategy: Strategy,
) -> "DataOverviewResponse":
    """数据全景：返回该策略已关联的切片列表 + 覆盖度验证结果。"""
    from .schemas import DataOverviewResponse

    slice_summaries = [
        SliceSummary(
            slice_id=ss.slice_id,
            slice_name=ss.slice.name if ss.slice else None,
            monitor_id=ss.slice.monitor_id if ss.slice else (strategy.social_monitor_id or 0),
            monitor_name=(
                ss.slice.monitor.name
                if (ss.slice and ss.slice.monitor)
                else ""
            ),
        )
        for ss in strategy.slices
    ]

    return DataOverviewResponse(
        slices=slice_summaries,
        coverage_check_result=strategy.coverage_check_result,
        strategy=_strategy_read(strategy),
    )


async def adjust_slices(
    db: AsyncSession,
    strategy: Strategy,
    adjustments: list[dict],
    current_user_id: int,
) -> Strategy:
    """微调切片配置（名称/主体/竞品），调整后重新触发覆盖度验证。

    每个 adjustment 格式：{slice_id, name?, subject?, competitors?}
    """
    from src.social_media.analysis.models import SocialSlice

    # 校验 slice 归属
    strategy_slice_ids = {ss.slice_id for ss in strategy.slices}

    for adj in adjustments:
        sid = adj.get("slice_id")
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

        # result_data 中存 subject / competitors（供 LLM 使用）
        if "subject" in adj or "competitors" in adj:
            result_data = dict(slice_obj.result_data or {})
            meta = dict(result_data.get("meta") or {})
            if "subject" in adj and adj["subject"] is not None:
                meta["subject"] = adj["subject"]
            if "competitors" in adj and adj["competitors"] is not None:
                meta["competitors"] = adj["competitors"]
            result_data["meta"] = meta
            slice_obj.result_data = result_data
            flag_modified(slice_obj, "result_data")

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
            logger.info(
                "Strategy %s: 调整后覆盖度通过，状态推进到 ready", strategy.id
            )
    except Exception as e:
        logger.error(
            "Strategy %s: 调整切片后覆盖度验证失败: %s", strategy.id, e, exc_info=True
        )

    await db.commit()
    return await get_strategy_by_id(db, strategy.id)
