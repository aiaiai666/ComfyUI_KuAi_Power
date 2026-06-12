"""Grok 视频生成节点"""

import json
import os
import time
import requests
from ..Sora2.kuai_utils import (
    env_or,
    http_headers_json,
    http_headers_auth_only,
    ensure_list_from_urls,
    extract_error_message_from_response,
    extract_task_failure_detail,
)

GROK_SUCCESS_STATUSES = {"completed", "success", "succeeded", "succeed"}
GROK_FAILED_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}


def _grok_status_key(status):
    return str(status or "").strip().lower()


def _is_grok_success_status(status):
    return _grok_status_key(status) in GROK_SUCCESS_STATUSES


def _is_grok_failed_status(status):
    return _grok_status_key(status) in GROK_FAILED_STATUSES


def wait_grok_task_success(task_id, api_key="", api_base="https://api.kegeai.top",
                           max_wait_time=1200, poll_interval=10,
                           task_label="Grok 视频任务"):
    querier = GrokQueryVideo()
    elapsed = 0

    print(f"[ComfyUI_KuAi_Power] 等待{task_label}成功: {task_id}")

    while True:
        queried_task_id, status, video_url, enhanced_prompt, status_update_time = querier.query(
            task_id, api_key, api_base
        )

        if _is_grok_success_status(status):
            if not str(video_url).strip():
                raise RuntimeError(f"{task_label}已成功但未返回视频URL，任务ID: {queried_task_id}")
            return queried_task_id, status, video_url, enhanced_prompt, status_update_time, elapsed

        if _is_grok_failed_status(status):
            raise RuntimeError(f"{task_label}失败，任务ID: {queried_task_id}，状态: {status}")

        if elapsed >= max_wait_time:
            raise RuntimeError(
                f"{task_label}等待超时（等待了 {max_wait_time} 秒）。"
                f"任务ID: {queried_task_id}，最后状态: {status}。"
            )

        print(
            f"[ComfyUI_KuAi_Power] {task_label}尚未成功，状态: {status}，"
            f"已等待 {elapsed}/{max_wait_time} 秒"
        )
        time.sleep(poll_interval)
        elapsed += poll_interval


class GrokCreateVideo:
    """创建 Grok 视频生成任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词（支持中英文）"
                }),
                "model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)", "grok-video-3-15s (15秒)"], {
                    "default": "grok-video-3 (6秒)",
                    "tooltip": "选择 Grok 模型"
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
                    "tooltip": "自动将中文提示词优化并翻译为英文"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "image_urls": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "参考图片URL（多个用逗号、分号或换行分隔）"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用下拉模型）"
                }),
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子；改变 seed 可避免重复提交"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "enhance_prompt": "提示词增强",
            "api_key": "API密钥",
            "image_urls": "参考图片URL",
            "custom_model": "自定义模型",
            "api_base": "API地址",
            "seed": "随机种子",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "增强提示词")
    FUNCTION = "create"
    CATEGORY = "KuAi/Grok"

    def create(self, prompt, model, aspect_ratio, size, enhance_prompt, api_key="", seed=0, image_urls="", api_base="https://api.kegeai.top", custom_model=""):
        """创建 Grok 视频生成任务"""
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        api_base = api_base.rstrip("/")
        headers = http_headers_auth_only(api_key)

        # 提取实际的模型名称（去掉时长说明）
        actual_model = model.split(" (")[0] if " (" in model else model
        effective_model = (custom_model or "").strip() or actual_model

        # 根据 effective_model 判断是否支持 1080P（只有 15 秒模型支持）
        effective_size = size
        if "15s" not in effective_model.lower() and size == "1080P":
            effective_size = "720P"
            print(f"[ComfyUI_KuAi_Power] 警告：{effective_model} 不支持 1080P，已自动降级到 720P")

        # 解析图片URL列表
        images = ensure_list_from_urls(image_urls) if image_urls else []

        payload = {
            "model": effective_model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "size": effective_size,
            "enhance_prompt": bool(enhance_prompt),
            "images": images,
            "seed": int(seed) if seed else 0,
        }

        print(f"[ComfyUI_KuAi_Power] Grok 创建视频任务: {prompt[:50]}...")
        print(f"[ComfyUI_KuAi_Power] 模型: {effective_model}, 宽高比: {aspect_ratio}, 分辨率: {effective_size}")
        if enhance_prompt:
            print(f"[ComfyUI_KuAi_Power] 提示词增强: 已启用")

        try:
            resp = requests.post(
                f"{api_base}/v1/video/create",
                json=payload,
                headers=headers,
                timeout=30
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok 视频创建失败: {detail}")

            result = resp.json()
            task_id = result.get("id", "")
            status = result.get("status", "pending")
            enhanced_prompt = result.get("enhanced_prompt", "")

            print(f"[ComfyUI_KuAi_Power] Grok 任务已创建: {task_id}, 状态: {status}")
            if enhanced_prompt and enhanced_prompt != prompt:
                print(f"[ComfyUI_KuAi_Power] 增强后的提示词: {enhanced_prompt[:100]}...")

            return (task_id, status, enhanced_prompt)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Grok 视频创建失败: {str(e)}")


class GrokQueryVideo:
    """查询 Grok 视频生成任务状态"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {
                    "default": "",
                    "tooltip": "任务ID"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                    "tooltip": "API端点地址"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "task_id": "任务ID",
            "api_key": "API密钥",
            "api_base": "API地址"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "增强提示词", "状态更新时间")
    FUNCTION = "query"
    CATEGORY = "KuAi/Grok"

    def query(self, task_id, api_key="", api_base="https://api.kegeai.top"):
        """查询 Grok 视频生成任务状态"""
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        if not task_id:
            raise RuntimeError("任务ID不能为空")

        api_base = api_base.rstrip("/")
        headers = http_headers_json(api_key)

        print(f"[ComfyUI_KuAi_Power] Grok 查询任务: {task_id}")

        try:
            resp = requests.get(
                f"{api_base}/v1/video/query",
                params={"id": task_id},
                headers=headers,
                timeout=30
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok 视频查询失败: {detail}")

            result = resp.json()
            status = result.get("status", "unknown")
            video_url = result.get("video_url") or ""
            enhanced_prompt = result.get("enhanced_prompt", "")
            status_update_time = int(result.get("status_update_time", 0))

            if _is_grok_failed_status(status):
                fail_detail = extract_task_failure_detail(result)
                if not fail_detail:
                    fail_detail = json.dumps(result, ensure_ascii=False)
                raise RuntimeError(f"Grok 视频任务失败: {fail_detail}")

            if _is_grok_success_status(status) and not str(video_url).strip():
                missing_detail = extract_task_failure_detail(result) or "任务已完成但未返回视频URL"
                raise RuntimeError(f"Grok 视频查询失败: {missing_detail}")

            print(f"[ComfyUI_KuAi_Power] Grok 任务状态: {status}")
            if video_url:
                print(f"[ComfyUI_KuAi_Power] Grok 视频URL: {video_url}")

            return (task_id, status, video_url, enhanced_prompt, status_update_time)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Grok 视频查询失败: {str(e)}")


class GrokCreateAndWait:
    """创建 Grok 视频并等待完成（一键生成）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)", "grok-video-3-15s (15秒)"], {
                    "default": "grok-video-3 (6秒)",
                    "tooltip": "选择 Grok 模型"
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
                    "tooltip": "自动将中文提示词优化并翻译为英文"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "image_urls": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "参考图片URL（多个用逗号、分号或换行分隔）"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用下拉模型）"
                }),
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "max_wait_time": ("INT", {
                    "default": 1200,
                    "min": 60,
                    "max": 1800,
                    "tooltip": "最大等待时间（秒）"
                }),
                "poll_interval": ("INT", {
                    "default": 10,
                    "min": 5,
                    "max": 60,
                    "tooltip": "轮询间隔（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "enhance_prompt": "提示词增强",
            "api_key": "API密钥",
            "image_urls": "参考图片URL",
            "custom_model": "自定义模型",
            "api_base": "API地址",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "增强提示词")
    FUNCTION = "create_and_wait"
    CATEGORY = "KuAi/Grok"

    def create_and_wait(self, prompt, model, aspect_ratio, size, enhance_prompt=True, api_key="",
                       image_urls="", api_base="https://api.kegeai.top",
                       max_wait_time=1200, poll_interval=10, custom_model=""):
        """创建 Grok 视频并等待完成"""
        # 创建任务
        creator = GrokCreateVideo()
        task_id, status, enhanced_prompt = creator.create(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            size=size,
            enhance_prompt=enhance_prompt,
            api_key=api_key,
            image_urls=image_urls,
            api_base=api_base,
            custom_model=custom_model,
        )

        # 如果已经完成，直接返回
        if status in ["completed", "failed"]:
            querier = GrokQueryVideo()
            task_id, status, video_url, enhanced_prompt, _ = querier.query(task_id, api_key, api_base)
            return (task_id, status, video_url, enhanced_prompt)

        # 轮询等待完成
        print(f"[ComfyUI_KuAi_Power] Grok 等待视频生成完成，最多等待 {max_wait_time} 秒...")

        querier = GrokQueryVideo()
        elapsed = 0

        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                task_id, status, video_url, enhanced_prompt, _ = querier.query(task_id, api_key, api_base)

                if status == "completed":
                    print(f"[ComfyUI_KuAi_Power] Grok 视频生成完成！")
                    return (task_id, status, video_url, enhanced_prompt)

                print(f"[ComfyUI_KuAi_Power] Grok 任务进行中... 已等待 {elapsed}/{max_wait_time} 秒")

            except RuntimeError:
                raise
            except Exception as e:
                print(f"[ComfyUI_KuAi_Power] Grok 查询出错: {str(e)}")
                # 继续等待，不立即失败

        # 超时
        raise RuntimeError(
            f"Grok 视频生成超时（等待了 {max_wait_time} 秒）。"
            f"任务ID: {task_id}，可使用查询节点继续检查状态。"
        )


class GrokImage2Video:
    """OpenAI 格式 Grok 图生视频创建节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["grok-videos"], {
                    "default": "grok-videos",
                    "tooltip": "OpenAI 视频格式模型名称"
                }),
                "seconds": (["6", "10"], {
                    "default": "6",
                    "tooltip": "视频时长（秒）"
                }),
                "size": (["16:9", "9:16"], {
                    "default": "16:9",
                    "tooltip": "视频宽高比"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "input_reference": ("STRING", {
                    "forceInput": True,
                    "tooltip": "图片 URL"
                }),
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子；改变 seed 可避免重复提交"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "seconds": "时长",
            "size": "宽高比",
            "api_key": "API密钥",
            "input_reference": "图片URL",
            "api_base": "API地址"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("任务ID", "状态", "原始响应", "状态更新时间")
    FUNCTION = "create"
    CATEGORY = "KuAi/Grok"

    def create(self, prompt, model="grok-videos", seconds="6", size="16:9", api_key="", seed=0,
               input_reference="", api_base="https://ai.kegeai.top",
               aspect_ratio=None, enhance_prompt=True, image_url_1="", image_url_2="", image_url_3="",
               custom_model="", images=""):
        """使用 OpenAI 视频格式创建 Grok 图生视频任务"""
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        normalized_prompt = str(prompt or "").strip()
        if not normalized_prompt:
            raise RuntimeError("提示词不能为空")

        legacy_model = f"{model or ''} {custom_model or ''}".lower()
        effective_model = (custom_model or "").strip() or str(model or "grok-videos").strip()
        if effective_model.startswith("grok-video-"):
            effective_model = "grok-videos"
        if not effective_model:
            effective_model = "grok-videos"

        normalized_seconds = str(seconds or "").strip()
        if "10s" in legacy_model:
            normalized_seconds = "10"
        elif normalized_seconds not in {"6", "10"} and "6" in legacy_model:
            normalized_seconds = "6"
        elif normalized_seconds not in {"6", "10"}:
            normalized_seconds = "6"
        if normalized_seconds not in {"6", "10"}:
            raise RuntimeError("seconds 只能是 6 或 10")

        normalized_size = str(size or "").strip()
        if normalized_size not in {"16:9", "9:16"}:
            legacy_aspect_ratio = str(aspect_ratio or "").strip()
            normalized_size = {
                "3:2": "16:9",
                "2:3": "9:16",
                "1:1": "16:9",
            }.get(legacy_aspect_ratio, normalized_size)
        if normalized_size not in {"16:9", "9:16"}:
            raise RuntimeError("size 只能是 16:9 或 9:16")

        legacy_images = ensure_list_from_urls(images) if images else []
        normalized_input_reference = str(
            input_reference
            or image_url_1
            or image_url_2
            or image_url_3
            or (legacy_images[0] if legacy_images else "")
            or ""
        ).strip()

        api_base = str(api_base or "https://ai.kegeai.top").rstrip("/")
        headers = http_headers_auth_only(api_key)
        files = [
            ("model", (None, effective_model)),
            ("prompt", (None, normalized_prompt)),
            ("seconds", (None, normalized_seconds)),
            ("size", (None, normalized_size)),
        ]
        if normalized_input_reference:
            files.append(("input_reference", (None, normalized_input_reference)))

        print(f"[ComfyUI_KuAi_Power] Grok OpenAI格式图生视频任务: {normalized_prompt[:50]}...")
        print(f"[ComfyUI_KuAi_Power] 模型: {effective_model}, 时长: {normalized_seconds}s, 宽高比: {normalized_size}")

        try:
            resp = requests.post(
                f"{api_base}/v1/videos",
                files=files,
                headers=headers,
                timeout=60
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok 视频创建失败: {detail}")

            result = resp.json()
            task_id = str(
                result.get("id")
                or result.get("task_id")
                or result.get("data", {}).get("id", "")
                or result.get("data", {}).get("task_id", "")
            ).strip()
            status = str(
                result.get("status")
                or result.get("data", {}).get("status", "pending")
                or "pending"
            ).strip()
            raw_response = json.dumps(result, ensure_ascii=False)
            status_update_time = int(result.get("status_update_time", result.get("data", {}).get("status_update_time", 0) or 0))

            if not task_id:
                raise RuntimeError(f"创建响应缺少任务 ID")

            print(f"[ComfyUI_KuAi_Power] Grok OpenAI格式视频任务已创建: {task_id}, 状态: {status}")

            return (task_id, status, raw_response, status_update_time)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Grok 视频创建失败: {str(e)}")


class GrokImage2VideoUnified:
    """Grok 视频统一格式图生视频创建节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": (["grok-video-3", "grok-video-3-10s"], {
                    "default": "grok-video-3",
                    "tooltip": "模型名称"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "seconds": (["6", "10"], {
                    "default": "6",
                    "tooltip": "生成视频的时间长度（秒）"
                }),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {
                    "default": "3:2",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P"], {
                    "default": "720P",
                    "tooltip": "视频分辨率（当前接口暂只支持720P）"
                }),
                "images": ("STRING", {
                    "forceInput": True,
                    "multiline": True,
                    "tooltip": "垫图图片链接，多个用逗号、分号或换行分隔"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子；改变 seed 可避免重复提交"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model": "模型",
            "prompt": "提示词",
            "seconds": "时长",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "images": "图片URL",
            "api_key": "API密钥",
            "api_base": "API地址"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("任务ID", "状态", "原始响应", "状态更新时间")
    FUNCTION = "create"
    CATEGORY = "KuAi/Grok"

    def create(self, model="grok-video-3", prompt="", seconds="6", aspect_ratio="3:2", size="720P",
               images="", api_key="", seed=0, api_base="https://ai.kegeai.top", custom_model=""):
        """使用 /v1/video/create 统一格式创建 Grok 图生视频任务"""
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        normalized_prompt = str(prompt or "").strip()
        if not normalized_prompt:
            raise RuntimeError("提示词不能为空")

        actual_model = str(model or "grok-video-3").split(" (")[0].strip()
        effective_model = (custom_model or "").strip() or actual_model
        if not effective_model:
            effective_model = "grok-video-3"

        normalized_seconds = str(seconds or "").strip()
        if normalized_seconds not in {"6", "10"}:
            raise RuntimeError("seconds 只能是 6 或 10")

        normalized_aspect_ratio = str(aspect_ratio or "").strip()
        if normalized_aspect_ratio not in {"2:3", "3:2", "1:1"}:
            raise RuntimeError("aspect_ratio 只能是 2:3、3:2 或 1:1")

        normalized_size = str(size or "").strip()
        if normalized_size != "720P":
            raise RuntimeError("size 当前只支持 720P")

        image_list = ensure_list_from_urls(images) if images else []
        if not image_list:
            raise RuntimeError("images 不能为空，请提供至少一个垫图图片链接")

        api_base = str(api_base or "https://ai.kegeai.top").rstrip("/")
        payload = {
            "model": effective_model,
            "prompt": normalized_prompt,
            "seconds": normalized_seconds,
            "aspect_ratio": normalized_aspect_ratio,
            "size": normalized_size,
            "images": image_list,
            "seed": int(seed) if seed else 0,
        }

        print(f"[ComfyUI_KuAi_Power] Grok 统一格式图生视频任务: {normalized_prompt[:50]}...")
        print(f"[ComfyUI_KuAi_Power] 模型: {effective_model}, 时长: {normalized_seconds}s, 宽高比: {normalized_aspect_ratio}, 分辨率: {normalized_size}, 图片数: {len(image_list)}")

        try:
            resp = requests.post(
                f"{api_base}/v1/video/create",
                json=payload,
                headers=http_headers_json(api_key),
                timeout=60
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok 统一格式视频创建失败: {detail}")

            result = resp.json()
            task_id = str(result.get("id") or result.get("task_id") or "").strip()
            status = str(result.get("status") or "pending").strip()
            raw_response = json.dumps(result, ensure_ascii=False)
            status_update_time = int(result.get("status_update_time", 0) or 0)

            if not task_id:
                raise RuntimeError("创建响应缺少任务 ID")

            print(f"[ComfyUI_KuAi_Power] Grok 统一格式视频任务已创建: {task_id}, 状态: {status}")
            return (task_id, status, raw_response, status_update_time)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Grok 统一格式视频创建失败: {str(e)}")


class GrokImage2VideoAndWait:
    """Grok 图生视频一键生成节点（支持 0-3 张图片）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)"], {
                    "default": "grok-video-3 (6秒)",
                    "tooltip": "选择 Grok 模型"
                }),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {
                    "default": "3:2",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P"], {
                    "default": "720P",
                    "tooltip": "视频分辨率（暂只支持720P）"
                }),
                "enhance_prompt": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "自动将中文提示词优化并翻译为英文"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "image_url_1": ("STRING", {
                    "forceInput": True,
                    "tooltip": "第1张参考图片URL（来自图片上传节点）"
                }),
                "image_url_2": ("STRING", {
                    "forceInput": True,
                    "tooltip": "第2张参考图片URL（可选）"
                }),
                "image_url_3": ("STRING", {
                    "forceInput": True,
                    "tooltip": "第3张参考图片URL（可选）"
                }),
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用下拉模型）"
                }),
                "max_wait_time": ("INT", {
                    "default": 1200,
                    "min": 60,
                    "max": 1800,
                    "tooltip": "最大等待时间（秒）"
                }),
                "poll_interval": ("INT", {
                    "default": 10,
                    "min": 5,
                    "max": 60,
                    "tooltip": "轮询间隔（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "enhance_prompt": "提示词增强",
            "api_key": "API密钥",
            "image_url_1": "参考图片1",
            "image_url_2": "参考图片2",
            "image_url_3": "参考图片3",
            "api_base": "API地址",
            "custom_model": "自定义模型",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "增强提示词")
    FUNCTION = "create_and_wait"
    CATEGORY = "KuAi/Grok"

    def create_and_wait(self, prompt, model, aspect_ratio, size, enhance_prompt=True,
                       api_key="", image_url_1="", image_url_2="", image_url_3="",
                       api_base="https://ai.kegeai.top",
                       max_wait_time=1200, poll_interval=10, custom_model=""):
        """创建 Grok 图生视频并等待完成"""
        # 1. 创建任务
        creator = GrokImage2VideoUnified()
        seconds = "10" if "10s" in str(custom_model or model or "").lower() else "6"
        task_id, status, enhanced_prompt, _ = creator.create(
            prompt=prompt,
            model=model,
            seconds=seconds,
            aspect_ratio=aspect_ratio,
            size=size,
            api_key=api_key,
            images="\n".join([url for url in [image_url_1, image_url_2, image_url_3] if str(url or "").strip()]),
            api_base=api_base,
            custom_model=custom_model,
        )

        # 2. 如果已经完成，直接返回
        if _is_grok_success_status(status) or _is_grok_failed_status(status):
            querier = GrokQueryVideo()
            task_id, status, video_url, enhanced_prompt, _ = querier.query(task_id, api_key, api_base)
            return (task_id, status, video_url, enhanced_prompt)

        # 3. 轮询等待完成
        print(f"[ComfyUI_KuAi_Power] Grok 等待视频生成完成，最多等待 {max_wait_time} 秒...")

        querier = GrokQueryVideo()
        elapsed = 0

        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                task_id, status, video_url, enhanced_prompt, _ = querier.query(task_id, api_key, api_base)

                if _is_grok_success_status(status):
                    print(f"[ComfyUI_KuAi_Power] Grok 视频生成完成！")
                    return (task_id, status, video_url, enhanced_prompt)

                print(f"[ComfyUI_KuAi_Power] Grok 任务进行中... 已等待 {elapsed}/{max_wait_time} 秒")

            except RuntimeError:
                raise
            except Exception as e:
                print(f"[ComfyUI_KuAi_Power] Grok 查询出错: {str(e)}")
                # 继续等待，不立即失败

        # 4. 超时
        raise RuntimeError(
            f"Grok 视频生成超时（等待了 {max_wait_time} 秒）。"
            f"任务ID: {task_id}，可使用查询节点继续检查状态。"
        )


class GrokText2Video:
    """Grok 文生视频创建节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)", "grok-video-3-15s (15秒)"], {
                    "default": "grok-video-3 (6秒)",
                    "tooltip": "选择 Grok 模型"
                }),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {
                    "default": "3:2",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P", "1080P"], {
                    "default": "720P",
                    "tooltip": "视频分辨率（暂只支持720P）"
                }),
                                "enhance_prompt": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "自动将中文提示词优化并翻译为英文"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用下拉模型）"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子；改变 seed 可避免重复提交"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "enhance_prompt": "提示词增强",
            "api_key": "API密钥",
            "api_base": "API地址",
            "custom_model": "自定义模型"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "增强提示词")
    FUNCTION = "create"
    CATEGORY = "KuAi/Grok"

    def create(self, prompt, model, aspect_ratio, size, enhance_prompt=True, api_key="", seed=0, api_base="https://api.kegeai.top", custom_model=""):
        """创建 Grok 文生视频任务"""
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        api_base = api_base.rstrip("/")
        headers = http_headers_auth_only(api_key)

        # 提取实际的模型名称（去掉时长说明）
        actual_model = model.split(" (")[0] if " (" in model else model
        effective_model = (custom_model or "").strip() or actual_model

        # 根据 effective_model 判断是否支持 1080P（只有 15 秒模型支持）
        effective_size = size
        if "15s" not in effective_model.lower() and size == "1080P":
            effective_size = "720P"
            print(f"[ComfyUI_KuAi_Power] 警告：{effective_model} 不支持 1080P，已自动降级到 720P")

        payload = {
            "model": effective_model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "size": effective_size,
            "enhance_prompt": bool(enhance_prompt),
            "images": [],
            "seed": int(seed) if seed else 0,
        }

        print(f"[ComfyUI_KuAi_Power] Grok 文生视频任务: {prompt[:50]}...")
        print(f"[ComfyUI_KuAi_Power] 模型: {effective_model}, 宽高比: {aspect_ratio}, 分辨率: {effective_size}")

        try:
            resp = requests.post(
                f"{api_base}/v1/video/create",
                json=payload,
                headers=headers,
                timeout=30
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok 文生视频创建失败: {detail}")

            result = resp.json()
            task_id = result.get("id", "")
            status = result.get("status", "pending")
            enhanced_prompt = result.get("enhanced_prompt", "")

            print(f"[ComfyUI_KuAi_Power] Grok 文生视频任务已创建: {task_id}, 状态: {status}")

            return (task_id, status, enhanced_prompt)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Grok 文生视频创建失败: {str(e)}")


class GrokText2VideoAndWait:
    """Grok 文生视频一键生成节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
                }),
                "model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)"], {
                    "default": "grok-video-3 (6秒)",
                    "tooltip": "选择 Grok 模型"
                }),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {
                    "default": "3:2",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P", "1080P"], {
                    "default": "720P",
                    "tooltip": "视频分辨率（暂只支持720P）"
                }),
                                "enhance_prompt": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "自动将中文提示词优化并翻译为英文"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用下拉模型）"
                }),
                "max_wait_time": ("INT", {
                    "default": 1200,
                    "min": 60,
                    "max": 1800,
                    "tooltip": "最大等待时间（秒）"
                }),
                "poll_interval": ("INT", {
                    "default": 10,
                    "min": 5,
                    "max": 60,
                    "tooltip": "轮询间隔（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "enhance_prompt": "提示词增强",
            "api_key": "API密钥",
            "api_base": "API地址",
            "custom_model": "自定义模型",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "增强提示词")
    FUNCTION = "create_and_wait"
    CATEGORY = "KuAi/Grok"

    def create_and_wait(self, prompt, model, aspect_ratio, size, enhance_prompt=True,
                       api_key="", api_base="https://api.kegeai.top",
                       max_wait_time=1200, poll_interval=10, custom_model=""):
        """创建 Grok 文生视频并等待完成"""
        # 1. 创建任务
        creator = GrokText2Video()
        task_id, status, enhanced_prompt = creator.create(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            size=size,
            enhance_prompt=enhance_prompt,
            api_key=api_key,
            api_base=api_base,
            custom_model=custom_model,
        )

        # 2. 如果已经完成，直接返回
        if status in ["completed", "failed"]:
            querier = GrokQueryVideo()
            task_id, status, video_url, enhanced_prompt, _ = querier.query(task_id, api_key, api_base)
            return (task_id, status, video_url, enhanced_prompt)

        # 3. 轮询等待完成
        print(f"[ComfyUI_KuAi_Power] Grok 等待文生视频完成，最多等待 {max_wait_time} 秒...")

        querier = GrokQueryVideo()
        elapsed = 0

        while elapsed < max_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                task_id, status, video_url, enhanced_prompt, _ = querier.query(task_id, api_key, api_base)

                if status == "completed":
                    print(f"[ComfyUI_KuAi_Power] Grok 文生视频完成！")
                    return (task_id, status, video_url, enhanced_prompt)

                print(f"[ComfyUI_KuAi_Power] Grok 任务进行中... 已等待 {elapsed}/{max_wait_time} 秒")

            except RuntimeError:
                raise
            except Exception as e:
                print(f"[ComfyUI_KuAi_Power] Grok 查询出错: {str(e)}")
                # 继续等待，不立即失败

        # 4. 超时
        raise RuntimeError(
            f"Grok 文生视频超时（等待了 {max_wait_time} 秒）。"
            f"任务ID: {task_id}，可使用查询节点继续检查状态。"
        )


def explain_grok_extend_error(detail: str) -> str:
    if "task_origin_not_exist" not in detail:
        return f"Grok 扩展视频失败: {detail}"

    return (
        "Grok 扩展视频失败：原始视频任务不存在或不可扩展。"
        "请确认 task_id 是否来自首段视频节点的真实输出、首段生成和扩展是否使用同一个 API 地址、"
        "以及当前 API Key 是否属于创建该任务的同一账号。"
        f" 后端详情: {detail}"
    )


class GrokExtendVideo:
    """创建 Grok 扩展视频任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "扩展视频提示词"}),
                "task_id": ("STRING", {"default": "", "tooltip": "待扩展的视频任务ID"}),
                "model": (["grok-video-3"], {"default": "grok-video-3", "tooltip": "选择 Grok 模型"}),
                "start_time": ("INT", {"default": 10, "min": 1, "max": 9999, "tooltip": "从第几秒开始扩展"}),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {"default": "3:2", "tooltip": "视频宽高比"}),
                "size": (["720P", "1080P"], {"default": "720P", "tooltip": "视频分辨率"}),
                "upscale": ("BOOLEAN", {"default": False, "tooltip": "是否启用放大"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
            },
            "optional": {
                "api_base": ("STRING", {"default": "https://ai.kegeai.top", "tooltip": "API端点地址"}),
                "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型（留空使用下拉模型）"}),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "扩展提示词", "task_id": "任务ID", "model": "模型",
            "start_time": "开始扩展时间", "aspect_ratio": "宽高比", "size": "分辨率",
            "upscale": "是否放大", "api_key": "API密钥", "api_base": "API地址", "custom_model": "自定义模型"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("任务ID", "状态", "扩展提示词", "状态更新时间", "视频时长")
    FUNCTION = "create"
    CATEGORY = "KuAi/Grok"

    def create(self, prompt, task_id, model, start_time, aspect_ratio, size, upscale=False,
               api_key="", api_base="https://ai.kegeai.top", custom_model=""):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")
        if not str(task_id).strip():
            raise RuntimeError("任务ID不能为空")
        if not str(prompt).strip():
            raise RuntimeError("提示词不能为空")
        try:
            normalized_start_time = int(start_time)
        except (TypeError, ValueError):
            raise RuntimeError("start_time 必须是整数")
        if normalized_start_time <= 0:
            raise RuntimeError("start_time 必须大于 0")

        api_base = api_base.rstrip("/")
        headers = http_headers_auth_only(api_key)
        effective_model = (custom_model or "").strip() or model
        total_duration = normalized_start_time + (6 if effective_model == "grok-video-3" else 6)

        payload = {
            "model": effective_model,
            "prompt": prompt,
            "task_id": task_id,
            "aspect_ratio": aspect_ratio,
            "size": size,
            "start_time": normalized_start_time,
            "upscale": bool(upscale),
        }

        print(f"[ComfyUI_KuAi_Power] Grok 扩展视频任务: {task_id} 从 {normalized_start_time}s 开始扩展")
        print(f"[ComfyUI_KuAi_Power] 模型: {effective_model}, 宽高比: {aspect_ratio}, 分辨率: {size}")

        try:
            resp = requests.post(f"{api_base}/v1/video/extend", json=payload, headers=headers, timeout=30)
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(explain_grok_extend_error(detail))

            result = resp.json()
            new_task_id = result.get("id", "")
            status = result.get("status", "pending")
            enhanced_prompt = result.get("enhanced_prompt") or prompt
            status_update_time = int(result.get("status_update_time", 0))

            if not new_task_id:
                raise RuntimeError("创建响应缺少任务 ID")

            print(f"[ComfyUI_KuAi_Power] Grok 扩展任务已创建: {new_task_id}, 状态: {status}")
            return (new_task_id, status, enhanced_prompt, status_update_time, total_duration)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Grok 扩展视频失败: {str(e)}")


class GrokExtendVideoAndWait:
    """创建 Grok 扩展视频并等待完成"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "扩展视频提示词"}),
                "task_id": ("STRING", {"default": "", "tooltip": "待扩展的视频任务ID"}),
                "model": (["grok-video-3"], {"default": "grok-video-3", "tooltip": "选择 Grok 模型"}),
                "start_time": ("INT", {"default": 10, "min": 1, "max": 9999, "tooltip": "从第几秒开始扩展"}),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {"default": "3:2", "tooltip": "视频宽高比"}),
                "size": (["720P", "1080P"], {"default": "720P", "tooltip": "视频分辨率"}),
                "upscale": ("BOOLEAN", {"default": False, "tooltip": "是否启用放大"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
            },
            "optional": {
                "api_base": ("STRING", {"default": "https://ai.kegeai.top", "tooltip": "API端点地址"}),
                "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型（留空使用下拉模型）"}),
                "max_wait_time": ("INT", {"default": 1200, "min": 60, "max": 1800, "tooltip": "最大等待时间（秒）"}),
                "poll_interval": ("INT", {"default": 10, "min": 5, "max": 60, "tooltip": "轮询间隔（秒）"}),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "扩展提示词", "task_id": "任务ID", "model": "模型",
            "start_time": "开始扩展时间", "aspect_ratio": "宽高比", "size": "分辨率",
            "upscale": "是否放大", "api_key": "API密钥", "api_base": "API地址",
            "custom_model": "自定义模型", "max_wait_time": "最大等待时间", "poll_interval": "轮询间隔"
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "扩展提示词", "视频时长")
    FUNCTION = "create_and_wait"
    CATEGORY = "KuAi/Grok"

    def create_and_wait(self, prompt, task_id, model, start_time, aspect_ratio, size, upscale=False,
                       api_key="", api_base="https://ai.kegeai.top", custom_model="",
                       max_wait_time=1200, poll_interval=10):
        source_task_id, source_status, source_video_url, _, _, source_elapsed = wait_grok_task_success(
            task_id=task_id,
            api_key=api_key,
            api_base=api_base,
            max_wait_time=max_wait_time,
            poll_interval=poll_interval,
            task_label="Grok 原视频任务",
        )
        print(
            f"[ComfyUI_KuAi_Power] Grok 原视频任务已成功: {source_task_id}, "
            f"状态: {source_status}, 视频URL已获取"
        )

        creator = GrokExtendVideo()
        new_task_id, status, enhanced_prompt, _, total_duration = creator.create(
            prompt=prompt, task_id=source_task_id, model=model, start_time=start_time,
            aspect_ratio=aspect_ratio, size=size, upscale=upscale,
            api_key=api_key, api_base=api_base, custom_model=custom_model,
        )

        if _is_grok_success_status(status):
            querier = GrokQueryVideo()
            new_task_id, status, video_url, enhanced_prompt, _ = querier.query(new_task_id, api_key, api_base)
            return (new_task_id, status, video_url, enhanced_prompt, total_duration)
        if _is_grok_failed_status(status):
            raise RuntimeError(f"Grok 扩展视频失败: {enhanced_prompt or '任务创建失败'}")

        remaining_wait_time = max(0, int(max_wait_time) - int(source_elapsed))
        print(f"[ComfyUI_KuAi_Power] Grok 等待扩展视频完成，剩余最多等待 {remaining_wait_time} 秒...")

        querier = GrokQueryVideo()
        elapsed = 0

        while elapsed < remaining_wait_time:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                new_task_id, status, video_url, enhanced_prompt, _ = querier.query(new_task_id, api_key, api_base)
                if _is_grok_success_status(status):
                    print(f"[ComfyUI_KuAi_Power] Grok 扩展视频完成！")
                    return (new_task_id, status, video_url, enhanced_prompt, total_duration)
                print(f"[ComfyUI_KuAi_Power] Grok 扩展任务进行中... 已等待 {elapsed}/{remaining_wait_time} 秒")
            except RuntimeError:
                raise
            except Exception as e:
                print(f"[ComfyUI_KuAi_Power] Grok 查询出错: {str(e)}")

        raise RuntimeError(
            f"Grok 扩展视频超时（总等待了 {max_wait_time} 秒）。"
            f"任务ID: {new_task_id}，可使用查询节点继续检查状态。"
        )
