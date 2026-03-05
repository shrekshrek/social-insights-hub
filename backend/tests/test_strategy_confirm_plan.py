"""Strategy confirm-plan service 测试 — Step 3"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.strategies.service import confirm_plan

_NOW = datetime(2026, 3, 1, 0, 0, 0)


def _make_strategy(suggested_ids=None):
    s = MagicMock()
    s.id = 1
    s.name = "测试策略"
    s.suggested_monitor_ids = suggested_ids or []
    s.status = "consulting"
    s.slices = []
    s.creator = MagicMock()
    s.creator.username = "tester"
    s.brand_brief = None
    s.consultation_rounds = []
    s.slice_plan = []
    s.evaluation_result = None
    s.phase1_result = None
    s.phase2_result = None
    s.phase3_result = None
    s.created_by = 1
    s.created_at = _NOW
    s.updated_at = _NOW
    return s


_TWO_SUGGESTIONS = [
    {"name": "竞品声量监测", "rationale": "了解竞品曝光", "platforms": ["xiaohongshu"], "keywords": ["竞品A"]},
    {"name": "品牌口碑监测", "rationale": "监测品牌口碑", "platforms": ["weibo"], "keywords": ["品牌"]},
]


class TestConfirmPlan:
    @pytest.mark.asyncio
    @patch("src.strategies.service.get_strategy_by_id")
    @patch("src.social_media.monitors.service.create_monitor")
    async def test_two_suggestions_create_two_monitors(
        self, mock_create, mock_get_by_id
    ):
        """2 条 suggestion → 创建 2 个 Monitor，suggested_monitor_ids=[id1, id2]"""
        strategy = _make_strategy()
        db = AsyncMock()

        # mock create_monitor 依次返回 id=10, id=11
        m1 = MagicMock()
        m1.id = 10
        m2 = MagicMock()
        m2.id = 11
        mock_create.side_effect = [
            {"monitor": m1, "created_tasks": []},
            {"monitor": m2, "created_tasks": []},
        ]
        mock_get_by_id.return_value = strategy

        result = await confirm_plan(db, strategy, _TWO_SUGGESTIONS, current_user_id=1)

        assert result.created_monitor_ids == [10, 11]
        assert result.partial_errors == []
        assert 10 in strategy.suggested_monitor_ids
        assert 11 in strategy.suggested_monitor_ids
        assert strategy.status == "monitors_created"

    @pytest.mark.asyncio
    @patch("src.strategies.service.get_strategy_by_id")
    @patch("src.social_media.monitors.service.create_monitor")
    async def test_partial_failure_keeps_successful_ones(
        self, mock_create, mock_get_by_id
    ):
        """第 1 条成功，第 2 条 409 → created_ids=[10], partial_errors 包含失败信息"""
        strategy = _make_strategy()
        db = AsyncMock()

        m1 = MagicMock()
        m1.id = 10
        mock_create.side_effect = [
            {"monitor": m1, "created_tasks": []},
            HTTPException(status_code=409, detail="Monitor with name '品牌口碑监测' already exists"),
        ]
        mock_get_by_id.return_value = strategy

        result = await confirm_plan(db, strategy, _TWO_SUGGESTIONS, current_user_id=1)

        assert result.created_monitor_ids == [10]
        assert len(result.partial_errors) == 1
        assert "品牌口碑监测" in result.partial_errors[0]
        assert strategy.suggested_monitor_ids == [10]

    @pytest.mark.asyncio
    @patch("src.strategies.service.get_strategy_by_id")
    @patch("src.social_media.monitors.service.create_monitor")
    async def test_repeat_call_appends_suggested_ids(
        self, mock_create, mock_get_by_id
    ):
        """重复调用 confirm-plan → suggested_monitor_ids 追加（不覆盖）"""
        strategy = _make_strategy(suggested_ids=[10])  # 已有一个
        db = AsyncMock()

        m_new = MagicMock()
        m_new.id = 20
        mock_create.return_value = {"monitor": m_new, "created_tasks": []}
        mock_get_by_id.return_value = strategy

        result = await confirm_plan(
            db, strategy, [{"name": "新监测", "rationale": "新理由"}], current_user_id=1
        )

        assert result.created_monitor_ids == [20]
        assert 10 in strategy.suggested_monitor_ids  # 旧的保留
        assert 20 in strategy.suggested_monitor_ids  # 新的追加

    @pytest.mark.asyncio
    @patch("src.strategies.service.get_strategy_by_id")
    @patch("src.social_media.monitors.service.create_monitor")
    async def test_empty_name_suggestion_skipped(
        self, mock_create, mock_get_by_id
    ):
        """空 name 的 suggestion → 跳过，记录到 partial_errors，不调 create_monitor"""
        strategy = _make_strategy()
        db = AsyncMock()
        mock_get_by_id.return_value = strategy

        result = await confirm_plan(
            db, strategy, [{"name": "", "rationale": "理由"}], current_user_id=1
        )

        mock_create.assert_not_called()
        assert result.created_monitor_ids == []
        assert len(result.partial_errors) == 1
