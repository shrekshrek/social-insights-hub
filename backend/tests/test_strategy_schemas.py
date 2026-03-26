"""策略 Schemas 单元测试"""

import pytest
from pydantic import ValidationError

from src.strategies.schemas import BrandBrief, StrategyCreate, StrategyUpdate, PhaseResultEdit


class TestStrategyCreate:
    """StrategyCreate 校验"""

    def test_valid_create(self):
        data = StrategyCreate(name="测试策略", slice_ids=[1, 2])
        assert data.name == "测试策略"
        assert data.slice_ids == [1, 2]
        assert data.brand_brief is None

    def test_name_min_length(self):
        with pytest.raises(ValidationError):
            StrategyCreate(name="", slice_ids=[1])

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            StrategyCreate(name="x" * 256, slice_ids=[1])

    def test_name_at_max_length(self):
        data = StrategyCreate(name="x" * 255, slice_ids=[1])
        assert len(data.name) == 255

    def test_slice_ids_optional_empty(self):
        """slice_ids 现在是可选的，允许空列表（快速路径和引导路径均支持）"""
        data = StrategyCreate(name="测试", slice_ids=[])
        assert data.slice_ids == []

    def test_slice_ids_defaults_empty(self):
        """不传 slice_ids 时默认为空列表"""
        data = StrategyCreate(name="测试")
        assert data.slice_ids == []

    def test_with_brand_brief(self):
        brief = BrandBrief(subject="test", analysis_goal="awareness")
        data = StrategyCreate(name="策略", slice_ids=[1], brand_brief=brief)
        assert data.brand_brief.subject == "test"
        assert data.brand_brief.analysis_goal == "awareness"

    def test_with_brand_brief_dict(self):
        """brand_brief 支持 dict 形式传入（Pydantic 自动转换）"""
        brief = {"subject": "test", "analysis_goal": "awareness"}
        data = StrategyCreate(name="策略", slice_ids=[1], brand_brief=brief)
        assert data.brand_brief.subject == "test"


class TestStrategyUpdate:
    """StrategyUpdate 校验"""

    def test_empty_update(self):
        data = StrategyUpdate()
        assert data.name is None
        assert data.brand_brief is None

    def test_name_update(self):
        data = StrategyUpdate(name="新名称")
        assert data.name == "新名称"

    def test_name_min_length(self):
        with pytest.raises(ValidationError):
            StrategyUpdate(name="")


class TestPhaseResultEdit:
    """PhaseResultEdit 校验"""

    def test_valid_result(self):
        data = PhaseResultEdit(result={"key": "value"})
        assert data.result == {"key": "value"}

    def test_result_required(self):
        with pytest.raises(ValidationError):
            PhaseResultEdit()
