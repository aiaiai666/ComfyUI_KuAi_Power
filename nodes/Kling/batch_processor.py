"""可灵批量处理器"""

import json
import os
import time
from ..Sora2.kuai_utils import env_or
from .kling import KlingText2VideoAndWait, KlingImage2VideoAndWait


class KlingBatchProcessor:
    """可灵批量处理器"""

    def __init__(self):
        self.text2video_node = KlingText2VideoAndWait()
        self.image2video_node = KlingImage2VideoAndWait()

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
                    "tooltip": "API 密钥"
                }),
                "output_dir": ("STRING", {
                    "default": "./output/batch",
                    "tooltip": "输出目录"
                }),
                "delay_between_tasks": ("FLOAT", {
                    "default": 2.0,
                    "min": 0.0,
                    "max": 60.0,
                    "step": 0.5,
                    "tooltip": "任务间延迟（秒）"
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
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("处理结果", "输出目录")
    FUNCTION = "process_batch"
    CATEGORY = "KuAi/Kling"

    def process_batch(self, batch_tasks, api_key="", output_dir="./output/batch",
                     delay_between_tasks=2.0):
        """批量处理任务"""
        try:
            # 解析任务数据
            tasks = json.loads(batch_tasks)
            if not tasks:
                raise ValueError("没有任务需要处理")

            # 获取 API Key
            api_key = env_or(api_key, "KUAI_API_KEY")
            if not api_key:
                raise ValueError("未配置 API Key")

            # 创建输出目录
            os.makedirs(output_dir, exist_ok=True)

            # 处理结果统计
            results = {
                "total": len(tasks),
                "success": 0,
                "failed": 0,
                "errors": [],
                "task_ids": []
            }

            print(f"\n{'='*60}")
            print(f"[Batch] 开始批量处理 {len(tasks)} 个任务")
            print(f"{'='*60}\n")

            # 逐个处理任务
            for idx, task in enumerate(tasks, start=1):
                try:
                    print(f"\n[{idx}/{len(tasks)}] 处理任务 (行 {task.get('_row_number', '?')})")

                    # 处理单个任务
                    task_info = self._process_single_task(task, idx, api_key, output_dir)

                    results["success"] += 1
                    results["task_ids"].append(task_info)
                    print(f"✓ 任务 {idx} 完成")

                except Exception as e:
                    results["failed"] += 1
                    error_msg = f"任务 {idx}: {str(e)}"
                    results["errors"].append(error_msg)
                    print(f"✗ {error_msg}")

                # 任务间延迟
                if idx < len(tasks) and delay_between_tasks > 0:
                    time.sleep(delay_between_tasks)

            # 保存任务列表
            tasks_file = os.path.join(output_dir, "tasks.json")
            with open(tasks_file, 'w', encoding='utf-8') as f:
                json.dump(results["task_ids"], f, ensure_ascii=False, indent=2)

            # 生成结果报告
            report = self._generate_report(results)
            print(f"\n{'='*60}")
            print(report)
            print(f"{'='*60}\n")

            return (report, output_dir)

        except Exception as e:
            error_msg = f"批量处理失败: {str(e)}"
            print(f"[Batch] {error_msg}")
            raise RuntimeError(error_msg)

    def _process_single_task(self, task, task_idx, api_key, output_dir):
        """处理单个任务"""
        # 解析任务类型
        task_type = task.get("task_type", "").strip().lower()
        if not task_type:
            raise ValueError("任务类型不能为空")

        # 解析提示词
        prompt = task.get("prompt", "").strip()
        if not prompt and task_type == "text2video":
            raise ValueError("文生视频任务的提示词不能为空")

        # 解析通用参数
        model_name = task.get("model_name", "kling-v1").strip()
        mode = task.get("mode", "std").strip()
        duration = task.get("duration", "5").strip()
        negative_prompt = task.get("negative_prompt", "").strip()
        cfg_scale = float(task.get("cfg_scale", 0.5))
        multi_shot = str(task.get("multi_shot", "false")).lower() == "true"
        watermark = str(task.get("watermark", "false")).lower() == "true"
        output_prefix = task.get("output_prefix", f"task_{task_idx}").strip()

        # 根据任务类型处理
        if task_type == "text2video":
            aspect_ratio = task.get("aspect_ratio", "16:9").strip()
            
            status, video_url, video_duration, task_id = self.text2video_node.run(
                prompt=prompt,
                model_name=model_name,
                mode=mode,
                duration=duration,
                aspect_ratio=aspect_ratio,
                negative_prompt=negative_prompt,
                cfg_scale=cfg_scale,
                multi_shot=multi_shot,
                watermark=watermark,
                api_key=api_key
            )

        elif task_type == "image2video":
            image = task.get("image", "").strip()
            if not image:
                raise ValueError("图生视频任务的图片不能为空")
            
            image_tail = task.get("image_tail", "").strip()
            
            status, video_url, video_duration, task_id = self.image2video_node.run(
                image=image,
                model_name=model_name,
                mode=mode,
                duration=duration,
                prompt=prompt,
                image_tail=image_tail,
                negative_prompt=negative_prompt,
                cfg_scale=cfg_scale,
                multi_shot=multi_shot,
                watermark=watermark,
                api_key=api_key
            )

        else:
            raise ValueError(f"不支持的任务类型: {task_type}")

        # 构建任务信息
        task_info = {
            "task_id": task_id,
            "task_type": task_type,
            "status": status,
            "video_url": video_url,
            "duration": video_duration,
            "output_prefix": output_prefix,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        return task_info

    def _generate_report(self, results):
        """生成处理结果报告"""
        lines = [
            "\n批量处理完成",
            f"总任务数: {results['total']}",
            f"成功: {results['success']}",
            f"失败: {results['failed']}",
        ]

        if results['errors']:
            lines.append("\n失败任务详情:")
            for error in results['errors']:
                lines.append(f"  - {error}")

        return "\n".join(lines)
