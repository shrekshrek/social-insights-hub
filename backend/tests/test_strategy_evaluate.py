"""Strategy Evaluate Chain + batch_add_slices + confirm_ready 测试 — Step 4"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.langchain.chains.strategy_evaluate_chain import (
    format_evaluate_inputs,
    parse_evaluate_response,
)
from src.strategies.service import batch_add_slices, confirm_ready, evaluate_strategy

_NOW = datetime(2026, 3, 1)

# ── format_evaluate_inputs 单元测试 ──────────────────────────────────────────


class TestFormatEvaluateInputs:
    def test_no_brief_renders_placeholder(self):
        result = format_evaluate_inputs(brief=None, slice_plan=[], slices_data=[])
        assert "用户未提供 Brief" in result["brief_section"]

    def test_no_slices_renders_placeholder(self):
        result = format_evaluate_inputs(brief=None, slice_plan=[], slices_data=[])
        assert "未关联任何切片" in result["slice_summary_section"]

    def test_brief_fields_rendered(self):
        brief = {
            "brand_name": "测试品牌",
            "analysis_goal": "竞品分析",
            "competitors": ["竞品A"],
        }
        result = format_evaluate_inputs(brief=brief, slice_plan=[], slices_data=[])
        section = result["brief_section"]
        assert "测试品牌" in section
        assert "竞品分析" in section
        assert "竞品A" in section

    def test_slice_plan_rendered(self):
        plan = [{"name": "竞品切片", "purpose": "对比分析"}]
        result = format_evaluate_inputs(brief=None, slice_plan=plan, slices_data=[])
        assert "竞品切片" in result["slice_plan_section"]
        assert "对比分析" in result["slice_plan_section"]

    def test_slices_data_summary_rendered(self):
        slices = [{"meta": {"subject": "品牌A", "competitors": ["竞品B"]}}]
        result = format_evaluate_inputs(brief=None, slice_plan=[], slices_data=slices)
        assert "品牌A" in result["slice_summary_section"]
        assert "1 个切片" in result["slice_summary_section"]


# ── parse_evaluate_response 单元测试 ─────────────────────────────────────────


class TestParseEvaluateResponse:
    _valid = json.dumps({
        "overall_score": 0.75,
        "is_sufficient": True,
        "coverage_analysis": [{"dimension": "需求覆盖度", "score": 0.8, "status": "sufficient", "note": "ok"}],
        "slice_suggestions": [],
        "gap_analysis": [],
        "supplementary_tasks": None,
    })

    def test_valid_json_parsed(self):
        result = parse_evaluate_response(self._valid)
        assert result["overall_score"] == 0.75
        assert result["is_sufficient"] is True
        assert len(result["coverage_analysis"]) == 1

    def test_json_in_code_block(self):
        wrapped = f"```json\n{self._valid}\n```"
        result = parse_evaluate_response(wrapped)
        assert result["overall_score"] == 0.75

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="无法解析为 JSON"):
            parse_evaluate_response("不是 JSON")

    def test_missing_fields_get_defaults(self):
        minimal = json.dumps({"overall_score": 0.5})
        result = parse_evaluate_response(minimal)
        assert result["is_sufficient"] is False
        assert result["coverage_analysis"] == []
        assert result["gap_analysis"] == []
        assert result["supplementary_tasks"] is None


# ── evaluate_strategy service 测试 ───────────────────────────────────────────

_MOCK_EVAL_SUFFICIENT = json.dumps({
    "overall_score": 0.8,
    "is_sufficient": True,
    "coverage_analysis": [{"dimension": "需求覆盖度", "score": 0.8, "status": "sufficient", "note": "充分"}],
    "slice_suggestions": [],
    "gap_analysis": [],
    "supplementary_tasks": None,
})

_MOCK_EVAL_INSUFFICIENT = json.dumps({
    "overall_score": 0.2,
    "is_sufficient": False,
    "coverage_analysis": [],
    "slice_suggestions": [],
    "gap_analysis": [{"gap_type": "no_data", "description": "无切片数据", "priority": "high"}],
    "supplementary_tasks": [{"platform": "xiaohongshu", "keywords": ["品牌"], "reason": "补充"}],
})


def _make_strategy_with_slices(n_slices=1):
    s = MagicMock()
    s.id = 1
    s.name = "测试策略"
    s.brand_brief = {"brand_name": "品牌", "analysis_goal": "竞品"}
    s.slice_plan = []
    s.evaluation_result = None
    s.status = "monitors_created"
    s.slices = [MagicMock() for _ in range(n_slices)]
    s.creator = MagicMock()
    s.creator.username = "tester"
    s.created_by = 1
    s.created_at = _NOW
    s.updated_at = _NOW
    s.phase1_result = s.phase2_result = s.phase3_result = None
    s.consultation_rounds = []
    s.suggested_monitor_ids = []
    return s


class TestEvaluateStrategy:
    @pytest.mark.asyncio
    @patch("src.strategies.service.load_slice_data")
    @patch("src.strategies.service.create_strategy_evaluate_chain")
    async def test_happy_path_sufficient(self, mock_chain_factory, mock_load):
        """有效切片 → AI 返回 is_sufficient=True"""
        strategy = _make_strategy_with_slices(1)
        mock_load.return_value = [{"meta": {"subject": "品牌"}}]
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content=_MOCK_EVAL_SUFFICIENT)
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()
        result = await evaluate_strategy(db, strategy)

        assert result.overall_score == 0.8
        assert result.is_sufficient is True
        assert strategy.evaluation_result is not None

    @pytest.mark.asyncio
    @patch("src.strategies.service.load_slice_data")
    @patch("src.strategies.service.create_strategy_evaluate_chain")
    async def test_no_slices_returns_insufficient(self, mock_chain_factory, mock_load):
        """无关联切片 → AI 评估 is_sufficient=False, overall_score < 0.3"""
        strategy = _make_strategy_with_slices(0)
        mock_load.return_value = []  # 无切片数据
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content=_MOCK_EVAL_INSUFFICIENT)
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()
        result = await evaluate_strategy(db, strategy)

        assert result.is_sufficient is False
        assert result.overall_score < 0.3

    @pytest.mark.asyncio
    @patch("src.strategies.service.load_slice_data")
    @patch("src.strategies.service.create_strategy_evaluate_chain")
    async def test_llm_parse_failure_raises_500(self, mock_chain_factory, mock_load):
        """LLM 返回无效 JSON → HTTP 500，evaluation_result 不更新"""
        strategy = _make_strategy_with_slices(1)
        mock_load.return_value = [{}]
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content="不是 JSON")
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await evaluate_strategy(db, strategy)

        assert exc_info.value.status_code == 500
        assert strategy.evaluation_result is None  # 未更新


# ── batch_add_slices 测试 ─────────────────────────────────────────────────────


class TestBatchAddSlices:
    @pytest.mark.asyncio
    async def test_duplicate_slice_id_upsert_no_error(self):
        """重复 slice_id → upsert，不报错，不重复添加"""
        strategy = MagicMock()
        strategy.id = 1

        db = AsyncMock()

        # 模拟 slice 存在且有权限
        mock_slice = MagicMock()
        mock_slice.monitor_id = 10

        # 模拟已存在的 StrategySlice
        existing_link = MagicMock()  # 非 None → 跳过 add

        db.get.side_effect = [mock_slice, existing_link]  # slice_obj, 已存在的关联

        with patch("src.strategies.service.check_monitor_access", return_value=True):
            with patch("src.strategies.service.get_strategy_by_id", return_value=strategy):
                result = await batch_add_slices(db, strategy, [42], user_id=1)

        # add 未被调用（已存在的关联不重复）
        db.add.assert_not_called()
        assert result == strategy

    @pytest.mark.asyncio
    async def test_nonexistent_slice_raises_404(self):
        """不存在的 slice_id → 404"""
        strategy = MagicMock()
        strategy.id = 1
        db = AsyncMock()
        db.get.return_value = None  # slice 不存在

        with pytest.raises(HTTPException) as exc_info:
            await batch_add_slices(db, strategy, [999], user_id=1)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_no_access_raises_403(self):
        """无监测访问权限 → 403"""
        strategy = MagicMock()
        strategy.id = 1
        db = AsyncMock()

        mock_slice = MagicMock()
        mock_slice.monitor_id = 10
        db.get.return_value = mock_slice

        with patch("src.strategies.service.check_monitor_access", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await batch_add_slices(db, strategy, [42], user_id=1)

        assert exc_info.value.status_code == 403


# ── confirm_ready 测试 ────────────────────────────────────────────────────────


class TestConfirmReady:
    @pytest.mark.asyncio
    async def test_advances_to_slices_ready(self):
        """任意非 completed 状态 → 推进到 slices_ready"""
        strategy = MagicMock()
        strategy.id = 1
        strategy.status = "monitors_created"

        db = AsyncMock()
        with patch("src.strategies.service.get_strategy_by_id", return_value=strategy):
            await confirm_ready(db, strategy)

        assert strategy.status == "slices_ready"

    @pytest.mark.asyncio
    async def test_briefing_status_advances(self):
        """briefing 状态也可以跳转（跳过引导流程的快速路径）"""
        strategy = MagicMock()
        strategy.id = 1
        strategy.status = "briefing"

        db = AsyncMock()
        with patch("src.strategies.service.get_strategy_by_id", return_value=strategy):
            await confirm_ready(db, strategy)

        assert strategy.status == "slices_ready"

    @pytest.mark.asyncio
    async def test_completed_status_raises_400(self):
        """completed 状态 → 400"""
        strategy = MagicMock()
        strategy.id = 1
        strategy.status = "completed"

        db = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await confirm_ready(db, strategy)

        assert exc_info.value.status_code == 400
