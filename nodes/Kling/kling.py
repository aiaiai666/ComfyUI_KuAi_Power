"""可灵视频生成核心节点"""

import json
import time
import requests
from ..Sora2.kuai_utils import env_or, http_headers_auth_only, raise_for_bad_status
from .kling_utils import parse_kling_response, KLING_MODELS, KLING_ASPECT_RATIOS


class KlingText2Video:
    """可灵文生视频节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频提示词"
                }),
                "model_name": (KLING_MODELS, {
                    "default": "kling-v2-6",
                    "tooltip": "模型选择"
                }),
                "mode": (["std", "pro"], {
                    "default": "std",
                    "tooltip": "生成模式：std（标准）, pro（专家）"
                }),
                "duration": (["5", "10"], {
                    "default": "5",
                    "tooltip": "视频时长（秒）"
                }),
                "aspect_ratio": (KLING_ASPECT_RATIOS, {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
            },
            "optional": {
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型名称（留空使用上方下拉框选择的模型）"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "负面提示词"
                }),
                "cfg_scale": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1,
                    "tooltip": "提示词引导强度"
                }),
                "multi_shot": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否生成多镜头视频"
                }),
                "watermark": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否添加水印"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "timeout": ("INT", {
                    "default": 120,
                    "min": 5,
                    "max": 600,
                    "tooltip": "超时时间(秒)"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("任务ID", "状态", "创建时间")
    FUNCTION = "create"
    CATEGORY = "KuAi/Kling"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model_name": "模型名称",
            "mode": "模式",
            "duration": "时长",
            "aspect_ratio": "宽高比",
            "custom_model": "自定义模型",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG强度",
            "multi_shot": "多镜头",
            "watermark": "水印",
            "api_key": "API密钥",
            "api_base": "API地址",
            "timeout": "超时",
        }

    def create(self, prompt, model_name="kling-v2-6", mode="std", duration="5", aspect_ratio="16:9",
               custom_model="", negative_prompt="", cfg_scale=0.5, multi_shot=False, watermark=False,
               api_key="", api_base="https://ai.kegeai.top", timeout=120):
        """创建文生视频任务"""

        # 解析 API key
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置")

        # 处理自定义模型：如果 custom_model 不为空且不是纯空格，则使用它
        final_model = custom_model.strip() if custom_model and custom_model.strip() else model_name

        # 构建请求
        endpoint = api_base.rstrip("/") + "/kling/v1/videos/text2video"
        headers = http_headers_auth_only(api_key)

        payload = {
            "model_name": final_model,
            "prompt": prompt,
            "mode": mode,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "multi_shot": multi_shot,
            "watermark_info": {
                "enabled": watermark
            }
        }

        # 添加可选参数
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        if cfg_scale != 0.5:
            payload["cfg_scale"] = cfg_scale

        # 调用 API
        try:
            print(f"[ComfyUI_KuAi_Power] 创建可灵文生视频任务: {final_model}, {mode}, {duration}s")
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=int(timeout))
            raise_for_bad_status(resp, "创建文生视频任务失败")

            data = resp.json()
            task_id, status, created_at = parse_kling_response(data)

            if not task_id:
                raise RuntimeError(f"创建响应缺少任务 ID: {json.dumps(data, ensure_ascii=False)}")

            print(f"[ComfyUI_KuAi_Power] 任务创建成功: {task_id}, 状态: {status}")
            return (task_id, status, created_at)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"创建文生视频任务失败: {str(e)}")


class KlingImage2Video:
    """可灵图生视频节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "图片 URL 或 Base64 编码"
                }),
                "model_name": (KLING_MODELS, {
                    "default": "kling-v2-6",
                    "tooltip": "模型选择"
                }),
                "mode": (["std", "pro"], {
                    "default": "std",
                    "tooltip": "生成模式：std（标准）, pro（专家）"
                }),
                "duration": (["5", "10"], {
                    "default": "5",
                    "tooltip": "视频时长（秒）"
                }),
            },
            "optional": {
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型名称（留空使用上方下拉框选择的模型）"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "提示词（可选，用于引导生成）"
                }),
                "image_tail": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "尾帧图片 URL 或 Base64"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "负面提示词"
                }),
                "cfg_scale": ("FLOAT", {
                    "default": 0.5,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1,
                    "tooltip": "提示词引导强度"
                }),
                "multi_shot": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否生成多镜头视频"
                }),
                "watermark": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否添加水印"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "timeout": ("INT", {
                    "default": 120,
                    "min": 5,
                    "max": 600,
                    "tooltip": "超时时间(秒)"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("任务ID", "状态", "创建时间")
    FUNCTION = "create"
    CATEGORY = "KuAi/Kling"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image": "图片",
            "model_name": "模型名称",
            "mode": "模式",
            "duration": "时长",
            "custom_model": "自定义模型",
            "prompt": "提示词",
            "image_tail": "尾帧图片",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG强度",
            "multi_shot": "多镜头",
            "watermark": "水印",
            "api_key": "API密钥",
            "api_base": "API地址",
            "timeout": "超时",
        }

    def create(self, image, model_name="kling-v2-6", mode="std", duration="5",
               custom_model="", prompt="", image_tail="", negative_prompt="", cfg_scale=0.5, multi_shot=False, watermark=False,
               api_key="", api_base="https://ai.kegeai.top", timeout=120):
        """创建图生视频任务"""

        # 解析 API key
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置")

        if not image:
            raise RuntimeError("请提供图片 URL 或 Base64 编码")

        # 处理自定义模型：如果 custom_model 不为空且不是纯空格，则使用它
        final_model = custom_model.strip() if custom_model and custom_model.strip() else model_name

        # 构建请求
        endpoint = api_base.rstrip("/") + "/kling/v1/videos/image2video"
        headers = http_headers_auth_only(api_key)

        payload = {
            "model_name": final_model,
            "image": image,
            "mode": mode,
            "duration": duration,
            "multi_shot": multi_shot,
            "watermark_info": {
                "enabled": watermark
            }
        }

        # 添加可选参数
        if prompt:
            payload["prompt"] = prompt

        if image_tail:
            payload["image_tail"] = image_tail

        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        if cfg_scale != 0.5:
            payload["cfg_scale"] = cfg_scale

        # 调用 API
        try:
            print(f"[ComfyUI_KuAi_Power] 创建可灵图生视频任务: {final_model}, {mode}, {duration}s")
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=int(timeout))
            raise_for_bad_status(resp, "创建图生视频任务失败")

            data = resp.json()
            task_id, status, created_at = parse_kling_response(data)

            if not task_id:
                raise RuntimeError(f"创建响应缺少任务 ID: {json.dumps(data, ensure_ascii=False)}")

            print(f"[ComfyUI_KuAi_Power] 任务创建成功: {task_id}, 状态: {status}")
            return (task_id, status, created_at)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"创建图生视频任务失败: {str(e)}")


class KlingQueryTask:
    """可灵查询任务节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {
                    "default": "",
                    "tooltip": "任务 ID"
                }),
            },
            "optional": {
                "wait": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否等待任务完成"
                }),
                "poll_interval_sec": ("INT", {
                    "default": 15,
                    "min": 5,
                    "max": 90,
                    "tooltip": "轮询间隔(秒)"
                }),
                "timeout_sec": ("INT", {
                    "default": 1200,
                    "min": 600,
                    "max": 9600,
                    "tooltip": "总超时时间(秒)"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥"
                }),
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频URL", "时长", "原始响应")
    FUNCTION = "query"
    CATEGORY = "KuAi/Kling"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "task_id": "任务ID",
            "wait": "等待完成",
            "poll_interval_sec": "轮询间隔",
            "timeout_sec": "总超时",
            "api_key": "API密钥",
            "api_base": "API地址",
        }

    def query(self, task_id, wait=True, poll_interval_sec=15, timeout_sec=1200,
              api_key="", api_base="https://ai.kegeai.top"):
        """查询任务状态"""

        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")

        if not task_id:
            raise RuntimeError("请提供任务 ID")

        endpoint = api_base.rstrip("/") + f"/kling/v1/videos/text2video/{task_id}"
        headers = http_headers_auth_only(api_key)

        def query_once():
            """查询一次"""
            try:
                resp = requests.get(endpoint, headers=headers, timeout=60)
                raise_for_bad_status(resp, "查询任务失败")

                data = resp.json()

                # 解析响应
                if data.get("code") != 0:
                    raise RuntimeError(f"查询失败: {data.get('message', '未知错误')}")

                task_data = data.get("data", {})
                status = task_data.get("task_status", "")
                task_info = task_data.get("task_info", {})
                video_url = task_info.get("video_url", "")
                duration = task_info.get("duration", "")

                # 检查任务失败
                if status == "failed":
                    error_msg = task_info.get("error", "任务失败")
                    raise RuntimeError(f"任务执行失败: {error_msg}")

                # 检查视频 URL
                if status == "succeed" and not video_url:
                    raise RuntimeError("任务完成但未返回视频 URL")

                return (status, video_url, duration, json.dumps(data, ensure_ascii=False))

            except RuntimeError:
                raise
            except Exception as e:
                raise RuntimeError(f"查询任务失败: {str(e)}")

        # 如果不等待，直接返回
        if not wait:
            return query_once()

        # 轮询等待
        print(f"[KlingQueryTask] 开始轮询任务 {task_id}，超时 {timeout_sec} 秒，间隔 {poll_interval_sec} 秒")
        deadline = time.time() + int(timeout_sec)
        last_raw = ""
        poll_count = 0

        while time.time() < deadline:
            poll_count += 1
            status, video_url, duration, raw = query_once()
            last_raw = raw

            print(f"[KlingQueryTask] 第 {poll_count} 次查询: 状态={status}")

            if status in ("succeed", "failed"):
                print(f"[KlingQueryTask] 任务完成: {status}")
                return (status, video_url, duration, raw)

            time.sleep(int(poll_interval_sec))

        # 超时
        print(f"[KlingQueryTask] 轮询超时")
        return ("timeout", "", "", last_raw or json.dumps({"error": "timeout"}, ensure_ascii=False))


class KlingText2VideoAndWait:
    """可灵文生视频一键生成节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频提示词"
                }),
                "model_name": (KLING_MODELS, {
                    "default": "kling-v2-6",
                    "tooltip": "模型选择"
                }),
                "mode": (["std", "pro"], {
                    "default": "std",
                    "tooltip": "生成模式"
                }),
                "duration": (["5", "10"], {
                    "default": "5",
                    "tooltip": "视频时长（秒）"
                }),
                "aspect_ratio": (KLING_ASPECT_RATIOS, {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
            },
            "optional": {
                "custom_model": ("STRING", {"default": ""}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "cfg_scale": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.1}),
                "multi_shot": ("BOOLEAN", {"default": False}),
                "watermark": ("BOOLEAN", {"default": False}),
                "api_key": ("STRING", {"default": ""}),
                "api_base": ("STRING", {"default": "https://ai.kegeai.top"}),
                "create_timeout": ("INT", {"default": 1800, "min": 5, "max": 9999}),
                "poll_interval_sec": ("INT", {"default": 15, "min": 5, "max": 90}),
                "wait_timeout_sec": ("INT", {"default": 1800, "min": 600, "max": 9999}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频URL", "时长", "任务ID")
    FUNCTION = "run"
    CATEGORY = "KuAi/Kling"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model_name": "模型名称",
            "mode": "模式",
            "duration": "时长",
            "aspect_ratio": "宽高比",
            "custom_model": "自定义模型",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG强度",
            "multi_shot": "多镜头",
            "watermark": "水印",
            "api_key": "API密钥",
            "api_base": "API地址",
            "create_timeout": "创建超时",
            "poll_interval_sec": "轮询间隔",
            "wait_timeout_sec": "等待超时",
        }

    def run(self, prompt, model_name="kling-v2-6", mode="std", duration="5", aspect_ratio="16:9",
            custom_model="", negative_prompt="", cfg_scale=0.5, multi_shot=False, watermark=False,
            api_key="", api_base="https://ai.kegeai.top",
            create_timeout=120, poll_interval_sec=15, wait_timeout_sec=1200):
        """一键创建并等待完成"""

        # 创建任务
        creator = KlingText2Video()
        task_id, status, _ = creator.create(
            prompt=prompt, model_name=model_name, mode=mode, duration=duration, aspect_ratio=aspect_ratio,
            custom_model=custom_model, negative_prompt=negative_prompt, cfg_scale=cfg_scale, multi_shot=multi_shot, watermark=watermark,
            api_key=api_key, api_base=api_base, timeout=create_timeout
        )

        # 查询任务
        querier = KlingQueryTask()
        status, video_url, video_duration, _raw = querier.query(
            task_id=task_id, wait=True, poll_interval_sec=poll_interval_sec, timeout_sec=wait_timeout_sec,
            api_key=api_key, api_base=api_base
        )

        return (status, video_url, video_duration, task_id)


class KlingImage2VideoAndWait:
    """可灵图生视频一键生成节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "图片 URL 或 Base64"
                }),
                "model_name": (KLING_MODELS, {
                    "default": "kling-v2-6",
                    "tooltip": "模型选择"
                }),
                "mode": (["std", "pro"], {
                    "default": "std",
                    "tooltip": "生成模式"
                }),
                "duration": (["5", "10"], {
                    "default": "5",
                    "tooltip": "视频时长（秒）"
                }),
            },
            "optional": {
                "custom_model": ("STRING", {"default": ""}),
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "image_tail": ("STRING", {"default": ""}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True}),
                "cfg_scale": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.1}),
                "multi_shot": ("BOOLEAN", {"default": False}),
                "watermark": ("BOOLEAN", {"default": False}),
                "api_key": ("STRING", {"default": ""}),
                "api_base": ("STRING", {"default": "https://ai.kegeai.top"}),
                "create_timeout": ("INT", {"default": 1800, "min": 5, "max": 9999}),
                "poll_interval_sec": ("INT", {"default": 15, "min": 5, "max": 90}),
                "wait_timeout_sec": ("INT", {"default": 1800, "min": 600, "max": 9999}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频URL", "时长", "任务ID")
    FUNCTION = "run"
    CATEGORY = "KuAi/Kling"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image": "图片",
            "model_name": "模型名称",
            "mode": "模式",
            "duration": "时长",
            "custom_model": "自定义模型",
            "prompt": "提示词",
            "image_tail": "尾帧图片",
            "negative_prompt": "负面提示词",
            "cfg_scale": "CFG强度",
            "multi_shot": "多镜头",
            "watermark": "水印",
            "api_key": "API密钥",
            "api_base": "API地址",
            "create_timeout": "创建超时",
            "poll_interval_sec": "轮询间隔",
            "wait_timeout_sec": "等待超时",
        }

    def run(self, image, model_name="kling-v2-6", mode="std", duration="5",
            custom_model="", prompt="", image_tail="", negative_prompt="", cfg_scale=0.5, multi_shot=False, watermark=False,
            api_key="", api_base="https://ai.kegeai.top",
            create_timeout=120, poll_interval_sec=15, wait_timeout_sec=1200):
        """一键创建并等待完成"""

        # 创建任务
        creator = KlingImage2Video()
        task_id, status, _ = creator.create(
            image=image, model_name=model_name, mode=mode, duration=duration,
            custom_model=custom_model, prompt=prompt, image_tail=image_tail, negative_prompt=negative_prompt,
            cfg_scale=cfg_scale, multi_shot=multi_shot, watermark=watermark,
            api_key=api_key, api_base=api_base, timeout=create_timeout
        )

        # 查询任务
        querier = KlingQueryTask()
        status, video_url, video_duration, _raw = querier.query(
            task_id=task_id, wait=True, poll_interval_sec=poll_interval_sec, timeout_sec=wait_timeout_sec,
            api_key=api_key, api_base=api_base
        )

        return (status, video_url, video_duration, task_id)
