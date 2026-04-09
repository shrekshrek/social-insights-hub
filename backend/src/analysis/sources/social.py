"""Social media source adapter for the analysis module.

⚠️ TODO: 占位文件。analysis/service.py 当前仍直接 import 大量 src.social_media.*
内容（约 16 处），目标是逐步把这些查询/聚合 helper 迁移到本文件，让
analysis/service.py 不再直接 import social_media。

迁移优先级（建议在后续清理 PR 中处理）：
- get_posts_for_screening / get_post_for_deep_analysis 类查询
- screening / deep / aggregation 各 stage 内的 SocialPost / SocialTask 形态依赖
- analysis/router.py:522,550 的 monitor 访问校验

新增功能时请优先放在本文件，避免再向 analysis/service.py 增加 social_media 耦合。
"""
