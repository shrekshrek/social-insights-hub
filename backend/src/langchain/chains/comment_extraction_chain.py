#!/usr/bin/env python3
"""评论信息提取的LangChain处理链

提供评论内容的信息提取功能，包括实体识别和观点提取
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm


# Comment extraction prompts - keep original templates unchanged
COMMENT_ANALYSIS_SYSTEM_TEMPLATE = """
你是评论信息提取专家。逐条分析评论，提取结构化信息并整合，保持评论间信息隔离。

## 提取范围

**实体识别策略**：
- **明确提及**：评论中直接提到的实体名称
- **隐含指向**：评论未明确提及品牌，但明显在评价背景上下文中的产品时，可结合背景确定实体名称，但评价内容必须来自评论

## 提取维度：

1. **实体信息**：逐条评论分析，识别其中涉及的实体
    * 要点：
      - 逐条独立分析每条评论，避免跨评论信息混合
      - 只有当多条评论都涉及同一实体时，才汇总该实体的信息
      - 如果评论未涉及任何实体，不强制归属
    * 类型分类指导（**必须严格遵守，只能选择以下4种类型之一**）：
      - **品牌**：公司名称、品牌名称（如：苹果、华为、可口可乐）
      - **商品**：具体产品、游戏、应用、角色、物品（如：iPhone、鸣潮、相里要、游戏角色）
      - **服务**：提供的服务、技术方案、平台服务、技术概念（如：云服务、在线教育、配送服务、D2M技术）
      - **其他**：实在无法归入上述三类的实体（如：抽象概念、地点、时间等）
    * 字段：
      * **name:** 实体名称（明确提及的用评论中的名称，隐含指向的用背景中的名称）
      * **type:** "品牌"、"商品"、"服务" 或 "其他"
      * **sentiment:** 对该实体的整体情感倾向 (1=正面, 0=中性, -1=负面)
      * **features:** 实体特性/功能/亮点
      * **issues:** 当前存在的问题/缺点
      * **expectations:** 用户改进期望/建议
      * **audience:** 目标人群/用户类型
      * **scenarios:** 使用场景/用途
      * **market_factors:** 价格/促销/销售渠道
      * **competitors:** 与其他实体比较

2. **通用观点信息**：提取不针对特定实体的观点和见解
    * 要点：
      - 评论中明确表达但不针对任何具体实体的观点
      - 按观点类别分类整理
      - 如果找不到符合条件的通用观点信息，应返回空列表
    * 字段：
      * **category:** 观点类别（如："产品", "价格", "服务", "行业"等）
      * **opinions:** 具体观点内容列表，不针对特定实体
      * **sentiment:** 该类别观点的整体情感倾向 (1=正面, 0=中性, -1=负面)

## 提取要求：

1. 评论独立性：逐条分析评论，避免将不同评论的信息错误混合
2. 实体级汇总：仅当多条评论涉及同一实体时才汇总信息
3. 信息来源清晰：评价内容必须来自评论，实体名称可结合背景确定
4. 完整短语：提取有意义的完整表达，不断章取义

## 输出格式：
{{
  "entities": [
    {{
      "name": "string",
      "type": "品牌|商品|服务|其他",
      "sentiment": 1|0|-1,
      "features": ["string"],
      "issues": ["string"],
      "expectations": ["string"],
      "audience": ["string"],
      "scenarios": ["string"],
      "market_factors": ["string"],
      "competitors": ["string"]
    }}
  ],
  "general_opinions": [
    {{
      "category": "string",
      "opinions": ["string"],
      "sentiment": 1|0|-1
    }}
  ]
}}

只输出JSON格式，不要额外文本。

**重要约束**：
- type字段必须且只能是："品牌"、"商品"、"服务"、"其他"中的一个
- 当不确定归类时，优先选择"其他"
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

