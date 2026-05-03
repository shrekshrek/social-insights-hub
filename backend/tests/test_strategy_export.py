"""Strategy Word Export 单元测试"""

import pytest
from io import BytesIO
from unittest.mock import MagicMock

pytest.importorskip("docx", reason="python-docx 仅在 Docker 容器内安装，跳过宿主机测试")
from src.strategies.export_docx import generate_strategy_docx


def _make_strategy(
    name: str = "测试策略",
    insight: dict | None = None,
    brand_role: dict | None = None,
    big_idea: dict | None = None,
) -> MagicMock:
    # spec 限定属性，避免 MagicMock 对未知字段自动产生 truthy 属性掩盖重构错误
    strategy = MagicMock(
        spec=[
            "name",
            "insight_result",
            "brand_strategy_branches",
            "agenda_map_result",
            "landscape_result",
            "strategic_brief_result",
            "output_type",
            "brand_brief",
            "research_design",
        ]
    )
    strategy.name = name
    strategy.insight_result = insight
    # 多分支：把单 brand_role/big_idea 包成单元素 selected branch
    if brand_role is not None or big_idea is not None:
        strategy.brand_strategy_branches = [{
            "tension_id": 0,
            "tension_summary": "test tension",
            "brand_role": brand_role,
            "big_idea": big_idea,
            "selected": True,
            "status": "big_idea_done" if big_idea else "brand_role_done",
        }]
    else:
        strategy.brand_strategy_branches = None
    strategy.agenda_map_result = None
    strategy.landscape_result = None
    strategy.strategic_brief_result = None
    strategy.output_type = "campaign_strategy"
    strategy.brand_brief = None
    strategy.research_design = None
    return strategy


class TestGenerateStrategyDocx:
    def test_empty_stages(self):
        """所有 stage 为空时不报错，返回有效 docx"""
        strategy = _make_strategy()
        buf = generate_strategy_docx(strategy)
        assert isinstance(buf, BytesIO)
        # DOCX (ZIP) 文件开头为 PK 签名
        content = buf.read()
        assert content[:2] == b"PK"

    def test_full_stages(self):
        """三个阶段都有数据时正常生成"""
        strategy = _make_strategy(
            insight={
                "social_tensions": [
                    {
                        "statement": "价格矛盾",
                        "confidence": "high",
                        "evidence": [
                            {"type": "topic", "description": "负面占62%", "source": "s1"}
                        ],
                    }
                ],
                "brand_opportunities": [
                    {
                        "statement": "性价比空白",
                        "evidence": [],
                        "related_tensions": [0],
                    }
                ],
            },
            brand_role={
                "brand_social_role": {
                    "statement": "行业教育者",
                    "elaboration": "阐释内容",
                    "evidence": [],
                },
                "social_strategy": {
                    "statement": "种草+教育",
                    "core_message": "核心信息",
                    "rhythm": "日常种草",
                    "evidence": [],
                },
            },
            big_idea={
                "big_idea": {
                    "statement": "真实生活实验室",
                    "elaboration": "创意阐释",
                    "tension_echo": "回应矛盾",
                    "evidence": [],
                },
                "content_strategy": {
                    "pillars": [
                        {
                            "name": "支柱1",
                            "description": "描述",
                            "reference_examples": ["案例A"],
                        }
                    ],
                    "evidence": [],
                },
            },
        )
        buf = generate_strategy_docx(strategy)
        content = buf.read()
        assert len(content) > 0
        assert content[:2] == b"PK"

    def test_partial_stages(self):
        """只有 Insight 层有数据"""
        strategy = _make_strategy(
            insight={
                "social_tensions": [],
                "brand_opportunities": [],
            },
        )
        buf = generate_strategy_docx(strategy)
        content = buf.read()
        assert content[:2] == b"PK"

    def test_returns_seeked_bytesio(self):
        """返回的 BytesIO 已 seek(0)"""
        strategy = _make_strategy()
        buf = generate_strategy_docx(strategy)
        assert buf.tell() == 0
