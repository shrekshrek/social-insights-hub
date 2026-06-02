"""新闻逐篇轻量标注链

批量处理（5篇一组），对每篇新闻文章标注：
- relevance: 与研究目标的相关程度
- sentiment: 情感倾向
- article_type: 文章类型
- mentioned_entities: 提及的实体名单
- key_quotes: 关键引述
- summary: 一句话摘要
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm


NEWS_TAGGING_SYSTEM = """你是新闻分析助手，负责对新闻文章进行结构化标注。

## 研究目标
{analysis_goal}

## 研究主体
{subject}

## 研究主体的已知竞品
{competitors}

## 标注维度

1. **relevance**：与研究目标的相关程度
   - high：研究目标是文章核心讨论对象
   - medium：有涉及但非核心
   - low：仅顺带提及或不相关

2. **sentiment**：文章对研究目标的情感/立场（-2 到 2 整数）
   - 2：强烈正面（重大利好、高度肯定）
   - 1：轻度正面（一般性积极评价、温和利好）
   - 0：中性（客观陈述、无明显倾向）
   - -1：轻度负面（一般性批评、轻微风险提示）
   - -2：强烈负面（重大利空、严厉批评、丑闻危机）

3. **article_type**：文章类型
   - report：新闻报道（事实为主）
   - opinion：评论/观点文章
   - pr：公关稿/新闻通稿
   - analysis：深度分析/行业研究

4. **mentioned_entities**：文章中提及的实体
   - name：实体名称。**遇到「研究主体」或「已知竞品」的变体**（如 "绿米联创Aqara" / "aqara" / "Aqara Home" 都应归到 "Aqara"；"卧安机器人" / "switch bot" 都归到 "SwitchBot"），**必须统一使用上述研究主体/竞品列表中的规范名**
   - role：
     - `target`：name **严格等于** 研究主体 `{subject}`（规范名归一后）
     - `competitor`：按「研究主体的已知竞品」列表状态分两种模式
       - **显式列表模式**（列表非"（未指定）"）：role=competitor **严格限定**在列表内；列表之外的同品类品牌一律归 context（尊重用户显式意图）
       - **自动发现模式**（列表为"（未指定）"）：**由你自行识别** `{subject}` 的同品类或场景级竞争品牌，归 competitor（新闻报道本身会明示品牌关系网络，如 "A 与 B、C 等品牌竞争..."，按文章语境判断）
     - `context`：其他所有实体（行业名、场景、第三方平台等）
   - **硬规则**（两种模式共同遵守）：
     - 禁止根据文章提及频率或主角倾向判断 target——target 只能是 `{subject}`
     - 即使 `{subject}` 在文章中未出现，也不得把其他品牌标为 target
     - 若 `{subject}` 为空字符串，所有实体统一标为 context（独立监测场景无显式对比对象）

5. **key_quotes**：文章中的关键引述（直接引语）
   - speaker：发言人
   - quote：原文引述（不超过50字）
   - 无引述则返回空数组

6. **summary**：一句话摘要（不超过80字）

## 输出格式
返回JSON数组，每篇文章一个对象：
[{{"article_index": 0, "relevance": "high", "sentiment": 2, "article_type": "report", "mentioned_entities": [{{"name": "品牌A", "role": "target"}}], "key_quotes": [{{"speaker": "某高管", "quote": "..."}}], "summary": "..."}}, ...]

只输出JSON，无额外文本。"""


NEWS_TAGGING_USER = """请对以下 {article_count} 篇新闻文章进行标注：

{articles_content}

请以JSON数组格式返回结果（按文章顺序），每篇包含 article_index、relevance、sentiment、article_type、mentioned_entities、key_quotes、summary 字段。"""


def create_tagging_chain() -> Runnable:
    """创建新闻逐篇标注链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", NEWS_TAGGING_SYSTEM),
            ("user", NEWS_TAGGING_USER),
        ]
    )
    return prompt | llm


def format_articles_for_tagging(
    articles: list[dict], use_full_text: bool = False
) -> str:
    """格式化文章内容用于标注

    Args:
        articles: 文章列表，每个包含 title, source_name, snippet/full_text
        use_full_text: True 使用全文（collect），False 使用 snippet（probe）
    """
    parts: list[str] = []
    for i, article in enumerate(articles):
        content = article.get("full_text") if use_full_text else None
        if not content:
            content = article.get("snippet") or ""
        # 全文截断到 2000 字，避免超出 context
        if len(content) > 2000:
            content = content[:2000] + "..."

        parts.append(
            f"--- 文章 {i} ---\n"
            f"标题: {article.get('title', '')}\n"
            f"来源: {article.get('source_name', '')}\n"
            f"内容:\n{content}\n"
        )
    return "\n".join(parts)
