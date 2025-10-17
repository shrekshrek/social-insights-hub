"""XiaoHongShu platform adapter with real crawler implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from src.platforms.base import CrawlerAdapter, TaskExecutionContext
from src.data.notes import service as notes_service
from src.signing import SignatureGenerationError, generate_signature

from .client import XhsClient


class XiaoHongShuAdapter(CrawlerAdapter):
    """XiaoHongShu crawler adapter implementing search and detail modes."""

    name = "xhs"

    async def execute(self, context: TaskExecutionContext) -> None:
        """
        Execute XHS crawler task.

        Supports crawler_type:
        - search: Search notes by keywords
        - detail: Get note details by note_ids
        """
        config = context.task.config or {}
        crawler_type = context.task.crawler_type

        # Initialize client with account cookies and proxy
        cookies = context.account.cookies if context.account else None
        client = XhsClient(
            cookies=cookies,
            proxy=context.proxy,
            timeout=config.get("timeout", 30),
        )

        try:
            # Verify cookie before executing task
            if context.account and cookies:
                await context.log("INFO", "验证账号 Cookie 有效性...")
                is_valid, message = await client.verify_cookie()
                if is_valid:
                    await context.log("INFO", f"✅ {message}")
                else:
                    await context.log("ERROR", f"❌ Cookie 验证失败: {message}")
                    await context.log("WARNING", "Cookie 可能已过期或无效，建议更换账号")
                    # 继续执行，但用户已被警告
            elif not context.account:
                await context.log("WARNING", "未配置账号，将尝试匿名访问（可能无法获取数据）")

            if crawler_type == "search":
                await self._execute_search(context, client, config)
            elif crawler_type == "detail":
                await self._execute_detail(context, client, config)
            else:
                await context.log("ERROR", f"不支持的爬取模式: {crawler_type}")
                raise ValueError(f"Unsupported crawler_type: {crawler_type}")
        finally:
            await client.close()

    async def _execute_search(
        self,
        context: TaskExecutionContext,
        client: XhsClient,
        config: Dict[str, Any],
    ) -> None:
        """Execute search mode crawler."""
        # Get keywords
        keywords = config.get("keywords")
        if not keywords:
            await context.log("WARNING", "未配置关键词，跳过搜索")
            await context.update_progress(100, crawled_count=0)
            return

        keyword_list = [kw.strip() for kw in str(keywords).split(",") if kw.strip()]
        if not keyword_list:
            await context.log("WARNING", "关键词列表为空，跳过搜索")
            await context.update_progress(100, crawled_count=0)
            return

        # Get config
        max_count = config.get("max_count", 20)
        sort_type = config.get(
            "sort_type", "general"
        )  # general/popularity_descending/time_descending
        note_type = config.get("note_type", 0)  # 0=all, 1=video, 2=image
        enable_details = config.get("enable_details", False)

        await context.log(
            "INFO",
            f"开始搜索小红书笔记，关键词: {', '.join(keyword_list)}，"
            f"最大数量: {max_count}，排序: {sort_type}",
        )

        all_notes: List[Dict[str, Any]] = []
        total_keywords = len(keyword_list)

        for idx, keyword in enumerate(keyword_list, 1):
            try:
                await context.log(
                    "INFO", f"[{idx}/{total_keywords}] 搜索关键词: {keyword}"
                )

                # Generate signature
                try:
                    sig_data = await generate_signature(
                        "xhs",
                        {
                            "keyword": keyword,
                            "page": 1,
                            "sort": sort_type,
                        },
                    )
                    x_s = sig_data.get("x-s", "")
                    x_t = sig_data.get("x-t", "")
                    await context.log("DEBUG", f"签名生成成功: x-s={x_s[:20]}...")
                except SignatureGenerationError as exc:
                    await context.log("ERROR", f"关键词 {keyword} 签名失败: {exc}")
                    continue

                # Search notes
                notes = await client.search_notes(
                    keyword=keyword,
                    page=1,
                    page_size=min(max_count, 20),
                    sort_type=sort_type,
                    note_type=note_type,
                    x_s=x_s,
                    x_t=x_t,
                )

                if not notes:
                    await context.log("WARNING", f"关键词 {keyword} 未搜索到笔记")
                    continue

                await context.log(
                    "INFO", f"关键词 {keyword} 搜索到 {len(notes)} 条笔记"
                )

                # Add keyword to each note
                for note in notes:
                    note["keyword"] = keyword

                # Get note details if enabled
                if enable_details:
                    await context.log("INFO", f"开始获取 {len(notes)} 条笔记详情...")
                    detailed_notes = await self._fetch_note_details(
                        context, client, notes
                    )
                    all_notes.extend(detailed_notes)
                else:
                    all_notes.extend(notes)

                # Update progress
                progress = int(90 * idx / total_keywords)
                await context.update_progress(progress, crawled_count=len(all_notes))

                # Rate limiting
                if idx < total_keywords:
                    await asyncio.sleep(2)  # 2 seconds between keywords

            except Exception as exc:
                await context.log("ERROR", f"关键词 {keyword} 搜索失败: {exc}")
                continue

        # Save results
        if all_notes:
            await context.log("INFO", f"保存 {len(all_notes)} 条笔记到数据库...")
            await notes_service.bulk_save_notes_from_crawler(
                context.db,
                context.task.id,
                context.task.platform,
                all_notes,
            )

        await context.log("INFO", f"搜索任务完成，共获取 {len(all_notes)} 条笔记")
        await context.update_progress(100, crawled_count=len(all_notes))

    async def _execute_detail(
        self,
        context: TaskExecutionContext,
        client: XhsClient,
        config: Dict[str, Any],
    ) -> None:
        """Execute detail mode crawler."""
        # Get note IDs
        urls = config.get("urls", [])
        if not urls:
            await context.log("WARNING", "未配置笔记URL或ID，跳过详情爬取")
            await context.update_progress(100, crawled_count=0)
            return

        # Extract note IDs from URLs or use IDs directly
        note_ids = []
        for url in urls:
            if isinstance(url, str):
                # Extract note_id from URL: https://www.xiaohongshu.com/explore/xxxx
                if "explore/" in url:
                    note_id = url.split("explore/")[-1].split("?")[0]
                    note_ids.append(note_id)
                else:
                    note_ids.append(url)  # Assume it's already a note_id

        if not note_ids:
            await context.log("WARNING", "未能解析出有效的笔记ID")
            await context.update_progress(100, crawled_count=0)
            return

        await context.log("INFO", f"开始获取 {len(note_ids)} 条笔记详情...")

        # Fetch details
        notes = [{"note_id": nid} for nid in note_ids]
        detailed_notes = await self._fetch_note_details(context, client, notes)

        # Save results
        if detailed_notes:
            await context.log("INFO", f"保存 {len(detailed_notes)} 条笔记到数据库...")
            await notes_service.bulk_save_notes_from_crawler(
                context.db,
                context.task.id,
                context.task.platform,
                detailed_notes,
            )

        await context.log("INFO", f"详情任务完成，共获取 {len(detailed_notes)} 条笔记")
        await context.update_progress(100, crawled_count=len(detailed_notes))

    async def _fetch_note_details(
        self,
        context: TaskExecutionContext,
        client: XhsClient,
        notes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Fetch detailed information for notes."""
        detailed_notes = []
        total = len(notes)

        for idx, note in enumerate(notes, 1):
            note_id = note.get("note_id")
            if not note_id:
                continue

            try:
                # Generate signature
                sig_data = await generate_signature(
                    "xhs",
                    {"source_note_id": note_id},
                )
                x_s = sig_data.get("x-s", "")
                x_t = sig_data.get("x-t", "")

                # Get detail
                detail = await client.get_note_detail(
                    note_id=note_id,
                    x_s=x_s,
                    x_t=x_t,
                )

                if detail:
                    # Merge with original note data
                    merged = {**note, **detail}
                    detailed_notes.append(merged)
                    await context.log(
                        "DEBUG", f"[{idx}/{total}] 获取笔记详情成功: {note_id}"
                    )
                else:
                    await context.log(
                        "WARNING", f"[{idx}/{total}] 笔记详情为空: {note_id}"
                    )
                    detailed_notes.append(note)  # Use original data

                # Rate limiting
                if idx < total:
                    await asyncio.sleep(1)

            except Exception as exc:
                await context.log("WARNING", f"获取笔记详情失败 {note_id}: {exc}")
                detailed_notes.append(note)  # Use original data
                continue

        return detailed_notes
