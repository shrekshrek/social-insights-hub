#!/usr/bin/env python3
"""帖子信息提取的LangChain处理链

提供帖子内容的信息提取功能，包括实体识别、观点提取和内容总结
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm


# Post extraction prompts
POST_EXTRACTION_SYSTEM_TEMPLATE = """你是舆情分析专家，从社交媒体内容中提取结构化信息。

## 提取要求（重要）
1. **只提取不推断**：严格复制原文短语，不改写意译，不捏造内容
2. **完整表达**：提取有意义的完整短语，不断章取义
3. **无则留空**：原文未提及的内容，对应字段返回空数组
4. **避免重复**：不同字段间不要提取重复内容

## 提取内容

### 1. 实体信息 (entities)
识别原文提及的品牌、产品、服务、人物等实体：

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

### 3. 内容总结 (summary)
20-100字客观概括原文主旨，不添加个人见解

## 输出格式
{{
  "entities": [{{"name": "", "type": "", "sentiment": 0, "features": [], "issues": [], "expectations": [], "audience": [], "scenarios": [], "market_factors": [], "competitors": []}}],
  "general_opinions": [{{"category": "", "opinions": [], "sentiment": 0}}],
  "summary": ""
}}

只输出JSON，不要有其他文字。
"""

POST_EXTRACTION_USER_TEMPLATE = """请提取以下文本的品牌/产品信息和通用观点，并生成总结：

{content}
"""


def create_post_extraction_chain() -> Runnable:
    """创建帖子信息提取的LangChain链
    
    Returns:
        Runnable: 用于帖子信息提取的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", POST_EXTRACTION_SYSTEM_TEMPLATE),
        ("user", POST_EXTRACTION_USER_TEMPLATE),
    ])
    
    # 在新项目中，我们推荐使用 with_structured_output (LangChain > 0.1)
    # 或者直接在调用处解析JSON（保持与screening_tasks一致的模式）
    # 这里我们返回 runnables 以供 task 中使用
    
    return prompt | llm



