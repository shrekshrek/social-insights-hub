#!/usr/bin/env python3
"""
Path B 实验:LLM-native 一把梭 insight 分析

对照 Path A(现有 pipeline)的产出,验证 LLM-native 一次性分析在策略研究场景
是否能以更低成本产出更好的 insight。

## 使用方法

1. 确保 Docker 服务已启动:`docker-compose up -d`(postgres 暴露在 localhost:5432)
2. 设置环境变量:`export DEEPSEEK_API_KEY=sk-xxx`
3. 修改下方的 `STRATEGY_ID / SOCIAL_MONITOR_ID / NEWS_MONITOR_ID` 为目标策略
4. 运行:`python3 run_path_b_insight.py`

## 输出

- `/tmp/path_b_experiment/path_b_insight.json`: 模型产出的 insight JSON
- `/tmp/path_b_experiment/path_b_response_full.json`: DeepSeek 完整 response(含 usage)
- `/tmp/path_b_experiment/path_b_prompt_user.txt`: 发送的 user prompt(便于复查)

## 如何对比 Path A

对照 Path A 产出的 SQL:
    SELECT insight_result FROM strategies WHERE id = <STRATEGY_ID>;

## 参考

详见 [docs/experiments/path-b-insight-comparison.md](../../docs/experiments/path-b-insight-comparison.md)
"""
import json
import os
import sys
from urllib import request as urllib_request

import psycopg

DB_URL = "host=localhost port=5432 dbname=crawler_db user=postgres password=postgres"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    print("ERROR: set DEEPSEEK_API_KEY env var", file=sys.stderr)
    sys.exit(1)

# === 实验参数(按需修改) ===
STRATEGY_ID = 18            # 目标策略 ID
SOCIAL_MONITOR_ID = 44      # 对应的社媒 monitor_id
NEWS_MONITOR_ID = 4         # 对应的新闻 monitor_id
POSTS_PER_PLATFORM = 40     # 每平台采样 Top N 帖
COMMENTS_PER_POST = 8       # 每帖采样 Top N 评论
CONTENT_MAX_CHARS = 400     # 帖正文截断长度
COMMENT_MAX_CHARS = 80      # 评论截断长度


def fetch_brand_brief(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT brand_brief FROM strategies WHERE id = %s", (STRATEGY_ID,))
        (brief,) = cur.fetchone()
        return brief


def fetch_sampled_posts(conn):
    """每平台按互动量取 top N"""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT
                    sp.id, sp.title, sp.content, sp.author_name,
                    sp.likes_count, sp.comments_count,
                    p.name AS platform,
                    ROW_NUMBER() OVER (
                        PARTITION BY sp.platform_id
                        ORDER BY (sp.likes_count + sp.comments_count*2) DESC
                    ) AS rn
                FROM social_posts sp
                JOIN social_tasks st ON sp.task_id = st.id
                JOIN platforms p ON sp.platform_id = p.id
                WHERE st.monitor_id = %s AND sp.is_deleted = false
            )
            SELECT id, title, content, author_name, likes_count, comments_count, platform
            FROM ranked WHERE rn <= %s
            ORDER BY platform, rn
            """,
            (SOCIAL_MONITOR_ID, POSTS_PER_PLATFORM),
        )
        return cur.fetchall()


def fetch_top_comments(conn, post_ids):
    """为采样帖子取 top N 评论(按赞数)"""
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT post_id, content, author_name, likes_count,
                    ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY likes_count DESC) AS rn
                FROM social_comments
                WHERE post_id = ANY(%s) AND content IS NOT NULL AND LENGTH(content) > 3
            )
            SELECT post_id, content, author_name, likes_count
            FROM ranked WHERE rn <= %s
            ORDER BY post_id, rn
            """,
            (list(post_ids), COMMENTS_PER_POST),
        )
        rows = cur.fetchall()
    by_post: dict[int, list] = {}
    for pid, content, author, likes in rows:
        by_post.setdefault(pid, []).append((content, author, likes))
    return by_post


def fetch_news(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT na.title, na.snippet, na.source_name, na.source_tier, na.published_at
            FROM news_articles na
            JOIN news_tasks nt ON na.task_id = nt.id
            WHERE nt.monitor_id = %s
            ORDER BY na.published_at DESC NULLS LAST
            """,
            (NEWS_MONITOR_ID,),
        )
        return cur.fetchall()


def truncate(text: str | None, n: int) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text[:n] + ("…" if len(text) > n else "")


def build_corpus(posts, comments_by_post, news):
    lines = ["# 社交媒体原始数据样本\n"]
    platform_groups: dict[str, list] = {}
    for row in posts:
        pid, title, content, author, likes, comments_n, platform = row
        platform_groups.setdefault(platform, []).append(row)

    for platform, rows in platform_groups.items():
        lines.append(f"\n## 平台:{platform}(按互动量 Top {len(rows)})\n")
        for row in rows:
            pid, title, content, author, likes, comments_n, _ = row
            lines.append(
                f"\n### [post_id={pid}] {truncate(title, 50)}\n"
                f"- 作者: {author or '未知'} | 赞: {likes} | 评论: {comments_n}\n"
                f"- 正文: {truncate(content, CONTENT_MAX_CHARS)}\n"
            )
            cmts = comments_by_post.get(pid, [])
            if cmts:
                lines.append("- 热评:")
                for cc, ca, cl in cmts:
                    lines.append(f"  - [{cl}赞] {truncate(cc, COMMENT_MAX_CHARS)}")
                lines.append("")

    lines.append("\n# 新闻媒体原始数据\n")
    for title, snippet, src, tier, pub in news:
        lines.append(
            f"- **[{tier}] {src}** ({pub.strftime('%Y-%m-%d') if pub else 'N/A'}): "
            f"{truncate(title, 80)} — {truncate(snippet, 200)}"
        )

    return "\n".join(lines)


SYSTEM_PROMPT = """你是一位资深社交媒体策略分析师,擅长从原始数据中挖掘深层洞察。

## 任务
基于提供的社媒帖+评论+新闻原始数据,完成两项工作:

1. **Social Tension(社会矛盾)**: 识别消费者在该品类/话题上的核心矛盾、痛点或未被满足的需求
2. **Brand Opportunity(品牌机会)**: 基于 Tension 和竞品格局,找到品牌可切入的差异化机会

## 洞察质量标准(重要)

**核心要求: 输出不能是"认真浏览一遍内容就能得出"的结论。**

优先挖掘以下类型:
1. **反常信号**: 热度高但情感负向、热度低但情感极正向、同一实体在不同语境下情感反转
2. **跨数据源交叉洞察**: 只有对比社媒 vs 新闻 vs 不同平台才能发现的模式,至少 1 条 Tension 必须满足
3. **常识颠覆**: 每条结论须明确说明它如何修正行业通常认知,不接受"用户关注健康"此类任何人都能猜到的结论

## 证据要求
- 每条结论必须附带数据论据(evidence),标明来源(post_id / 新闻来源)
- 直接引用用户原话或新闻报道原文最有力
- evidence 至少 2 条

## 输出格式

严格按以下 JSON 结构输出(不要有 markdown 代码块标记):

{
  "social_tensions": [
    {
      "statement": "矛盾陈述",
      "conventional_wisdom": "行业常识",
      "data_reality": "数据反驳",
      "evidence": [
        {"type": "用户原话/媒体叙事/跨源对比", "description": "具体描述", "source": "post_id=xxx / 新闻来源"}
      ],
      "confidence": "high|medium|low"
    }
  ],
  "brand_opportunities": [
    {
      "statement": "机会陈述",
      "rationale": "基于哪些 tension + 竞品空白",
      "evidence": [
        {"type": "类型", "description": "描述", "source": "来源"}
      ],
      "confidence": "high|medium|low"
    }
  ]
}

至少 3 条 tensions + 3 条 opportunities。"""


def build_user_prompt(brief: dict, corpus: str) -> str:
    subject = brief.get("subject", "")
    goal = brief.get("analysis_goal", "")
    constraints = brief.get("constraints", "")

    return f"""# 品牌 Brief

**研究主体**: {subject}
**研究目标**: {goal}
**约束/背景**: {constraints}

---

{corpus}

---

请基于以上 Brief + 原始数据,按系统提示的要求产出 social_tensions + brand_opportunities 的 JSON。"""


def call_deepseek(system: str, user: str) -> dict:
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }
    req = urllib_request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib_request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    conn = psycopg.connect(DB_URL)
    try:
        brief = fetch_brand_brief(conn)
        posts = fetch_sampled_posts(conn)
        post_ids = [r[0] for r in posts]
        comments_by_post = fetch_top_comments(conn, post_ids)
        news = fetch_news(conn)

        print(f"[data] sampled {len(posts)} posts across platforms")
        print(f"[data] fetched {sum(len(v) for v in comments_by_post.values())} comments")
        print(f"[data] {len(news)} news articles")

        corpus = build_corpus(posts, comments_by_post, news)
        print(f"[corpus] {len(corpus)} chars")

        user = build_user_prompt(brief, corpus)
        print(f"[prompt] system={len(SYSTEM_PROMPT)} chars, user={len(user)} chars")

        with open("/tmp/path_b_experiment/path_b_prompt_user.txt", "w") as f:
            f.write(user)

        print("[deepseek] calling...")
        resp = call_deepseek(SYSTEM_PROMPT, user)

        with open("/tmp/path_b_experiment/path_b_response_full.json", "w") as f:
            json.dump(resp, f, ensure_ascii=False, indent=2)

        usage = resp.get("usage", {})
        print(f"[usage] {json.dumps(usage, indent=2)}")

        content = resp["choices"][0]["message"]["content"]
        with open("/tmp/path_b_experiment/path_b_insight.json", "w") as f:
            f.write(content)
        print("[done] saved /tmp/path_b_experiment/path_b_insight.json")

        try:
            parsed = json.loads(content)
            print(f"[parsed] tensions={len(parsed.get('social_tensions', []))} "
                  f"opps={len(parsed.get('brand_opportunities', []))}")
        except json.JSONDecodeError as e:
            print(f"[warn] json parse failed: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
