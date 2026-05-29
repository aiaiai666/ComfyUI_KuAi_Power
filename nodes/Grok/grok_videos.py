"""Grok-videos 6-10s 视频节点"""

import json
import time

import requests

from ..Sora2.kuai_utils import (
    env_or,
    extract_error_message_from_response,
    extract_task_failure_detail,
    http_headers_auth_only,
    http_headers_json,
)


_ALLOWED_SECONDS = {"6", "10"}
_ALLOWED_SIZES = {"16:9", "9:16"}


def _normalize_prompt(prompt):
    value = str(prompt or "").strip()
    if not value:
        raise RuntimeError("提示词不能为空")
    return value


def _normalize_task_id(task_id):
    value = str(task_id or "").strip()
    if not value:
        raise RuntimeError("任务ID不能为空")
    return value


def _normalize_seconds(seconds):
    value = str(seconds or "").strip()
    if value not in _ALLOWED_SECONDS:
        raise RuntimeError("seconds 只能是 6 或 10")
    return value


def _normalize_size(size):
    value = str(size or "").strip()
    if value not in _ALLOWED_SIZES:
        raise RuntimeError("size 只能是 16:9 或 9:16")
    return value


def _normalize_input_reference(input_reference):
    return str(input_reference or "").strip()


def _normalize_max_wait_time(max_wait_time):
    try:
        value = int(max_wait_time)
    except Exception:
        raise RuntimeError("最大等待时间必须是整数")
    if value < 60 or value > 1800:
        raise RuntimeError("最大等待时间必须在 60 到 1800 秒之间")
    return value


def _normalize_poll_interval(poll_interval):
    try:
        value = int(poll_interval)
    except Exception:
        raise RuntimeError("轮询间隔必须是整数")
    if value < 5 or value > 60:
        raise RuntimeError("轮询间隔必须在 5 到 60 秒之间")
    return value


def _extract_task_id(data):
    return str(
        data.get("id")
        or data.get("task_id")
        or data.get("data", {}).get("id", "")
        or data.get("data", {}).get("task_id", "")
    ).strip()


def _extract_status(data, default="pending"):
    return str(
        data.get("status")
        or data.get("data", {}).get("status", default)
        or default
    ).strip()


def _extract_video_url(data):
    return str(
        data.get("video_url")
        or data.get("data", {}).get("video_url", "")
        or data.get("url", "")
    ).strip()


def _extract_cover_url(data):
    return str(
        data.get("cover_url")
        or data.get("cover")
        or data.get("poster_url")
        or data.get("thumbnail_url")
        or data.get("data", {}).get("cover_url", "")
        or data.get("data", {}).get("cover", "")
        or data.get("data", {}).get("poster_url", "")
        or data.get("data", {}).get("thumbnail_url", "")
    ).strip()


class GrokVideosCreateVideo:
    """创建 Grok-videos 视频任务"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
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
                    "default": "",
                    "tooltip": "参考图片URL（留空则按文生视频处理）"
                }),
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                    "tooltip": "API端点地址"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "seconds": "时长",
            "size": "宽高比",
            "api_key": "API密钥",
            "input_reference": "参考图片URL",
            "api_base": "API地址",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "原始响应")
    FUNCTION = "create"
    CATEGORY = "KuAi/Grok"

    def create(self, prompt, seconds, size, api_key="", input_reference="", api_base="https://api.kegeai.top"):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        normalized_prompt = _normalize_prompt(prompt)
        normalized_seconds = _normalize_seconds(seconds)
        normalized_size = _normalize_size(size)
        normalized_input_reference = _normalize_input_reference(input_reference)

        api_base = str(api_base or "https://api.kegeai.top").rstrip("/")
        headers = http_headers_auth_only(api_key)
        files = [
            ("model", (None, "grok-videos")),
            ("prompt", (None, normalized_prompt)),
            ("seconds", (None, normalized_seconds)),
            ("size", (None, normalized_size)),
        ]
        if normalized_input_reference:
            files.append(("input_reference", (None, normalized_input_reference)))

        print(f"[ComfyUI_KuAi_Power] Grok-videos 创建视频任务: {normalized_prompt[:50]}...")
        print(f"[ComfyUI_KuAi_Power] 时长: {normalized_seconds} 秒, 宽高比: {normalized_size}")
        if normalized_input_reference:
            print("[ComfyUI_KuAi_Power] 模式: 图生视频")
        else:
            print("[ComfyUI_KuAi_Power] 模式: 文生视频")

        try:
            resp = requests.post(
                f"{api_base}/v1/videos",
                files=files,
                headers=headers,
                timeout=60,
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok-videos 创建任务失败: {detail}")

            result = resp.json()
            task_id = _extract_task_id(result)
            if not task_id:
                raise RuntimeError("Grok-videos 创建任务失败: 响应中缺少任务ID")
            status = _extract_status(result, "pending")
            raw = json.dumps(result, ensure_ascii=False)

            print(f"[ComfyUI_KuAi_Power] Grok-videos 任务已创建: {task_id}, 状态: {status}")
            return (task_id, status, raw)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Grok-videos 创建任务失败: {str(exc)}")


class GrokVideosQueryVideo:
    """查询 Grok-videos 视频任务状态"""

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
            "api_base": "API地址",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "封面URL", "原始响应")
    FUNCTION = "query"
    CATEGORY = "KuAi/Grok"

    def query(self, task_id, api_key="", api_base="https://api.kegeai.top"):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        normalized_task_id = _normalize_task_id(task_id)
        api_base = str(api_base or "https://api.kegeai.top").rstrip("/")
        headers = http_headers_json(api_key)

        print(f"[ComfyUI_KuAi_Power] Grok-videos 查询任务: {normalized_task_id}")

        try:
            resp = requests.get(
                f"{api_base}/v1/video/query",
                params={"id": normalized_task_id},
                headers=headers,
                timeout=30,
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok-videos 查询失败: {detail}")

            result = resp.json()
            status = _extract_status(result, "unknown")
            video_url = _extract_video_url(result)
            cover_url = _extract_cover_url(result)
            raw = json.dumps(result, ensure_ascii=False)

            if status == "failed":
                fail_detail = extract_task_failure_detail(result) or raw
                raise RuntimeError(f"Grok-videos 任务失败: {fail_detail}")

            if status == "completed" and not video_url:
                raise RuntimeError("Grok-videos 查询失败: 任务已完成但未返回视频URL")

            print(f"[ComfyUI_KuAi_Power] Grok-videos 任务状态: {status}")
            if video_url:
                print(f"[ComfyUI_KuAi_Power] Grok-videos 视频URL: {video_url}")

            return (normalized_task_id, status, video_url, cover_url, raw)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Grok-videos 查询失败: {str(exc)}")


class GrokVideosCreateAndWait:
    """创建 Grok-videos 视频并等待完成"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词"
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
                    "default": "",
                    "tooltip": "参考图片URL（留空则按文生视频处理）"
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
            "seconds": "时长",
            "size": "宽高比",
            "api_key": "API密钥",
            "input_reference": "参考图片URL",
            "api_base": "API地址",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "原始响应")
    FUNCTION = "create_and_wait"
    CATEGORY = "KuAi/Grok"

    def create_and_wait(
        self,
        prompt,
        seconds,
        size,
        api_key="",
        input_reference="",
        api_base="https://api.kegeai.top",
        max_wait_time=1200,
        poll_interval=10,
    ):
        normalized_max_wait_time = _normalize_max_wait_time(max_wait_time)
        normalized_poll_interval = _normalize_poll_interval(poll_interval)

        creator = GrokVideosCreateVideo()
        task_id, status, raw = creator.create(
            prompt=prompt,
            seconds=seconds,
            size=size,
            api_key=api_key,
            input_reference=input_reference,
            api_base=api_base,
        )

        querier = GrokVideosQueryVideo()

        if status == "completed":
            task_id, status, video_url, _cover_url, query_raw = querier.query(task_id, api_key, api_base)
            return (task_id, status, video_url, query_raw)

        if status == "failed":
            raise RuntimeError(f"Grok-videos 任务创建后立即失败: {raw}")

        print(f"[ComfyUI_KuAi_Power] Grok-videos 等待视频生成完成，最多等待 {normalized_max_wait_time} 秒...")
        elapsed = 0

        while elapsed < normalized_max_wait_time:
            time.sleep(normalized_poll_interval)
            elapsed += normalized_poll_interval
            task_id, status, video_url, _cover_url, query_raw = querier.query(task_id, api_key, api_base)

            if status == "completed":
                print("[ComfyUI_KuAi_Power] Grok-videos 视频生成完成！")
                return (task_id, status, video_url, query_raw)

            print(f"[ComfyUI_KuAi_Power] Grok-videos 任务进行中... 已等待 {elapsed}/{normalized_max_wait_time} 秒")

        raise RuntimeError(
            f"Grok-videos 视频生成超时（等待了 {normalized_max_wait_time} 秒）。"
            f"任务ID: {task_id}，可使用查询节点继续检查状态。"
        )
