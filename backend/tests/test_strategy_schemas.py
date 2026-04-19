"""策略 Schemas 单元测试"""

import pytest
from pydantic import ValidationError

from src.strategies.schemas import BrandBrief, StrategyCreate, StrategyUpdate, StageResultEdit


class TestStrategyCreate:
    """StrategyCreate 校验"""

    def test_valid_create(self):
        data = StrategyCreate(name="测试策略")
        assert data.name == "测试策略"
        assert data.brand_brief is None

    def test_name_min_length(self):
        with pytest.raises(ValidationError):
            StrategyCreate(name="")

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            StrategyCreate(name="x" * 256)

    def test_name_at_max_length(self):
        data = StrategyCreate(name="x" * 255)
        assert len(data.name) == 255

    def test_with_brand_brief(self):
        brief = BrandBrief(subject="test", analysis_goal="awareness")
        data = StrategyCreate(name="策略", brand_brief=brief)
        assert data.brand_brief.subject == "test"
        assert data.brand_brief.analysis_goal == "awareness"

    def test_with_brand_brief_dict(self):
        """brand_brief 支持 dict 形式传入（Pydantic 自动转换）"""
        brief = {"subject": "test", "analysis_goal": "awareness"}
        data = StrategyCreate(name="策略", brand_brief=brief)
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


class TestStageResultEdit:
    """StageResultEdit 校验"""

    def test_valid_result(self):
        data = StageResultEdit(result={"key": "value"})
        assert data.result == {"key": "value"}

    def test_result_required(self):
        with pytest.raises(ValidationError):
            StageResultEdit()
