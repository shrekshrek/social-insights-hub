"""Tests for spam_distribution module."""

from src.social_media.analysis.celery_tasks.aggregation.spam_distribution import (
    build_spam_distributions,
    _build_spam_map,
    _compute_spam_dist_4d,
    _compute_spam_dist_2d,
    _compute_spam_group,
)


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_posts_data(scores: dict[int, float | None]) -> list[dict]:
    """Helper: create posts_data from {post_id: spam_score} mapping."""
    return [{"post_id": pid, "spam_score": score} for pid, score in scores.items()]


# ── _build_spam_map ───────────────────────────────────────────────────


class TestBuildSpamMap:
    def test_mixed_scores(self):
        posts = _make_posts_data({1: 8.0, 2: 3.0, 3: 6.0, 4: 5.9})
        result = _build_spam_map(posts, threshold=6.0)
        assert result == {1: "high", 2: "low", 3: "high", 4: "low"}

    def test_none_scores_excluded(self):
        posts = _make_posts_data({1: 8.0, 2: None, 3: 3.0})
        result = _build_spam_map(posts, threshold=6.0)
        assert result == {1: "high", 3: "low"}
        assert 2 not in result

    def test_all_none(self):
        posts = _make_posts_data({1: None, 2: None})
        result = _build_spam_map(posts, threshold=6.0)
        assert result == {}

    def test_empty_posts(self):
        result = _build_spam_map([], threshold=6.0)
        assert result == {}

    def test_custom_threshold(self):
        posts = _make_posts_data({1: 5.0, 2: 4.9})
        result = _build_spam_map(posts, threshold=5.0)
        assert result == {1: "high", 2: "low"}


# ── _compute_spam_dist_4d ─────────────────────────────────────────────


class TestComputeSpamDist4d:
    def test_mixed_sources(self):
        spam_map = {1: "high", 2: "low", 3: "high", 4: "low"}
        result = _compute_spam_dist_4d(
            post_source_ids=[1, 2],
            comment_source_ids=[3, 4],
            spam_map=spam_map,
        )
        assert result == {
            "high_spam": {"total": 2, "post": 1, "comment": 1},
            "low_spam": {"total": 2, "post": 1, "comment": 1},
        }

    def test_all_high_spam(self):
        spam_map = {1: "high", 2: "high"}
        result = _compute_spam_dist_4d(
            post_source_ids=[1],
            comment_source_ids=[2],
            spam_map=spam_map,
        )
        assert result["high_spam"] == {"total": 2, "post": 1, "comment": 1}
        assert result["low_spam"] == {"total": 0, "post": 0, "comment": 0}

    def test_all_low_spam(self):
        spam_map = {1: "low", 2: "low"}
        result = _compute_spam_dist_4d(
            post_source_ids=[1, 2],
            comment_source_ids=[],
            spam_map=spam_map,
        )
        assert result["high_spam"] == {"total": 0, "post": 0, "comment": 0}
        assert result["low_spam"] == {"total": 2, "post": 2, "comment": 0}

    def test_ids_not_in_spam_map(self):
        spam_map = {1: "high"}
        result = _compute_spam_dist_4d(
            post_source_ids=[1, 99],
            comment_source_ids=[100],
            spam_map=spam_map,
        )
        # Only post_id=1 is in spam_map
        assert result["high_spam"] == {"total": 1, "post": 1, "comment": 0}
        assert result["low_spam"] == {"total": 0, "post": 0, "comment": 0}

    def test_all_ids_not_in_spam_map_returns_none(self):
        spam_map = {1: "high"}
        result = _compute_spam_dist_4d(
            post_source_ids=[99],
            comment_source_ids=[100],
            spam_map=spam_map,
        )
        assert result is None

    def test_empty_ids(self):
        spam_map = {1: "high"}
        result = _compute_spam_dist_4d(
            post_source_ids=[],
            comment_source_ids=[],
            spam_map=spam_map,
        )
        assert result is None


# ── _compute_spam_dist_2d ─────────────────────────────────────────────


class TestComputeSpamDist2d:
    def test_mixed(self):
        spam_map = {1: "high", 2: "low", 3: "high"}
        result = _compute_spam_dist_2d([1, 2, 3], spam_map)
        assert result == {"high": 2, "low": 1}

    def test_all_not_in_map_returns_none(self):
        spam_map = {1: "high"}
        result = _compute_spam_dist_2d([99, 100], spam_map)
        assert result is None

    def test_empty_post_ids(self):
        spam_map = {1: "high"}
        result = _compute_spam_dist_2d([], spam_map)
        assert result is None


# ── _compute_spam_group ───────────────────────────────────────────────


class TestComputeSpamGroup:
    def test_high(self):
        assert _compute_spam_group(1, {1: "high"}) == "high"

    def test_low(self):
        assert _compute_spam_group(2, {2: "low"}) == "low"

    def test_not_in_map(self):
        assert _compute_spam_group(99, {1: "high"}) is None

    def test_none_post_id(self):
        assert _compute_spam_group(None, {1: "high"}) is None


# ── build_spam_distributions (integration) ────────────────────────────


class TestBuildSpamDistributions:
    """Integration tests for the main entry point."""

    def _default_posts(self):
        return _make_posts_data({
            1: 8.0,   # high
            2: 3.0,   # low
            3: 7.0,   # high
            4: 2.0,   # low
            5: None,  # excluded
        })

    def test_entities_get_4d_distribution(self):
        entities = [
            {"name": "A", "post_source_ids": [1, 2], "comment_source_ids": [3]},
        ]
        config = build_spam_distributions(
            aggregated_entities=entities,
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=[],
            ipa_points=[],
            competitor_series=[],
            time_distribution=[],
            posts_data=self._default_posts(),
        )
        dist = entities[0]["spam_distribution"]
        assert dist["high_spam"]["post"] == 1   # post_id=1 is high
        assert dist["low_spam"]["post"] == 1    # post_id=2 is low
        assert dist["high_spam"]["comment"] == 1  # post_id=3 is high
        assert config["threshold"] == 6.0

    def test_opinions_get_4d_distribution(self):
        opinions = [
            {"name": "B", "post_source_ids": [1], "comment_source_ids": [2, 4]},
        ]
        build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=opinions,
            quadrant_data=[],
            kol_voices=[],
            ipa_points=[],
            competitor_series=[],
            time_distribution=[],
            posts_data=self._default_posts(),
        )
        dist = opinions[0]["spam_distribution"]
        assert dist["high_spam"]["post"] == 1
        assert dist["low_spam"]["comment"] == 2  # post_id=2,4 are low

    def test_quadrant_gets_spam_group(self):
        quadrant = [
            {"post_id": 1, "x": 0.5, "y": 0.5},
            {"post_id": 5, "x": 0.1, "y": 0.1},  # spam_score=None
        ]
        build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=[],
            quadrant_data=quadrant,
            kol_voices=[],
            ipa_points=[],
            competitor_series=[],
            time_distribution=[],
            posts_data=self._default_posts(),
        )
        assert quadrant[0]["spam_group"] == "high"
        assert quadrant[1]["spam_group"] is None

    def test_kol_gets_spam_group(self):
        kol = [{"post_id": 2, "author": "A"}]
        build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=kol,
            ipa_points=[],
            competitor_series=[],
            time_distribution=[],
            posts_data=self._default_posts(),
        )
        assert kol[0]["spam_group"] == "low"

    def test_ipa_gets_4d_distribution(self):
        # post_id=1: high (8.0), post_id=2: low (3.0), post_id=3: high (7.0)
        ipa = [{"name": "X", "post_source_ids": [1, 2], "comment_source_ids": [3]}]
        build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=[],
            ipa_points=ipa,
            competitor_series=[],
            time_distribution=[],
            posts_data=self._default_posts(),
        )
        dist = ipa[0]["spam_distribution"]
        assert dist["high_spam"] == {"total": 2, "post": 1, "comment": 1}
        assert dist["low_spam"] == {"total": 1, "post": 1, "comment": 0}

    def test_ipa_no_source_ids_returns_none(self):
        """IPA point from entity attribute without source IDs gets None."""
        ipa = [{"name": "X", "post_ids": [1, 2]}]  # no post_source_ids
        build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=[],
            ipa_points=ipa,
            competitor_series=[],
            time_distribution=[],
            posts_data=self._default_posts(),
        )
        assert ipa[0]["spam_distribution"] is None

    def test_competitor_series_gets_4d_distribution(self):
        series = [{"name": "Brand", "post_source_ids": [1], "comment_source_ids": [4]}]
        build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=[],
            ipa_points=[],
            competitor_series=series,
            time_distribution=[],
            posts_data=self._default_posts(),
        )
        dist = series[0]["spam_distribution"]
        assert dist["high_spam"] == {"total": 1, "post": 1, "comment": 0}
        assert dist["low_spam"] == {"total": 1, "post": 0, "comment": 1}

    def test_time_distribution_gets_breakdown(self):
        time_dist = [{"date": "2024-01-01", "post_ids": [1, 2]}]
        build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=[],
            ipa_points=[],
            competitor_series=[],
            time_distribution=time_dist,
            posts_data=self._default_posts(),
        )
        assert time_dist[0]["spam_breakdown"] == {"high": 1, "low": 1}

    def test_all_unscreened_posts(self):
        """When all posts have spam_score=None, all spam fields should be None."""
        posts = _make_posts_data({1: None, 2: None})
        entities = [{"name": "A", "post_source_ids": [1], "comment_source_ids": [2]}]
        quadrant = [{"post_id": 1}]
        ipa = [{"name": "X", "post_ids": [1, 2]}]
        time_dist = [{"date": "2024-01-01", "post_ids": [1]}]

        build_spam_distributions(
            aggregated_entities=entities,
            aggregated_opinions=[],
            quadrant_data=quadrant,
            kol_voices=[],
            ipa_points=ipa,
            competitor_series=[],
            time_distribution=time_dist,
            posts_data=posts,
        )
        assert entities[0]["spam_distribution"] is None
        assert quadrant[0]["spam_group"] is None
        assert ipa[0]["spam_distribution"] is None
        assert time_dist[0]["spam_breakdown"] is None

    def test_custom_threshold(self):
        posts = _make_posts_data({1: 5.0, 2: 4.9})
        entities = [{"name": "A", "post_source_ids": [1, 2], "comment_source_ids": []}]
        build_spam_distributions(
            aggregated_entities=entities,
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=[],
            ipa_points=[],
            competitor_series=[],
            time_distribution=[],
            posts_data=posts,
            threshold=5.0,
        )
        dist = entities[0]["spam_distribution"]
        assert dist["high_spam"]["post"] == 1
        assert dist["low_spam"]["post"] == 1

    def test_returns_spam_config(self):
        config = build_spam_distributions(
            aggregated_entities=[],
            aggregated_opinions=[],
            quadrant_data=[],
            kol_voices=[],
            ipa_points=[],
            competitor_series=[],
            time_distribution=[],
            posts_data=self._default_posts(),
            threshold=7.0,
        )
        assert config["threshold"] == 7.0
