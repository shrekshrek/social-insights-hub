#!/usr/bin/env python3
"""帖子信息提取的LangChain处理链

提供帖子内容的信息提取功能，包括实体识别、观点提取和内容总结
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm


# Post extraction prompts - keep original templates unchanged
POST_EXTRACTION_SYSTEM_TEMPLATE = """
你是信息提取专家。提取文本中的结构化信息，不要分析或推断。

## 提取内容：

1. **实体信息**：识别文本中提及的实体，并提取相关属性
   * 要点：
     - 必须是原文中明确提及的实体信息
     - 如果找不到符合条件的实体信息，应返回空列表
   * 类型分类指导（**必须严格遵守，只能选择以下4种类型之一**）：
     - **品牌**：公司名称、品牌名称（如：苹果、华为、可口可乐）
     - **商品**：具体产品、游戏、应用、角色、物品（如：iPhone、鸣潮、相里要、游戏角色）
     - **服务**：提供的服务、技术方案、平台服务、技术概念（如：云服务、在线教育、配送服务、D2M技术）
     - **其他**：实在无法归入上述三类的实体（如：抽象概念、地点、时间等）
   * 字段：
     * **name:** 实体名称
     * **type:** "品牌"、"商品"、"服务" 或 "其他"
     * **sentiment:** 情感倾向 (1=正面, 0=中性, -1=负面)
     * **features:** 实体特性/功能/优点
     * **issues:** 当前存在的问题/缺点
     * **expectations:** 用户改进期望/建议
     * **audience:** 目标人群/用户类型
     * **scenarios:** 使用场景/用途
     * **market_factors:** 价格/促销/销售渠道
     * **competitors:** 与其他实体比较

2. **通用观点信息**：提取与特定实体无关的观点和见解
   * 要点：
     - 必须是原文中明确表达的观点、意见、建议等
     - 按观点类别分类整理
     - 如果找不到符合条件的通用观点信息，应返回空列表
   * 字段：
     * **category:** 观点类别(如"产品"、"价格"、"服务"、"行业"等)
     * **opinions:** 具体观点内容列表，不针对特定实体
     * **sentiment:** 该类别观点的整体情感倾向 (1=正面, 0=中性, -1=负面)

3. **内容总结**：用100-200字对原文内容进行简明扼要的总结

## 提取要求：
1. 只提取不分析：严格复制原文短语，不改写意译
2. 完整短语：提取有意义的完整表达，不断章取义
3. 避免重复：不同字段间避免提取重复内容
4. 总结客观：总结应当客观反映原文内容，不添加个人见解

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
  ],
  "summary": "string"
}}

只输出JSON格式，不要额外文本。

**重要约束**：
- type字段必须且只能是："品牌"、"商品"、"服务"、"其他"中的一个
- 当不确定归类时，优先选择"其他"
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



