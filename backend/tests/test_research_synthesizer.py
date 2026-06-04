"""Research Agent synthesizer 节点单元测试

回归测试:确保当 `selected=[]` 但 `findings` 已跨轮累积时,不走空返回分支,
避免丢弃已完成的分析结果(见 2026-04-20 发现的边界 bug,Task 38 复现)。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.research_agent.nodes.synthesizer import (
    _build_coverage,
    _coerce_findings_dict,
    synthesize_node,
)


def _make_state(
    selected: list, findings: list, questions: list[str] | None = None
) -> dict:
    return {
        "query": "乐虎功能饮料市场研究",
        "research_questions": questions
        or [
            "乐虎在功能饮料市场的份额是多少?",
            "年轻消费者对乐虎的品牌认知如何?",
        ],
        "profile_name": "industry",
        "selected": selected,
        "findings": findings,
        "documents": [],
        "token_usage_records": [],
    }


def _make_finding(src_title: str, url: str) -> dict:
    return {
        "source_title": src_title,
        "source_url": url,
        "source_tier": "tier2",
        "key_points": ["核心观点 1", "核心观点 2"],
        "data_points": [
            {"metric": "市场份额", "value": "25%", "period": "2023"},
        ],
        "relevance_to_questions": {
            "乐虎在功能饮料市场的份额是多少?": "根据报告,乐虎份额为 25%",
        },
    }


class TestSynthesizerEmptyBranch:
    """验证空返回分支的正确触发条件"""

    def test_both_empty_triggers_empty_response(self):
        """selected 和 findings 都空 → 正常走空返回"""
        state = _make_state(selected=[], findings=[])
        result = synthesize_node(state)

        assert (
            "未找到相关数据"
            in result["findings_by_question"]["乐虎在功能饮料市场的份额是多少?"][
                "answer_summary"
            ]
        )
        # 未调用 LLM,空返回不应产生 token 记录
        assert "token_usage_records" not in result

    def test_findings_populated_but_selected_empty_should_NOT_early_return(self):
        """
        关键回归测试:Task 38 的场景。
        findings 已跨轮累积,但最后一轮 selected 被 filter 跨轮去重清空。
        修复前 → 走空返回,丢弃 10 篇分析结果。
        修复后 → 使用 findings 综合,不走空返回分支。
        """
        findings = [
            _make_finding("东鹏特饮行业报告", "https://example.com/1"),
            _make_finding("功能饮料市场白皮书", "https://example.com/2"),
        ]
        state = _make_state(selected=[], findings=findings)

        # Mock ChatDeepSeek 避免真实 LLM 调用
        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "findings_by_question": {
                    "乐虎在功能饮料市场的份额是多少?": {
                        "answer_summary": "乐虎在功能饮料市场份额约 25%",
                        "confidence": "high",
                        "data_points": [{"metric": "市场份额", "value": "25%"}],
                        "source_refs": ["src_0"],
                    },
                    "年轻消费者对乐虎的品牌认知如何?": {
                        "answer_summary": "年轻消费者认知较弱",
                        "confidence": "medium",
                        "data_points": [],
                        "source_refs": ["src_1"],
                    },
                },
                "synthesis": "# 乐虎研究\n\n综合分析...",
                "information_gaps": [],
            }
        )
        mock_response.usage_metadata = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "total_tokens": 1500,
        }

        with patch("src.research_agent.nodes.synthesizer.ChatDeepSeek") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_response
            mock_llm_cls.return_value = mock_llm

            result = synthesize_node(state)

            # 关键断言:LLM 被调用(说明未走空返回)
            mock_llm.invoke.assert_called_once()

            # 发送给 LLM 的 prompt 应含 findings 内容
            call_args = mock_llm.invoke.call_args[0][0]
            human_msg = call_args[1]
            assert "东鹏特饮行业报告" in human_msg.content
            assert "功能饮料市场白皮书" in human_msg.content

        # 产出应有实质内容,不是"未找到"
        findings_by_q = result["findings_by_question"]
        assert (
            "未找到相关数据"
            not in findings_by_q["乐虎在功能饮料市场的份额是多少?"]["answer_summary"]
        )
        assert findings_by_q["乐虎在功能饮料市场的份额是多少?"]["confidence"] == "high"

    def test_selected_populated_but_findings_empty_uses_snippets(self):
        """Phase 1 场景:selected 有卡片但无 findings → 走 snippets fallback"""
        selected = [
            {
                "title": "市场报告",
                "url": "https://example.com/1",
                "snippet": "功能饮料市场规模 600 亿...",
                "source_tier": "tier2",
            },
        ]
        state = _make_state(selected=selected, findings=[])

        mock_response = MagicMock()
        mock_response.content = json.dumps(
            {
                "findings_by_question": {
                    "乐虎在功能饮料市场的份额是多少?": {
                        "answer_summary": "见综合报告",
                        "confidence": "medium",
                        "data_points": [],
                        "source_refs": ["src_0"],
                    },
                },
                "synthesis": "基于 snippets 的综合",
                "information_gaps": [],
            }
        )
        mock_response.usage_metadata = {
            "input_tokens": 500,
            "output_tokens": 200,
            "total_tokens": 700,
        }

        with patch("src.research_agent.nodes.synthesizer.ChatDeepSeek") as mock_llm_cls:
            mock_llm = MagicMock()
            mock_llm.invoke.return_value = mock_response
            mock_llm_cls.return_value = mock_llm

            result = synthesize_node(state)
            mock_llm.invoke.assert_called_once()

            # Prompt 应包含 snippet
            call_args = mock_llm.invoke.call_args[0][0]
            human_msg = call_args[1]
            assert "功能饮料市场规模 600 亿" in human_msg.content

        assert "synthesis" in result


class TestCoerceFindingsDict:
    """LLM 把 findings_by_question 输出成任意畸形类型时都规整为 dict（防 .values() 崩）。"""

    @pytest.mark.parametrize(
        "value, expected_keys",
        [
            ({"rq1": {"confidence": "high"}}, {"rq1"}),  # dict 原样
            # list → dict：有 question 用 question，缺失用 q{i}
            (
                [{"question": "rq1", "confidence": "high"}, {"confidence": "low"}],
                {"rq1", "q1"},
            ),
            (None, set()),  # 显式 null（曾导致 _build_coverage 的 .values() 崩）
            ("oops", set()),  # 标量字符串
            (123, set()),  # 标量数字
        ],
    )
    def test_coerce_returns_dict(self, value, expected_keys):
        result = _coerce_findings_dict(value)
        assert isinstance(result, dict)
        assert set(result.keys()) == expected_keys

    def test_build_coverage_on_coerced_list(self):
        """list 规整后进 _build_coverage 不再崩，统计正确。"""
        findings = _coerce_findings_dict(
            [
                {"question": "rq1", "confidence": "high"},
                {"question": "rq2", "confidence": "low"},
            ]
        )
        coverage = _build_coverage(findings, selected=[])
        assert coverage["questions_total"] == 2
        assert coverage["high_confidence_count"] == 1  # 仅 rq1
        assert coverage["questions_covered"] == 1  # high 计入；low 不计
