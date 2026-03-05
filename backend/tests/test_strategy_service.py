"""Strategy Service 单元测试 — 状态流转 + 编辑清除"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.strategies.service import (
    STATUS_ORDER,
    edit_phase_result,
    generate_phase2,
    generate_phase3,
)


class TestStatusOrder:
    def test_draft_is_lowest(self):
        assert STATUS_ORDER["draft"] == 0

    def test_phase1_done_before_phase2_done(self):
        assert STATUS_ORDER["phase1_done"] < STATUS_ORDER["phase2_done"]

    def test_completed_is_highest(self):
        assert STATUS_ORDER["completed"] == 3


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


class TestEditPhaseResult:
    @pytest.mark.asyncio
    @patch("src.strategies.service.get_strategy_by_id")
    async def test_edit_phase1_clears_downstream(self, mock_get):
        """编辑 phase1 清除 phase2/3 结果"""
        strategy = MagicMock()
        strategy.id = 1
        db = AsyncMock()
        mock_get.return_value = strategy

        result = {"social_tensions": [{"statement": "test"}]}
        await edit_phase_result(db, strategy, phase=1, result=result)

        assert strategy.phase1_result == result
        assert strategy.phase2_result is None
        assert strategy.phase3_result is None
        assert strategy.status == "phase1_done"

    @pytest.mark.asyncio
    @patch("src.strategies.service.get_strategy_by_id")
    async def test_edit_phase2_clears_phase3(self, mock_get):
        """编辑 phase2 清除 phase3 结果"""
        strategy = MagicMock()
        strategy.id = 1
        db = AsyncMock()
        mock_get.return_value = strategy

        result = {"brand_social_role": {"statement": "test"}}
        await edit_phase_result(db, strategy, phase=2, result=result)

        assert strategy.phase2_result == result
        assert strategy.phase3_result is None
        assert strategy.status == "phase2_done"

    @pytest.mark.asyncio
    @patch("src.strategies.service.get_strategy_by_id")
    async def test_edit_phase3_keeps_status(self, mock_get):
        """编辑 phase3 保持 completed"""
        strategy = MagicMock()
        strategy.id = 1
        db = AsyncMock()
        mock_get.return_value = strategy

        result = {"big_idea": {"statement": "test"}}
        await edit_phase_result(db, strategy, phase=3, result=result)

        assert strategy.phase3_result == result
        # status 不变（保持原有值）

    @pytest.mark.asyncio
    async def test_invalid_phase(self):
        """无效 phase → 400"""
        strategy = MagicMock()
        db = AsyncMock()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await edit_phase_result(db, strategy, phase=4, result={})
        assert exc_info.value.status_code == 400
