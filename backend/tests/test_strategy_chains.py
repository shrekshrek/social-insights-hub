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
from src.llm.chains.strategy.research_design_chain import (
    _fix_orphan_dimensions,
)
from src.llm.chains.strategy.coverage_check_chain import (
    _select_evidence,
    format_coverage_check_inputs,
)


# ==================== Insight (brand_strategy 第 1 层) ====================


class TestParseInsight:
    def test_valid_json(self):
        raw = json.dumps(
            {
                "social_tensions": [
                    {
                        "statement": "消费者对价格不满",
                        "evidence": [
                            {
                                "type": "topic_sentiment",
                                "description": "负面占比62%",
                                "source": "s1",
                            }
                        ],
                        "confidence": "high",
                    }
                ],
                "brand_opportunities": [
                    {
                        "statement": "性价比定位空白",
                        "evidence": [
                            {
                                "type": "sov_gap",
                                "description": "无头部品牌",
                                "source": "s1",
                            }
                        ],
                        "related_tensions": [0],
                    }
                ],
            }
        )
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
                    "aligned_entities": [
                        {"name": "E1", "role": "target", "heat": 10, "sentiment": 0.5}
                    ],
                    "aligned_topics": [{"name": "T1", "category": "功能", "heat": 5}],
                },
                "layers": {
                    "landscape": {"overview": {"nsr": 0.3}, "sov_ranking": []},
                    "intent": {"topic_radar": {}, "unmet_needs": []},
                },
                "reports": {"landscape_report": "报告内容"},
            }
        ]
        result = format_slice_data_for_insight(
            slices, brief={"brand": "test"}, research_design=None
        )
        assert "Brand Brief" in result["brief_section"]
        data = json.loads(result["slice_data"])
        assert len(data) == 1
        assert data[0]["subject"] == "测试"
        assert data[0]["mode"] == "品牌聚焦"

    def test_no_brief(self):
        result = format_slice_data_for_insight([{"meta": {}}], research_design=None)
        assert result["brief_section"] == ""

    def test_news_media_section_includes_themes(self):
        """新闻补充段必须携带议题层（themes）——消费者-媒体分歧识别的直接对照面。

        媒体议题（抽象讨论维度 + 态度）与社媒 aligned_topics 同构，缺它时
        LLM 只能从实体+引语间接拼凑媒体侧的讨论维度。三层（insight/brand_role/
        big_idea）共用 _format_news_media_section，测 insight 入口即覆盖。
        """
        news_slices = [
            {
                "name": "品牌媒体声量",
                "result_data": {
                    "descriptive": {"articles_filtered": 56},
                    "entities": [
                        {"name": "品牌A", "role": "target", "mention_count": 9}
                    ],
                    "quotes": [],
                    "themes": [
                        {
                            "name": "抄袭争议",
                            "article_count": 5,
                            "source_count": 4,
                            "sentiment_avg": -0.6,
                            "tier_weighted_score": 7.5,
                        }
                    ],
                },
            }
        ]
        result = format_slice_data_for_insight(
            [{"meta": {}}],
            research_design=None,
            news_slices=news_slices,
        )
        section = result["news_media_section"]
        assert "抄袭争议" in section
        # 引导文案需提示议题层存在及其情感量纲（与社媒话题量纲不同）
        assert "议题" in section
        assert "[-2,2]" in section


# ==================== Brand Role (brand_strategy 第 2 层) ====================


class TestParseBrandRole:
    def test_valid_json(self):
        raw = json.dumps(
            {
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
            }
        )
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
        raw = json.dumps(
            {
                "big_idea": {
                    "statement": "真实生活实验室",
                    "elaboration": "阐释",
                    "tension_echo": "回应矛盾",
                    "evidence": [],
                },
                "content_strategy": {
                    "pillars": [
                        {"name": "P1", "description": "描述", "reference_examples": []}
                    ],
                    "evidence": [],
                },
            }
        )
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


# ==================== _fix_orphan_dimensions（research_design 后置修复） ====================


class TestFixOrphanDimensions:
    """覆盖 strategy 41 事故场景及对称社媒/新闻孤儿维度兜底。"""

    def test_strategy_41_news_competitive_orphan_repaired(self):
        """LLM 把 social/news 同概念命名分裂（"竞品配方沟通策略" / "竞品配方沟通新闻"），
        blueprint 只引用了 social 那条 → news 那条变孤儿，修复后必须进入品牌聚焦+大盘切片。"""
        data_plan = [
            {
                "dimension_name": "消费者对Velora及益生菌配方认知",
                "channel": "social_media",
                "question_ids": ["rq1"],
            },
            {
                "dimension_name": "竞品配方沟通策略",
                "channel": "social_media",
                "question_ids": ["rq3"],
            },
            {
                "dimension_name": "行业趋势与科研新闻",
                "channel": "news_media",
                "question_ids": ["rq4"],
            },
            {
                "dimension_name": "竞品配方沟通新闻",
                "channel": "news_media",
                "question_ids": ["rq3"],
            },
        ]
        slice_blueprint = [
            {
                "name": "Velora品牌认知与竞争对比",
                "subject": "Velora",
                "source_dimensions": [
                    "消费者对Velora及益生菌配方认知",
                    "竞品配方沟通策略",
                ],
            },
            {
                "name": "高端奶粉行业趋势与益生菌配方价值",
                "subject": "",
                "source_dimensions": ["竞品配方沟通策略", "行业趋势与科研新闻"],
            },
        ]
        dim_type_map = {
            "消费者对Velora及益生菌配方认知": "consumer_voice",
            "竞品配方沟通策略": "competitive",
            "行业趋势与科研新闻": "industry",
            "竞品配方沟通新闻": "competitive",
        }
        fixed = _fix_orphan_dimensions(data_plan, slice_blueprint, dim_type_map)
        focused_dims = set(fixed[0]["source_dimensions"])
        general_dims = set(fixed[1]["source_dimensions"])
        # competitive 类孤儿：品牌聚焦 + 大盘 都要进
        assert "竞品配方沟通新闻" in focused_dims
        assert "竞品配方沟通新闻" in general_dims
        # 非孤儿维度不变
        assert "消费者对Velora及益生菌配方认知" in focused_dims
        assert "行业趋势与科研新闻" in general_dims

    def test_no_orphan_returns_unchanged(self):
        """所有 dim 都被引用时不修改 blueprint。"""
        data_plan = [{"dimension_name": "A"}, {"dimension_name": "B"}]
        slice_blueprint = [
            {"name": "s1", "subject": "X", "source_dimensions": ["A", "B"]},
        ]
        result = _fix_orphan_dimensions(
            data_plan, slice_blueprint, {"A": "competitive", "B": "industry"}
        )
        assert result == slice_blueprint

    def test_consumer_voice_orphan_to_focused(self):
        data_plan = [{"dimension_name": "消费者声音"}]
        slice_blueprint = [
            {"name": "聚焦", "subject": "X", "source_dimensions": []},
            {"name": "大盘", "subject": "", "source_dimensions": []},
        ]
        fixed = _fix_orphan_dimensions(
            data_plan, slice_blueprint, {"消费者声音": "consumer_voice"}
        )
        assert "消费者声音" in fixed[0]["source_dimensions"]
        assert "消费者声音" not in fixed[1]["source_dimensions"]

    def test_industry_orphan_to_general(self):
        data_plan = [{"dimension_name": "行业新闻"}]
        slice_blueprint = [
            {"name": "聚焦", "subject": "X", "source_dimensions": []},
            {"name": "大盘", "subject": "", "source_dimensions": []},
        ]
        fixed = _fix_orphan_dimensions(
            data_plan, slice_blueprint, {"行业新闻": "industry"}
        )
        assert "行业新闻" not in fixed[0]["source_dimensions"]
        assert "行业新闻" in fixed[1]["source_dimensions"]

    def test_unknown_type_falls_back_to_first_slice(self):
        data_plan = [{"dimension_name": "X"}]
        slice_blueprint = [
            {"name": "s1", "subject": "Y", "source_dimensions": []},
        ]
        fixed = _fix_orphan_dimensions(data_plan, slice_blueprint, {})
        assert "X" in fixed[0]["source_dimensions"]

    def test_competitive_no_general_slice_only_focused(self):
        """只有品牌聚焦切片时 competitive 孤儿仅进 focused，不报错。"""
        data_plan = [{"dimension_name": "竞品X"}]
        slice_blueprint = [
            {"name": "聚焦", "subject": "Y", "source_dimensions": []},
        ]
        fixed = _fix_orphan_dimensions(
            data_plan, slice_blueprint, {"竞品X": "competitive"}
        )
        assert fixed[0]["source_dimensions"] == ["竞品X"]

    def test_dedup_when_already_partially_referenced(self):
        """同名维度已在某切片但缺另一切片时，仅追加缺失的那个切片，不重复。"""
        data_plan = [{"dimension_name": "竞品A"}]
        slice_blueprint = [
            {"name": "聚焦", "subject": "Y", "source_dimensions": ["竞品A"]},
            {"name": "大盘", "subject": "", "source_dimensions": []},
        ]
        # 注意：当前 dim 已被任一切片引用就不再视为孤儿（与设计一致）
        fixed = _fix_orphan_dimensions(
            data_plan, slice_blueprint, {"竞品A": "competitive"}
        )
        # 已被引用 → 不视为孤儿，blueprint 不变
        assert fixed == slice_blueprint


# ==================== _select_evidence（coverage_check 输入截断） ====================


class TestSelectEvidence:
    """覆盖 strategy 41 事故场景：低排序高 source 实体不能被截断丢弃。"""

    def test_strategy_41_high_source_low_position_kept(self):
        """益生菌配方 source=12 处于第 50 位（远超 top 15）也必须传给 LLM。"""
        items = (
            [
                {"name": f"高频 {i}", "source_count": 100 - i} for i in range(20)
            ]  # 0..19 高 source
            + [
                {"name": f"中频 {i}", "source_count": 5} for i in range(30)
            ]  # 20..49 中 source
            + [{"name": "益生菌配方", "source_count": 12}]  # 第 50 位 source=12
            + [
                {"name": f"低频 {i}", "source_count": 1} for i in range(50)
            ]  # 51..100 低 source
        )
        selected, total, covered = _select_evidence(items, source_key="source_count")
        names = {i["name"] for i in selected}
        assert "益生菌配方" in names, "source>=3 的实体必须保留，不能被位置截断"
        assert total == 101
        assert covered == 51  # 20 高频 + 30 中频 + 益生菌配方

    def test_sorted_by_source_desc(self):
        items = [
            {"name": "low", "source_count": 1},
            {"name": "high", "source_count": 50},
            {"name": "mid", "source_count": 5},
        ]
        selected, _, _ = _select_evidence(items, source_key="source_count")
        # source>=3 排前，source<3 兜底排后
        assert selected[0]["name"] == "high"
        assert selected[1]["name"] == "mid"
        assert selected[-1]["name"] == "low"

    def test_all_below_threshold_keeps_top_n(self):
        """全部 source<3 时只保留兜底 top 15。"""
        items = [{"name": f"x{i}", "source_count": 2} for i in range(50)]
        selected, total, covered = _select_evidence(items, source_key="source_count")
        assert total == 50
        assert covered == 0
        assert len(selected) == 15  # _PARTIAL_BACKUP_COUNT

    def test_empty_input(self):
        selected, total, covered = _select_evidence([], source_key="source_count")
        assert selected == []
        assert total == 0
        assert covered == 0

    def test_invalid_source_value_treated_as_zero(self):
        items = [
            {"name": "a", "source_count": None},
            {"name": "b", "source_count": "abc"},
            {"name": "c", "source_count": 5},
        ]
        selected, _, covered = _select_evidence(items, source_key="source_count")
        assert covered == 1
        assert selected[0]["name"] == "c"

    def test_format_coverage_check_inputs_includes_low_position_high_source(self):
        """端到端：strategy 41 切片 148 的真实结构在 LLM 输入里能看到「益生菌配方」。"""
        slices_data = [
            (
                "Velora品牌认知与竞争对比",
                {
                    "foundation": {
                        "aligned_entities": (
                            [
                                {"name": f"E{i}", "source_count": 100 - i}
                                for i in range(15)
                            ]
                            + [{"name": "益生菌配方", "source_count": 12}]
                            + [{"name": f"L{i}", "source_count": 1} for i in range(50)]
                        ),
                        "aligned_topics": [],
                    },
                    "layers": {"landscape": {"overview": {"total_volume": 100}}},
                },
            ),
        ]
        result = format_coverage_check_inputs(
            brief={"subject": "Velora", "analysis_goal": "益生菌配方"},
            research_questions=[
                {
                    "id": "rq1",
                    "question": "益生菌配方 认知",
                    "dimension": "consumer_voice",
                    "priority": "high",
                },
            ],
            slices_data=slices_data,
        )
        assert "益生菌配方" in result["slices_summary_section"]
        # 元信息体现全貌
        assert "共 66 个" in result["slices_summary_section"]
        assert "source≥3 的 16 个" in result["slices_summary_section"]

    def test_format_coverage_check_inputs_news_slice_includes_themes(self):
        """新闻切片的议题层（themes）必须进入 LLM 输入——与社媒话题路径对称。

        themes 是新闻侧的"话题路径"证据：RQ 表述偏抽象议题（如"媒体对安全性的
        态度"）时实体清单可能零字面命中，缺 themes 会造成假阴性 uncovered。
        """
        slices_data = [
            (
                "[新闻] 品牌媒体声量",
                {
                    "descriptive": {
                        "sentiment_distribution": {
                            "positive": 10,
                            "neutral": 5,
                            "negative": 3,
                        },
                        "sentiment_overall": 0.5,
                    },
                    "entities": [
                        {
                            "name": "品牌A",
                            "role": "target",
                            "mention_count": 9,
                            "source_count": 6,
                            "sentiment_avg": 0.4,
                        }
                    ],
                    "themes": [
                        {
                            "name": "价格争议",
                            "article_count": 7,
                            "source_count": 5,
                            "sentiment_avg": -0.6,
                        },
                        {
                            "name": "技术创新",
                            "article_count": 2,
                            "source_count": 1,
                            "sentiment_avg": 0.8,
                        },
                    ],
                },
            ),
        ]
        result = format_coverage_check_inputs(
            brief={"subject": "品牌A", "analysis_goal": "媒体态度"},
            research_questions=[
                {
                    "id": "rq1",
                    "question": "媒体对价格的态度",
                    "dimension": "media_narrative",
                    "priority": "high",
                },
            ],
            slices_data=slices_data,
        )
        summary = result["slices_summary_section"]
        # 实体通道不受影响
        assert "品牌A" in summary
        # 议题通道：名称 + 元信息行 + article_count 映射为 mentions
        assert "价格争议" in summary
        assert "议题（共 2 个" in summary
        assert "source≥3 的 1 个" in summary
        assert "mentions=7" in summary
        # source<3 的议题走兜底路径，也必须可见（partial 上下文）
        assert "技术创新" in summary
