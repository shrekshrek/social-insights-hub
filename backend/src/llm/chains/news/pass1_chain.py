"""新闻 Slice 综合分析 — Pass 1：清洗归一抽取链

职责（"工人活"，结构化输出，下流给策略）：
- entities：变体合并 + role 校正（target/competitor/context）
- quotes：从原始 key_quotes 中精选 + speaker 分级（official/executive/analyst/kol/other）
- event_clusters：哪些 article_indices 讲的是同一事件

不做（这些归 Pass 2）：
- 事件命名（event_title）/ frame 文字
- briefing / 任何散文总结
- coverage 主观打分

设计要点：
- 输出 schema 严格，低温度，可重试
- 文章用 article_index（输入下标）引用，不用 article_id（让 LLM 数小数字而非长 ID）
- 后处理在 service 层把 article_index → article_id

详见 docs/adr/003-news-analysis-redesign.md。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm


NEWS_PASS1_SYSTEM = """你是新闻数据清洗员，从已标注的新闻文章中提取**结构化数据**——不写结论、不做解读。

## 研究目标
{analysis_goal}

## 研究主体
{subject}

## 研究主体的已知竞品
{competitors}

## 任务

只做三件事：实体归一 + 引述精选 + 事件聚类。

输出 JSON，无任何额外文字、无 markdown。

## 输出格式

{{
  "entities": [
    {{
      "name": "<规范化后的实体名>",
      "role": "<target | competitor | context>",
      "article_indices": [<int>, ...],
      "representative_article_indices": [<int>, ...]
    }}
  ],
  "quotes": [
    {{
      "speaker": "<发言人姓名/职务>",
      "speaker_role": "<official | executive | analyst | kol | other>",
      "quote": "<原文引述，≤50字>",
      "article_index": <int>,
      "context": "<1句话上下文，≤30字>"
    }}
  ],
  "event_clusters": [
    {{
      "article_indices": [<int>, ...]
    }}
  ]
}}

## entities 规则

**变体归一（必须）**：
- 同一实体的不同写法合并为一个条目（如 "绿米联创Aqara" / "aqara" / "Aqara Home" 全归 "Aqara"；
  "卧安机器人" / "switch bot" / "SwitchBot" 全归 "SwitchBot"；
  "国家市场监督管理总局" / "市场监管总局" 全归 "国家市场监督管理总局"）
- 遇到 `{subject}` / `{competitors}` 列表中的品牌变体，必须统一用列表中的规范名
- 同一规范名只输出一条 entity，article_indices 累加合并所有变体提及的文章

**role 归类（硬规则）**：
- 三种运行模式：
  1. **退化模式**：若 `{subject}` 为空字符串，所有实体一律 `role=context`
  2. **显式列表模式**（`{subject}` 非空 + `{competitors}` 非空且非"（未指定）"）：
     - name 严格等于 `{subject}` → `role=target`（即使 0 篇提及也要保留，article_indices=[]）
     - name ∈ `{competitors}` 列表 → `role=competitor`
     - 列表外所有实体（含同品类品牌）→ `role=context`（尊重用户显式意图）
  3. **自动发现模式**（`{subject}` 非空 + `{competitors}` 为空）：
     - name 等于 `{subject}` → `role=target`
     - 你自行判定的同品类/场景级竞争品牌 → `role=competitor`
     - 其他（行业名、平台、第三方、上下游）→ `role=context`
- **禁止**：根据提及频率把高频品牌当 target；显式模式下把列表外品牌标 competitor

**representative_article_indices**：
- 从 article_indices 中挑 3-5 个最具代表性的（优先 tier1 + 内容直接讨论该实体）
- 总文章 < 3 篇时，全部都是代表性的

**数量上限**：最多 15 个 entities，按 article_indices 长度降序。

## quotes 规则

**speaker_role 分级（必须区分）**：
- `official`：政府部委、监管机构、官媒社论作者、行业协会发声
- `executive`：公司高管（CEO / 总裁 / VP / 创始人 / 总监级）
- `analyst`：研究机构 / 行业分析师 / 学者 / 智库
- `kol`：自媒体作者 / 行业 KOL / 知名博主
- `other`：上述都不是（普通员工、消费者、匿名、不可识别）

**精选规则**：
- 不是把所有原始 quotes 都列出来，是挑最有信息密度的
- 优先级：`official` > `executive` > `analyst` > `kol` > `other`
- 同 speaker 多条引述只保留最有信息含量的一条
- 公关稿 (article_type=pr) 里的高管套话**不要选**

**字段约束**：
- `quote` 是原文，不是你的复述。≤50 字。如原文超过 50 字，截取最有力的一段，不要改写
- `context` 一句话说清"这是在什么场合说的"（如"4 月 15 日发布会致辞"/"接受财新采访时表示"），≤30 字
- `article_index` 必须是该 quote 所在文章在输入列表中的下标

**数量上限**：最多 8 条。若 official + executive + analyst 加起来不足 8 条，可以补 kol，但不要为凑数加 other。

## event_clusters 规则

**判定标准**：
- 多篇文章报道**同一事件**（同一时间、同一主体、同一动作/情况）→ 归一个 cluster
- 不同维度评论同一事件也算同一 cluster（首发报道 + 评论 + 后续跟进）
- 题目关键词相似但讲不同事的不要合并（"小米发布新车" 和 "小米发布新手机" 是两个事件）

**判断辅助信号**：
- published_at 时间相近（一般 ±7 天内）
- mentioned_entities 重合度高
- summary 描述同一事实

**数量约束**：
- 单篇文章不算事件——只有 article_indices.length ≥ 2 才输出
- 所有 cluster 的 article_indices 不重叠（一篇文章只属于一个事件）
- 没有跨文章重叠时输出空数组 `[]`

只输出 JSON。"""


NEWS_PASS1_USER = """以下是 {article_count} 篇已标注新闻文章（多个 task 合并 + URL 去重 + 过滤 low 后）：

{articles_content}

请按 system 中定义的 schema 输出 JSON。"""


def create_pass1_chain() -> Runnable:
    """创建 Slice Pass 1 清洗归一抽取链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", NEWS_PASS1_SYSTEM),
        ("user", NEWS_PASS1_USER),
    ])
    return prompt | llm


def format_articles_for_pass1(articles: list[dict]) -> str:
    """把已标注文章列表格式化为 Pass 1 输入文本。

    每篇文章塞精选字段（不塞 full_text，控制 input 体积）。
    article 应包含：title / source_name / source_tier / article_type /
    sentiment / published_at / summary / mentioned_entities / key_quotes。

    输出每篇约 200-400 token，slice 内典型 50-300 篇文章总输入 10-120K。
    """
    parts: list[str] = []
    for i, a in enumerate(articles):
        ents_raw = a.get("mentioned_entities") or []
        ents_str = ", ".join(
            f"{(e or {}).get('name', '')}({(e or {}).get('role', '')})"
            for e in ents_raw if (e or {}).get("name")
        )
        quotes_raw = a.get("key_quotes") or []
        quotes_str = " || ".join(
            f"{(q or {}).get('speaker', '')}: \"{(q or {}).get('quote', '')}\""
            for q in quotes_raw if (q or {}).get("quote")
        )
        parts.append(
            f"[{i}] {a.get('title', '')}\n"
            f"  来源: {a.get('source_name', '')} ({a.get('source_tier', 'tier3')})\n"
            f"  日期: {a.get('published_at', '未知')} | 类型: {a.get('article_type', '-')} | 情感: {a.get('sentiment', '-')}\n"
            f"  实体: {ents_str or '无'}\n"
            f"  引述: {quotes_str or '无'}\n"
            f"  摘要: {a.get('summary', '-')}\n"
        )
    return "\n".join(parts)
