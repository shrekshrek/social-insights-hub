"""evaluator.py 核心评分逻辑的单元测试(纯函数,不涉及 DB)"""

from __future__ import annotations

from src.strategies.evaluator import (
    _score_completeness,
    _score_evidence_density,
    _score_subject_focus,
    collect_evidence_text,
    extract_post_ids,
    iter_insight_claims,
)


# ======================================================================
# extract_post_ids
# ======================================================================


class TestExtractPostIds:
    def test_basic(self):
        assert extract_post_ids("post_id=12345") == [12345]

    def test_multiple(self):
        text = "ref post_id=111 and post_id=222, also post_id:333"
        assert extract_post_ids(text) == [111, 222, 333]

    def test_with_colon(self):
        assert extract_post_ids("引用 post_id: 9876") == [9876]

    def test_empty(self):
        assert extract_post_ids("") == []
        assert extract_post_ids(None) == []  # type: ignore[arg-type]

    def test_no_match(self):
        assert extract_post_ids("slice 0, unmet_needs[0]") == []


# ======================================================================
# iter_insight_claims
# ======================================================================


class TestIterInsightClaims:
    def test_tensions_and_opps(self):
        output = {
            "social_tensions": [
                {
                    "statement": "t1",
                    "evidence": [{"source": "s1"}],
                    "confidence": "high",
                }
            ],
            "brand_opportunities": [
                {"statement": "o1", "evidence": [], "rationale": "r"},
            ],
        }
        claims = iter_insight_claims(output)
        assert len(claims) == 2
        assert claims[0]["kind"] == "tension"
        assert claims[0]["extra"]["confidence"] == "high"
        assert claims[1]["kind"] == "opportunity"
        assert claims[1]["extra"]["rationale"] == "r"

    def test_empty_output(self):
        assert iter_insight_claims({}) == []


# ======================================================================
# collect_evidence_text
# ======================================================================


class TestCollectEvidenceText:
    def test_includes_statement_and_evidence(self):
        claim = {
            "statement": "主题",
            "evidence": [
                {"source": "post_id=111", "description": "原话"},
                {"source": "post_id=222"},
            ],
        }
        text = collect_evidence_text(claim)
        assert "主题" in text
        assert "post_id=111" in text
        assert "post_id=222" in text
        assert "原话" in text


# ======================================================================
# _score_evidence_density
# ======================================================================


class TestEvidenceDensity:
    def test_full_score_all_have_2_plus(self):
        claims = [
            {"kind": "tension", "statement": "t", "evidence": [{"x": 1}, {"y": 2}]},
            {
                "kind": "opportunity",
                "statement": "o",
                "evidence": [{"a": 1}, {"b": 2}, {"c": 3}],
            },
        ]
        d = _score_evidence_density(claims)
        assert d.score == 1.0
        assert d.details["claims_with_2plus"] == 2

    def test_partial_score(self):
        claims = [
            {"kind": "tension", "statement": "t", "evidence": []},
            {"kind": "tension", "statement": "t", "evidence": [{"x": 1}]},
            {"kind": "tension", "statement": "t", "evidence": [{"x": 1}, {"y": 2}]},
        ]
        d = _score_evidence_density(claims)
        # (0 + 0.5 + 1.0) / 3 = 0.5
        assert abs(d.score - 0.5) < 1e-6

    def test_empty_claims(self):
        d = _score_evidence_density([])
        assert d.score == 0.0


# ======================================================================
# _score_subject_focus
# ======================================================================


class TestSubjectFocus:
    def test_full_focus(self):
        claims = [
            {"kind": "tension", "statement": "猎风的消费者...", "evidence": []},
            {"kind": "opportunity", "statement": "猎风可以...", "evidence": []},
        ]
        d = _score_subject_focus(claims, "猎风")
        # 2/2 = 100% >= 60%,满分
        assert d.score == 1.0

    def test_no_subject(self):
        d = _score_subject_focus(
            [{"kind": "tension", "statement": "t", "evidence": []}], None
        )
        assert d.score == 0.0

    def test_partial_focus_below_target(self):
        claims = [
            {"kind": "tension", "statement": "猎风好", "evidence": []},
            {"kind": "tension", "statement": "其他品牌", "evidence": []},
            {"kind": "tension", "statement": "再其他", "evidence": []},
        ]
        d = _score_subject_focus(claims, "猎风")
        # 1/3 = 0.333, target 0.6, score = 0.333/0.6 = 0.555
        assert 0.5 < d.score < 0.6

    def test_focus_in_evidence_not_statement(self):
        """subject 在 evidence 里也算命中"""
        claims = [
            {
                "kind": "tension",
                "statement": "消费者痛点",
                "evidence": [{"description": "猎风相关的原话"}],
            },
        ]
        d = _score_subject_focus(claims, "猎风")
        assert d.score == 1.0


# ======================================================================
# _score_completeness
# ======================================================================


class TestCompleteness:
    def test_full_tension(self):
        claims = [
            {
                "kind": "tension",
                "statement": "s",
                "evidence": [{"x": 1}],
                "extra": {
                    "confidence": "high",
                    "conventional_wisdom": "cw",
                    "data_reality": "dr",
                },
            },
        ]
        d = _score_completeness(claims)
        assert d.score == 1.0

    def test_opportunity_with_rationale(self):
        claims = [
            {
                "kind": "opportunity",
                "statement": "s",
                "evidence": [{"x": 1}],
                "extra": {"confidence": "high", "rationale": "r"},
            },
        ]
        d = _score_completeness(claims)
        assert d.score == 1.0

    def test_opportunity_missing_rationale(self):
        claims = [
            {
                "kind": "opportunity",
                "statement": "s",
                "evidence": [{"x": 1}],
                "extra": {"confidence": "high"},  # 缺 rationale 和 why_non_obvious
            },
        ]
        d = _score_completeness(claims)
        # 4 字段里 3 个填(statement, confidence, evidence),rationale/why_non_obvious 缺
        assert abs(d.score - 0.75) < 1e-6
