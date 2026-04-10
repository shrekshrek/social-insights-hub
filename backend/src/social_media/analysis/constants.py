"""Analysis module shared constants."""

# spam_score >= SPAM_HIGH_THRESHOLD 的原文归入高广告（推广）组，否则归入低广告（有机）组。
# 适用于：任务级聚合、项目级切片、原文筛选查询。
SPAM_HIGH_THRESHOLD: float = 6.0

# 发送给 LLM 做聚类/归纳的术语（原话、特征词）条数上限。
TOP_TERMS_FOR_LLM: int = 160

# 每个实体/观点保留的 (task_id, post_id) 样本数量（用于前端溯源）。
MAX_POST_IDS_SAMPLE: int = 50

# original_terms 列表截断长度（每个实体/观点最多保留 N 条原话）。
ORIGINAL_TERMS_MAX: int = 20

# 单条原话文本的最大字符长度（超长截断，防止 token/内存膨胀）。
ORIGINAL_TERM_MAX_LEN: int = 100

# 实体×维度矩阵中，单元格的最小提及数（低于此值的单元格不展示）。
MIN_CELL_MENTIONS: int = 5
