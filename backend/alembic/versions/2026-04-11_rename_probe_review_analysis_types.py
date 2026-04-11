"""rename_probe_review_analysis_types

将 AnalysisJob.analysis_type 中的旧值 `strategy_probe_review` 按渠道拆分为：
- `strategy_social_probe_review`（社媒探测审查）
- `strategy_news_probe_review`（新闻探测审查）

判定依据：`analysis_config->>'channel' = 'news'` 的记录归属新闻通道，其余归社媒。
新值与 chain 命名（`strategy_social_probe_review_chain` / `strategy_news_probe_review_chain`）
及其他策略枚举（`strategy_coverage_check` / `strategy_phase*` / `strategy_market_report_*`）
保持 `strategy_` 前缀一致。历史 service.py 曾在新闻 callsite 误用 STRATEGY_PROBE_REVIEW，
本次迁移一并修复。

同时合并旧的 `230d35bb79d5`（rename news_tasks created_by）分支 head 到
`d4e5f6a1b2c3`（strategy_market_report_results），消除多 head 状态。

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3, 230d35bb79d5
Create Date: 2026-04-11

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a1b2c3d4"
down_revision: Union[str, tuple[str, ...], None] = ("d4e5f6a1b2c3", "230d35bb79d5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 先处理新闻渠道：analysis_config.channel = 'news'
    op.execute(
        """
        UPDATE analysis_jobs
           SET analysis_type = 'strategy_news_probe_review'
         WHERE analysis_type = 'strategy_probe_review'
           AND analysis_config IS NOT NULL
           AND (analysis_config::jsonb ->> 'channel') = 'news'
        """
    )

    # 剩余的都归社媒
    op.execute(
        """
        UPDATE analysis_jobs
           SET analysis_type = 'strategy_social_probe_review'
         WHERE analysis_type = 'strategy_probe_review'
        """
    )


def downgrade() -> None:
    # 两类都回滚为旧值
    op.execute(
        """
        UPDATE analysis_jobs
           SET analysis_type = 'strategy_probe_review'
         WHERE analysis_type IN ('strategy_social_probe_review', 'strategy_news_probe_review')
        """
    )
