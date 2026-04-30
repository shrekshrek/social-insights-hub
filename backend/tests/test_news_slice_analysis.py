"""新闻 Slice 综合分析纯函数测试（ADR-003）

覆盖范围：
- _dedupe_and_filter：URL 去重 + 过滤 low + 跨任务命中映射
- _compute_descriptive：描述层 SQL 派生（来源/情感/类型/时序/重叠）
- _compute_entity_sentiments：sentiment 多维派生工具
- _derive_entities：Pass 1 → 派生 entity（含 sentiment）
- _enforce_entity_roles：三种运行模式 + 变体合并
- _recompute_entity_sentiments：合并变体后重算

不覆盖：LLM 调用本身（chain.invoke）— 在集成测试中覆盖。
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.news_media.analysis.service import (
    _compute_descriptive,
    _compute_entity_sentiments,
    _dedupe_and_filter,
    _derive_entities,
    _enforce_entity_roles,
    _recompute_entity_sentiments,
)


def _article(
    *,
    id: int,
    task_id: int,
    url: str,
    title: str = "title",
    source_name: str = "src",
    source_tier: str = "tier3",
    search_source: str = "baidu",
    article_type: str | None = "report",
    relevance: str | None = "high",
    sentiment: float | None = 0,
    published_at: datetime | None = None,
    summary: str | None = None,
    mentioned_entities: list | None = None,
    key_quotes: list | None = None,
):
    """构造一个最小可用的 NewsArticle 替身（不依赖 SQLAlchemy）。"""
    return SimpleNamespace(
        id=id,
        task_id=task_id,
        url=url,
        title=title,
        source_name=source_name,
        source_tier=source_tier,
        search_source=search_source,
        article_type=article_type,
        relevance=relevance,
        sentiment=sentiment,
        published_at=published_at,
        summary=summary,
        mentioned_entities=mentioned_entities or [],
        key_quotes=key_quotes or [],
    )


# ==================== _dedupe_and_filter ====================


class TestDedupeAndFilter:
    def test_dedupes_same_url_across_tasks(self):
        articles = [
            _article(id=1, task_id=10, url="u1"),
            _article(id=2, task_id=11, url="u1"),  # 同 URL，task=11
            _article(id=3, task_id=10, url="u2"),
        ]
        filtered, url_to_task_ids = _dedupe_and_filter(articles)

        # 去重后 2 篇（u1 仅保留一条 = 首见 id=1）
        assert len(filtered) == 2
        assert filtered[0].id == 1
        assert filtered[1].id == 3

        # url_to_task_ids 保留所有命中（用于跨任务重叠分析）
        assert url_to_task_ids["u1"] == [10, 11]
        assert url_to_task_ids["u2"] == [10]

    def test_filters_relevance_low(self):
        articles = [
            _article(id=1, task_id=1, url="u1", relevance="high"),
            _article(id=2, task_id=1, url="u2", relevance="low"),  # 过滤
            _article(id=3, task_id=1, url="u3", relevance="medium"),
            _article(id=4, task_id=1, url="u4", relevance=None),  # None 也保留
        ]
        filtered, _ = _dedupe_and_filter(articles)
        assert {a.id for a in filtered} == {1, 3, 4}

    def test_dedup_keeps_first_seen_record(self):
        # 同一 URL 多 task 命中时，保留**首见**记录（用于 article 字段一致性）
        articles = [
            _article(id=1, task_id=1, url="u1", source_tier="tier1"),
            _article(id=2, task_id=2, url="u1", source_tier="tier3"),
        ]
        filtered, url_to_task_ids = _dedupe_and_filter(articles)
        assert len(filtered) == 1
        assert filtered[0].source_tier == "tier1"
        assert url_to_task_ids["u1"] == [1, 2]


# ==================== _compute_descriptive ====================


class TestComputeDescriptive:
    def _basic_setup(self):
        d1 = datetime(2026, 4, 1, tzinfo=timezone.utc)
        d2 = datetime(2026, 4, 2, tzinfo=timezone.utc)
        articles = [
            _article(id=1, task_id=10, url="u1", source_tier="tier1",
                     sentiment=2, article_type="report", published_at=d1),
            _article(id=2, task_id=10, url="u2", source_tier="tier3",
                     sentiment=-1, article_type="opinion", published_at=d1),
            _article(id=3, task_id=11, url="u3", source_tier="wechat_mp",
                     sentiment=0, article_type="pr", published_at=d2),
        ]
        url_to_task_ids = {"u1": [10], "u2": [10], "u3": [11, 12]}
        return articles, url_to_task_ids

    def test_basic_distributions(self):
        articles, url_to_task_ids = self._basic_setup()
        result = _compute_descriptive(articles, url_to_task_ids)

        assert result["source_tier_distribution"] == {
            "tier1": 1, "tier2": 0, "tier3": 1, "wechat_mp": 1,
        }
        assert result["article_type_distribution"]["report"] == 1
        assert result["article_type_distribution"]["pr"] == 1
        assert result["sentiment_distribution"] == {
            "positive": 1, "neutral": 1, "negative": 1,
        }

    def test_sentiment_overall_and_by_tier(self):
        articles, url_to_task_ids = self._basic_setup()
        result = _compute_descriptive(articles, url_to_task_ids)

        # 综合情感 = (2 + -1 + 0) / 3 ≈ 0.333
        assert result["sentiment_overall"] == pytest.approx(0.333, abs=0.001)
        # 各 tier 各自情感
        assert result["sentiment_by_tier"]["tier1"] == 2.0
        assert result["sentiment_by_tier"]["tier3"] == -1.0
        assert result["sentiment_by_tier"]["wechat_mp"] == 0.0
        assert result["sentiment_by_tier"]["tier2"] is None  # 无样本

    def test_cross_task_overlap_distribution(self):
        articles, url_to_task_ids = self._basic_setup()
        result = _compute_descriptive(articles, url_to_task_ids)

        overlap = result["cross_task_overlap"]["distribution"]
        assert overlap["single_task"] == 2  # u1, u2
        assert overlap["two_tasks"] == 1  # u3 (task 11+12)
        assert overlap["three_plus"] == 0

        # high_overlap_articles 仅含 ≥ 2 task
        high = result["cross_task_overlap"]["high_overlap_articles"]
        assert len(high) == 1
        assert high[0]["url"] == "u3"
        assert high[0]["task_count"] == 2

    def test_coverage_timeseries_buckets_by_day_with_tier(self):
        articles, url_to_task_ids = self._basic_setup()
        result = _compute_descriptive(articles, url_to_task_ids)

        ts = result["coverage_timeseries"]
        assert len(ts) == 2  # 4-01, 4-02
        assert ts[0]["date"] == "2026-04-01"
        assert ts[0]["count"] == 2
        assert ts[0]["count_by_tier"]["tier1"] == 1
        assert ts[0]["count_by_tier"]["tier3"] == 1

    def test_sentiment_timeseries_includes_tier_weighted(self):
        articles, url_to_task_ids = self._basic_setup()
        result = _compute_descriptive(articles, url_to_task_ids)

        ts = result["sentiment_timeseries"]
        # 4-01: tier1(w=4)*2 + tier3(w=1)*(-1) = 7; weight_total = 5; weighted = 1.4
        bucket_d1 = next(t for t in ts if t["date"] == "2026-04-01")
        assert bucket_d1["sentiment_avg"] == pytest.approx(0.5, abs=0.001)
        assert bucket_d1["sentiment_weighted_by_tier"] == pytest.approx(1.4, abs=0.001)


# ==================== _compute_entity_sentiments ====================


class TestComputeEntitySentiments:
    def test_empty_returns_none_fields(self):
        result = _compute_entity_sentiments([], {})
        assert result["sentiment_avg"] is None
        assert result["sentiment_weighted_by_tier"] is None
        assert all(result["sentiment_by_tier"][t] is None for t in result["sentiment_by_tier"])
        assert result["source_count"] == 0

    def test_aggregates_across_tiers(self):
        a1 = _article(id=1, task_id=1, url="u1", source_tier="tier1", sentiment=2,
                      source_name="新华社")
        a2 = _article(id=2, task_id=1, url="u2", source_tier="tier3", sentiment=-2,
                      source_name="某门户")
        article_by_id = {1: a1, 2: a2}

        result = _compute_entity_sentiments([1, 2], article_by_id)

        # 等权 = (2 + -2) / 2 = 0
        assert result["sentiment_avg"] == 0.0
        # tier 加权 = (2*4 + -2*1) / (4+1) = 6/5 = 1.2
        assert result["sentiment_weighted_by_tier"] == pytest.approx(1.2, abs=0.001)
        # tier1 = 2, tier3 = -2
        assert result["sentiment_by_tier"]["tier1"] == 2.0
        assert result["sentiment_by_tier"]["tier3"] == -2.0
        assert result["sentiment_by_tier"]["tier2"] is None
        assert result["source_count"] == 2

    def test_skips_none_sentiment_but_counts_source(self):
        a = _article(id=1, task_id=1, url="u1", source_tier="tier1", sentiment=None,
                     source_name="src1")
        result = _compute_entity_sentiments([1], {1: a})
        assert result["sentiment_avg"] is None
        assert result["source_count"] == 1


# ==================== _derive_entities ====================


class TestDeriveEntities:
    def test_maps_indices_to_article_ids(self):
        a1 = _article(id=10, task_id=1, url="u1", source_tier="tier1", sentiment=1,
                      source_name="src1")
        a2 = _article(id=20, task_id=1, url="u2", source_tier="tier3", sentiment=-1,
                      source_name="src2")
        article_by_index = {0: a1, 1: a2}
        article_by_id = {10: a1, 20: a2}

        pass1_entities = [{
            "name": "Aqara",
            "role": "target",
            "article_indices": [0, 1],
            "representative_article_indices": [0],
        }]
        result = _derive_entities(pass1_entities, article_by_index, article_by_id)

        assert len(result) == 1
        e = result[0]
        assert e["article_ids"] == [10, 20]
        assert e["representative_article_ids"] == [10]
        assert e["mention_count"] == 2
        assert e["source_count"] == 2  # src1 + src2
        assert e["sentiment_avg"] == 0.0
        # tier 加权 = (1*4 + -1*1) / 5 = 0.6
        assert e["sentiment_weighted_by_tier"] == pytest.approx(0.6, abs=0.001)

    def test_skips_invalid_entries(self):
        article_by_index: dict = {}
        article_by_id: dict = {}
        # 无 name 或非 dict 的条目应该被忽略
        pass1 = [{}, {"name": ""}, "string-not-dict", {"name": "Valid", "article_indices": []}]
        result = _derive_entities(pass1, article_by_index, article_by_id)
        assert len(result) == 1
        assert result[0]["name"] == "Valid"

    def test_sort_target_first_then_competitor_then_context(self):
        article_by_index: dict = {}
        article_by_id: dict = {}
        pass1 = [
            {"name": "X", "role": "context", "article_indices": []},
            {"name": "Y", "role": "competitor", "article_indices": []},
            {"name": "Z", "role": "target", "article_indices": []},
        ]
        result = _derive_entities(pass1, article_by_index, article_by_id)
        assert [e["name"] for e in result] == ["Z", "Y", "X"]


# ==================== _enforce_entity_roles ====================


class TestEnforceEntityRoles:
    def test_degraded_mode_subject_empty_all_context(self):
        entities = [
            {"name": "Aqara", "role": "target", "mention_count": 5, "article_ids": [1, 2]},
            {"name": "其他", "role": "competitor", "mention_count": 2, "article_ids": [3]},
        ]
        _enforce_entity_roles(entities, subject="", competitors=[])
        # subject 为空 → 所有实体强制 context（不动 article_ids）
        assert all(e["role"] == "context" for e in entities)

    def test_explicit_mode_strict_listing(self):
        entities = [
            {"name": "Aqara", "role": "context", "mention_count": 5, "article_ids": [1, 2],
             "representative_article_ids": [1]},
            {"name": "SwitchBot", "role": "context", "mention_count": 3, "article_ids": [3],
             "representative_article_ids": []},
            {"name": "随便竞品", "role": "competitor", "mention_count": 2, "article_ids": [4],
             "representative_article_ids": []},
        ]
        _enforce_entity_roles(
            entities, subject="Aqara", competitors=["SwitchBot"],
        )
        roles = {e["name"]: e["role"] for e in entities}
        # subject 严格归 target
        assert roles["Aqara"] == "target"
        # competitors 列表内归 competitor
        assert roles["SwitchBot"] == "competitor"
        # 列表外强制 context（即使原来标 competitor 也强制改）
        assert roles["随便竞品"] == "context"

    def test_explicit_mode_merges_variants_to_canonical(self):
        # "绿米联创Aqara" 是 Aqara 的变体，必须合并
        entities = [
            {"name": "Aqara", "role": "context", "mention_count": 3, "article_ids": [1, 2, 3],
             "representative_article_ids": [1]},
            {"name": "绿米联创Aqara", "role": "context", "mention_count": 2, "article_ids": [4, 5],
             "representative_article_ids": [4]},
        ]
        _enforce_entity_roles(entities, subject="Aqara", competitors=[])

        # 找合并后 Aqara 条目
        canonical = next(e for e in entities if e["name"] == "Aqara")
        # mention 累加且去重（5 个唯一 article_id）
        assert canonical["mention_count"] == 5
        assert set(canonical["article_ids"]) == {1, 2, 3, 4, 5}
        assert canonical["role"] == "target"
        # 变体不应继续出现在 entities 中
        assert "绿米联创Aqara" not in {e["name"] for e in entities}

    def test_explicit_mode_target_zero_mentions_preserved(self):
        # subject 不在文章里出现，但仍要保留 target 占位条目
        entities = [
            {"name": "其他品牌", "role": "context", "mention_count": 5,
             "article_ids": [1, 2, 3, 4, 5], "representative_article_ids": []},
        ]
        _enforce_entity_roles(entities, subject="MyBrand", competitors=["X"])

        # MyBrand 即使未提及，必须出现且 role=target
        target = next((e for e in entities if e["role"] == "target"), None)
        assert target is not None
        assert target["name"] == "MyBrand"
        assert target["mention_count"] == 0
        assert target["article_ids"] == []

    def test_auto_discovery_mode_keeps_llm_competitors(self):
        # subject 非空 + competitors 空 → 自动发现，保留 LLM 自判 competitor
        entities = [
            {"name": "MyBrand", "role": "target", "mention_count": 5,
             "article_ids": [1], "representative_article_ids": []},
            {"name": "LLM 标的竞品", "role": "competitor", "mention_count": 3,
             "article_ids": [2], "representative_article_ids": []},
        ]
        _enforce_entity_roles(entities, subject="MyBrand", competitors=[])
        roles = {e["name"]: e["role"] for e in entities}
        assert roles["MyBrand"] == "target"
        # 自动发现模式不强制把 LLM 标的 competitor 改成 context
        assert roles["LLM 标的竞品"] == "competitor"

    def test_auto_discovery_mode_blocks_other_target(self):
        # 自动发现下也禁止其他实体被标 target；只有 subject 才能是 target
        entities = [
            {"name": "其他", "role": "target", "mention_count": 99,
             "article_ids": [1], "representative_article_ids": []},
        ]
        _enforce_entity_roles(entities, subject="MyBrand", competitors=[])

        # "其他" 必须被改成非 target
        other = next(e for e in entities if e["name"] == "其他")
        assert other["role"] != "target"
        # subject 自动占位为 target（即使 0 提及）
        targets = [e for e in entities if e["role"] == "target"]
        assert len(targets) == 1
        assert targets[0]["name"] == "MyBrand"


# ==================== _recompute_entity_sentiments ====================


class TestRecomputeEntitySentiments:
    def test_recompute_after_merge_includes_all_article_sentiments(self):
        # 模拟合并后场景：article_ids 来自不同 tier，sentiment 字段需要重算
        a1 = _article(id=1, task_id=1, url="u1", source_tier="tier1", sentiment=2,
                      source_name="新华社")
        a2 = _article(id=2, task_id=1, url="u2", source_tier="tier3", sentiment=-2,
                      source_name="自媒体")
        article_by_id = {1: a1, 2: a2}

        # 合并后的 entity（sentiment 字段是 None 占位）
        entities = [{
            "name": "X",
            "role": "target",
            "article_ids": [1, 2],
            "source_count": 0,
            "sentiment_avg": None,
            "sentiment_weighted_by_tier": None,
            "sentiment_by_tier": {"tier1": None, "tier2": None, "tier3": None, "wechat_mp": None},
        }]
        _recompute_entity_sentiments(entities, article_by_id)

        e = entities[0]
        assert e["sentiment_avg"] == 0.0
        assert e["sentiment_weighted_by_tier"] == pytest.approx(1.2, abs=0.001)
        assert e["sentiment_by_tier"]["tier1"] == 2.0
        assert e["sentiment_by_tier"]["tier3"] == -2.0
        assert e["source_count"] == 2

    def test_recompute_with_empty_articles(self):
        # 0 提及（target 占位条目）
        entities = [{
            "name": "MyBrand",
            "role": "target",
            "article_ids": [],
            "source_count": 0,
            "sentiment_avg": None,
            "sentiment_weighted_by_tier": None,
            "sentiment_by_tier": {"tier1": None, "tier2": None, "tier3": None, "wechat_mp": None},
        }]
        _recompute_entity_sentiments(entities, {})
        e = entities[0]
        assert e["sentiment_avg"] is None
        assert e["sentiment_weighted_by_tier"] is None
        assert e["source_count"] == 0
