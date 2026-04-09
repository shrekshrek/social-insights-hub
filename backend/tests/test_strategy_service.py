"""Strategy Service 单元测试 — 状态流转 + 编辑清除"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.strategies.service import (
    STATUS_ORDER,
    _create_auto_slices,
    approve_probe,
    check_collection_status,
    generate_phase2,
    generate_phase3,
)


class TestStatusOrder:
    def test_draft_is_lowest(self):
        assert STATUS_ORDER["draft"] == 0

    def test_planned_after_draft(self):
        assert STATUS_ORDER["planned"] > STATUS_ORDER["draft"]

    def test_probing_after_planned(self):
        assert STATUS_ORDER["probing"] > STATUS_ORDER["planned"]

    def test_phase1_done_before_phase2_done(self):
        assert STATUS_ORDER["phase1_done"] < STATUS_ORDER["phase2_done"]

    def test_completed_is_highest(self):
        assert STATUS_ORDER["completed"] == max(STATUS_ORDER.values())

    def test_all_8_statuses(self):
        assert len(STATUS_ORDER) == 8


class TestGeneratePhase2Precondition:
    @pytest.mark.asyncio
    async def test_rejects_draft_status(self):
        """generate_phase2 在 status=draft 时 → 409"""
        strategy = MagicMock()
        strategy.status = "draft"
        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await generate_phase2(db, strategy)
        assert exc_info.value.status_code == 409


class TestGeneratePhase3Precondition:
    @pytest.mark.asyncio
    async def test_rejects_phase1_done(self):
        """generate_phase3 在 status=phase1_done 时 → 409"""
        strategy = MagicMock()
        strategy.status = "phase1_done"
        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await generate_phase3(db, strategy)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_rejects_draft(self):
        """generate_phase3 在 status=draft 时 → 409"""
        strategy = MagicMock()
        strategy.status = "draft"
        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await generate_phase3(db, strategy)
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
    @pytest.mark.asyncio
    @patch("src.strategies.service._strategy_read", return_value={"id": 1})
    @patch("src.strategies.service._create_auto_slices", new_callable=AsyncMock)
    async def test_trigger_auto_slices_only_when_strategy_has_no_slices(
        self,
        mock_create_auto_slices,
        _mock_strategy_read,
    ):
        task = MagicMock()
        task.id = 1
        task.keywords = "kw"
        task.status = "completed"
        task.posts_count = 10
        task.analysis_result = {"ok": True}
        task.platform = MagicMock(code="wb")

        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [task]
        db.execute = AsyncMock(return_value=result)

        strategy = MagicMock()
        strategy.id = 1
        strategy.task_ids = [1]
        strategy.slices = []

        await check_collection_status(db, strategy, current_user_id=1)
        mock_create_auto_slices.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.strategies.service._strategy_read", return_value={"id": 1})
    @patch("src.strategies.service._create_auto_slices", new_callable=AsyncMock)
    async def test_skip_auto_slices_when_strategy_already_has_slices(
        self,
        mock_create_auto_slices,
        _mock_strategy_read,
    ):
        task = MagicMock()
        task.id = 1
        task.keywords = "kw"
        task.status = "completed"
        task.posts_count = 10
        task.analysis_result = {"ok": True}
        task.platform = MagicMock(code="wb")

        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [task]
        db.execute = AsyncMock(return_value=result)

        strategy = MagicMock()
        strategy.id = 1
        strategy.task_ids = [1]
        strategy.slices = [MagicMock()]

        await check_collection_status(db, strategy, current_user_id=1)
        mock_create_auto_slices.assert_not_awaited()
