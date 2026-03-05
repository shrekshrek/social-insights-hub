"""Strategy Word Export 单元测试"""

from io import BytesIO
from unittest.mock import MagicMock

from src.strategies.export_docx import generate_strategy_docx


def _make_strategy(
    name: str = "测试策略",
    phase1: dict | None = None,
    phase2: dict | None = None,
    phase3: dict | None = None,
) -> MagicMock:
    strategy = MagicMock()
    strategy.name = name
    strategy.phase1_result = phase1
    strategy.phase2_result = phase2
    strategy.phase3_result = phase3
    return strategy


class TestGenerateStrategyDocx:
    def test_empty_phases(self):
        """所有 phase 为空时不报错，返回有效 docx"""
        strategy = _make_strategy()
        buf = generate_strategy_docx(strategy)
        assert isinstance(buf, BytesIO)
        # DOCX (ZIP) 文件开头为 PK 签名
        content = buf.read()
        assert content[:2] == b"PK"

    def test_full_phases(self):
        """三个阶段都有数据时正常生成"""
        strategy = _make_strategy(
            phase1={
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
            phase2={
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
            phase3={
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

    def test_partial_phases(self):
        """只有 Phase 1 有数据"""
        strategy = _make_strategy(
            phase1={
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
