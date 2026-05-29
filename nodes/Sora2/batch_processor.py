"""Sora2 批量处理器"""

import json
import os
import time
import hashlib
from pathlib import Path

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from .kuai_utils import env_or, SORA2_DURATION_OPTIONS, SORA2_MODELS
from .sora2 import SoraCreateVideo, SoraText2Video, SoraQueryTask


class Sora2BatchProcessor:
    """Sora2 视频批量生成处理器"""

    def __init__(self):
        self.creator_with_images = SoraCreateVideo()
        self.creator_text_only = SoraText2Video()
        self.querier = SoraQueryTask()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "batch_tasks": ("STRING", {
                    "forceInput": True,
                    "tooltip": "来自 CSV 读取器的批量任务数据"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
                "output_dir": ("STRING", {
                    "default": "./output/sora2_batch",
                    "tooltip": "输出目录（任务信息与本地视频保存位置）"
                }),
                "delay_between_tasks": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.0,
                    "max": 60.0,
                    "step": 0.5,
                    "tooltip": "任务间延迟（秒）"
                }),
            },
            "optional": {
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "wait_for_completion": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否等待视频生成完成"
                }),
                "auto_download": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "等待完成后自动下载视频到本地"
                }),
                "max_wait_time": ("INT", {
                    "default": 1200,
                    "min": 600,
                    "max": 9600,
                    "tooltip": "最大等待时间（秒）"
                }),
                "poll_interval": ("INT", {
                    "default": 15,
                    "min": 5,
                    "max": 90,
                    "tooltip": "轮询间隔（秒）"
                }),
                "download_timeout": ("INT", {
                    "default": 180,
                    "min": 30,
                    "max": 600,
                    "tooltip": "视频下载超时（秒）"
                }),
                "default_model": (SORA2_MODELS, {
                    "default": "sora-2-all",
                    "tooltip": "默认模型（任务未指定时使用）"
                }),
                "default_duration_sora2": (SORA2_DURATION_OPTIONS, {
                    "default": "15",
                    "tooltip": "默认 sora-2 时长（任务未指定时使用）"
                }),
                "default_duration_sora2pro": (SORA2_DURATION_OPTIONS, {
                    "default": "15",
                    "tooltip": "默认 sora-2-pro 时长（任务未指定时使用）"
                }),
                "default_custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "默认自定义模型（留空则使用默认模型）"
                }),
                "default_orientation": (["portrait", "landscape"], {
                    "default": "portrait",
                    "tooltip": "默认方向（任务未指定时使用）"
                }),
                "default_size": (["small", "large"], {
                    "default": "large",
                    "tooltip": "默认尺寸（任务未指定时使用）"
                }),
                "default_watermark": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "默认水印（任务未指定时使用）"
                }),
                "create_timeout": ("INT", {
                    "default": 120,
                    "min": 5,
                    "max": 600,
                    "tooltip": "创建任务超时（秒）"
                }),
                "max_workers": ("INT", {
                    "default": 8,
                    "min": 1,
                    "max": 100,
                    "tooltip": "并发提交数量"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "batch_tasks": "批量任务",
            "api_key": "API密钥",
            "output_dir": "输出目录",
            "delay_between_tasks": "任务间延迟",
            "api_base": "API地址",
            "wait_for_completion": "等待完成",
            "auto_download": "自动下载",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔",
            "download_timeout": "下载超时",
            "default_model": "默认模型",
            "default_duration_sora2": "默认sora-2时长",
            "default_duration_sora2pro": "默认sora-2-pro时长",
            "default_custom_model": "默认自定义模型",
            "default_orientation": "默认方向",
            "default_size": "默认尺寸",
            "default_watermark": "默认水印",
            "create_timeout": "创建超时",
            "max_workers": "并发数量",
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("处理结果", "输出目录")
    FUNCTION = "process_batch"
    CATEGORY = "KuAi/Sora2"

    def process_batch(self, batch_tasks, api_key="", output_dir="./output/sora2_batch",
                     delay_between_tasks=2.0, api_base="https://ai.kegeai.top",
                     wait_for_completion=False, auto_download=True,
                     max_wait_time=1200, poll_interval=15, download_timeout=180,
                     default_model="sora-2-all", default_duration_sora2="15", default_duration_sora2pro="15",
                     default_custom_model="", default_orientation="portrait", default_size="large",
                     default_watermark=False, create_timeout=120, max_workers=8):
        """批量生成视频"""
        try:
            tasks = json.loads(batch_tasks)
            if not tasks:
                raise ValueError("没有任务需要处理")

            api_key = env_or(api_key, "KUAI_API_KEY")
            if not api_key:
                raise ValueError("未配置 API Key")

            os.makedirs(output_dir, exist_ok=True)

            results = {
                "total": len(tasks),
                "success": 0,
                "failed": 0,
                "errors": [],
                "video_tasks": []
            }

            print(f"\n{'='*60}")
            print(f"[Sora2Batch] 开始批量生成 {len(tasks)} 个视频")
            print(f"[Sora2Batch] 输出目录: {output_dir}")
            print(f"[Sora2Batch] 等待完成: {'是' if wait_for_completion else '否'}")
            print(f"[Sora2Batch] 自动下载: {'是' if (wait_for_completion and auto_download) else '否'}")
            print(f"{'='*60}\n")

            total_tasks = len(tasks)
            max_workers = min(max(int(max_workers), 1), 100, total_tasks)
            futures = {}
            task_results_by_idx = {}

            def _run_task(task_idx, task_data):
                if delay_between_tasks > 0:
                    # 并发模式下仍保留提交节流：按索引错峰启动
                    time.sleep((task_idx - 1) * delay_between_tasks)

                print(f"\n[{task_idx}/{total_tasks}] 处理任务 (行 {task_data.get('_row_number', '?')})")
                task_info = self._process_single_task(
                    task=task_data,
                    task_idx=task_idx,
                    api_key=api_key,
                    api_base=api_base,
                    output_dir=output_dir,
                    wait_for_completion=wait_for_completion,
                    auto_download=auto_download,
                    max_wait_time=max_wait_time,
                    poll_interval=poll_interval,
                    download_timeout=download_timeout,
                    default_model=default_model,
                    default_duration_sora2=default_duration_sora2,
                    default_duration_sora2pro=default_duration_sora2pro,
                    default_custom_model=default_custom_model,
                    default_orientation=default_orientation,
                    default_size=default_size,
                    default_watermark=default_watermark,
                    create_timeout=create_timeout,
                )
                return task_info

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for idx, task in enumerate(tasks, start=1):
                    future = executor.submit(_run_task, idx, task)
                    futures[future] = idx

                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        task_info = future.result()
                        results["success"] += 1
                        task_results_by_idx[idx] = task_info
                        print(f"✓ 任务 {idx} 完成")
                    except Exception as e:
                        results["failed"] += 1
                        error_msg = f"任务 {idx}: {str(e)}"
                        results["errors"].append(error_msg)
                        print(f"✗ {error_msg}")

            results["video_tasks"] = [task_results_by_idx[i] for i in sorted(task_results_by_idx.keys())]

            tasks_file = os.path.join(output_dir, "tasks.json")
            with open(tasks_file, 'w', encoding='utf-8') as f:
                json.dump(results["video_tasks"], f, ensure_ascii=False, indent=2)

            report = self._generate_report(results)
            print(f"\n{'='*60}")
            print(report)
            print(f"{'='*60}\n")

            return (report, output_dir)

        except Exception as e:
            error_msg = f"批量处理失败: {str(e)}"
            print(f"[Sora2Batch] {error_msg}")
            raise RuntimeError(error_msg)

    def _process_single_task(self, task, task_idx, api_key, api_base, output_dir,
                            wait_for_completion, auto_download, max_wait_time,
                            poll_interval, download_timeout,
                            default_model, default_duration_sora2, default_duration_sora2pro,
                            default_custom_model, default_orientation, default_size,
                            default_watermark, create_timeout):
        """处理单个视频生成任务"""
        prompt = task.get("prompt", "").strip()
        images = task.get("images", "").strip()
        model = (str(task.get("model", "")).strip() or default_model)
        duration_sora2 = str(task.get("duration_sora2", "")).strip() or str(default_duration_sora2)
        duration_sora2pro = str(task.get("duration_sora2pro", "")).strip() or str(default_duration_sora2pro)
        custom_model = str(task.get("custom_model", "")).strip() or str(default_custom_model).strip()
        orientation = (str(task.get("orientation", "")).strip() or default_orientation)
        size = (str(task.get("size", "")).strip() or default_size)

        if "watermark" in task and str(task.get("watermark", "")).strip() != "":
            watermark = str(task.get("watermark", "false")).strip().lower() in ("true", "1", "yes")
        else:
            watermark = bool(default_watermark)

        output_prefix = task.get("output_prefix", f"video_{task_idx}").strip() or f"video_{task_idx}"

        if not prompt:
            raise ValueError("提示词不能为空")

        print(f"  提示词: {prompt[:50]}...")
        print(f"  模型: {custom_model if custom_model else model}")
        print(f"  方向: {orientation}")
        print(f"  尺寸: {size}")

        if images:
            print(f"  图片: {images[:50]}...")
            task_id, status, status_update_time = self.creator_with_images.create(
                images=images,
                prompt=prompt,
                model=model,
                duration_sora2=duration_sora2,
                duration_sora2pro=duration_sora2pro,
                custom_model=custom_model,
                api_base=api_base,
                api_key=api_key,
                orientation=orientation,
                size=size,
                watermark=watermark,
                timeout=create_timeout,
            )
        else:
            print("  类型: 文生视频")
            task_id, status, status_update_time = self.creator_text_only.create(
                prompt=prompt,
                model=model,
                duration_sora2=duration_sora2,
                duration_sora2pro=duration_sora2pro,
                custom_model=custom_model,
                api_base=api_base,
                api_key=api_key,
                orientation=orientation,
                size=size,
                watermark=watermark,
                timeout=create_timeout,
            )

        print(f"  任务ID: {task_id}")
        print(f"  状态: {status}")

        actual_model = custom_model if custom_model else model
        task_info = {
            "task_id": task_id,
            "prompt": prompt,
            "model": actual_model,
            "orientation": orientation,
            "size": size,
            "has_images": bool(images),
            "status": status,
            "status_update_time": status_update_time,
            "output_prefix": output_prefix,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        if wait_for_completion:
            print("  等待视频生成完成...")
            try:
                final_status, video_url, gif_url, thumbnail_url, _raw = self.querier.query(
                    task_id=task_id,
                    api_base=api_base,
                    api_key=api_key,
                    wait=True,
                    poll_interval_sec=poll_interval,
                    timeout_sec=max_wait_time
                )

                task_info["final_status"] = final_status
                task_info["video_url"] = video_url
                task_info["gif_url"] = gif_url
                task_info["thumbnail_url"] = thumbnail_url
                task_info["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

                print(f"  最终状态: {final_status}")
                if video_url:
                    print(f"  视频URL: {video_url[:50]}...")

                if auto_download:
                    if final_status == "completed" and str(video_url).strip():
                        local_path, download_status = self._download_video(
                            video_url=video_url,
                            output_prefix=output_prefix,
                            output_dir=output_dir,
                            timeout=download_timeout,
                        )
                        task_info["local_video_path"] = local_path
                        task_info["download_status"] = download_status
                        if local_path:
                            print(f"  本地保存: {local_path}")
                        else:
                            print(f"  下载状态: {download_status}")
                    else:
                        task_info["local_video_path"] = ""
                        task_info["download_status"] = "skip_no_video"

            except Exception as e:
                print(f"  等待完成失败: {str(e)}")
                task_info["wait_error"] = str(e)
                if auto_download:
                    task_info["local_video_path"] = ""
                    task_info["download_status"] = "skip_wait_error"

        task_file = os.path.join(output_dir, f"{output_prefix}.json")
        with open(task_file, 'w', encoding='utf-8') as f:
            json.dump(task_info, f, ensure_ascii=False, indent=2)

        return task_info

    def _download_video(self, video_url, output_prefix, output_dir, timeout):
        """下载视频到输出目录，返回 (相对路径, 下载状态)。"""
        try:
            comfy_root = Path(__file__).parent.parent.parent.parent.parent
            target_dir = Path(output_dir)
            if not target_dir.is_absolute():
                target_dir = comfy_root / target_dir
            target_dir.mkdir(parents=True, exist_ok=True)

            url_hash = hashlib.md5(video_url.encode("utf-8")).hexdigest()[:8]
            filepath = target_dir / f"{output_prefix}_{url_hash}.mp4"

            resp = requests.get(video_url, timeout=int(timeout), stream=True)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            rel_path = str(filepath.relative_to(comfy_root))
            return rel_path, "downloaded"
        except Exception as e:
            return "", f"download_failed: {str(e)}"

    def _generate_report(self, results):
        """生成处理结果报告"""
        lines = [
            "\n批量视频生成完成",
            f"总任务数: {results['total']}",
            f"成功: {results['success']}",
            f"失败: {results['failed']}",
        ]

        if results['errors']:
            lines.append("\n失败任务详情:")
            for error in results['errors']:
                lines.append(f"  - {error}")

        if results['video_tasks']:
            lines.append("\n任务结果:")
            for task in results['video_tasks']:
                status = task.get("final_status") or task.get("status") or "unknown"
                prompt_preview = task.get("prompt", "")[:30]
                local_path = task.get("local_video_path", "")
                download_status = task.get("download_status", "")

                base_line = f"  - {task.get('task_id', '')}: {status} | {prompt_preview}..."
                lines.append(base_line)

                if local_path:
                    lines.append(f"    本地文件: {local_path}")
                elif download_status:
                    lines.append(f"    下载状态: {download_status}")

        local_saved = sum(1 for t in results["video_tasks"] if t.get("local_video_path"))
        download_failed = sum(1 for t in results["video_tasks"] if str(t.get("download_status", "")).startswith("download_failed"))
        lines.append("\n本地保存结果:")
        lines.append(f"  - 已保存到本地: {local_saved}")
        lines.append(f"  - 下载失败: {download_failed}")

        return "\n".join(lines)


NODE_CLASS_MAPPINGS = {
    "Sora2BatchProcessor": Sora2BatchProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "Sora2BatchProcessor": "📦 Sora2 批量处理器",
}
