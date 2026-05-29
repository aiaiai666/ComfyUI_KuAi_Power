"""实时批量处理监控节点 - 使用 WebSocket 推送实时进度"""

import threading
import asyncio
import time
from typing import Dict, Any

try:
    import server
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("[RealtimeBatchMonitor] 警告: 无法导入 server 模块，WebSocket 推送不可用")

from .batch_state import BatchProcessState


class RealtimeBatchMonitor:
    """实时批量处理监控节点 - 后台线程 + WebSocket 推送"""

    # 类级别的线程控制
    _monitor_thread = None
    _thread_controller = threading.Event()
    _thread_lock = threading.Lock()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "enable": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "启用/禁用实时监控"
                }),
            },
            "optional": {
                "refresh_rate": ("FLOAT", {
                    "default": 3.0,
                    "min": 1.0,
                    "max": 10.0,
                    "step": 0.5,
                    "tooltip": "刷新间隔（秒）"
                }),
                "max_tasks": ("INT", {
                    "default": 10,
                    "min": 5,
                    "max": 50,
                    "tooltip": "最多显示任务数"
                }),
                "max_logs": ("INT", {
                    "default": 50,
                    "min": 10,
                    "max": 200,
                    "tooltip": "最多显示日志条数"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "enable": "启用监控",
            "refresh_rate": "刷新间隔",
            "max_tasks": "最多显示任务数",
            "max_logs": "最多显示日志条数",
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("监控状态",)
    FUNCTION = "monitor"
    CATEGORY = "KuAi/Utils"
    OUTPUT_NODE = True

    def monitor(self, enable=True, refresh_rate=3.0, max_tasks=10, max_logs=50):
        """启动或停止实时监控"""
        try:
            if not WEBSOCKET_AVAILABLE:
                return {
                    "ui": {"text": ["WebSocket 不可用，无法启动实时监控"]},
                    "result": ("WebSocket 不可用",)
                }

            if enable:
                # 启动监控
                self._start_monitor(refresh_rate, max_tasks, max_logs)
                status = f"✓ 实时监控已启动\n刷新间隔: {refresh_rate}秒\n最多显示: {max_tasks}个任务, {max_logs}条日志"
            else:
                # 停止监控
                self._stop_monitor()
                status = "✗ 实时监控已停止"

            print(f"[RealtimeBatchMonitor] {status}")

            return {
                "ui": {"text": [status]},
                "result": (status,)
            }

        except Exception as e:
            error_msg = f"❌ 监控失败: {str(e)}"
            print(f"[RealtimeBatchMonitor] {error_msg}")
            return {
                "ui": {"text": [error_msg]},
                "result": (error_msg,)
            }

    @classmethod
    def _start_monitor(cls, refresh_rate: float, max_tasks: int, max_logs: int):
        """启动后台监控线程"""
        with cls._thread_lock:
            # 如果已有线程在运行，先停止
            if cls._monitor_thread and cls._monitor_thread.is_alive():
                print("[RealtimeBatchMonitor] 停止现有监控线程...")
                cls._thread_controller.set()
                cls._monitor_thread.join(timeout=5.0)

            # 重置控制器
            cls._thread_controller.clear()

            # 启动新线程
            cls._monitor_thread = threading.Thread(
                target=cls._monitor_loop_wrapper,
                args=(refresh_rate, max_tasks, max_logs),
                daemon=True,
                name="RealtimeBatchMonitor"
            )
            cls._monitor_thread.start()
            print(f"[RealtimeBatchMonitor] 监控线程已启动 (刷新间隔: {refresh_rate}s)")

    @classmethod
    def _stop_monitor(cls):
        """停止后台监控线程"""
        with cls._thread_lock:
            if cls._monitor_thread and cls._monitor_thread.is_alive():
                print("[RealtimeBatchMonitor] 停止监控线程...")
                cls._thread_controller.set()
                cls._monitor_thread.join(timeout=5.0)
                print("[RealtimeBatchMonitor] 监控线程已停止")

    @classmethod
    def _monitor_loop_wrapper(cls, refresh_rate: float, max_tasks: int, max_logs: int):
        """线程入口 - 包装 asyncio 事件循环"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(cls._monitor_loop(refresh_rate, max_tasks, max_logs))
        except Exception as e:
            print(f"[RealtimeBatchMonitor] 监控循环异常: {e}")
        finally:
            try:
                loop.close()
            except:
                pass

    @classmethod
    async def _monitor_loop(cls, refresh_rate: float, max_tasks: int, max_logs: int):
        """异步监控循环 - 定期读取状态并推送"""
        state_manager = BatchProcessState()
        last_session_id = None

        print(f"[RealtimeBatchMonitor] 监控循环开始 (间隔: {refresh_rate}s)")

        while not cls._thread_controller.is_set():
            try:
                # 读取当前状态
                state = state_manager.get_state()

                # 检查是否有活动会话
                session_id = state.get("session_id", "")
                if session_id:
                    # 计算统计信息
                    stats = state_manager.get_statistics()

                    # 准备推送数据
                    push_data = cls._format_push_data(state, stats, max_tasks, max_logs)

                    # 通过 WebSocket 推送
                    if WEBSOCKET_AVAILABLE:
                        server.PromptServer.instance.send_sync('kuai.batch.progress', push_data)

                    # 检测会话变化
                    if session_id != last_session_id:
                        print(f"[RealtimeBatchMonitor] 检测到新会话: {session_id}")
                        last_session_id = session_id

                    # 检测会话完成
                    total = state.get("total", 0)
                    completed = state.get("completed", 0)
                    failed = state.get("failed", 0)
                    if total > 0 and (completed + failed) >= total:
                        print(f"[RealtimeBatchMonitor] 会话完成: {session_id}")
                        # 发送完成通知
                        push_data["completed"] = True
                        server.PromptServer.instance.send_sync('kuai.batch.progress', push_data)

                # 等待下一次刷新
                await asyncio.sleep(refresh_rate)

            except Exception as e:
                print(f"[RealtimeBatchMonitor] 监控循环错误: {e}")
                await asyncio.sleep(refresh_rate)

        print("[RealtimeBatchMonitor] 监控循环结束")

    @classmethod
    def _format_push_data(cls, state: Dict[str, Any], stats: Dict[str, Any],
                          max_tasks: int, max_logs: int) -> Dict[str, Any]:
        """格式化推送数据"""
        # 基础信息
        data = {
            "session_id": state.get("session_id", ""),
            "start_time": state.get("start_time", ""),
            "last_update": state.get("last_update", ""),
            "total": state.get("total", 0),
            "completed": state.get("completed", 0),
            "failed": state.get("failed", 0),
            "processing": state.get("processing", 0),
            "statistics": stats,
            "completed": False  # 会话是否完成
        }

        # 计算进度百分比
        total = data["total"]
        if total > 0:
            data["progress"] = ((data["completed"] + data["failed"]) / total) * 100
        else:
            data["progress"] = 0

        # 最新任务列表（按更新时间倒序）
        tasks = state.get("tasks", [])
        if tasks:
            sorted_tasks = sorted(tasks, key=lambda x: x.get("update_time", ""), reverse=True)
            data["tasks"] = sorted_tasks[:max_tasks]
        else:
            data["tasks"] = []

        # 最新日志（按时间倒序）
        logs = state.get("logs", [])
        if logs:
            data["logs"] = logs[-max_logs:]  # 取最新的 N 条
        else:
            data["logs"] = []

        return data


NODE_CLASS_MAPPINGS = {
    "RealtimeBatchMonitor": RealtimeBatchMonitor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RealtimeBatchMonitor": "📡 实时批量监控",
}
