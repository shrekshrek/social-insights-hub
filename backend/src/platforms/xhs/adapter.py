"""XiaoHongShu platform adapter (placeholder implementation)."""

from __future__ import annotations

from typing import List

from src.platforms.base import CrawlerAdapter, TaskExecutionContext
from src.signing import SignatureGenerationError, generate_signature
from src.results import service as result_service

from .client import XhsClient, XhsNote


class XiaoHongShuAdapter(CrawlerAdapter):
    name = "xhs"

    def __init__(self) -> None:
        self._client = XhsClient()

    async def execute(self, context: TaskExecutionContext) -> None:
        config = context.task.config or {}
        keywords = config.get("keywords")
        if not keywords:
            await context.log("WARNING", "未配置关键词，跳过小红书执行")
            await context.update_progress(100, crawled_count=0)
            return

        keyword_list = [kw.strip() for kw in str(keywords).split(",") if kw.strip()]
        if not keyword_list:
            await context.log("WARNING", "关键词列表为空，跳过执行")
            await context.update_progress(100, crawled_count=0)
            return

        await context.log(
            "INFO", f"开始执行小红书任务，关键词: {', '.join(keyword_list)}"
        )

        all_notes: List[XhsNote] = []
        for keyword in keyword_list:
            try:
                signature = await generate_signature(
                    "xhs",
                    {"keyword": keyword, "task_id": context.task.id},
                )
            except SignatureGenerationError as exc:
                await context.log("ERROR", f"关键词 {keyword} 签名失败: {exc}")
                raise

            await context.log(
                "DEBUG",
                f"关键词 {keyword} 签名成功: {signature.get('signature')}",
            )

            notes = await self._client.search_notes(
                keyword, limit=config.get("max_count", 5)
            )
            all_notes.extend(notes)
            await context.update_progress(
                max(
                    5,
                    min(
                        90,
                        int(90 * len(all_notes) / max(1, config.get("max_count", 5))),
                    ),
                ),
                crawled_count=len(all_notes),
            )

        db_session = getattr(context, "db", None)
        if all_notes and db_session is not None:
            await result_service.bulk_create_notes(
                db_session,
                context.task,
                [note.__dict__ for note in all_notes],
            )
        elif all_notes:
            await context.log("DEBUG", "Skipping result persistence because db session is not available")

        await context.log("INFO", f"共获取 {len(all_notes)} 条模拟笔记数据")
        await context.update_progress(100, crawled_count=len(all_notes))
        await context.log("INFO", "小红书任务执行完成")
