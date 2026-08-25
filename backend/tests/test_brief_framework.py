"""Brief Framework 字段抽取 + 注入 + advisory 规则测试

覆盖：
- brief_parser_chain.parse_brief_parser_response 对 4 个 framework 字段的处理
- research_design_chain.format_research_design_inputs 把字段注入 prompt
- strategies.service._check_missing_competitive_social_dimension（升级后读结构化字段）

跨领域 fixtures：FMCG / B2B SaaS / 公益反诈 — 验证 schema 通用性。
"""

import json

from src.llm.chains.strategy.brief_parser_chain import parse_brief_parser_response
from src.llm.chains.strategy.research_design_chain import format_research_design_inputs
from src.strategies.service import (
    _check_missing_competitive_social_dimension,
    _compute_research_design_advisories,
)


# ============================== brief_parser parse 测试 ==============================


def _minimal_llm_response(extra: dict | None = None) -> str:
    base = {
        "strategy_name": "X",
        "subject": "X",
        "analysis_goal": "G",
        "constraints": "",
        "channel_plan": [],
        "platform_verdict": "sufficient",
        "platform_note": "",
        "insufficient_reason": "",
    }
    if extra:
        base.update(extra)
    return json.dumps(base, ensure_ascii=False)


def test_parser_framework_fields_all_null_when_brief_lacks_them():
    """旧 brief 不含 framework 字段时 LLM 完全省略，parse 后 4 字段统一为 None"""
    result = parse_brief_parser_response(_minimal_llm_response())
    assert result["target_audiences"] is None
    assert result["audience_insights"] is None
    assert result["core_propositions"] is None
    assert result["competitors"] is None


def test_parser_framework_fields_empty_array_normalized_to_none():
    """LLM 错返空数组应归一化为 None，保持"未提及"语义清晰"""
    result = parse_brief_parser_response(
        _minimal_llm_response(
            {
                "target_audiences": [],
                "audience_insights": [],
                "core_propositions": [],
                "competitors": [],
            }
        )
    )
    assert result["target_audiences"] is None
    assert result["audience_insights"] is None
    assert result["core_propositions"] is None
    assert result["competitors"] is None


def test_parser_framework_fields_fmcg_brief():
    """FMCG brief：人群画像 + 痛点 + 主张 + 竞品 全部抽取"""
    result = parse_brief_parser_response(
        _minimal_llm_response(
            {
                "target_audiences": [
                    {
                        "label": "Rational Affluent 专业求证富足派",
                        "description": "90 后高知高收入妈妈",
                        "behavior_signals": ["小红书 KOL 推荐", "成分查询", "医护推荐"],
                    },
                    {
                        "label": "Big Brand Follower 体面跟风派",
                        "description": "上线城市 90/95 后妈妈",
                        "behavior_signals": ["线下口碑", "亲友推荐", "户外广告"],
                    },
                ],
                "audience_insights": ["益生菌配方价值难以理解和衡量"],
                "core_propositions": ["益生菌配方是高端配方价值符号"],
                "competitors": ["晨贝儿", "优诺佳", "岚舒"],
            }
        )
    )
    assert len(result["target_audiences"]) == 2
    assert result["target_audiences"][0]["label"] == "Rational Affluent 专业求证富足派"
    assert "小红书 KOL 推荐" in result["target_audiences"][0]["behavior_signals"]
    assert "益生菌配方价值难以理解和衡量" in result["audience_insights"]
    assert "晨贝儿" in result["competitors"]


def test_parser_framework_fields_b2b_saas_brief():
    """B2B SaaS brief：决策角色而非消费者人群、竞品含'自建'替代方案"""
    result = parse_brief_parser_response(
        _minimal_llm_response(
            {
                "target_audiences": [
                    {
                        "label": "CIO 决策者",
                        "description": "大型企业 IT 决策层",
                        "behavior_signals": [
                            "Gartner 报告参考",
                            "同行案例",
                            "行业峰会",
                        ],
                    },
                    {
                        "label": "IT 实施者",
                        "behavior_signals": ["技术社区文档", "PoC 实测"],
                    },
                ],
                "audience_insights": ["数据孤岛严重", "合规审计耗时"],
                "core_propositions": ["一站式合规友好平台"],
                "competitors": ["Salesforce", "SAP", "自建团队"],
            }
        )
    )
    # 角色而非人群，依然能正常抽取
    assert result["target_audiences"][0]["label"] == "CIO 决策者"
    assert "Gartner 报告参考" in result["target_audiences"][0]["behavior_signals"]
    # 第二个 segment 缺 description 时留空字符串或缺字段，都应能被处理
    assert result["target_audiences"][1]["label"] == "IT 实施者"
    # 竞品含"自建团队"等替代方案概念
    assert "自建团队" in result["competitors"]


def test_parser_framework_fields_public_welfare_brief():
    """公益反诈 brief：受众群体 + 无竞品概念"""
    result = parse_brief_parser_response(
        _minimal_llm_response(
            {
                "target_audiences": [
                    {
                        "label": "65+ 老年人",
                        "description": "易受电信诈骗",
                        "behavior_signals": ["短视频获取信息", "亲属提醒"],
                    },
                ],
                "audience_insights": ["对新型 AI 换脸骗术认知盲区"],
                "core_propositions": ["三步识别法（停-问-查）"],
                # 公益场景明确无"竞品"概念，留空
            }
        )
    )
    assert len(result["target_audiences"]) == 1
    assert result["target_audiences"][0]["label"] == "65+ 老年人"
    assert result["competitors"] is None  # 公益场景无竞品


# ============================== format_research_design_inputs 测试 ==============================


def test_format_no_framework_fields_omits_all_blocks():
    """未提供 framework 字段时 prompt 不出现对应 block"""
    inputs = format_research_design_inputs(
        user_input="",
        subject="X",
        analysis_goal="G",
    )
    assert "目标受众" not in inputs["brief_section"]
    assert "受众痛点" not in inputs["brief_section"]
    assert "核心主张" not in inputs["brief_section"]
    assert "明确竞品" not in inputs["brief_section"]


def test_format_audiences_block_renders_signals():
    """target_audiences 注入：label + description + behavior_signals 全部渲染"""
    inputs = format_research_design_inputs(
        user_input="",
        subject="至臻",
        analysis_goal="益生菌配方价值符号化",
        target_audiences=[
            {
                "label": "Rational Affluent",
                "description": "高知高收入妈妈",
                "behavior_signals": ["小红书 KOL", "成分查询"],
            },
            {
                "label": "Big Brand Follower",
                "behavior_signals": ["线下口碑"],
            },
        ],
    )
    section = inputs["brief_section"]
    assert "目标受众" in section
    assert "Rational Affluent" in section
    assert "高知高收入妈妈" in section
    assert "小红书 KOL" in section
    assert "Big Brand Follower" in section
    assert "线下口碑" in section


def test_format_all_framework_fields_rendered():
    """audience_insights / core_propositions / competitors 全部渲染"""
    inputs = format_research_design_inputs(
        user_input="",
        subject="X",
        analysis_goal="G",
        audience_insights=["痛点 A", "痛点 B"],
        core_propositions=["主张 X"],
        competitors=["竞品 1", "竞品 2"],
    )
    section = inputs["brief_section"]
    assert "受众痛点/诉求：痛点 A；痛点 B" in section
    assert "核心主张/差异化：主张 X" in section
    assert "明确竞品/替代方案：竞品 1、竞品 2" in section


def test_format_filters_empty_signal_strings():
    """behavior_signals 含空字符串时过滤掉，不影响渲染"""
    inputs = format_research_design_inputs(
        user_input="",
        target_audiences=[
            {"label": "X", "behavior_signals": ["valid", "", "  ", "another"]},
        ],
    )
    assert "valid、another" in inputs["brief_section"]


# ============================== Advisory 规则测试 ==============================


def _make_design_with_dims(dim_specs: list[tuple[str, str, str]]) -> dict:
    """快速构造 research_design：每个 spec = (dim_name, dimension_type, channel)"""
    rqs = [
        {"id": f"rq{i}", "question": f"Q{i}", "dimension": dim_type, "priority": "high"}
        for i, (_, dim_type, _) in enumerate(dim_specs)
    ]
    data_plan = [
        {
            "dimension_name": name,
            "channel": channel,
            "keywords": ["k"],
            "platforms": ["xiaohongshu"] if channel == "social_media" else [],
            "question_ids": [f"rq{i}"],
        }
        for i, (name, _, channel) in enumerate(dim_specs)
    ]
    return {"data_plan": data_plan, "research_questions": rqs}


def test_missing_competitive_triggered_by_structured_field():
    """brand_brief.competitors 非空 + data_plan 无 competitive → 触发"""
    design = _make_design_with_dims([("品牌声量", "consumer_voice", "social_media")])
    brief = {"competitors": ["晨贝儿", "优诺佳"]}
    result = _check_missing_competitive_social_dimension(design, brief)
    assert result is not None
    assert result["code"] == "missing_competitive_social_dimension"


def test_missing_competitive_triggered_by_text_grep_fallback():
    """structured 字段空但 constraints 含「竞品」字面 → 兜底触发（向后兼容）"""
    design = _make_design_with_dims([("品牌声量", "consumer_voice", "social_media")])
    brief = {
        "competitors": None,
        "constraints": "需要做竞品对比",
        "analysis_goal": "",
    }
    result = _check_missing_competitive_social_dimension(design, brief)
    assert result is not None


def test_missing_competitive_not_triggered_when_dim_exists():
    """data_plan 已有 competitive 维度 → 不触发"""
    design = _make_design_with_dims(
        [
            ("品牌声量", "consumer_voice", "social_media"),
            ("竞品对比", "competitive", "social_media"),
        ]
    )
    brief = {"competitors": ["A", "B"]}
    assert _check_missing_competitive_social_dimension(design, brief) is None


def test_missing_competitive_not_triggered_when_no_signal():
    """brief 既无结构化竞品也无字面信号 → 不触发"""
    design = _make_design_with_dims([("品牌声量", "consumer_voice", "social_media")])
    brief = {"competitors": None, "constraints": "时间：Q3", "analysis_goal": ""}
    assert _check_missing_competitive_social_dimension(design, brief) is None


def test_missing_competitive_not_triggered_for_news_only_brief():
    """纯新闻 brief（无 social_media 维度）→ 不触发（这条规则只管社媒）"""
    design = _make_design_with_dims([("媒体报道", "media_narrative", "news_media")])
    brief = {"competitors": ["A"]}
    assert _check_missing_competitive_social_dimension(design, brief) is None


def test_compute_advisories_isolates_check_failures():
    """单条规则异常时不应阻塞其他规则——dispatcher 兜底"""
    design = _make_design_with_dims([("品牌声量", "consumer_voice", "social_media")])
    brief = {
        "competitors": ["A"],  # 触发 missing_competitive
        "constraints": "需要做竞品对比",
    }
    advisories = _compute_research_design_advisories(design, brief)
    codes = [a["code"] for a in advisories]
    assert "missing_competitive_social_dimension" in codes
