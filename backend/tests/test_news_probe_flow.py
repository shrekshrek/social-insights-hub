"""新闻探测流程单元测试

覆盖范围：
1. RefineProbeRequest / NewsRefinementItem schema 校验
2. news_probe_review_chain 的 format/parse 辅助函数
3. news_media service._search_and_store_articles 的双渠道参数传递
4. strategies service._run_news_probe_review_one 的 (assessment, usage, duration) 返回契约
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.langchain.chains.news_probe_review_chain import (
    format_single_news_probe_review_inputs,
    parse_single_news_probe_review_response,
)
from src.strategies.schemas import (
    NewsRefinementItem,
    RefineProbeRequest,
    RefinementItem,
)


# ==================== Schema 校验 ====================


class TestNewsRefinementItem:
    def test_replace_operation(self):
        item = NewsRefinementItem(task_id=1, new_keyword="新关键词")
        assert item.task_id == 1
        assert item.new_keyword == "新关键词"
        assert item.dimension is None

    def test_remove_operation(self):
        item = NewsRefinementItem(task_id=1, new_keyword=None)
        assert item.task_id == 1
        assert item.new_keyword is None

    def test_add_operation_requires_keyword(self):
        with pytest.raises(ValidationError) as exc:
            NewsRefinementItem(task_id=None, new_keyword=None, dimension="品牌声量")
        assert "new_keyword" in str(exc.value)

    def test_add_operation_requires_dimension(self):
        with pytest.raises(ValidationError) as exc:
            NewsRefinementItem(task_id=None, new_keyword="kw", dimension=None)
        assert "dimension" in str(exc.value)

    def test_add_operation_valid(self):
        item = NewsRefinementItem(
            task_id=None, new_keyword="kw", dimension="品牌声量"
        )
        assert item.dimension == "品牌声量"


class TestRefineProbeRequest:
    def test_empty_both_rejected(self):
        with pytest.raises(ValidationError) as exc:
            RefineProbeRequest(refinements=[], news_refinements=[])
        assert "至少提供一项" in str(exc.value)

    def test_social_only_ok(self):
        req = RefineProbeRequest(
            refinements=[
                RefinementItem(task_id=1, new_keyword="kw", platform="wb")
            ],
            news_refinements=[],
        )
        assert len(req.refinements) == 1
        assert req.news_refinements == []

    def test_news_only_ok(self):
        req = RefineProbeRequest(
            refinements=[],
            news_refinements=[NewsRefinementItem(task_id=1, new_keyword="kw")],
        )
        assert req.refinements == []
        assert len(req.news_refinements) == 1

    def test_both_ok(self):
        req = RefineProbeRequest(
            refinements=[
                RefinementItem(task_id=1, new_keyword="s", platform="wb")
            ],
            news_refinements=[NewsRefinementItem(task_id=2, new_keyword="n")],
        )
        assert len(req.refinements) == 1
        assert len(req.news_refinements) == 1


# ==================== news_probe_review_chain 辅助函数 ====================


class TestFormatSingleNewsProbeReviewInputs:
    def test_basic_format_with_dimension_mapping(self):
        research_design = {
            "_news_task_dimension_map": {"42": "品牌声量"},
            "data_plan": [
                {"dimension_name": "品牌声量", "question_ids": ["q1"]},
            ],
            "research_questions": [
                {"id": "q1", "question": "品牌形象如何？"},
            ],
            "understanding_summary": "研究品牌形象",
        }
        task = {
            "task_id": 42,
            "keyword": "某品牌",
            "articles_total": 3,
            "source_tier_distribution": {"tier1": 2, "tier2": 1, "tier3": 0},
            "articles": [
                {
                    "title": "T1",
                    "source_name": "新华社",
                    "source_tier": "tier1",
                    "snippet": "摘要1",
                },
                {
                    "title": "T2",
                    "source_name": "央视",
                    "source_tier": "tier1",
                    "snippet": "摘要2",
                },
                {
                    "title": "T3",
                    "source_name": "36氪",
                    "source_tier": "tier2",
                    "snippet": "摘要3",
                },
            ],
        }
        brief = {"subject": "某品牌", "analysis_goal": "品牌认知"}

        result = format_single_news_probe_review_inputs(research_design, task, brief)

        assert "research_design_section" in result
        assert "probe_task_section" in result
        assert "某品牌" in result["research_design_section"]
        assert "品牌认知" in result["research_design_section"]
        assert "品牌声量" in result["probe_task_section"]
        assert "品牌形象如何？" in result["probe_task_section"]
        assert "tier1=2" in result["probe_task_section"]
        assert "新华社" in result["probe_task_section"]

    def test_long_snippet_truncation(self):
        task = {
            "task_id": 1,
            "keyword": "kw",
            "articles_total": 1,
            "source_tier_distribution": {"tier1": 0, "tier2": 0, "tier3": 1},
            "articles": [
                {
                    "title": "T",
                    "source_name": "某站",
                    "source_tier": "tier3",
                    "snippet": "A" * 200,
                },
            ],
        }
        result = format_single_news_probe_review_inputs({}, task, None)
        assert "…" in result["probe_task_section"]

    def test_empty_articles(self):
        task = {
            "task_id": 1,
            "keyword": "kw",
            "articles_total": 0,
            "source_tier_distribution": {},
            "articles": [],
        }
        result = format_single_news_probe_review_inputs({}, task, None)
        assert "（无）" in result["probe_task_section"]


class TestParseSingleNewsProbeReviewResponse:
    def test_parse_plain_json(self):
        text = '{"task_id": 1, "verdict": "pass", "note": "ok"}'
        result = parse_single_news_probe_review_response(text)
        assert result["verdict"] == "pass"
        assert result["task_id"] == 1

    def test_parse_markdown_wrapped(self):
        text = '```json\n{"task_id": 1, "verdict": "fail", "note": "跑题"}\n```'
        result = parse_single_news_probe_review_response(text)
        assert result["verdict"] == "fail"

    def test_parse_generic_codeblock(self):
        text = '```\n{"task_id": 1, "verdict": "pass", "note": "ok"}\n```'
        result = parse_single_news_probe_review_response(text)
        assert result["verdict"] == "pass"

    def test_missing_verdict_raises(self):
        with pytest.raises(ValueError, match="verdict"):
            parse_single_news_probe_review_response('{"task_id": 1}')

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="JSON"):
            parse_single_news_probe_review_response("not json at all")


# ==================== service 层集成 ====================


class TestSearchAndStoreArticlesDualChannel:
    """验证 execute_news_probe 通过 _PROBE_CHANNELS 传递双渠道参数"""

    @pytest.mark.asyncio
    async def test_execute_news_probe_uses_dual_channel(self):
        from src.news_media.tasks import service as news_service

        task = MagicMock()
        task.id = 1
        task.keywords = "测试"
        task.status = "pending"

        captured = {}

        async def fake_search(db, t, max_results, channels):
            captured["max_results"] = max_results
            captured["channels"] = channels
            return []

        with patch.object(
            news_service, "_search_and_store_articles", side_effect=fake_search
        ):
            db = AsyncMock()
            await news_service.execute_news_probe(db, task)

        assert captured["max_results"] == 25
        assert "baidu" in captured["channels"]
        assert "duckduckgo" in captured["channels"]


class TestRunNewsProbeReviewOne:
    """_run_news_probe_review_one 返回 (assessment, usage, duration) 三元组"""

    @pytest.mark.asyncio
    async def test_success_returns_triple(self):
        from src.strategies import service as strategies_service

        fake_resp = MagicMock()
        fake_resp.content = '{"task_id": 1, "keyword": "k", "verdict": "pass", "note": "ok"}'

        chain = MagicMock()
        chain.ainvoke = AsyncMock(return_value=fake_resp)

        with patch.object(
            strategies_service,
            "extract_token_usage",
            return_value={"summary": {"total_tokens": 100}},
        ):
            assessment, usage, duration = await strategies_service._run_news_probe_review_one(
                chain,
                {},
                None,
                {"task_id": 1, "keyword": "k", "articles_total": 0, "articles": []},
            )

        assert assessment is not None
        assert assessment["verdict"] == "pass"
        assert assessment["task_id"] == 1
        assert usage == {"summary": {"total_tokens": 100}}
        assert isinstance(duration, float)

    @pytest.mark.asyncio
    async def test_failure_returns_none_triple(self):
        from src.strategies import service as strategies_service

        chain = MagicMock()
        chain.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))

        assessment, usage, duration = await strategies_service._run_news_probe_review_one(
            chain,
            {},
            None,
            {"task_id": 1, "keyword": "k", "articles_total": 0, "articles": []},
        )

        assert assessment is None
        assert usage is None
        assert isinstance(duration, float)
