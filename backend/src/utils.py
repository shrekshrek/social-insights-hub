"""
通用工具函数
包含 CPU 密集型任务处理等实用功能
"""

from typing import Callable, Any
from fastapi.concurrency import run_in_threadpool
import functools


async def run_cpu_bound_task(func: Callable, *args, **kwargs) -> Any:
    """
    在线程池中运行 CPU 密集型任务，避免阻塞事件循环

    Args:
        func: 要执行的同步函数
        *args: 函数位置参数
        **kwargs: 函数关键字参数

    Returns:
        函数执行结果

    Example:
        async def process_data(data: list):
            # CPU 密集型操作
            result = await run_cpu_bound_task(complex_calculation, data)
            return result
    """
    return await run_in_threadpool(func, *args, **kwargs)


def async_wrap(func: Callable) -> Callable:
    """
    装饰器：将同步函数包装为异步函数（在线程池中执行）

    Example:
        @async_wrap
        def heavy_computation(data):
            # CPU 密集型计算
            return result

        # 现在可以异步调用
        result = await heavy_computation(data)
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await run_in_threadpool(func, *args, **kwargs)

    return wrapper


# 示例：CPU 密集型任务
def calculate_fibonacci(n: int) -> int:
    """
    计算斐波那契数列（示例 CPU 密集型任务）

    Args:
        n: 要计算的位置

    Returns:
        斐波那契数列在位置 n 的值
    """
    if n <= 1:
        return n
    return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 2)


# 使用装饰器包装为异步函数
@async_wrap
def process_large_dataset(data: list) -> dict:
    """
    处理大型数据集（示例 CPU 密集型任务）

    Args:
        data: 要处理的数据列表

    Returns:
        处理结果统计
    """
    # 模拟 CPU 密集型操作
    result = {
        "count": len(data),
        "sum": sum(data) if all(isinstance(x, (int, float)) for x in data) else 0,
        "processed": True,
    }
    return result


# 示例：在路由中使用
"""
from src.utils import run_cpu_bound_task, calculate_fibonacci

@router.get("/compute/fibonacci/{n}")
async def compute_fibonacci(n: int):
    if n > 40:
        raise HTTPException(status_code=400, detail="Number too large")
    
    # 在线程池中运行 CPU 密集型任务
    result = await run_cpu_bound_task(calculate_fibonacci, n)
    return {"n": n, "result": result}
"""
