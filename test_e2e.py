#!/usr/bin/env python3
"""端到端测试：创建任务 -> 执行 -> 查询笔记数据"""

import asyncio
import httpx
import json
import time

BASE_URL = "http://localhost:8000/api/v1"

async def main():
    print("=" * 60)
    print("端到端测试：笔记数据模块")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # 1. 登录获取 token
        print("\n[步骤 1] 登录获取 Token...")
        login_response = await client.post(
            f"{BASE_URL}/auth/token",
            data={"username": "admin", "password": "admin123"}
        )
        login_response.raise_for_status()
        token = login_response.json()["access_token"]
        print(f"✅ Token 获取成功: {token[:20]}...")

        headers = {"Authorization": f"Bearer {token}"}

        # 2. 创建测试任务
        print("\n[步骤 2] 创建测试爬虫任务...")
        task_data = {
            "name": "端到端测试-笔记数据模块",
            "platform": "xhs",
            "crawler_type": "search",
            "config": {
                "keywords": "旅游,美食",
                "max_count": 3,
                "sort_type": "general"
            }
        }

        create_response = await client.post(
            f"{BASE_URL}/crawler-tasks",
            json=task_data,
            headers=headers
        )
        create_response.raise_for_status()
        task = create_response.json()
        task_id = task["id"]
        print(f"✅ 任务创建成功")
        print(f"   任务ID: {task_id}")
        print(f"   任务名称: {task['name']}")
        print(f"   关键词: {task['config']['keywords']}")

        # 3. 启动任务
        print(f"\n[步骤 3] 启动任务 {task_id}...")
        start_response = await client.post(
            f"{BASE_URL}/crawler-tasks/{task_id}/start",
            headers=headers
        )
        start_response.raise_for_status()
        print(f"✅ 任务已启动")

        # 4. 等待任务完成
        print(f"\n[步骤 4] 等待任务执行完成...")
        max_wait = 60  # 最多等待60秒
        start_time = time.time()

        while time.time() - start_time < max_wait:
            status_response = await client.get(
                f"{BASE_URL}/crawler-tasks/{task_id}",
                headers=headers
            )
            status_response.raise_for_status()
            task_info = status_response.json()
            status = task_info["status"]

            print(f"   当前状态: {status} | 进度: {task_info.get('progress', 0)}%", end="\r")

            if status in ["completed", "failed"]:
                print()  # 换行
                if status == "completed":
                    print(f"✅ 任务执行完成")
                    print(f"   爬取数量: {task_info.get('crawled_count', 0)}")
                else:
                    print(f"❌ 任务执行失败")
                break

            await asyncio.sleep(2)
        else:
            print(f"\n⚠️  任务执行超时（超过 {max_wait} 秒）")

        # 5. 查询任务日志
        print(f"\n[步骤 5] 查询任务执行日志...")
        logs_response = await client.get(
            f"{BASE_URL}/crawler-tasks/{task_id}/logs",
            headers=headers
        )
        logs_response.raise_for_status()
        logs = logs_response.json()

        if logs:
            print(f"✅ 获取到 {len(logs)} 条日志")
            print("\n最近的日志：")
            for log in logs[-5:]:
                print(f"   [{log['level']}] {log['message']}")
        else:
            print("⚠️  未获取到日志")

        # 6. 查询任务关联的笔记数据（新数据模块）
        print(f"\n[步骤 6] 查询任务关联的笔记数据（新数据模块）...")
        notes_response = await client.get(
            f"{BASE_URL}/data/notes/tasks/{task_id}/notes",
            headers=headers
        )
        notes_response.raise_for_status()
        notes = notes_response.json()

        print(f"✅ 查询成功！获取到 {len(notes)} 条笔记数据")

        if notes:
            print("\n笔记详情：")
            for idx, note in enumerate(notes[:3], 1):
                print(f"\n  【笔记 {idx}】")
                print(f"    ID: {note['note_id']}")
                print(f"    标题: {note['title'][:50]}...")
                print(f"    作者: {note.get('author_name', 'N/A')}")
                print(f"    点赞: {note.get('liked_count', 0)} | "
                      f"收藏: {note.get('collected_count', 0)} | "
                      f"评论: {note.get('comment_count', 0)}")
                print(f"    爬取时间: {note['crawled_at']}")
        else:
            print("\n⚠️  未爬取到笔记数据（可能账号被风控或关键词无结果）")

        # 7. 查询笔记统计
        print(f"\n[步骤 7] 查询笔记统计...")
        count_response = await client.get(
            f"{BASE_URL}/data/notes/tasks/{task_id}/count",
            headers=headers
        )
        count_response.raise_for_status()
        count_data = count_response.json()
        print(f"✅ 任务 {task_id} 共关联 {count_data['note_count']} 条笔记")

        # 8. 查询所有笔记列表
        print(f"\n[步骤 8] 查询数据库中所有笔记...")
        all_notes_response = await client.get(
            f"{BASE_URL}/data/notes",
            params={"limit": 10},
            headers=headers
        )
        all_notes_response.raise_for_status()
        all_notes = all_notes_response.json()
        print(f"✅ 数据库中共有 {len(all_notes)} 条笔记（显示前10条）")

        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)

        # 返回结果摘要
        return {
            "task_id": task_id,
            "task_status": status,
            "notes_count": len(notes),
            "total_notes": len(all_notes),
        }

if __name__ == "__main__":
    result = asyncio.run(main())
    print(f"\n📊 结果摘要:")
    print(f"  - 任务ID: {result['task_id']}")
    print(f"  - 任务状态: {result['task_status']}")
    print(f"  - 本次爬取笔记数: {result['notes_count']}")
    print(f"  - 数据库总笔记数: {result['total_notes']}")
