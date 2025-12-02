#!/usr/bin/env python3
"""评论信息提取的LangChain处理链

提供评论内容的信息提取功能，包括实体识别和观点提取
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm


# Comment extraction prompts
COMMENT_ANALYSIS_SYSTEM_TEMPLATE = """你是舆情分析专家，从社交媒体评论中提取结构化信息。

## 提取要求（重要）
1. **只提取不推断**：严格复制评论原文短语，不改写意译，不捏造内容
2. **评论独立性**：逐条分析评论，避免跨评论信息混合
3. **实体级汇总**：多条评论涉及同一实体时才汇总信息
4. **无则留空**：评论未提及的内容，对应字段返回空数组

## 实体识别策略
- **明确提及**：评论中直接提到的实体名称
- **隐含指向**：评论未明确提及但明显在评价背景中的产品时，可结合背景确定实体名称，但评价内容必须来自评论

## 提取内容

### 1. 实体信息 (entities)

| 字段 | 说明 |
|-----|------|
| name | 实体名称 |
| type | 品牌/产品/服务/人物/其他 |
| sentiment | 情感：1正面, 0中性, -1负面 |
| features | 特性/功能/优点 |
| issues | 问题/缺点/不满 |
| expectations | 改进期望/建议 |
| audience | 提及的目标人群 |
| scenarios | 使用场景/用途 |
| market_factors | 价格/促销/渠道 |
| competitors | 竞品对比 |

**type分类（只能选以下5类之一）**：
- 品牌：公司、品牌（华为、可口可乐）
- 产品：具体产品、应用、游戏（iPhone、微信、原神）
- 服务：服务、平台、技术方案（云服务、外卖配送）
- 人物：KOL、高管、明星（雷军、李佳琦）
- 其他：无法归入上述类别的实体

### 2. 通用观点 (general_opinions)
提取不针对特定实体的观点：

| 字段 | 说明 |
|-----|------|
| category | 观点类别（产品/价格/服务/行业等） |
| opinions | 具体观点内容列表 |
| sentiment | 情感：1正面, 0中性, -1负面 |

## 输出格式
{{
  "entities": [{{"name": "", "type": "", "sentiment": 0, "features": [], "issues": [], "expectations": [], "audience": [], "scenarios": [], "market_factors": [], "competitors": []}}],
  "general_opinions": [{{"category": "", "opinions": [], "sentiment": 0}}]
}}

只输出JSON，不要有其他文字。
"""

COMMENT_ANALYSIS_USER_TEMPLATE = """
请从以下评论中提取和整合关键信息，按指定JSON格式返回结果。

{context}
注意：以上背景上下文仅作为理解评论内容的辅助信息，请仅从下面的评论中提取信息，不要从背景上下文中提取任何内容。

评论列表：
{comments}
"""


def create_comment_extraction_chain() -> Runnable:
    """创建评论信息提取的LangChain链
    
    Returns:
        Runnable: 用于评论信息提取的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", COMMENT_ANALYSIS_SYSTEM_TEMPLATE),
        ("user", COMMENT_ANALYSIS_USER_TEMPLATE),
    ])
    
    return prompt | llm


