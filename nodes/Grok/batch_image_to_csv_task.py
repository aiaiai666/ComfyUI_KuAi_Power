"""Grok 批量图片转任务列表节点

将 BatchImageUploader 输出的 JSON URL 列表转换为 CSV 并发处理器可用的任务列表。
实现完全闭环：BatchImageUploader → GrokBatchImageToCSVTask → GrokCSVConcurrentProcessor
"""

import json


class GrokBatchImageToCSVTask:
    """将批量上传的图片 URL 转换为 Grok CSV 并发处理任务列表"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_urls_json": ("STRING", {
                    "forceInput": True,
                    "tooltip": "来自 BatchImageUploader 的 JSON URL 列表"
                }),
                "prompt_template": ("STRING", {
                    "default": "生成视频",
                    "multiline": True,
                    "tooltip": "提示词模板（支持 {index} 占位符，如：第{index}个视频）"
                }),
                "model": ([
                    "grok-video-3 (6秒)",
                    "grok-video-3-10s (10秒)",
                    "grok-video-3-15s (15秒)"
                ], {
                    "default": "grok-video-3 (6秒)",
                    "tooltip": "Grok 模型"
                }),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {
                    "default": "3:2",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P", "1080P"], {
                    "default": "1080P",
                    "tooltip": "视频分辨率"
                }),
                "enhance_prompt": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "自动优化并翻译提示词"
                }),
                "output_prefix_template": ("STRING", {
                    "default": "grok_{index}",
                    "tooltip": "输出文件名前缀模板（支持 {index} 占位符）"
                }),
            },
            "optional": {
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型名称（留空使用上方选择的模型）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        """中文标签"""
        return {
            "image_urls_json": "图片URL列表",
            "prompt_template": "提示词模板",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "enhance_prompt": "优化提示词",
            "output_prefix_template": "输出前缀模板",
            "custom_model": "自定义模型",
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("任务列表JSON", "任务数量")
    FUNCTION = "generate_tasks"
    CATEGORY = "KuAi/Grok"

    def generate_tasks(self, image_urls_json, prompt_template, model,
                      aspect_ratio, size, enhance_prompt,
                      output_prefix_template, custom_model=""):
        """生成任务列表"""
        try:
            # 1. 解析 JSON URL 列表
            try:
                image_urls = json.loads(image_urls_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"无法解析图片 URL 列表: {str(e)}")

            if not isinstance(image_urls, list):
                raise ValueError(f"图片 URL 列表格式错误，期望数组，实际: {type(image_urls)}")

            if not image_urls:
                raise ValueError("图片 URL 列表为空")

            print(f"[ComfyUI_KuAi_Power] 生成 {len(image_urls)} 个 Grok 任务")

            # 2. 为每个 URL 生成任务
            tasks = []
            for idx, url in enumerate(image_urls, start=1):
                # 替换模板中的占位符
                prompt = prompt_template.replace("{index}", str(idx))
                output_prefix = output_prefix_template.replace("{index}", str(idx))

                # 构建任务字典（匹配 CSV 并发处理器期望的格式）
                task = {
                    "_row_number": idx,
                    "prompt": prompt,
                    "image_urls": url,  # 单个 URL 字符串
                    "model": model,
                    "aspect_ratio": aspect_ratio,
                    "size": size,
                    "enhance_prompt": "true" if enhance_prompt else "false",
                    "output_prefix": output_prefix,
                }

                # 添加自定义模型（如果提供）
                if custom_model:
                    task["custom_model"] = custom_model

                tasks.append(task)

            # 3. 转换为 JSON
            tasks_json = json.dumps(tasks, ensure_ascii=False, indent=2)

            print(f"[ComfyUI_KuAi_Power] 任务列表生成完成:")
            print(f"  - 任务数量: {len(tasks)}")
            print(f"  - 提示词模板: {prompt_template}")
            print(f"  - 输出前缀模板: {output_prefix_template}")

            return (tasks_json, len(tasks))

        except Exception as e:
            error_msg = f"生成任务列表失败: {str(e)}"
            print(f"[ComfyUI_KuAi_Power] {error_msg}")
            raise RuntimeError(error_msg)


NODE_CLASS_MAPPINGS = {
    "GrokBatchImageToCSVTask": GrokBatchImageToCSVTask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokBatchImageToCSVTask": "📋 Grok 批量图片转任务列表（legacy）",
}
