"""Strategy LLM Chain 单元测试 — parse 函数 + format 函数"""

import json

from src.llm.chains.strategy.brand_strategy.insight_chain import (
    format_slice_data_for_insight,
    parse_insight_response,
)
from src.llm.chains.strategy.brand_strategy.brand_role_chain import (
    format_data_for_brand_role,
    parse_brand_role_response,
)
from src.llm.chains.strategy.brand_strategy.big_idea_chain import (
    format_data_for_big_idea,
    parse_big_idea_response,
)


# ==================== Insight (brand_strategy 第 1 层) ====================


class TestParseInsight:
    def test_valid_json(self):
        raw = json.dumps({
            "social_tensions": [
                {
                    "statement": "消费者对价格不满",
                    "evidence": [{"type": "topic_sentiment", "description": "负面占比62%", "source": "s1"}],
                    "confidence": "high",
                }
            ],
            "brand_opportunities": [
                {
                    "statement": "性价比定位空白",
                    "evidence": [{"type": "sov_gap", "description": "无头部品牌", "source": "s1"}],
                    "related_tensions": [0],
                }
            ],
        })
        result = parse_insight_response(raw)
        assert len(result["social_tensions"]) == 1
        assert result["social_tensions"][0]["confidence"] == "high"
        assert len(result["brand_opportunities"]) == 1

    def test_json_in_code_block(self):
        raw = '```json\n{"social_tensions": [], "brand_opportunities": []}\n```'
        result = parse_insight_response(raw)
        assert result["social_tensions"] == []

    def test_invalid_json(self):
        result = parse_insight_response("这不是JSON")
        assert result["social_tensions"] == []
        assert result["brand_opportunities"] == []

    def test_missing_fields(self):
        result = parse_insight_response('{"foo": "bar"}')
        assert "social_tensions" in result
        assert "brand_opportunities" in result


class TestFormatInsight:
    def test_basic_format(self):
        slices = [
            {
                "meta": {"subject": "测试", "competitors": ["A"], "keywords": ["key"]},
                "foundation": {
                    "aligned_entities": [{"name": "E1", "role": "target", "heat": 10, "sentiment": 0.5}],
                    "aligned_topics": [{"name": "T1", "category": "功能", "heat": 5}],
                },
                "layers": {
                    "landscape": {"overview": {"nsr": 0.3}, "sov_ranking": []},
                    "intent": {"topic_radar": {}, "unmet_needs": []},
                },
                "reports": {"landscape_report": "报告内容"},
            }
        ]
        result = format_slice_data_for_insight(slices, brief={"brand": "test"}, research_design=None)
        assert "Brand Brief" in result["brief_section"]
        data = json.loads(result["slice_data"])
        assert len(data) == 1
        assert data[0]["subject"] == "测试"
        assert data[0]["mode"] == "品牌聚焦"

    def test_no_brief(self):
        result = format_slice_data_for_insight([{"meta": {}}], research_design=None)
        assert result["brief_section"] == ""


# ==================== Brand Role (brand_strategy 第 2 层) ====================


class TestParseBrandRole:
    def test_valid_json(self):
        raw = json.dumps({
            "brand_social_role": {
                "statement": "行业教育者",
                "elaboration": "阐释",
                "evidence": [],
            },
            "social_strategy": {
                "statement": "种草+教育",
                "core_message": "核心信息",
                "rhythm": "日常种草",
                "evidence": [],
            },
        })
        result = parse_brand_role_response(raw)
        assert result["brand_social_role"]["statement"] == "行业教育者"
        assert result["social_strategy"]["rhythm"] == "日常种草"

    def test_invalid_json(self):
        result = parse_brand_role_response("not json")
        assert result["brand_social_role"]["statement"] == ""
        assert result["social_strategy"]["statement"] == ""

    def test_missing_fields(self):
        result = parse_brand_role_response("{}")
        assert "brand_social_role" in result
        assert "social_strategy" in result


class TestFormatBrandRole:
    def test_basic_format(self):
        result = format_data_for_brand_role(
            insight_result={
                "social_tensions": [
                    {"id": 0, "statement": "T0"},
                    {"id": 1, "statement": "T1"},
                ],
            },
            selected_tension_id=0,
            slices=[{"layers": {"focus": {"kol_voices": [{"text": "hi"}]}}}],
            brief=None,
        )
        # 多分支模式下注入 focused tension section 而非完整 insight_result
        assert "insight_focused_section" in result


# ==================== Big Idea (brand_strategy 第 3 层) ====================


class TestParseBigIdea:
    def test_valid_json(self):
        raw = json.dumps({
            "big_idea": {
                "statement": "真实生活实验室",
                "elaboration": "阐释",
                "tension_echo": "回应矛盾",
                "evidence": [],
            },
            "content_strategy": {
                "pillars": [{"name": "P1", "description": "描述", "reference_examples": []}],
                "evidence": [],
            },
        })
        result = parse_big_idea_response(raw)
        assert result["big_idea"]["tension_echo"] == "回应矛盾"
        assert len(result["content_strategy"]["pillars"]) == 1

    def test_invalid_json(self):
        result = parse_big_idea_response("broken")
        assert result["big_idea"]["statement"] == ""
        assert result["content_strategy"]["pillars"] == []


class TestFormatBigIdea:
    def test_basic_format(self):
        result = format_data_for_big_idea(
            insight_result={
                "social_tensions": [
                    {"id": 0, "statement": "T0"},
                ],
            },
            selected_tension_id=0,
            branch_brand_role={"brand_social_role": {}},
            slices=[{"layers": {}, "foundation": {}}],
        )
        # 多分支模式：注入 focused tension + 当前分支 brand_role
        assert "insight_focused_section" in result
        assert "branch_brand_role_section" in result
