"""Strategy Consult Chain + Service — Step 2 测试（mock LLM）"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.langchain.chains.strategy_consult_chain import (
    format_consult_inputs,
    parse_consult_response,
)
from src.strategies.service import consult_strategy


# ── format_consult_inputs 单元测试 ────────────────────────────────────────────


class TestFormatConsultInputs:
    def test_no_brief_renders_placeholder(self):
        result = format_consult_inputs("我要分析竞品", brief=None, consultation_rounds=[])
        assert "用户未提供 Brief" in result["brief_section"]
        assert result["user_input"] == "我要分析竞品"
        assert result["history_section"] == ""

    def test_brief_renders_key_fields(self):
        brief = {
            "brand_name": "测试品牌",
            "analysis_goal": "提升声量",
            "industry": "消费电子",
            "competitors": ["A品牌", "B品牌"],
        }
        result = format_consult_inputs("开始", brief=brief, consultation_rounds=[])
        section = result["brief_section"]
        assert "测试品牌" in section
        assert "提升声量" in section
        assert "消费电子" in section
        assert "A品牌" in section

    def test_history_section_includes_previous_rounds(self):
        rounds = [
            {
                "round_number": 1,
                "user_input": "第一轮输入",
                "answers": None,
                "ai_response": {"understanding_summary": "理解摘要"},
            }
        ]
        result = format_consult_inputs("第二轮输入", brief=None, consultation_rounds=rounds)
        assert "第 1 轮" in result["history_section"]
        assert "第一轮输入" in result["history_section"]
        assert "理解摘要" in result["history_section"]

    def test_answers_appended_to_user_input(self):
        result = format_consult_inputs(
            "主输入",
            brief=None,
            consultation_rounds=[],
            answers={"q1": "回答1"},
        )
        assert "回答1" in result["user_input"]


# ── parse_consult_response 单元测试 ──────────────────────────────────────────


class TestParseConsultResponse:
    _valid_json = json.dumps({
        "understanding_summary": "用户想分析竞品",
        "clarification_questions": [],
        "monitor_suggestions": [
            {
                "name": "竞品声量监测",
                "platforms": ["xiaohongshu"],
                "keywords": ["品牌A"],
                "task_type": "posts",
                "rationale": "了解竞品曝光",
            }
        ],
        "slice_plan": [{"name": "竞品对比", "purpose": "对比分析", "expected_sources": ["竞品声量监测"]}],
        "confidence": 0.8,
    })

    def test_valid_json_parsed(self):
        result = parse_consult_response(self._valid_json)
        assert result["understanding_summary"] == "用户想分析竞品"
        assert len(result["monitor_suggestions"]) == 1
        assert result["confidence"] == 0.8

    def test_json_in_code_block(self):
        wrapped = f"```json\n{self._valid_json}\n```"
        result = parse_consult_response(wrapped)
        assert result["monitor_suggestions"][0]["name"] == "竞品声量监测"

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="无法解析为 JSON"):
            parse_consult_response("这不是 JSON")

    def test_missing_fields_get_defaults(self):
        minimal = json.dumps({"understanding_summary": "摘要"})
        result = parse_consult_response(minimal)
        assert result["clarification_questions"] == []
        assert result["monitor_suggestions"] == []
        assert result["slice_plan"] == []
        assert result["confidence"] == 0.0


# ── consult_strategy service 集成测试 ────────────────────────────────────────


_MOCK_LLM_OUTPUT = json.dumps({
    "understanding_summary": "用户想监测竞品表现",
    "clarification_questions": [{"id": "q1", "question": "主要竞品是哪几个？"}],
    "monitor_suggestions": [
        {
            "name": "竞品小红书声量",
            "platforms": ["xiaohongshu"],
            "keywords": ["竞品A", "竞品B"],
            "task_type": "posts",
            "rationale": "了解竞品在种草平台的表现",
        }
    ],
    "slice_plan": [],
    "confidence": 0.65,
})


@pytest.fixture
def mock_strategy():
    s = MagicMock()
    s.id = 1
    s.brand_brief = {"brand_name": "测试品牌", "analysis_goal": "竞品分析"}
    s.consultation_rounds = []
    s.status = "briefing"
    return s


class TestConsultStrategyService:
    @pytest.mark.asyncio
    @patch("src.strategies.service.create_strategy_consult_chain")
    async def test_happy_path_returns_consult_response(self, mock_chain_factory, mock_strategy):
        """有效输入 → AI 回复包含 monitor_suggestions"""
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content=_MOCK_LLM_OUTPUT)
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()

        result = await consult_strategy(db, mock_strategy, "我想分析竞品", None)

        assert result.round_number == 1
        assert result.understanding_summary == "用户想监测竞品表现"
        assert len(result.monitor_suggestions) == 1
        assert result.monitor_suggestions[0]["name"] == "竞品小红书声量"
        assert result.confidence == 0.65

    @pytest.mark.asyncio
    @patch("src.strategies.service.create_strategy_consult_chain")
    async def test_rounds_accumulate(self, mock_chain_factory, mock_strategy):
        """连续两次 consult → consultation_rounds 长度累加（不覆盖）"""
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content=_MOCK_LLM_OUTPUT)
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()

        # 第一轮
        await consult_strategy(db, mock_strategy, "第一轮", None)
        assert len(mock_strategy.consultation_rounds) == 1
        assert mock_strategy.consultation_rounds[0]["round_number"] == 1

        # 第二轮（模拟第二轮输入，round 继续累加）
        await consult_strategy(db, mock_strategy, "第二轮", None)
        assert len(mock_strategy.consultation_rounds) == 2
        assert mock_strategy.consultation_rounds[1]["round_number"] == 2

    @pytest.mark.asyncio
    @patch("src.strategies.service.create_strategy_consult_chain")
    async def test_status_advances_to_consulting(self, mock_chain_factory, mock_strategy):
        """首轮后 status = consulting"""
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content=_MOCK_LLM_OUTPUT)
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()
        assert mock_strategy.status == "briefing"

        await consult_strategy(db, mock_strategy, "输入", None)
        assert mock_strategy.status == "consulting"

    @pytest.mark.asyncio
    @patch("src.strategies.service.create_strategy_consult_chain")
    async def test_llm_parse_failure_raises_500(self, mock_chain_factory, mock_strategy):
        """LLM 返回无效 JSON → HTTP 500，strategy.consultation_rounds 不更新"""
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content="这不是 JSON")
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()
        original_rounds = list(mock_strategy.consultation_rounds)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await consult_strategy(db, mock_strategy, "输入", None)

        assert exc_info.value.status_code == 500
        # strategy 不被更新
        assert mock_strategy.consultation_rounds == original_rounds

    @pytest.mark.asyncio
    @patch("src.strategies.service.create_strategy_consult_chain")
    async def test_answers_forwarded_to_chain(self, mock_chain_factory, mock_strategy):
        """answers 正确传递给 format_consult_inputs（链被调用时传入了答案）"""
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = MagicMock(content=_MOCK_LLM_OUTPUT)
        mock_chain_factory.return_value = mock_chain

        db = AsyncMock()
        answers = {"q1": "竞品A、竞品B"}

        await consult_strategy(db, mock_strategy, "追问回答", answers)

        call_args = mock_chain.ainvoke.call_args[0][0]
        assert "竞品A、竞品B" in call_args["user_input"]
