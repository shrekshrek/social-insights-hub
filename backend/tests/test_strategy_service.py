"""Strategy Service 单元测试 — 状态流转 + 编辑清除"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.strategies.service import (
    STATUS_ORDER,
    _build_social_probe_summaries,
    _check_missing_competitive_social_dimension,
    _compute_research_design_advisories,
    _create_auto_slices,
    _dispatch_strategy_research_tasks,
    _social_slice_stage2_terminal,
    _try_advance_to_ready,
    approve_probe,
    check_collection_status,
    generate_brand_role,
    generate_big_idea,
)


class TestStatusOrder:
    def test_draft_is_lowest(self):
        assert STATUS_ORDER["draft"] == 0

    def test_planned_after_draft(self):
        assert STATUS_ORDER["planned"] > STATUS_ORDER["draft"]

    def test_probing_after_planned(self):
        assert STATUS_ORDER["probing"] > STATUS_ORDER["planned"]

    def test_insight_done_before_brand_role_done(self):
        assert STATUS_ORDER["insight_done"] < STATUS_ORDER["brand_role_done"]

    def test_completed_is_highest(self):
        assert STATUS_ORDER["completed"] == max(STATUS_ORDER.values())

    def test_all_statuses_present(self):
        # 10 个状态：brand_strategy 路径 8 个 + market_report 路径新增 2 个
        # (agenda_map_done 与 insight_done 共享 order，landscape_done 与 brand_role_done 共享 order)
        expected = {
            "draft", "planned", "probing", "collecting", "ready",
            "insight_done", "brand_role_done",
            "agenda_map_done", "landscape_done",
            "completed",
        }
        assert set(STATUS_ORDER.keys()) == expected

    def test_market_report_path_shares_order_with_brand_strategy(self):
        """两条路径在同层级共享 order 值，使 `>= ready` 等通用比较仍然有效"""
        assert STATUS_ORDER["agenda_map_done"] == STATUS_ORDER["insight_done"]
        assert STATUS_ORDER["landscape_done"] == STATUS_ORDER["brand_role_done"]


class TestGenerateBrandRolePrecondition:
    @pytest.mark.asyncio
    async def test_rejects_draft_status(self):
        """generate_brand_role 在 status=draft 时 → 409"""
        strategy = MagicMock()
        strategy.status = "draft"
        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await generate_brand_role(db, strategy)
        assert exc_info.value.status_code == 409


class TestGenerateBigIdeaPrecondition:
    @pytest.mark.asyncio
    async def test_rejects_insight_done(self):
        """generate_big_idea 在 status=insight_done 时 → 409（需要 brand_role_done 以上）"""
        strategy = MagicMock()
        strategy.status = "insight_done"
        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await generate_big_idea(db, strategy)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_rejects_draft(self):
        """generate_big_idea 在 status=draft 时 → 409"""
        strategy = MagicMock()
        strategy.status = "draft"
        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await generate_big_idea(db, strategy)
        assert exc_info.value.status_code == 409


class TestStrategyDataFlowGuards:
    @pytest.mark.asyncio
    async def test_approve_probe_requires_task_dimension_map(self):
        """approve_probe 在缺少 _task_dimension_map 时必须失败（不再兜底）"""
        strategy = MagicMock()
        strategy.id = 1
        strategy.task_ids = [11]
        strategy.monitor_id = 100
        strategy.research_design = {}

        probe_task = MagicMock()
        probe_task.id = 11

        db = AsyncMock()
        first_result = MagicMock()
        first_result.scalar_one_or_none.return_value = strategy
        second_result = MagicMock()
        second_result.scalars.return_value.all.return_value = [probe_task]
        db.execute = AsyncMock(side_effect=[first_result, second_result])

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await approve_probe(db, strategy, current_user_id=1)

        assert exc_info.value.status_code == 409
        assert "缺少任务维度映射" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_auto_slices_requires_collect_dimension_map(self):
        """_create_auto_slices 缺少 collect 映射时必须失败（不再关键词兜底）"""
        strategy = MagicMock()
        strategy.research_design = {
            "slice_blueprint": [
                {
                    "name": "品牌切片",
                    "source_dimensions": ["品牌声量"],
                }
            ]
        }
        strategy.monitor_id = 100
        strategy.brand_brief = {}

        collect_task = MagicMock()
        collect_task.id = 101

        # 去重查询（幂等优化）在配置校验之前先跑，需 mock db.execute 返回空，
        # 否则裸 AsyncMock 的 rows.all() 返回协程会在到达 409 前先报错
        empty_result = MagicMock()
        empty_result.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=empty_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _create_auto_slices(
                db=db,
                strategy=strategy,
                collect_tasks=[collect_task],
                current_user_id=1,
            )

        assert exc_info.value.status_code == 409
        assert "缺少 collect 任务维度映射" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_auto_slices_requires_blueprint_dimension_match(self):
        """切片 source_dimensions 未命中任务维度时必须失败（不再全量塞入）"""
        strategy = MagicMock()
        strategy.research_design = {
            "slice_blueprint": [
                {
                    "name": "竞品切片",
                    "source_dimensions": ["竞品声量"],
                }
            ],
            "_task_dimension_map": {"101": "品牌声量"},
        }
        strategy.monitor_id = 100
        strategy.brand_brief = {}

        collect_task = MagicMock()
        collect_task.id = 101

        # 去重查询（幂等优化）在配置校验之前先跑，需 mock db.execute 返回空，
        # 否则裸 AsyncMock 的 rows.all() 返回协程会在到达 409 前先报错
        empty_result = MagicMock()
        empty_result.all.return_value = []
        db = AsyncMock()
        db.execute = AsyncMock(return_value=empty_result)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _create_auto_slices(
                db=db,
                strategy=strategy,
                collect_tasks=[collect_task],
                current_user_id=1,
            )

        assert exc_info.value.status_code == 409
        assert "未匹配到任何任务" in exc_info.value.detail


class TestCheckCollectionStatusSliceTrigger:
    """验证 get_collection_status 的两阶段推进：

    - 阶段 A：任务全分析完成 + 切片未建 → 调 _create_auto_slices
    - 阶段 B：切片已建 + coverage 未跑 → 调 _try_advance_to_ready（新语义）
    """

    @staticmethod
    def _make_task():
        task = MagicMock()
        task.id = 1
        task.keywords = "kw"
        task.status = "completed"
        task.posts_count = 10
        task.analysis_result = {"ok": True}
        task.platform = MagicMock(code="wb")
        return task

    @staticmethod
    def _make_strategy():
        strategy = MagicMock()
        strategy.id = 1
        strategy.user_id = 1
        strategy.social_monitor_id = 1
        strategy.news_monitor_id = 1
        strategy.coverage_check_result = None
        return strategy

    @pytest.mark.asyncio
    @patch("src.strategies.service._get_research_agent_status", new_callable=AsyncMock)
    @patch("src.news_media.tasks.service.get_news_tasks_by_strategy", new_callable=AsyncMock)
    @patch("src.strategies.service._strategy_read", new_callable=AsyncMock)
    @patch("src.strategies.service._create_auto_slices", new_callable=AsyncMock)
    async def test_trigger_auto_slices_only_when_strategy_has_no_slices(
        self,
        mock_create_auto_slices,
        mock_strategy_read,
        mock_get_news,
        mock_research_status,
    ):
        mock_get_news.return_value = []
        from src.strategies.schemas import ResearchAgentStatus
        mock_research_status.return_value = ResearchAgentStatus()
        mock_strategy_read.return_value = None

        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = [self._make_task()]
        # 切片未建：两次 scalar_one_or_none 返回 None
        empty_slice = MagicMock()
        empty_slice.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[tasks_result, empty_slice, empty_slice])

        strategy = self._make_strategy()

        await check_collection_status(db, strategy, current_user_id=1)
        mock_create_auto_slices.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.strategies.service._try_advance_to_ready", new_callable=AsyncMock)
    @patch("src.strategies.service._get_research_agent_status", new_callable=AsyncMock)
    @patch("src.news_media.tasks.service.get_news_tasks_by_strategy", new_callable=AsyncMock)
    @patch("src.strategies.service._strategy_read", new_callable=AsyncMock)
    @patch("src.strategies.service._create_auto_slices", new_callable=AsyncMock)
    async def test_skip_auto_slices_when_strategy_already_has_slices(
        self,
        mock_create_auto_slices,
        mock_strategy_read,
        mock_get_news,
        mock_research_status,
        mock_try_advance,
    ):
        mock_get_news.return_value = []
        from src.strategies.schemas import ResearchAgentStatus
        mock_research_status.return_value = ResearchAgentStatus()
        mock_strategy_read.return_value = None
        mock_try_advance.return_value = False

        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = [self._make_task()]
        # 切片已建：两次 scalar_one_or_none 返回非 None
        has_slice = MagicMock()
        has_slice.scalar_one_or_none.return_value = 123

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[tasks_result, has_slice, has_slice])

        strategy = self._make_strategy()

        await check_collection_status(db, strategy, current_user_id=1)
        mock_create_auto_slices.assert_not_awaited()
        # 切片已建且 coverage 未跑 → 尝试推进 ready
        mock_try_advance.assert_awaited_once()


class TestSocialSliceStage2Terminal:
    """_social_slice_stage2_terminal: 判断切片 Stage2 是否到终态"""

    def _make_slice(self, stage2_status):
        slc = MagicMock()
        slc.result_data = {"pipeline": {"stage2": {"status": stage2_status}}}
        return slc

    def test_completed_is_terminal(self):
        assert _social_slice_stage2_terminal(self._make_slice("completed")) is True

    def test_failed_is_terminal(self):
        assert _social_slice_stage2_terminal(self._make_slice("failed")) is True

    def test_skipped_is_terminal(self):
        assert _social_slice_stage2_terminal(self._make_slice("skipped")) is True

    def test_processing_not_terminal(self):
        assert _social_slice_stage2_terminal(self._make_slice("processing")) is False

    def test_pending_not_terminal(self):
        assert _social_slice_stage2_terminal(self._make_slice("pending")) is False

    def test_missing_pipeline_not_terminal(self):
        slc = MagicMock()
        slc.result_data = {}
        assert _social_slice_stage2_terminal(slc) is False

    def test_none_result_data_not_terminal(self):
        slc = MagicMock()
        slc.result_data = None
        assert _social_slice_stage2_terminal(slc) is False


class TestDispatchStrategyResearchTasks:
    """_dispatch_strategy_research_tasks: 探测通过、进入 collecting 时启动专题研究

    研究任务的启动时机从 confirm_research（探测开始）迁移到 approve_probe（探测通过、
    进入全量采集），避免方向被否决时浪费 Tavily 调用。本组测试聚焦在新 helper 自身：
    创建条件、output_type 互斥、失败容忍。幂等性由 approve_probe 入口的
    status>=collecting 早返回守卫保证，不在此处重复测试。
    """

    @staticmethod
    def _make_strategy(
        *,
        output_type: str = "campaign_strategy",
        channel_plan: list | None = None,
        subject: str = "测试品牌",
        analysis_goal: str = "目标分析",
    ):
        strategy = MagicMock()
        strategy.id = 42
        strategy.output_type = output_type
        strategy.brand_brief = {
            "subject": subject,
            "analysis_goal": analysis_goal,
            "channel_plan": channel_plan or [],
        }
        return strategy

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_creates_industry_when_channel_brief_present(self, mock_create):
        strategy = self._make_strategy(
            channel_plan=[
                {"type": "industry_research", "channel_brief": "聚焦行业趋势"},
            ],
        )
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        mock_create.assert_awaited_once()
        kwargs = mock_create.await_args.kwargs
        assert kwargs["profile_name"] == "industry"
        assert kwargs["analysis_goal"] == "聚焦行业趋势"
        assert kwargs["title"] == "测试品牌"
        assert kwargs["search_config"] == {"context": "目标分析"}
        assert kwargs["strategy_id"] == 42
        assert kwargs["user_id"] == 7

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_skips_industry_when_channel_brief_absent(self, mock_create):
        strategy = self._make_strategy(channel_plan=[])
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_creates_creative_for_campaign_strategy(self, mock_create):
        strategy = self._make_strategy(
            output_type="campaign_strategy",
            channel_plan=[
                {"type": "creative_research", "channel_brief": "竞品 Campaign 案例"},
            ],
        )
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        mock_create.assert_awaited_once()
        kwargs = mock_create.await_args.kwargs
        assert kwargs["profile_name"] == "creative"
        assert kwargs["title"] == "测试品牌 竞品创意研究"

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_creates_creative_for_full_strategy(self, mock_create):
        strategy = self._make_strategy(
            output_type="full_strategy",
            channel_plan=[
                {"type": "creative_research", "channel_brief": "竞品 Campaign 案例"},
            ],
        )
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        mock_create.assert_awaited_once()
        kwargs = mock_create.await_args.kwargs
        assert kwargs["profile_name"] == "creative"

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_skips_creative_for_market_report(self, mock_create):
        """market_report 路径产出不消费 creative_references，即便 channel_brief 存在也不该启动"""
        strategy = self._make_strategy(
            output_type="market_report",
            channel_plan=[
                {"type": "creative_research", "channel_brief": "竞品 Campaign 案例"},
            ],
        )
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_skips_creative_when_channel_brief_absent(self, mock_create):
        strategy = self._make_strategy(
            output_type="campaign_strategy",
            channel_plan=[],
        )
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        mock_create.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_creates_both_when_both_channels_present(self, mock_create):
        strategy = self._make_strategy(
            output_type="full_strategy",
            channel_plan=[
                {"type": "industry_research", "channel_brief": "行业趋势"},
                {"type": "creative_research", "channel_brief": "创意素材"},
            ],
        )
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        assert mock_create.await_count == 2
        profiles = {call.kwargs["profile_name"] for call in mock_create.await_args_list}
        assert profiles == {"industry", "creative"}

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_failure_does_not_raise(self, mock_create):
        """create_research_task 失败时仅日志告警，不阻塞主流程（产出阶段优雅降级为空）"""
        mock_create.side_effect = RuntimeError("Tavily API 超时")
        strategy = self._make_strategy(
            channel_plan=[
                {"type": "industry_research", "channel_brief": "行业趋势"},
            ],
        )
        db = AsyncMock()

        # 不抛异常即通过
        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.research_agent.service.create_research_task", new_callable=AsyncMock)
    async def test_industry_failure_does_not_block_creative(self, mock_create):
        """行业研究创建失败时，创意研究仍应尝试启动（两者互不依赖）"""
        # 第一次（industry）失败，第二次（creative）成功
        mock_create.side_effect = [RuntimeError("行业研究失败"), None]
        strategy = self._make_strategy(
            output_type="campaign_strategy",
            channel_plan=[
                {"type": "industry_research", "channel_brief": "行业趋势"},
                {"type": "creative_research", "channel_brief": "创意素材"},
            ],
        )
        db = AsyncMock()

        await _dispatch_strategy_research_tasks(db, strategy, user_id=7)

        assert mock_create.await_count == 2


class TestBuildSocialProbeSummariesFailedSemantics:
    """_build_social_probe_summaries: 方案 B "失败必须解决" 的核心保证

    failed 任务永远不算 has_analysis（无论 analysis_result / posts_count 状态），
    用来阻塞 all_analyzed → 阻塞 probe review 触发，强制等待 retry 或人工删除。
    """

    @staticmethod
    def _make_task(
        *,
        task_id: int = 1,
        status: str = "completed",
        posts_count: int = 20,
        analysis_result: dict | None = None,
        platform_code: str = "wb",
    ):
        from datetime import datetime, timezone

        task = MagicMock()
        task.id = task_id
        task.keywords = "测试关键词"
        task.status = status
        task.posts_count = posts_count
        task.analysis_result = analysis_result
        task.platform = MagicMock(code=platform_code)
        task.updated_at = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)
        return task

    @staticmethod
    def _mock_db_with_tasks(tasks):
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = tasks
        db.execute.return_value = result
        return db

    @pytest.mark.asyncio
    async def test_failed_with_no_data_is_not_analyzed(self):
        """failed + 0 帖：旧 _PROBE_TERMINAL_STATUSES 含 failed 时会判 has_analysis=true，
        方案 B 下必须为 false 才能阻塞 all_analyzed"""
        db = self._mock_db_with_tasks([
            self._make_task(status="failed", posts_count=0),
        ])

        statuses, summaries = await _build_social_probe_summaries(db, [1])

        assert len(statuses) == 1
        assert statuses[0].has_analysis is False
        assert statuses[0].status == "failed"
        assert summaries == []

    @pytest.mark.asyncio
    async def test_failed_with_partial_analysis_is_not_analyzed(self):
        """failed + 已有 analysis_result（崩溃前部分写入）：仍不算 has_analysis，
        防止时序漏洞——失败任务即便有部分数据也不该被审查 """
        db = self._mock_db_with_tasks([
            self._make_task(
                status="failed",
                posts_count=10,
                analysis_result={"insights": {"top_topics": []}, "metrics": {}, "meta": {}},
            ),
        ])

        statuses, summaries = await _build_social_probe_summaries(db, [1])

        assert statuses[0].has_analysis is False
        assert summaries == [], "failed 任务的 partial analysis 不该进入审查 summaries"

    @pytest.mark.asyncio
    async def test_completed_with_data_is_analyzed(self):
        """成功路径回归：completed + analysis_result 正常算 has_analysis"""
        db = self._mock_db_with_tasks([
            self._make_task(
                status="completed",
                posts_count=20,
                analysis_result={
                    "insights": {"top_topics": [], "target_entities": [], "competitor_entities": []},
                    "metrics": {"marketing_analysis": {}},
                    "meta": {"data_volume": {}},
                },
            ),
        ])

        statuses, summaries = await _build_social_probe_summaries(db, [1])

        assert statuses[0].has_analysis is True
        assert len(summaries) == 1

    @pytest.mark.asyncio
    async def test_completed_with_no_data_is_analyzed_via_no_data_fallback(self):
        """completed + 0 帖：兜底视为已处理（规则层会自动 fail 给"建议移除"）"""
        db = self._mock_db_with_tasks([
            self._make_task(status="completed", posts_count=0),
        ])

        statuses, _ = await _build_social_probe_summaries(db, [1])

        assert statuses[0].has_analysis is True

    @pytest.mark.asyncio
    async def test_running_is_not_analyzed(self):
        """running 不算终态，has_analysis=false（既有行为，做回归保险）"""
        db = self._mock_db_with_tasks([
            self._make_task(status="running", posts_count=0),
        ])

        statuses, _ = await _build_social_probe_summaries(db, [1])

        assert statuses[0].has_analysis is False

    @pytest.mark.asyncio
    async def test_last_updated_at_exposed(self):
        """SocialProbeTaskStatus.last_updated_at 字段透传给前端用于'失败于 X 分钟前'"""
        from datetime import datetime, timezone

        db = self._mock_db_with_tasks([
            self._make_task(status="failed", posts_count=0),
        ])

        statuses, _ = await _build_social_probe_summaries(db, [1])

        assert statuses[0].last_updated_at == datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


class TestTryAdvanceToReady:
    """_try_advance_to_ready: Stage2 全完后跑 coverage_check 并置 ready"""

    def _make_strategy(self, status="collecting", coverage=None):
        strategy = MagicMock()
        strategy.id = 1
        strategy.status = status
        strategy.coverage_check_result = coverage
        strategy.social_monitor_id = 1
        strategy.news_monitor_id = None  # 简化：不涉及新闻
        strategy.brand_brief = {}
        strategy.research_design = {"research_questions": []}
        strategy.name = "test"
        return strategy

    def _make_social_slice(self, status="completed", stage2_status="completed", rd=None):
        slc = MagicMock()
        slc.id = 10
        slc.name = "slice"
        slc.status = status
        slc.result_data = rd or {
            "meta": {"subject": "x"},
            "foundation": {"aligned_entities": [{"text": "a"}]},
            "layers": {"landscape": {}},
            "pipeline": {"stage2": {"status": stage2_status}},
        }
        return slc

    @pytest.mark.asyncio
    async def test_noop_when_not_collecting(self):
        strategy = self._make_strategy(status="probing")
        db = AsyncMock()
        result = await _try_advance_to_ready(db, strategy)
        assert result is False
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_noop_when_coverage_already_ran(self):
        strategy = self._make_strategy(coverage={"overall_ready": False})
        db = AsyncMock()
        result = await _try_advance_to_ready(db, strategy)
        assert result is False
        db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_noop_when_stage2_not_terminal(self):
        strategy = self._make_strategy()
        slice_obj = self._make_social_slice(stage2_status="processing")

        slices_res = MagicMock()
        slices_res.scalars.return_value.all.return_value = [slice_obj]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=slices_res)

        result = await _try_advance_to_ready(db, strategy)
        assert result is False
        # Stage2 未完成不应置 ready
        assert strategy.status == "collecting"

    @pytest.mark.asyncio
    @patch("src.strategies.service.fire_notification")
    @patch("src.strategies.service.parse_coverage_check_response")
    @patch("src.strategies.service.format_coverage_check_inputs")
    @patch("src.strategies.service.create_coverage_check_chain")
    async def test_advances_to_ready_when_stage2_complete_and_coverage_passes(
        self,
        mock_chain_factory,
        mock_format,
        mock_parse,
        mock_notify,
    ):
        strategy = self._make_strategy()
        slice_obj = self._make_social_slice()

        slices_res = MagicMock()
        slices_res.scalars.return_value.all.return_value = [slice_obj]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=slices_res)

        mock_chain = AsyncMock()
        raw_response = MagicMock()
        raw_response.content = "{}"
        mock_chain.ainvoke.return_value = raw_response
        mock_chain_factory.return_value = mock_chain
        mock_parse.return_value = {"overall_ready": True}

        result = await _try_advance_to_ready(db, strategy)

        assert result is True
        assert strategy.status == "ready"
        assert strategy.coverage_check_result == {"overall_ready": True}

    @pytest.mark.asyncio
    @patch("src.strategies.service.fire_notification")
    @patch("src.strategies.service.parse_coverage_check_response")
    @patch("src.strategies.service.format_coverage_check_inputs")
    @patch("src.strategies.service.create_coverage_check_chain")
    async def test_keeps_collecting_when_coverage_not_ready(
        self,
        mock_chain_factory,
        mock_format,
        mock_parse,
        mock_notify,
    ):
        strategy = self._make_strategy()
        slice_obj = self._make_social_slice()

        slices_res = MagicMock()
        slices_res.scalars.return_value.all.return_value = [slice_obj]

        db = AsyncMock()
        db.execute = AsyncMock(return_value=slices_res)

        mock_chain = AsyncMock()
        raw_response = MagicMock()
        raw_response.content = "{}"
        mock_chain.ainvoke.return_value = raw_response
        mock_chain_factory.return_value = mock_chain
        mock_parse.return_value = {"overall_ready": False, "reason": "..."}

        result = await _try_advance_to_ready(db, strategy)

        assert result is False
        assert strategy.status == "collecting"
        # coverage 已跑过结果写入，下次轮询会跳过
        assert strategy.coverage_check_result == {"overall_ready": False, "reason": "..."}
        mock_notify.assert_not_called()


class TestResearchDesignAdvisories:
    """research design advisory 软提示规则单元测试"""

    @staticmethod
    def _design(
        *,
        has_social: bool = True,
        has_competitive: bool = False,
        has_news: bool = False,
    ) -> dict:
        """构造最小可用的 research_design dict"""
        rqs: list[dict] = []
        data_plan: list[dict] = []

        if has_social:
            rqs.append({"id": "rq1", "dimension": "consumer_voice"})
            data_plan.append({
                "channel": "social_media",
                "dimension_name": "主品 UGC",
                "question_ids": ["rq1"],
            })
        if has_competitive:
            rqs.append({"id": "rq_comp", "dimension": "competitive"})
            data_plan.append({
                "channel": "social_media",
                "dimension_name": "竞品 UGC",
                "question_ids": ["rq_comp"],
            })
        if has_news:
            rqs.append({"id": "rq_news", "dimension": "media_narrative"})
            data_plan.append({
                "channel": "news_media",
                "dimension_name": "竞品新闻",
                "question_ids": ["rq_news"],
            })

        return {"research_questions": rqs, "data_plan": data_plan}

    @staticmethod
    def _brief_with_competitor_signal(*, location: str = "constraints") -> dict:
        """构造含「竞品」信号的 brand_brief"""
        base = {
            "subject": "美赞臣 Enfinitas",
            "analysis_goal": "提升配方优越性的品牌形象",
            "constraints": "",
            "channel_plan": [
                {"type": "social_media", "solvable": ["消费者对 MFGM 的认知"]}
            ],
        }
        signal = "竞品：高端婴幼儿配方奶粉品牌"
        if location == "constraints":
            base["constraints"] = signal
        elif location == "analysis_goal":
            base["analysis_goal"] = base["analysis_goal"] + "；并对比竞品配方"
        elif location == "social_solvable":
            base["channel_plan"] = [
                {
                    "type": "social_media",
                    "solvable": ["消费者对 Enfinitas 及竞品高端奶粉的价值评价与对比"],
                }
            ]
        return base

    def test_triggers_when_brief_mentions_competitor_and_no_competitive_dim(self):
        design = self._design(has_social=True, has_competitive=False, has_news=True)
        brief = self._brief_with_competitor_signal(location="constraints")

        result = _check_missing_competitive_social_dimension(design, brief)

        assert result is not None
        assert result["code"] == "missing_competitive_social_dimension"
        assert result["severity"] == "warning"
        assert "竞品" in result["message"]

    def test_triggers_on_signal_in_social_solvable(self):
        """信号词出现在 channel_plan[social_media].solvable 也应触发"""
        design = self._design(has_social=True, has_competitive=False)
        brief = self._brief_with_competitor_signal(location="social_solvable")

        result = _check_missing_competitive_social_dimension(design, brief)

        assert result is not None

    def test_no_advisory_when_competitive_dim_already_present(self):
        design = self._design(has_social=True, has_competitive=True)
        brief = self._brief_with_competitor_signal(location="constraints")

        result = _check_missing_competitive_social_dimension(design, brief)

        assert result is None

    def test_no_advisory_when_brief_lacks_competitor_signal(self):
        design = self._design(has_social=True, has_competitive=False)
        brief = {
            "subject": "某品牌",
            "analysis_goal": "了解消费者对某品牌的认知",
            "constraints": "时间：Y26",
            "channel_plan": [
                {"type": "social_media", "solvable": ["消费者认知"]}
            ],
        }

        result = _check_missing_competitive_social_dimension(design, brief)

        assert result is None

    def test_no_advisory_when_no_social_media_dimension(self):
        """纯新闻 brief 不适用此规则"""
        design = self._design(has_social=False, has_competitive=False, has_news=True)
        brief = self._brief_with_competitor_signal(location="constraints")

        result = _check_missing_competitive_social_dimension(design, brief)

        assert result is None

    def test_compute_advisories_aggregates_results(self):
        """顶层入口在命中时返回非空 list，未命中时返回空 list"""
        triggering = self._compute_for(has_competitive=False, signal=True)
        non_triggering = self._compute_for(has_competitive=True, signal=True)

        assert len(triggering) == 1
        assert triggering[0]["code"] == "missing_competitive_social_dimension"
        assert non_triggering == []

    def _compute_for(self, *, has_competitive: bool, signal: bool) -> list[dict]:
        design = self._design(has_social=True, has_competitive=has_competitive)
        brief = (
            self._brief_with_competitor_signal(location="constraints")
            if signal
            else {
                "subject": "某品牌",
                "analysis_goal": "认知研究",
                "constraints": "",
                "channel_plan": [],
            }
        )
        return _compute_research_design_advisories(design, brief)
