#!/usr/bin/env python3
"""
测试 crawler-web 的小红书签名功能
验证 b1 默认值和签名生成是否正常工作
"""
import asyncio
import sys
import os

# 添加src到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from signing.platforms.xhs import javascript


async def test_signature():
    """测试签名生成"""

    print("=" * 60)
    print("🧪 测试 crawler-web XiaoHongShu 签名服务")
    print("=" * 60)

    # 测试数据
    test_cookie = "gid=yjy28Ji00y0yyjy28Ji02CDSid2lxyxxivi4CWv4EyxMDlq84Jlq9A888YYKY2q8fy0fSdJj; a1=192d859b9eewf19yw9k96pnk6x2m5i23zl0bzzkmj50000598930; webId=bb33e484cc4ee0eabcf4acb16f80ac4d; web_session=0400698c35612bdc3e71df3c0c344b5cb4de36"

    test_payload = {
        "uri": "/api/sns/web/v1/search/notes",
        "data": {
            "keyword": "deepseek",
            "page": 1,
            "page_size": 20,
            "search_id": "test123",
            "sort": "general",
            "note_type": 0
        },
        "cookies": test_cookie,
        "b1": ""  # 测试空b1，应该使用默认值
    }

    print("\n📋 测试参数:")
    print(f"  URI: {test_payload['uri']}")
    print(f"  Keyword: {test_payload['data']['keyword']}")
    print(f"  Cookie (前50字符): {test_cookie[:50]}...")
    print(f"  b1: {'(空 - 应使用默认值)' if not test_payload['b1'] else test_payload['b1'][:50]}")

    try:
        print("\n⏳ 正在生成签名...")

        # 检查签名服务是否可用
        if not javascript.is_available():
            print("❌ JavaScript 签名引擎不可用!")
            print("   请确保已安装 PyExecJS 和 Node.js")
            return False

        print("✅ JavaScript 签名引擎已就绪")

        # 启用详细日志
        import logging
        logging.basicConfig(level=logging.DEBUG)

        # 生成签名
        result = await javascript.generate_signature(test_payload)

        print("\n✅ 签名生成成功!")
        print("\n📊 签名结果:")
        print(f"  X-s: {result.get('x-s', '')[:50]}...")
        print(f"  X-t: {result.get('x-t', '')}")
        print(f"  x-s-common: {result.get('x-s-common', '')[:50]}...")
        print(f"  x-b3-traceid: {result.get('x-b3-traceid', '')}")

        x_mns_value = result.get('x-mns', '')
        print(f"  x-mns: {x_mns_value[:50] if x_mns_value else '(未生成或为空)'}...")
        print(f"  x-mns类型: {type(x_mns_value)}, 长度: {len(str(x_mns_value)) if x_mns_value else 0}")
        print(f"  x-mns完整值: {repr(x_mns_value)}")

        # 验证关键字段
        print("\n🔍 验证结果:")
        checks = []

        if result.get('x-s'):
            checks.append("✅ X-s 已生成")
        else:
            checks.append("❌ X-s 缺失")

        if result.get('x-t'):
            checks.append("✅ X-t 已生成")
        else:
            checks.append("❌ X-t 缺失")

        if result.get('x-s-common'):
            checks.append("✅ x-s-common 已生成")
        else:
            checks.append("❌ x-s-common 缺失")

        if result.get('x-b3-traceid'):
            checks.append("✅ x-b3-traceid 已生成")
        else:
            checks.append("❌ x-b3-traceid 缺失")

        if result.get('x-mns'):
            checks.append("✅ x-mns 已生成")
        else:
            checks.append("❌ x-mns 缺失")

        for check in checks:
            print(f"  {check}")

        # 检查是否所有必需字段都存在
        all_present = all([
            result.get('x-s'),
            result.get('x-t'),
            result.get('x-s-common'),
            result.get('x-b3-traceid'),
            result.get('x-mns')
        ])

        if all_present:
            print("\n🎉 所有签名头部都已正确生成!")
            print("✅ b1 默认值修复生效")
            print("✅ 签名服务工作正常")
            return True
        else:
            print("\n⚠️  部分签名头部缺失，可能存在问题")
            return False

    except Exception as e:
        print(f"\n❌ 签名生成失败:")
        print(f"   错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("crawler-web 小红书签名服务测试")
    print("=" * 60)

    success = asyncio.run(test_signature())

    print("\n" + "=" * 60)
    if success:
        print("✅ 测试通过 - 签名服务正常工作")
        sys.exit(0)
    else:
        print("❌ 测试失败 - 签名服务存在问题")
        sys.exit(1)
