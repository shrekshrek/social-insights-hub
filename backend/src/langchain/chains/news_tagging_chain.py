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

from src.langchain.llm import get_llm


NEWS_TAGGING_SYSTEM = """你是新闻分析助手，负责对新闻文章进行结构化标注。

## 研究目标
{analysis_goal}

## 标注维度

1. **relevance**：与研究目标的相关程度
   - high：研究目标是文章核心讨论对象
   - medium：有涉及但非核心
   - low：仅顺带提及或不相关

2. **sentiment**：文章对研究目标的情感/立场
   - 1：正面（积极评价、利好报道）
   - 0：中性（客观陈述）
   - -1：负面（批评、风险、利空报道）

3. **article_type**：文章类型
   - report：新闻报道（事实为主）
   - opinion：评论/观点文章
   - pr：公关稿/新闻通稿
   - analysis：深度分析/行业研究

4. **mentioned_entities**：文章中提及的实体
   - name：实体名称
   - role：target（研究目标）/ competitor（竞品）/ context（背景相关）

5. **key_quotes**：文章中的关键引述（直接引语）
   - speaker：发言人
   - quote：原文引述（不超过50字）
   - 无引述则返回空数组

6. **summary**：一句话摘要（不超过80字）

## 输出格式
返回JSON数组，每篇文章一个对象：
[{{"article_index": 0, "relevance": "high", "sentiment": 1, "article_type": "report", "mentioned_entities": [{{"name": "品牌A", "role": "target"}}], "key_quotes": [{{"speaker": "某高管", "quote": "..."}}], "summary": "..."}}, ...]

只输出JSON，无额外文本。"""


NEWS_TAGGING_USER = """请对以下 {article_count} 篇新闻文章进行标注：

{articles_content}

请以JSON数组格式返回结果（按文章顺序），每篇包含 article_index、relevance、sentiment、article_type、mentioned_entities、key_quotes、summary 字段。"""


def create_news_tagging_chain() -> Runnable:
    """创建新闻逐篇标注链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", NEWS_TAGGING_SYSTEM),
        ("user", NEWS_TAGGING_USER),
    ])
    return prompt | llm


def format_articles_for_tagging(articles: list[dict], use_full_text: bool = False) -> str:
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
