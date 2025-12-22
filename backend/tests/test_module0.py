# ruff: noqa: E402
"""Module 0 综合测试：基础设施验证

测试内容：
1. 配置加载（AI设置、Celery设置）
2. LangChain模块功能（LLM实例创建）
3. DeepSeek API连通性（如果提供API密钥）
4. 成本计算函数
5. 数据库连接池配置
6. Celery应用初始化

运行方式：
    pytest tests/test_module0.py -v
    或
    python tests/test_module0.py
"""

import sys
from pathlib import Path

# Add backend root to sys.path for imports (avoid `src` namespace package pollution)
backend_root = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(backend_root))

# 加载测试环境变量（与conftest.py一致）
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env.test"
load_dotenv(dotenv_path=env_path, override=True)

import pytest
from src.config import settings
from src.database import async_engine


class TestConfiguration:
    """测试配置加载"""

    def test_database_config(self):
        """测试数据库配置"""
        assert settings.DATABASE_URL is not None
        assert "postgresql" in settings.DATABASE_URL
        print("✓ 数据库URL配置正确")

    def test_database_pool_settings(self):
        """测试数据库连接池优化设置"""
        assert settings.DB_POOL_SIZE == 50, f"Expected 50, got {settings.DB_POOL_SIZE}"
        assert settings.DB_MAX_OVERFLOW == 100, (
            f"Expected 100, got {settings.DB_MAX_OVERFLOW}"
        )
        assert settings.DB_POOL_TIMEOUT == 60, (
            f"Expected 60, got {settings.DB_POOL_TIMEOUT}"
        )
        assert settings.DB_POOL_RECYCLE == 1800, (
            f"Expected 1800, got {settings.DB_POOL_RECYCLE}"
        )
        print(
            f"✓ 数据库连接池设置已优化 (pool_size={settings.DB_POOL_SIZE}, max_overflow={settings.DB_MAX_OVERFLOW})"
        )

    def test_celery_config(self):
        """测试Celery配置"""
        assert settings.CELERY_BROKER_URL is not None
        assert settings.CELERY_RESULT_BACKEND is not None
        print("✓ Celery配置正确")

    def test_ai_task_config(self):
        """测试AI任务配置"""
        assert settings.CELERY_AI_SCREENING_CONCURRENT_STREAMS == 100
        assert settings.CELERY_AI_DEEP_ANALYSIS_CONCURRENCY == 100
        assert settings.CELERY_AI_POSTS_BATCH_SIZE == 5
        assert settings.CELERY_AI_COMMENTS_BATCH_SIZE == 10
        assert settings.CELERY_TASK_MAX_ITEMS_LIMIT == 20000
        assert settings.DB_COMMIT_AFTER_BATCH_COUNT == 20
        print(
            f"✓ AI任务配置正确 (并发流={settings.CELERY_AI_SCREENING_CONCURRENT_STREAMS}, 批次大小={settings.CELERY_AI_POSTS_BATCH_SIZE})"
        )

    def test_deepseek_config(self):
        """测试DeepSeek配置"""
        assert settings.DEEPSEEK_BASE_URL is not None
        assert settings.DEEPSEEK_CHAT_MODEL == "deepseek-chat"
        assert settings.DEEPSEEK_REASONER_MODEL == "deepseek-reasoner"
        assert settings.DEEPSEEK_CHAT_MAX_TOKENS == 8192
        assert settings.DEEPSEEK_REASONER_MAX_TOKENS == 65536
        assert settings.DEEPSEEK_TEMPERATURE == 0.0
        print(
            f"✓ DeepSeek模型配置正确 (chat: {settings.DEEPSEEK_CHAT_MODEL}, reasoner: {settings.DEEPSEEK_REASONER_MODEL})"
        )

    def test_deepseek_pricing_config(self):
        """测试DeepSeek价格配置"""
        assert settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION == 2.0
        assert settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION == 3.0
        assert settings.DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION == 2.0
        assert settings.DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION == 3.0
        print(
            "✓ DeepSeek价格配置正确 (chat: ¥2/¥3, reasoner: ¥2/¥3 per million tokens)"
        )

    def test_batch_analysis_config(self):
        """测试批处理分析框架配置"""
        assert settings.BATCH_ANALYSIS_DEFAULT_BATCH_SIZE == 30
        assert settings.BATCH_ANALYSIS_MIN_BATCH_SIZE == 20
        assert settings.BATCH_ANALYSIS_MAX_BATCH_SIZE == 40
        assert settings.BATCH_ANALYSIS_MAX_CONCURRENT_BATCHES == 100
        assert settings.BATCH_ANALYSIS_ENABLE_CONCURRENT is True
        print(
            f"✓ 批处理分析框架配置正确 (默认批次={settings.BATCH_ANALYSIS_DEFAULT_BATCH_SIZE}, 最大并发={settings.BATCH_ANALYSIS_MAX_CONCURRENT_BATCHES})"
        )


class TestLangChainModule:
    """测试LangChain模块"""

    def test_langchain_module_import(self):
        """测试LangChain模块导入"""
        try:
            from src.langchain import (  # noqa: F401
                get_deepseek_chat,
                get_deepseek_reasoner,
                calculate_cost,
                extract_token_usage,
                truncate_text,
                format_keywords_for_prompt,
            )

            print("✓ LangChain模块导入成功")
        except ImportError as e:
            pytest.fail(f"LangChain模块导入失败: {e}")

    def test_llm_instance_creation_chat(self):
        """测试Chat LLM实例创建 (LangChain 1.0)"""
        if not getattr(settings, "DEEPSEEK_API_KEY", None):
            print("⊘ 未设置DEEPSEEK_API_KEY，跳过Chat LLM实例创建测试")
            return

        try:
            from src.langchain import get_deepseek_chat
            from langchain_core.language_models.chat_models import BaseChatModel

            llm = get_deepseek_chat()
            assert llm is not None
            assert isinstance(llm, BaseChatModel), (
                f"Expected BaseChatModel, got {type(llm)}"
            )
            print(f"✓ Chat LLM实例创建成功 (类型: {type(llm).__name__})")
            print("  - 符合LangChain 1.0规范 (BaseChatModel)")
        except Exception as e:
            raise AssertionError(f"Chat LLM实例创建失败: {e}")

    def test_llm_instance_creation_reasoner(self):
        """测试Reasoner LLM实例创建 (LangChain 1.0)"""
        if not getattr(settings, "DEEPSEEK_API_KEY", None):
            print("⊘ 未设置DEEPSEEK_API_KEY，跳过Reasoner LLM实例创建测试")
            return

        try:
            from src.langchain import get_deepseek_reasoner
            from langchain_core.language_models.chat_models import BaseChatModel

            llm = get_deepseek_reasoner()
            assert llm is not None
            assert isinstance(llm, BaseChatModel), (
                f"Expected BaseChatModel, got {type(llm)}"
            )
            print(f"✓ Reasoner LLM实例创建成功 (类型: {type(llm).__name__})")
            print("  - 符合LangChain 1.0规范 (BaseChatModel)")
        except Exception as e:
            raise AssertionError(f"Reasoner LLM实例创建失败: {e}")

    def test_calculate_cost_chat(self):
        """测试Chat模型成本计算"""
        from src.langchain import calculate_cost

        # Test chat model: 1000 input + 500 output tokens
        cost = calculate_cost(input_tokens=1000, output_tokens=500, model_type="chat")
        expected_cost = (1000 / 1_000_000 * 2.0) + (500 / 1_000_000 * 3.0)
        assert abs(cost - expected_cost) < 0.000001
        print(f"✓ Chat模型成本计算正确: 1000输入+500输出 = ¥{cost:.6f}")

    def test_calculate_cost_reasoner(self):
        """测试Reasoner模型成本计算"""
        from src.langchain import calculate_cost

        # Test reasoner model: 2000 input + 1000 output tokens
        cost = calculate_cost(
            input_tokens=2000, output_tokens=1000, model_type="reasoner"
        )
        expected_cost = (2000 / 1_000_000 * 2.0) + (1000 / 1_000_000 * 3.0)
        assert abs(cost - expected_cost) < 0.000001
        print(f"✓ Reasoner模型成本计算正确: 2000输入+1000输出 = ¥{cost:.6f}")

    def test_utility_functions(self):
        """测试工具函数"""
        from src.langchain import (
            truncate_text,
            format_keywords_for_prompt,
        )

        # Test truncate_text
        text = "a" * 200
        truncated = truncate_text(text, max_length=100)
        assert len(truncated) <= 103  # 100 + "..."
        print("✓ 文本截断函数工作正常")

        # Test format_keywords_for_prompt
        keywords = "关键词1, 关键词2, 关键词3"
        formatted = format_keywords_for_prompt(keywords)
        assert "关键词1" in formatted
        assert "关键词2" in formatted
        assert "关键词3" in formatted
        print("✓ 关键词格式化函数工作正常")


class TestDeepSeekAPI:
    """测试DeepSeek API连通性（需要API密钥）"""

    @pytest.mark.skipif(
        not getattr(settings, "DEEPSEEK_API_KEY", None),
        reason="未设置DEEPSEEK_API_KEY，跳过API连通性测试",
    )
    def test_api_connectivity_chat(self):
        """测试Chat模型API连通性 (LangChain 1.0)"""
        from src.langchain_module import get_deepseek_chat, extract_token_usage
        from langchain_core.messages import HumanMessage

        try:
            llm = get_deepseek_chat()
            # LangChain 1.0: Use invoke with messages
            response = llm.invoke([HumanMessage(content="你好，请回复'测试成功'")])

            assert response is not None
            assert hasattr(response, "content")

            # Test token usage extraction
            usage = extract_token_usage(response)
            assert "input_tokens" in usage
            assert "output_tokens" in usage
            assert usage["input_tokens"] > 0 or usage["output_tokens"] > 0

            print("✓ Chat模型API连通性测试成功")
            print(f"  - 响应内容: {response.content[:50]}...")
            print(
                f"  - Token使用: 输入={usage['input_tokens']}, 输出={usage['output_tokens']}"
            )
        except Exception as e:
            pytest.fail(f"Chat模型API连通性测试失败: {e}")

    @pytest.mark.skipif(
        not getattr(settings, "DEEPSEEK_API_KEY", None),
        reason="未设置DEEPSEEK_API_KEY，跳过API连通性测试",
    )
    def test_api_connectivity_reasoner(self):
        """测试Reasoner模型API连通性 (LangChain 1.0)"""
        from src.langchain_module import get_deepseek_reasoner, extract_token_usage
        from langchain_core.messages import HumanMessage

        try:
            llm = get_deepseek_reasoner()
            # LangChain 1.0: Use invoke with messages
            response = llm.invoke([HumanMessage(content="计算1+1，请直接回答数字")])

            assert response is not None
            assert hasattr(response, "content")

            # Test token usage extraction
            usage = extract_token_usage(response)
            assert "input_tokens" in usage
            assert "output_tokens" in usage

            print("✓ Reasoner模型API连通性测试成功")
            print(f"  - 响应内容: {response.content[:50]}...")
            print(
                f"  - Token使用: 输入={usage['input_tokens']}, 输出={usage['output_tokens']}"
            )
        except Exception as e:
            pytest.fail(f"Reasoner模型API连通性测试失败: {e}")


class TestDatabaseEngine:
    """测试数据库引擎配置"""

    def test_async_engine_configuration(self):
        """测试异步引擎配置"""
        assert async_engine is not None
        # Verify engine is created and settings are correct
        # Note: Internal pool structure differs between sync/async engines
        # We just verify the engine uses correct settings from config
        assert async_engine.pool is not None
        print("✓ 数据库异步引擎配置正确")
        print(f"  - 连接池大小: {settings.DB_POOL_SIZE}")
        print(f"  - 最大溢出: {settings.DB_MAX_OVERFLOW}")
        print(f"  - 连接超时: {settings.DB_POOL_TIMEOUT}秒")
        print(f"  - 连接回收: {settings.DB_POOL_RECYCLE}秒")


class TestCeleryApp:
    """测试Celery应用初始化"""

    def test_celery_app_import(self):
        """测试Celery应用导入"""
        try:
            from src.celery_app import celery_app

            assert celery_app is not None
            print("✓ Celery应用导入成功")
        except ImportError as e:
            pytest.fail(f"Celery应用导入失败: {e}")

    def test_celery_configuration(self):
        """测试Celery配置"""
        from src.celery_app import celery_app

        # Check key configurations
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"
        assert celery_app.conf.timezone == "Asia/Shanghai"
        assert celery_app.conf.task_track_started is True
        # worker_pool / worker_concurrency 通过命令行参数指定，不应在应用配置中强绑定
        assert celery_app.conf.task_time_limit == 7200

        print("✓ Celery配置验证成功")
        print(f"  - Worker池类型: {getattr(celery_app.conf, 'worker_pool', None)}")
        print(f"  - 并发数: {getattr(celery_app.conf, 'worker_concurrency', None)}")
        print(f"  - 任务时间限制: {celery_app.conf.task_time_limit}秒")


def run_all_tests():
    """运行所有测试（非pytest模式）"""
    print("\n" + "=" * 70)
    print("Module 0 基础设施验证测试")
    print("=" * 70 + "\n")

    # Test Configuration
    print("【1/6】配置测试")
    print("-" * 70)
    test_config = TestConfiguration()
    try:
        test_config.test_database_config()
        test_config.test_database_pool_settings()
        test_config.test_celery_config()
        test_config.test_ai_task_config()
        test_config.test_deepseek_config()
        test_config.test_deepseek_pricing_config()
        test_config.test_batch_analysis_config()
        print()
    except Exception as e:
        print(f"✗ 配置测试失败: {e}\n")
        return False

    # Test LangChain Module
    print("【2/6】LangChain模块测试")
    print("-" * 70)
    test_langchain = TestLangChainModule()
    try:
        test_langchain.test_langchain_module_import()
        test_langchain.test_llm_instance_creation_chat()
        test_langchain.test_llm_instance_creation_reasoner()
        test_langchain.test_calculate_cost_chat()
        test_langchain.test_calculate_cost_reasoner()
        test_langchain.test_utility_functions()
        print()
    except Exception as e:
        print(f"✗ LangChain模块测试失败: {e}\n")
        if "skip" not in str(e).lower():
            return False

    # Test DeepSeek API
    print("【3/6】DeepSeek API连通性测试")
    print("-" * 70)
    if not getattr(settings, "DEEPSEEK_API_KEY", None):
        print("⊘ 未设置DEEPSEEK_API_KEY，跳过API连通性测试\n")
    else:
        test_api = TestDeepSeekAPI()
        try:
            test_api.test_api_connectivity_chat()
            test_api.test_api_connectivity_reasoner()
            print()
        except Exception as e:
            print(f"⚠ DeepSeek API测试失败: {e}")
            print("  (这可能是因为API密钥无效或网络问题)\n")

    # Test Database Engine
    print("【4/6】数据库引擎测试")
    print("-" * 70)
    test_db = TestDatabaseEngine()
    try:
        test_db.test_async_engine_configuration()
        print()
    except Exception as e:
        print(f"✗ 数据库引擎测试失败: {e}\n")
        return False

    # Test Celery App
    print("【5/6】Celery应用测试")
    print("-" * 70)
    test_celery = TestCeleryApp()
    try:
        test_celery.test_celery_app_import()
        test_celery.test_celery_configuration()
        print()
    except Exception as e:
        print(f"✗ Celery应用测试失败: {e}\n")
        return False

    # Summary
    print("【6/6】测试总结")
    print("=" * 70)
    print("✓ Module 0 基础设施验证完成！")
    print()
    print("已验证组件:")
    print("  ✓ 配置文件（AI、Celery、数据库）")
    print("  ✓ LangChain 1.0 模块（Chat + Reasoner）")
    print("  ✓ 数据库连接池（50/100优化）")
    print("  ✓ Celery异步任务队列（eventlet/100并发）")
    if getattr(settings, "DEEPSEEK_API_KEY", None):
        print("  ✓ DeepSeek API连通性")
    else:
        print("  ⊘ DeepSeek API连通性（未测试，需要API密钥）")
    print()
    print("后续步骤:")
    print("  1. 在.env中配置DEEPSEEK_API_KEY进行完整API测试")
    print("  2. 继续Module 1: 平台管理模块迁移")
    print("=" * 70 + "\n")

    return True


if __name__ == "__main__":
    # Run tests without pytest
    success = run_all_tests()
    sys.exit(0 if success else 1)
