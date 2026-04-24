"""Strategy Service 单元测试 — 状态流转 + 编辑清除"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.strategies.service import (
    STATUS_ORDER,
    _create_auto_slices,
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

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _create_auto_slices(
                db=AsyncMock(),
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

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await _create_auto_slices(
                db=AsyncMock(),
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
