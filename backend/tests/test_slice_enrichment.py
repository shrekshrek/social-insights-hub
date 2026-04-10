"""切片流水线数据补全 — 单元测试

覆盖: _compute_time_distribution, _merge_kol_voices
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 1. _compute_time_distribution
# ---------------------------------------------------------------------------


class TestComputeTimeDistribution:
    """测试 time_distribution 计算"""

    def _call(self, post_info_by_key, spam_map_by_key=None):
        from src.social_media.analysis.monitor_slice import _compute_time_distribution

        return _compute_time_distribution(
            post_info_by_key=post_info_by_key,
            spam_map_by_key=spam_map_by_key or {},
        )

    def test_normal_multiple_dates(self):
        """3 条原文 2 个日期 → distribution 有 2 项，count 之和 = 3"""
        info = {
            "xhs:001": {"published_at": "2025-12-01T10:00:00Z"},
            "xhs:002": {"published_at": "2025-12-01T14:00:00Z"},
            "dy:003": {"published_at": "2025-12-02T10:00:00Z"},
        }
        result = self._call(info)
        assert len(result["distribution"]) == 2
        total = sum(d["count"] for d in result["distribution"])
        assert total == 3
        assert result["skipped_count"] == 0
        # 按日期排序
        dates = [d["date"] for d in result["distribution"]]
        assert dates == sorted(dates)

    def test_timezone_normalization(self):
        """不同时区的时间戳统一归 UTC 后取日期"""
        info = {
            # 2025-12-02T08:00+08:00 = 2025-12-02T00:00Z → 日期 2025-12-02
            "xhs:001": {"published_at": "2025-12-02T08:00:00+08:00"},
            # 2025-12-02T02:00+08:00 = 2025-12-01T18:00Z → 日期 2025-12-01
            "xhs:002": {"published_at": "2025-12-02T02:00:00+08:00"},
        }
        result = self._call(info)
        assert len(result["distribution"]) == 2
        dates = {d["date"] for d in result["distribution"]}
        assert dates == {"2025-12-01", "2025-12-02"}

    def test_missing_published_at(self):
        """published_at 为 None → skipped_count 递增"""
        info = {
            "xhs:001": {"published_at": "2025-12-01T10:00:00Z"},
            "xhs:002": {"published_at": None},
            "xhs:003": {},
        }
        result = self._call(info)
        assert result["skipped_count"] == 2
        assert len(result["distribution"]) == 1
        assert result["distribution"][0]["count"] == 1

    def test_organic_promo_split(self):
        """含 spam 高分原文 → promo_distribution 有条目"""
        info = {
            "xhs:001": {"published_at": "2025-12-01T10:00:00Z"},
            "xhs:002": {"published_at": "2025-12-01T14:00:00Z"},
            "dy:003": {"published_at": "2025-12-01T08:00:00Z"},
        }
        spam_map = {
            "xhs:001": "low",
            "xhs:002": "high",
            "dy:003": "low",
        }
        result = self._call(info, spam_map)

        # 全量 distribution
        assert result["distribution"][0]["count"] == 3

        # organic: 2 条 low
        assert len(result["organic_distribution"]) == 1
        assert result["organic_distribution"][0]["count"] == 2

        # promo: 1 条 high
        assert len(result["promo_distribution"]) == 1
        assert result["promo_distribution"][0]["count"] == 1

    def test_empty_input(self):
        """空 post_info_by_key → 空结果"""
        result = self._call({})
        assert result["distribution"] == []
        assert result["organic_distribution"] == []
        assert result["promo_distribution"] == []
        assert result["skipped_count"] == 0


# ---------------------------------------------------------------------------
# 2. _merge_kol_voices
# ---------------------------------------------------------------------------


class TestMergeKolVoices:
    """测试 KOL 声音跨任务合并"""

    def _call(self, task_data_list, post_key_by_id=None, spam_map_by_key=None, top_n=10):
        from src.social_media.analysis.monitor_slice import _merge_kol_voices

        return _merge_kol_voices(
            task_data_list=task_data_list,
            post_key_by_id=post_key_by_id or {},
            spam_map_by_key=spam_map_by_key or {},
            top_n=top_n,
        )

    def _make_task(self, task_id, kol_voices):
        return {
            "task_id": task_id,
            "analysis_result": {
                "insights": {
                    "kol_voices": kol_voices,
                }
            },
        }

    def test_cross_task_dedup(self):
        """同一原文在 2 个任务中 → 去重后仅保留 CII 最高的"""
        task1 = self._make_task(1, [
            {"post_id": 100, "author": "A", "title": "t", "cii": 5.0,
             "sentiment": 0.5, "summary": "s", "platform": "xhs"},
        ])
        task2 = self._make_task(2, [
            {"post_id": 200, "author": "A", "title": "t", "cii": 8.0,
             "sentiment": 0.5, "summary": "s", "platform": "xhs"},
        ])
        # 两个 post_id 映射到同一 post_key
        post_key_by_id = {100: "xhs:abc", 200: "xhs:abc"}
        result = self._call([task1, task2], post_key_by_id)
        assert len(result) == 1
        assert result[0]["cii"] == 8.0
        assert result[0]["post_id"] == 200
        assert result[0]["task_id"] == 2

    def test_top_n_sorting(self):
        """合并 15 条 → 返回 top 10，按 CII 降序"""
        voices = [
            {"post_id": i, "author": f"A{i}", "title": f"t{i}", "cii": float(i),
             "sentiment": 0.0, "summary": "s", "platform": "xhs"}
            for i in range(1, 16)
        ]
        task = self._make_task(1, voices)
        post_key_by_id = {i: f"xhs:{i}" for i in range(1, 16)}
        result = self._call([task], post_key_by_id, top_n=10)
        assert len(result) == 10
        assert result[0]["cii"] == 15.0
        assert result[-1]["cii"] == 6.0

    def test_spam_group_mapping(self):
        """spam_map_by_key 正确映射到 spam_group"""
        task = self._make_task(1, [
            {"post_id": 1, "author": "A", "title": "t", "cii": 5.0,
             "sentiment": 0.5, "summary": "s", "platform": "xhs"},
        ])
        post_key_by_id = {1: "xhs:001"}
        spam_map = {"xhs:001": "high"}
        result = self._call([task], post_key_by_id, spam_map)
        assert result[0]["spam_group"] == "high"

    def test_missing_kol_voices(self):
        """某任务无 insights 或 kol_voices → 跳过不报错"""
        task_no_insights = {"task_id": 1, "analysis_result": {}}
        task_no_kol = {"task_id": 2, "analysis_result": {"insights": {}}}
        task_none = {"task_id": 3, "analysis_result": None}
        result = self._call([task_no_insights, task_no_kol, task_none])
        assert result == []

    def test_post_key_not_found(self):
        """post_key_by_id 中找不到 post_id → 跳过该 KOL"""
        task = self._make_task(1, [
            {"post_id": 999, "author": "A", "title": "t", "cii": 5.0,
             "sentiment": 0.5, "summary": "s", "platform": "xhs"},
        ])
        result = self._call([task], post_key_by_id={})  # 空映射
        assert result == []
