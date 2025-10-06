import pytest

from types import SimpleNamespace

from src.tasks.orchestrator.dispatcher import TaskDispatcher
from src.tasks.orchestrator.queue import TaskQueue
from src.tasks.orchestrator.validator import TaskValidationError, TaskValidator


class DummyQueue(TaskQueue):
    def __init__(self) -> None:
        self.enqueue_calls: list[tuple[int, dict]] = []
        self.pause_calls: list[int] = []
        self.stop_calls: list[int] = []

    def enqueue_start(self, task_id: int, payload: dict) -> str:
        self.enqueue_calls.append((task_id, payload))
        return "job-123"

    def enqueue_pause(self, task_id: int) -> None:
        self.pause_calls.append(task_id)

    def enqueue_stop(self, task_id: int) -> None:
        self.stop_calls.append(task_id)


@pytest.mark.asyncio
async def test_dispatcher_enqueues_task_successfully():
    validator = TaskValidator()
    queue = DummyQueue()
    dispatcher = TaskDispatcher(validator, queue)

    task = SimpleNamespace(
        id=1,
        config={"keywords": "ai"},
        platform="xhs",
        crawler_type="search",
        status=None,
    )

    job_id = await dispatcher.start_task(task)

    assert job_id == "job-123"
    assert queue.enqueue_calls == [
        (1, {"config": {"keywords": "ai"}, "platform": "xhs", "crawler_type": "search"})
    ]


@pytest.mark.asyncio
async def test_dispatcher_validation_failure():
    validator = TaskValidator()
    queue = DummyQueue()
    dispatcher = TaskDispatcher(validator, queue)

    task = SimpleNamespace(
        id=2,
        config="invalid",  # 非 dict 将触发校验错误
        platform="xhs",
        crawler_type="search",
        status=None,
    )

    with pytest.raises(TaskValidationError):
        await dispatcher.start_task(task)

    assert queue.enqueue_calls == []
