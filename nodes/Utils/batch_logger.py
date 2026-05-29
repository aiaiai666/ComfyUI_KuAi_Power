"""批量处理日志工具函数"""

import json
from datetime import datetime
from typing import Dict, Any


def format_progress_log(progress: Dict[str, Any]) -> str:
    """
    格式化进度日志

    Args:
        progress: 包含 current, total, status, task_id, elapsed_time 的字典

    Returns:
        格式化的日志字符串
    """
    current = progress.get("current", 0)
    total = progress.get("total", 0)
    status = progress.get("status", "unknown")
    task_id = progress.get("task_id", "")
    elapsed = progress.get("elapsed_time", 0)

    percentage = (current / total * 100) if total > 0 else 0
    timestamp = datetime.now().strftime("%H:%M:%S")

    return f"[{timestamp}] 进度: {current}/{total} ({percentage:.1f}%) | 任务: {task_id} | 状态: {status} | 耗时: {elapsed:.1f}s"


def format_task_status(task: Dict[str, Any], show_details: bool = True) -> str:
    """
    格式化单个任务状态

    Args:
        task: 任务信息字典
        show_details: 是否显示详细信息

    Returns:
        格式化的任务状态字符串
    """
    idx = task.get("idx", task.get("task_idx", 0))
    status = task.get("status", "unknown")
    prompt = task.get("prompt", "")

    # 状态图标
    status_icon = {
        "completed": "✓",
        "failed": "✗",
        "processing": "⟳",
        "pending": "○"
    }.get(status, "?")

    # 基础信息
    line = f"  [{idx}] {status_icon} {status.upper()}"

    if show_details:
        # 添加提示词（截断）
        prompt_short = prompt[:50] + "..." if len(prompt) > 50 else prompt
        line += f" | {prompt_short}"

        # 添加结果信息
        if status == "completed":
            video_url = task.get("video_url", "")
            local_path = task.get("local_path", "")
            if local_path:
                line += f" | 已保存: {local_path}"
            elif video_url:
                line += f" | URL: {video_url[:50]}..."
        elif status == "failed":
            error = task.get("error", "未知错误")
            line += f" | 错误: {error}"

    return line


def format_batch_report(report_data: Dict[str, Any], verbose: bool = True) -> str:
    """
    格式化批量处理报告

    Args:
        report_data: 包含 total, success, failed, tasks 的字典
        verbose: 是否显示详细信息

    Returns:
        格式化的报告字符串
    """
    total = report_data.get("total", 0)
    success = report_data.get("success", 0)
    failed = report_data.get("failed", 0)
    tasks = report_data.get("tasks", [])

    lines = [
        "",
        "=" * 70,
        "📊 批量处理报告",
        "=" * 70,
        f"总计: {total}  |  成功: {success} ✓  |  失败: {failed} ✗",
        f"成功率: {(success/total*100):.1f}%" if total > 0 else "成功率: 0%",
        "=" * 70,
    ]

    if verbose and tasks:
        # 成功任务
        success_tasks = [t for t in tasks if t.get("status") == "completed"]
        if success_tasks:
            lines.append("")
            lines.append("✓ 成功任务:")
            for task in sorted(success_tasks, key=lambda x: x.get("idx", x.get("task_idx", 0))):
                lines.append(format_task_status(task, show_details=True))

        # 失败任务
        failed_tasks = [t for t in tasks if t.get("status") != "completed"]
        if failed_tasks:
            lines.append("")
            lines.append("✗ 失败任务:")
            for task in sorted(failed_tasks, key=lambda x: x.get("idx", x.get("task_idx", 0))):
                lines.append(format_task_status(task, show_details=True))

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)
