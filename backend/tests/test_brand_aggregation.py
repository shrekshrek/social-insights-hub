"""Tests for _aggregate_entities_by_parent source ID collection."""

from src.social_media.analysis.celery_tasks.aggregation.insights import (
    _aggregate_entities_by_parent,
)


class TestAggregateEntitiesByParentSourceIds:
    """Verify post_source_ids and comment_source_ids are collected and deduplicated."""

    def _make_entity(
        self,
        name: str,
        parent: str | None = None,
        role: str = "competitor",
        post_ids: list[int] | None = None,
        post_source_ids: list[int] | None = None,
        comment_source_ids: list[int] | None = None,
        mentions: int = 1,
    ) -> dict:
        entity = {
            "name": name,
            "role": role,
            "mentions": mentions,
            "heat": 10.0,
            "sentiment": 0.0,
            "post_ids": post_ids or [],
            "post_source_ids": post_source_ids or [],
            "comment_source_ids": comment_source_ids or [],
            "sentiment_distribution": {"positive": 1, "negative": 0, "neutral": 0},
        }
        if parent:
            entity["tags"] = {"parent": parent, "role": role}
        return entity

    def test_single_entity_passes_through(self):
        entities = [
            self._make_entity("P1", parent="Brand", post_source_ids=[1, 2], comment_source_ids=[3]),
        ]
        result = _aggregate_entities_by_parent(entities)
        brand = result["Brand"]
        assert sorted(brand["post_source_ids"]) == [1, 2]
        assert brand["comment_source_ids"] == [3]

    def test_multiple_products_dedup(self):
        """Two products under the same brand share overlapping source IDs."""
        entities = [
            self._make_entity("P1", parent="Brand", post_source_ids=[1, 2], comment_source_ids=[3]),
            self._make_entity("P2", parent="Brand", post_source_ids=[2, 4], comment_source_ids=[3, 5]),
        ]
        result = _aggregate_entities_by_parent(entities)
        brand = result["Brand"]
        assert sorted(brand["post_source_ids"]) == [1, 2, 4]
        assert sorted(brand["comment_source_ids"]) == [3, 5]

    def test_missing_source_ids_default_empty(self):
        entities = [
            self._make_entity("P1", parent="Brand"),  # no source IDs
        ]
        result = _aggregate_entities_by_parent(entities)
        brand = result["Brand"]
        assert brand["post_source_ids"] == []
        assert brand["comment_source_ids"] == []

    def test_role_filter(self):
        entities = [
            self._make_entity("T1", parent="Target", role="target", post_source_ids=[1]),
            self._make_entity("C1", parent="Comp", role="competitor", post_source_ids=[2]),
        ]
        result = _aggregate_entities_by_parent(entities, role_filter="target")
        assert "Target" in result
        assert "Comp" not in result
        assert result["Target"]["post_source_ids"] == [1]
