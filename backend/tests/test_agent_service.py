"""Agent Service 单元测试 — upload_result 状态校验

校验白名单语义 "can-receive-data" 状态集合的边界。背景：v2026.04 dedup 模型下
agent 端在 enable_checkpoint=1 时支持 failed → auto_retry 路径，云端必须允许 failed
状态的任务接收重传，否则数据丢失。具体见 _validate_upload_status 的 docstring。
"""

import logging

import pytest
from fastapi import HTTPException

from src.agent.service import _validate_upload_status


class TestValidateUploadStatus:
    """白名单内的状态不应抛出；白名单外应抛 409 INVALID_TASK_STATUS"""

    @pytest.mark.parametrize(
        "task_status",
        ["accepted", "running", "completed"],
    )
    def test_normal_statuses_pass(self, task_status):
        """正常上传路径：accepted / running / completed 直接放行"""
        # 不抛异常即通过
        _validate_upload_status(task_id=1, task_status=task_status)

    def test_pending_logs_warning_and_passes(self, caplog):
        """pending：timeout-reset 兜底路径，记 warning 但接收上传"""
        with caplog.at_level(logging.WARNING):
            _validate_upload_status(task_id=42, task_status="pending")

        assert any(
            "status=pending" in r.message and "42" in r.message
            for r in caplog.records
        )

    def test_failed_logs_info_and_passes(self, caplog):
        """failed：agent auto_retry 恢复路径，记 info 但接收上传（v2026.04 dedup 模型）"""
        with caplog.at_level(logging.INFO):
            _validate_upload_status(task_id=42, task_status="failed")

        assert any(
            "status=failed" in r.message and "auto_retry recovery" in r.message
            for r in caplog.records
        )

    @pytest.mark.parametrize(
        "task_status",
        ["probe_ready", "approved", "abandoned", "unknown"],
    )
    def test_disallowed_statuses_raise_409(self, task_status):
        """白名单外的状态应抛 409 INVALID_TASK_STATUS

        - probe_ready / approved：probe 完成后等待审查阶段，agent 不应再上传
        - 其他未知状态：兜底拒绝
        """
        with pytest.raises(HTTPException) as exc_info:
            _validate_upload_status(task_id=1, task_status=task_status)

        assert exc_info.value.status_code == 409
        detail = exc_info.value.detail
        assert detail["error_code"] == "INVALID_TASK_STATUS"
        assert task_status in detail["message"]

    def test_failed_recovery_does_not_raise_409(self):
        """回归保险：failed 状态绝不该走 409 分支（防止白名单被误改回退）

        本次修复的核心场景：agent enable_checkpoint=1 的 auto_retry 在 failed 状态下
        重传数据。如果云端拒绝，重传成功的数据会丢失。dedup 模型保证多次上传无副作用，
        因此 failed 必须留在白名单内。
        """
        # 不抛异常即通过；同时验证不是被 pending 分支误捕获
        _validate_upload_status(task_id=1, task_status="failed")
