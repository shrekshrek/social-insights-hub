"""
对比crawler-web和MediaCrawlerPro的签名生成
用于诊断为什么crawler-web返回空结果
"""
import asyncio
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from signing.platforms.xhs import javascript


async def test_signature():
    """测试签名生成"""

    # 测试数据 - 与crawler-web日志中的一致
    test_payload = {
        "uri": "/api/sns/web/v1/search/notes",
        "data": {
            "keyword": "六代机",
            "page": 1,
            "page_size": 4,
            "search_id": "2FHDH4DXN7NVH7FU9N37W",  # 使用相同的search_id
            "sort": "general",
            "note_type": 0,
        },
        "cookies": "gid=yjy28Ji00y0yyjy28Ji02CDSid2lxyxxivi4CWv4EyxMDlq84Jlq9A888YYKY2q8fy0fSdJj; x-user-id-pgy.xiaohongshu.com=65aa4027c800000000000001; customerClientId=081338402857050; abRequestId=c002c392-dea1-55ca-9a58-c6f94c28ff5b; a1=198e230d507rjm4bb2vt6e0z7kjdoqotqguttzgbq50000293192; webId=18a3d04f9cac4dcf10e8e6c3e97f3a3a; web_session=0400698e8d5bf0a6f1cfb41b1de3a4b0b8c4f2; unread={%22ub%22:%2268eb4e5400000000070373ac%22%2C%22ue%22:%2268eb4e5400000000070373ac%22%2C%22uc%22:19}; websectiga=4a7c29e42db0d5a8fd91c9ea78a8e5bb9dea94fefb7c7d00ec5270c56beafc44; sec_poison_id=9bbec9b0-aef9-41e8-a574-dc382e9ed08b; webBuild=4.50.0; xsecappid=xhs-pc-web; acw_tc=0a0b11831760960240785936e37407ddc8bf8c9ad98feb603bd3ad5cb69a8a",
    }

    print("=" * 80)
    print("🔍 签名测试 - crawler-web内置签名服务")
    print("=" * 80)

    try:
        print("\n📋 测试参数:")
        print(f"  URI: {test_payload['uri']}")
        print(f"  关键词: {test_payload['data']['keyword']}")
        print(f"  Cookie长度: {len(test_payload['cookies'])}")
        print(f"  Cookie前100字符: {test_payload['cookies'][:100]}...")

        # 提取a1
        a1 = ""
        for part in test_payload['cookies'].split(';'):
            part = part.strip()
            if part.startswith('a1='):
                a1 = part.split('=', 1)[1]
                break
        print(f"  a1: {a1[:20]}... (长度: {len(a1)})")

        print("\n⏳ 正在生成签名...")

        # 生成签名
        signature = await javascript.generate_signature(test_payload)

        print("\n✅ 签名生成成功!")
        print("\n📊 签名详情:")
        print(f"  X-s: {signature.get('x-s', '')[:60]}...")
        print(f"  X-t: {signature.get('x-t', '')}")
        print(f"  x-s-common: {signature.get('x-s-common', '')[:60]}...")
        print(f"  X-B3-Traceid: {signature.get('x-b3-traceid', '')}")
        print(f"  X-Mns: {signature.get('x-mns', '')[:60] if signature.get('x-mns') else '❌ 缺失'}...")

        # 检查关键字段
        print("\n🔍 关键字段检查:")
        issues = []
        if not signature.get('x-s'):
            issues.append("❌ x-s 缺失")
        else:
            print(f"  ✅ x-s: 存在 (长度: {len(signature.get('x-s', ''))})")

        if not signature.get('x-t'):
            issues.append("❌ x-t 缺失")
        else:
            print(f"  ✅ x-t: 存在")

        if not signature.get('x-s-common'):
            issues.append("❌ x-s-common 缺失")
        else:
            print(f"  ✅ x-s-common: 存在 (长度: {len(signature.get('x-s-common', ''))})")

        if not signature.get('x-b3-traceid'):
            issues.append("❌ x-b3-traceid 缺失")
        else:
            print(f"  ✅ x-b3-traceid: 存在")

        if not signature.get('x-mns'):
            issues.append("❌ X-Mns 缺失 - 这是关键问题!")
        else:
            print(f"  ✅ X-Mns: 存在 (长度: {len(signature.get('x-mns', ''))})")

        if issues:
            print("\n⚠️ 发现问题:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("\n✅ 所有必需字段都存在!")

        # 完整JSON输出
        print("\n📄 完整签名JSON:")
        print(json.dumps(signature, ensure_ascii=False, indent=2))

        return signature

    except Exception as e:
        print(f"\n❌ 签名生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def compare_with_logs():
    """与MediaCrawlerPro日志中的签名进行对比"""
    print("\n" + "=" * 80)
    print("📊 与MediaCrawlerPro对比")
    print("=" * 80)

    # MediaCrawlerPro成功时的特征
    print("\n✅ MediaCrawlerPro成功爬取特征:")
    print("  - 返回: Search notes res count:22")
    print("  - 数据: 20条笔记保存到JSON")
    print("  - Cookie: 相同的cookie (长度680)")

    print("\n❌ crawler-web失败特征:")
    print("  - 返回: {\"data\": {\"has_more\": false}, \"code\": 0}")
    print("  - 数据: 0条笔记")
    print("  - Cookie: 相同的cookie")

    print("\n🔍 可能的原因:")
    print("  1. X-Mns生成逻辑差异")
    print("  2. 签名参数顺序不同")
    print("  3. 时间戳差异")
    print("  4. User-Agent不匹配")
    print("  5. 小红书反爬限制 (频率/IP/环境)")


async def main():
    print("\n🚀 crawler-web签名诊断工具\n")

    # 测试签名生成
    signature = await test_signature()

    # 对比分析
    await compare_with_logs()

    print("\n" + "=" * 80)
    if signature and signature.get('x-mns'):
        print("✅ 签名生成正常，X-Mns存在")
        print("💡 建议: 问题可能是小红书API的反爬策略，尝试:")
        print("   1. 等待1-2小时后重试")
        print("   2. 重新获取最新Cookie")
        print("   3. 检查是否被IP限制")
    else:
        print("❌ 签名生成有问题，需要修复X-Mns生成逻辑")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
