"""图片URL列表转CSV任务 - 将批量上传的URL列表转换为批量处理任务"""

import json


class ImageURLsToGrokBatchTasks:
    """将图片URL列表转换为Grok批量图生视频任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_urls_json": ("STRING", {
                    "forceInput": True,
                    "tooltip": "来自批量上传节点的图片URL列表（JSON格式）"
                }),
                "prompt_template": ("STRING", {
                    "default": "将这张图片转换为视频，添加自然的镜头运动",
                    "multiline": True,
                    "tooltip": "提示词模板（每个图片使用相同的提示词）"
                }),
            },
            "optional": {
                "output_prefix": ("STRING", {
                    "default": "video",
                    "tooltip": "输出文件名前缀"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image_urls_json": "图片URL列表",
            "prompt_template": "提示词模板",
            "output_prefix": "输出前缀",
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("批量任务",)
    FUNCTION = "convert"
    CATEGORY = "KuAi/Utils"

    def convert(self, image_urls_json, prompt_template, output_prefix="video"):
        """将URL列表转换为Grok批量任务"""

        try:
            image_urls = json.loads(image_urls_json)

            if not isinstance(image_urls, list):
                raise ValueError("image_urls_json 必须是 JSON 数组格式")

            if not image_urls:
                raise ValueError("图片URL列表为空")

            print(f"[ComfyUI_KuAi_Power] 转换 {len(image_urls)} 个图片URL为Grok批量任务")

            tasks = []
            for idx, url in enumerate(image_urls, start=1):
                task = {
                    "_row_number": idx + 1,
                    "task_type": "image2video",
                    "prompt": prompt_template,
                    "image_urls": url,
                    "output_prefix": f"{output_prefix}_{idx}"
                }
                tasks.append(task)

            tasks_json = json.dumps(tasks, ensure_ascii=False, indent=2)
            print(f"[ComfyUI_KuAi_Power] 生成 {len(tasks)} 个Grok批量任务")

            return (tasks_json,)

        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析图片URL列表失败: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"转换失败: {str(e)}")


class ImageURLsToVeo3BatchTasks:
    """将图片URL列表转换为Veo3批量图生视频任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_urls_json": ("STRING", {
                    "forceInput": True,
                    "tooltip": "来自批量上传节点的图片URL列表（JSON格式）"
                }),
                "prompt_template": ("STRING", {
                    "default": "将这张图片转换为视频，添加自然的镜头运动",
                    "multiline": True,
                    "tooltip": "提示词模板（每个图片使用相同的提示词）"
                }),
            },
            "optional": {
                "output_prefix": ("STRING", {
                    "default": "video",
                    "tooltip": "输出文件名前缀"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image_urls_json": "图片URL列表",
            "prompt_template": "提示词模板",
            "output_prefix": "输出前缀",
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("批量任务",)
    FUNCTION = "convert"
    CATEGORY = "KuAi/Utils"

    def convert(self, image_urls_json, prompt_template, output_prefix="video"):
        """将URL列表转换为Veo3批量任务"""

        try:
            image_urls = json.loads(image_urls_json)

            if not isinstance(image_urls, list):
                raise ValueError("image_urls_json 必须是 JSON 数组格式")

            if not image_urls:
                raise ValueError("图片URL列表为空")

            print(f"[ComfyUI_KuAi_Power] 转换 {len(image_urls)} 个图片URL为Veo3批量任务")

            tasks = []
            for idx, url in enumerate(image_urls, start=1):
                task = {
                    "_row_number": idx + 1,
                    "task_type": "image2video",
                    "prompt": prompt_template,
                    "image_urls": url,
                    "output_prefix": f"{output_prefix}_{idx}"
                }
                tasks.append(task)

            tasks_json = json.dumps(tasks, ensure_ascii=False, indent=2)
            print(f"[ComfyUI_KuAi_Power] 生成 {len(tasks)} 个Veo3批量任务")

            return (tasks_json,)

        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析图片URL列表失败: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"转换失败: {str(e)}")


class ImageURLsToSoraBatchTasks:
    """将图片URL列表转换为Sora批量图生视频任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_urls_json": ("STRING", {
                    "forceInput": True,
                    "tooltip": "来自批量上传节点的图片URL列表（JSON格式）"
                }),
                "prompt_template": ("STRING", {
                    "default": "基于这张图片生成高质量视频，添加自然镜头运动",
                    "multiline": True,
                    "tooltip": "提示词模板（每个图片使用相同的提示词）"
                }),
            },
            "optional": {
                "output_prefix": ("STRING", {
                    "default": "sora_local",
                    "tooltip": "输出文件名前缀"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image_urls_json": "图片URL列表",
            "prompt_template": "提示词模板",
            "output_prefix": "输出前缀",
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("批量任务",)
    FUNCTION = "convert"
    CATEGORY = "KuAi/Utils"

    def convert(self, image_urls_json, prompt_template, output_prefix="sora_local"):
        """将URL列表转换为Sora批量任务"""

        try:
            image_urls = json.loads(image_urls_json)

            if not isinstance(image_urls, list):
                raise ValueError("image_urls_json 必须是 JSON 数组格式")

            if not image_urls:
                raise ValueError("图片URL列表为空")

            print(f"[ComfyUI_KuAi_Power] 转换 {len(image_urls)} 个图片URL为Sora批量任务")

            tasks = []
            for idx, url in enumerate(image_urls, start=1):
                task = {
                    "_row_number": idx + 1,
                    "prompt": prompt_template,
                    "images": url,
                    "model": "sora-2-all",
                    "duration_sora2": "10",
                    "duration_sora2pro": "15",
                    "orientation": "portrait",
                    "size": "large",
                    "watermark": "false",
                    "output_prefix": f"{output_prefix}_{idx}"
                }
                tasks.append(task)

            tasks_json = json.dumps(tasks, ensure_ascii=False, indent=2)
            print(f"[ComfyUI_KuAi_Power] 生成 {len(tasks)} 个Sora批量任务")

            return (tasks_json,)

        except json.JSONDecodeError as e:
            raise RuntimeError(f"解析图片URL列表失败: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"转换失败: {str(e)}")


NODE_CLASS_MAPPINGS = {
    "ImageURLsToGrokBatchTasks": ImageURLsToGrokBatchTasks,
    "ImageURLsToVeo3BatchTasks": ImageURLsToVeo3BatchTasks,
    "ImageURLsToSoraBatchTasks": ImageURLsToSoraBatchTasks,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageURLsToGrokBatchTasks": "🔄 图片URL转Grok批量任务",
    "ImageURLsToVeo3BatchTasks": "🔄 图片URL转Veo3批量任务",
    "ImageURLsToSoraBatchTasks": "🔄 图片URL转Sora批量任务",
}
