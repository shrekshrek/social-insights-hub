"""Channel-specific adapters for the analysis module.

各渠道（社媒/新闻/未来扩展）通过本目录下的 source 模块接入 analysis：
- 把渠道相关的数据查询、AnalysisJob 创建逻辑收拢在此
- analysis/service.py 与 router.py 不应直接 import 任何 src.{social,news}_media.* 内容
- 新增渠道时新建一个 sources/{channel}.py 文件即可

当前进度：
- sources/news.py: 已完成
- sources/social.py: 占位，待将 analysis/service.py 内的 social_media 依赖逐步迁入
"""
