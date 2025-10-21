"""临时脚本：测试 Cookie 验证功能."""

import asyncio
from src.platforms.xhs.client import XhsClient


async def test_cookie_verification():
    """测试 Cookie 是否有效."""

    # 您的 Cookie
    cookie_str = """gid=yjy28Ji00y0yyjy28Ji02CDSid2lxyxxivi4CWv4EyxMDlq84Jlq9A888YYKY2q8fy0fSdJj; x-user-id-pgy.xiaohongshu.com=65aa4027c800000000000001; customerClientId=081338402857050; abRequestId=c002c392-dea1-55ca-99c9-857759412c90; a1=198e230d507rjm4bb2vtzrhn2ih7j3s2cpqb1gqfa30000243372; webId=3a949d2262765665cac36c9286581fa5; web_session=0400698ecf35bc56739ca09ed83a4b151270f4; webBuild=4.83.0; unread={%22ub%22:%2268f1e58f0000000004005329%22%2C%22ue%22:%2268f111c70000000007003555%22%2C%22uc%22:24}; xsecappid=xhs-pc-web; acw_tc=0a4a8a3a17607019444502691e330c37285477ce9deb262f53751cdb9adf03; loadts=1760702209464"""

    print("=" * 60)
    print("🔍 开始测试 Cookie 验证功能")
    print("=" * 60)
    print(f"\n📋 Cookie 前50字符: {cookie_str[:50]}...")
    print(f"📏 Cookie 长度: {len(cookie_str)} 字符\n")

    # 创建客户端
    client = XhsClient(cookies=cookie_str)

    try:
        # 执行验证
        print("⏳ 正在验证 Cookie...")
        is_valid, message = await client.verify_cookie()

        print("\n" + "=" * 60)
        if is_valid:
            print("✅ 验证结果: 成功")
            print(f"📝 信息: {message}")
        else:
            print("❌ 验证结果: 失败")
            print(f"📝 原因: {message}")
        print("=" * 60)

        return is_valid, message

    except Exception as e:
        print(f"\n❌ 测试过程出错: {e}")
        import traceback

        traceback.print_exc()
        return False, str(e)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_cookie_verification())
