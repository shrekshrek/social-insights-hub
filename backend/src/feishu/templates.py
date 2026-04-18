"""飞书消息卡片模板

每个函数返回一个交互式卡片 dict，可直接作为 IM API 的 content。
"""

from src.config import settings


def _build_card(
    title: str,
    content: str,
    color: str = "blue",
    strategy_id: int | None = None,
) -> dict:
    """组装飞书交互卡片。

    Args:
        title:       卡片标题
        content:     卡片正文（支持 lark_md 语法）
        color:       标题栏颜色，支持 blue / green / yellow / red / grey
        strategy_id: 策略 ID，有值时在卡片底部追加「查看策略」按钮
    """
    elements: list[dict] = [
        {"tag": "div", "text": {"tag": "lark_md", "content": content}},
    ]

    if strategy_id and settings.FEISHU_FRONTEND_URL:
        url = f"{settings.FEISHU_FRONTEND_URL.rstrip('/')}/strategies/{strategy_id}"
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看策略"},
                    "type": "primary",
                    "url": url,
                }
            ],
        })

    return {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": color,
        },
        "elements": elements,
    }


# ---------------------------------------------------------------------------
# 探测阶段
# ---------------------------------------------------------------------------

def probe_needs_review_card(
    strategy_name: str,
    strategy_id: int,
    overall_verdict: str,
) -> dict:
    """探测审查结果为 partial_pass / fail 时的通知卡片。"""
    if overall_verdict == "partial_pass":
        return _build_card(
            title="⚠️ 探测审查：部分通过",
            content=(
                f"**策略：** {strategy_name}\n"
                "部分探测任务数据质量不足，请人工核查后手动确认探测或调整关键词"
            ),
            color="yellow",
            strategy_id=strategy_id,
        )
    return _build_card(
        title="❌ 探测审查：未通过",
        content=(
            f"**策略：** {strategy_name}\n"
            "探测数据质量不足，请调整关键词后重新探测"
        ),
        color="red",
        strategy_id=strategy_id,
    )


def data_ready_card(
    strategy_name: str,
    strategy_id: int,
    slice_count: int,
) -> dict:
    """切片创建完成、覆盖度验证通过，策略进入 ready 状态。"""
    return _build_card(
        title="✅ 数据已就绪",
        content=(
            f"**策略：** {strategy_name}\n"
            f"**分析切片：** {slice_count} 个\n"
            "可以开始生成策略产出"
        ),
        color="green",
        strategy_id=strategy_id,
    )


# ---------------------------------------------------------------------------
# 产出生成阶段（brand_strategy 路径）
# ---------------------------------------------------------------------------

def big_idea_done_card(strategy_name: str, strategy_id: int) -> dict:
    return _build_card(
        title="🎉 策略研究完成（Brand Strategy）",
        content=f"**策略：** {strategy_name}\nBig Idea 已生成，品牌策略研究全部完成",
        color="green",
        strategy_id=strategy_id,
    )


# ---------------------------------------------------------------------------
# 产出生成阶段（market_report 路径）
# ---------------------------------------------------------------------------

def strategic_brief_done_card(strategy_name: str, strategy_id: int) -> dict:
    return _build_card(
        title="🎉 策略研究完成（Market Report）",
        content=f"**策略：** {strategy_name}\n战略简报（Strategic Brief）已生成，市场报告研究全部完成",
        color="green",
        strategy_id=strategy_id,
    )
