"""Grok CSV 并发批量处理器 — 从 CSV 读取任务，按批次并发提交、轮询、下载"""

import json
import os
import time
import requests
import hashlib
import concurrent.futures
from pathlib import Path

from ..Sora2.kuai_utils import env_or
from .grok import GrokCreateVideo as _GrokCreateVideo
from .grok import GrokQueryVideo as _GrokQueryVideo
from ..Utils.batch_state import BatchProcessState


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def _download(video_url: str, save_dir: str, prefix: str, timeout: int) -> str:
    """下载单个视频，返回相对路径；失败返回空串"""
    try:
        comfy_root = Path(__file__).parent.parent.parent.parent.parent
        out_dir = comfy_root / save_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.md5(video_url.encode()).hexdigest()[:8]
        filepath = out_dir / f"{prefix}_{url_hash}.mp4"
        resp = requests.get(video_url, timeout=timeout, stream=True)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return str(filepath.relative_to(comfy_root))
    except Exception as e:
        print(f"[GrokCSVConcurrent] 下载失败 ({prefix}): {e}")
        return ""


def _process_one_task(task_idx: int, task: dict,
                      default_model: str, default_aspect_ratio: str,
                      default_size: str, default_enhance: bool,
                      api_key: str, api_base: str,
                      save_dir: str, max_wait_time: int,
                      poll_interval: int, download_timeout: int,
                      state_manager: BatchProcessState = None) -> dict:
    """
    单任务完整流程：提交 → 轮询 → 下载。
    GrokCreateVideo.create() 统一处理文/图生视频：
      image_urls="" → 文生视频
      image_urls="https://..." → 图生视频
    返回包含 task_id / status / video_url / local_path / error 的字典。
    """
    result = {"task_idx": task_idx, "row": task.get("_row_number", task_idx),
              "prompt": "", "status": "error", "video_url": "", "local_path": "", "error": ""}
    try:
        prompt = task.get("prompt", "").strip()
        if not prompt:
            raise ValueError("prompt 不能为空")

        model         = task.get("model", default_model).strip() or default_model
        aspect_ratio  = task.get("aspect_ratio", default_aspect_ratio).strip() or default_aspect_ratio
        size          = task.get("size", default_size).strip() or default_size
        image_urls    = task.get("image_urls", "").strip()
        output_prefix = task.get("output_prefix", f"grok_{task_idx}").strip() or f"grok_{task_idx}"
        enhance_raw   = task.get("enhance_prompt", "true")
        enhance       = str(enhance_raw).strip().lower() in ("true", "1", "yes") if enhance_raw else default_enhance
        custom_model  = task.get("custom_model", "").strip()

        result["prompt"] = prompt

        # 更新状态：pending
        if state_manager:
            state_manager.update_task(task_idx, "pending", prompt=prompt)
            state_manager.add_log(task_idx, "INFO", f"任务准备就绪 | 提示词: {prompt[:50]}...")

        # 1. 提交任务
        creator = _GrokCreateVideo()
        task_id, status, _ = creator.create(
            prompt=prompt, model=model, aspect_ratio=aspect_ratio,
            size=size, enhance_prompt=enhance, api_key=api_key,
            image_urls=image_urls, api_base=api_base, custom_model=custom_model,
        )
        result["task_id"] = task_id
        result["status"] = status
        print(f"[GrokCSVConcurrent] [{task_idx}] 已提交 task_id={task_id}")

        # 更新状态：processing
        if state_manager:
            state_manager.update_task(task_idx, "processing", task_id=task_id)
            state_manager.add_log(task_idx, "INFO", f"任务已提交 | task_id: {task_id} | 模型: {model}")

        # 2. 轮询直到完成
        querier = _GrokQueryVideo()
        elapsed = 0
        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval
            try:
                # query 返回 (task_id, status, video_url, enhanced_prompt, status_update_time)
                _, status, video_url, _, _ = querier.query(task_id, api_key, api_base)
                result["status"] = status

                # 记录轮询日志
                if state_manager:
                    state_manager.add_log(task_idx, "DEBUG", f"轮询中 {elapsed}/{max_wait_time}s | 状态: {status}")

                if status == "completed" and video_url:
                    result["video_url"] = video_url
                    print(f"[GrokCSVConcurrent] [{task_idx}] 完成，下载中...")

                    # 更新状态：completed（下载前）
                    if state_manager:
                        state_manager.update_task(task_idx, "completed", video_url=video_url)
                        state_manager.add_log(task_idx, "INFO", f"生成完成 | 开始下载: {video_url[:60]}...")

                    local = _download(video_url, save_dir, output_prefix, download_timeout)
                    result["local_path"] = local

                    # 更新状态：completed（下载后）
                    if state_manager:
                        state_manager.update_task(task_idx, "completed", video_url=video_url, local_path=local)
                        state_manager.add_log(task_idx, "INFO", f"下载完成 | 保存至: {local}")

                    return result
                print(f"[GrokCSVConcurrent] [{task_idx}] 进行中 {elapsed}/{max_wait_time}s")
            except RuntimeError:
                raise  # 任务失败，停止轮询
            except Exception as e:
                print(f"[GrokCSVConcurrent] [{task_idx}] 查询出错（继续重试）: {e}")

        raise RuntimeError(f"超时 ({max_wait_time}s)")

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "failed"
        print(f"[GrokCSVConcurrent] [{task_idx}] ✗ {e}")

        # 更新状态：failed
        if state_manager:
            state_manager.update_task(task_idx, "failed", error=str(e))
            state_manager.add_log(task_idx, "ERROR", f"任务失败 | 错误: {str(e)}")

        return result


# ─────────────────────────────────────────────
# 节点
# ─────────────────────────────────────────────

class GrokCSVConcurrentProcessor:
    """
    Grok CSV 并发批量处理器

    完整闭环：
      CSVBatchReader → GrokCSVConcurrentProcessor → 视频自动保存到本地
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "batch_tasks": ("STRING", {
                    "forceInput": True,
                    "tooltip": "来自 CSVBatchReader 的任务列表 JSON"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "save_dir": ("STRING", {
                    "default": "output/grok",
                    "tooltip": "视频保存目录（相对 ComfyUI 根目录），按平台自动分类"
                }),
                "batch_size": ("INT", {
                    "default": 10, "min": 1, "max": 20,
                    "tooltip": "每批并发任务数（建议 5-10）"
                }),
                "default_model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)", "grok-video-3-15s (15秒)"],
                                  {"default": "grok-video-3 (6秒)", "tooltip": "CSV 中未指定 model 时的默认值"}),
                "default_aspect_ratio": (["2:3", "3:2", "1:1"],
                                         {"default": "3:2", "tooltip": "CSV 中未指定时的默认宽高比"}),
                "default_size": (["720P", "1080P"],
                                 {"default": "720P", "tooltip": "CSV 中未指定时的默认分辨率"}),
                "default_enhance_prompt": ("BOOLEAN", {"default": True}),
                "api_base": ("STRING", {"default": "https://api.kegeai.top"}),
                "max_wait_time": ("INT", {"default": 1200, "min": 60, "max": 3600,
                                          "tooltip": "单任务最大等待时间（秒）"}),
                "poll_interval": ("INT", {"default": 10, "min": 5, "max": 60}),
                "download_timeout": ("INT", {"default": 1800, "min": 30, "max": 9999}),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "batch_tasks": "批量任务",
            "api_key": "API密钥",
            "save_dir": "视频保存目录",
            "batch_size": "并发批次大小",
            "default_model": "默认模型",
            "default_aspect_ratio": "默认宽高比",
            "default_size": "默认分辨率",
            "default_enhance_prompt": "默认提示词增强",
            "api_base": "API地址",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔",
            "download_timeout": "下载超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("处理报告", "视频保存目录", "详细报告JSON")
    FUNCTION = "process"
    CATEGORY = "KuAi/Grok"

    def process(self, batch_tasks, api_key,
                save_dir="output/grok", batch_size=10,
                default_model="grok-video-3 (6秒)", default_aspect_ratio="3:2",
                default_size="720P", default_enhance_prompt=True,
                api_base="https://api.kegeai.top",
                max_wait_time=1200, poll_interval=10, download_timeout=180):

        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")

        tasks = json.loads(batch_tasks)
        if not tasks:
            raise RuntimeError("任务列表为空")

        total = len(tasks)
        all_results = []

        # 初始化状态管理器
        state_manager = BatchProcessState()
        session_id = f"grok_{int(time.time())}"
        state_manager.start_session(session_id, total)

        print(f"\n{'='*60}")
        print(f"[GrokCSVConcurrent] 共 {total} 个任务，每批 {batch_size} 路并发")
        print(f"[GrokCSVConcurrent] 保存目录: {save_dir}")
        print(f"[GrokCSVConcurrent] 会话ID: {session_id}")
        print(f"{'='*60}\n")

        # 按 batch_size 分批并发处理
        for batch_start in range(0, total, batch_size):
            batch = tasks[batch_start: batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            print(f"\n[GrokCSVConcurrent] 批次 {batch_num}/{total_batches}：提交 {len(batch)} 个任务")

            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
                future_map = {}
                for local_i, task in enumerate(batch):
                    global_idx = batch_start + local_i + 1
                    future = executor.submit(
                        _process_one_task,
                        global_idx, task,
                        default_model, default_aspect_ratio, default_size, default_enhance_prompt,
                        api_key, api_base, save_dir, max_wait_time, poll_interval, download_timeout,
                        state_manager  # 传递状态管理器
                    )
                    future_map[future] = global_idx

                for future in concurrent.futures.as_completed(future_map):
                    result = future.result()  # _process_one_task 内部不抛出，总是返回 dict
                    all_results.append(result)

        # 生成报告
        success = [r for r in all_results if r.get("status") == "completed"]
        failed  = [r for r in all_results if r.get("status") != "completed"]

        lines = [
            f"\n{'='*60}",
            f"Grok CSV 并发处理完成",
            f"总计: {total}  成功: {len(success)}  失败: {len(failed)}",
            f"保存目录: {save_dir}",
            f"{'='*60}",
        ]
        # 成功列表
        if success:
            lines.append("\n✓ 成功任务:")
            for r in sorted(success, key=lambda x: x["task_idx"]):
                lines.append(f"  [{r['task_idx']}] 行{r['row']}  {r.get('local_path','')}")
        # 失败列表
        if failed:
            lines.append("\n✗ 失败任务:")
            for r in sorted(failed, key=lambda x: x["task_idx"]):
                lines.append(f"  [{r['task_idx']}] 行{r['row']}  {r.get('error','')}")

        report = "\n".join(lines)
        print(report)

        # 计算绝对保存目录（用于输出展示）
        comfy_root = Path(__file__).parent.parent.parent.parent.parent
        abs_save_dir = str(comfy_root / save_dir)

        # 生成详细报告 JSON（供日志节点使用）
        detailed_report = {
            "total": total,
            "success": len(success),
            "failed": len(failed),
            "tasks": [
                {
                    "idx": r["task_idx"],
                    "row": r["row"],
                    "status": r.get("status", "unknown"),
                    "prompt": r.get("prompt", ""),
                    "video_url": r.get("video_url", ""),
                    "local_path": r.get("local_path", ""),
                    "error": r.get("error", "")
                }
                for r in all_results
            ]
        }
        detailed_json = json.dumps(detailed_report, ensure_ascii=False)

        return (report, abs_save_dir, detailed_json)


# ─────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "GrokCSVConcurrentProcessor": GrokCSVConcurrentProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokCSVConcurrentProcessor": "📦 Grok CSV 并发批量处理器（legacy）",
}
