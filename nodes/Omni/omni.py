"""Omni 视频生成节点"""

import json
import time

import requests

from ..Sora2.kuai_utils import (
    env_or,
    ensure_list_from_urls,
    extract_error_message_from_response,
    extract_task_failure_detail,
    http_headers_auth_only,
    json_get,
)


OMNI_SUCCESS_STATUSES = {"completed", "complete", "success", "succeeded", "succeed", "done"}
OMNI_FAILED_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}
OMNI_DEFAULT_API_BASE = "https://ai.kegeai.top"
OMNI_DEFAULT_CREATE_MODEL = "omni-flash-components"
OMNI_DEFAULT_QUERY_MODEL = "omni-flash"


def _status_key(status):
    return str(status or "").strip().lower()


def _is_success_status(status):
    return _status_key(status) in OMNI_SUCCESS_STATUSES


def _is_failed_status(status):
    return _status_key(status) in OMNI_FAILED_STATUSES


def _first_non_empty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_status_update_time(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


def _query_model_from_task_id(task_id):
    prefix = str(task_id or "").split(":", 1)[0].strip()
    return prefix or OMNI_DEFAULT_QUERY_MODEL


def _query_model_from_create_model(model, task_id=""):
    from_task_id = _query_model_from_task_id(task_id)
    if from_task_id != OMNI_DEFAULT_QUERY_MODEL or ":" in str(task_id or ""):
        return from_task_id
    clean = str(model or "").strip()
    if clean.endswith("-components"):
        return clean[:-len("-components")]
    return clean or OMNI_DEFAULT_QUERY_MODEL


def _extract_video_url(data):
    if not isinstance(data, dict):
        return ""

    direct = _first_non_empty(
        data.get("video_url"),
        data.get("videoUrl"),
        data.get("url"),
        data.get("video"),
        json_get(data, "result.video_url", ""),
        json_get(data, "result.videoUrl", ""),
        json_get(data, "result.url", ""),
        json_get(data, "result.video", ""),
        json_get(data, "output.video_url", ""),
        json_get(data, "output.url", ""),
        json_get(data, "data.video_url", ""),
        json_get(data, "data.url", ""),
    )
    if direct:
        return direct

    for path in ("videos", "result.videos", "output.videos", "data.videos"):
        values = json_get(data, path, [])
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    nested = _first_non_empty(
                        item.get("url"),
                        item.get("video_url"),
                        item.get("videoUrl"),
                    )
                    if nested:
                        return nested

    return ""


def _build_images(image_1="", image_2="", image_urls=""):
    images = []
    for value in (image_1, image_2):
        clean = str(value or "").strip()
        if clean:
            images.append(clean)
    images.extend(ensure_list_from_urls(image_urls) if image_urls else [])
    return images


class OmniCreateVideo:
    """创建 Omni 视频生成任务，images 可为空"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频提示词；图片为空时为文生视频"
                }),
                "model": ([OMNI_DEFAULT_CREATE_MODEL, OMNI_DEFAULT_QUERY_MODEL], {
                    "default": OMNI_DEFAULT_CREATE_MODEL,
                    "tooltip": "创建模型名"
                }),
                "aspect_ratio": (["9:16", "16:9"], {
                    "default": "9:16",
                    "tooltip": "视频宽高比"
                }),
                "enable_upsample": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "启用超分"
                }),
                "enhance_prompt": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "中文提示词自动优化并翻译"
                }),
            },
            "optional": {
                "image_1": ("STRING", {
                    "default": "",
                    "tooltip": "首帧图片 URL；为空则不传图片"
                }),
                "image_2": ("STRING", {
                    "default": "",
                    "tooltip": "尾帧图片 URL；只传 image_1 时为首帧图生视频"
                }),
                "image_urls": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "额外图片 URL，多个用逗号、分号或换行分隔"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义创建模型；留空使用下拉模型"
                }),
                "api_base": ("STRING", {
                    "default": OMNI_DEFAULT_API_BASE,
                    "tooltip": "API 地址"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API Key；留空使用环境变量 KUAI_API_KEY"
                }),
                "timeout": ("INT", {
                    "default": 1800,
                    "min": 5,
                    "max": 9999,
                    "tooltip": "创建请求超时（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "enable_upsample": "启用超分",
            "enhance_prompt": "提示词增强",
            "image_1": "首帧图片URL",
            "image_2": "尾帧图片URL",
            "image_urls": "额外图片URL",
            "custom_model": "自定义模型",
            "api_base": "API地址",
            "api_key": "API密钥",
            "timeout": "超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "查询模型", "状态更新时间", "原始响应JSON")
    FUNCTION = "create"
    CATEGORY = "KuAi/Omni"

    def create(self, prompt, model, aspect_ratio, enable_upsample, enhance_prompt,
               image_1="", image_2="", image_urls="", custom_model="",
               api_base=OMNI_DEFAULT_API_BASE, api_key="", timeout=1800):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量 KUAI_API_KEY 中设置")

        api_base = (api_base or OMNI_DEFAULT_API_BASE).rstrip("/")
        effective_model = (custom_model or "").strip() or model
        images = _build_images(image_1=image_1, image_2=image_2, image_urls=image_urls)

        payload = {
            "model": effective_model,
            "aspect_ratio": aspect_ratio,
            "enable_upsample": bool(enable_upsample),
            "enhance_prompt": bool(enhance_prompt),
            "images": images,
            "prompt": prompt,
        }

        try:
            resp = requests.post(
                f"{api_base}/v1/video/create",
                headers=http_headers_auth_only(api_key),
                json=payload,
                timeout=int(timeout),
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Omni 视频创建失败: {detail}")
            data = resp.json()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Omni 视频创建失败: {exc}")

        task_id = data.get("id") or ""
        status = data.get("status") or ""
        status_update_time = _normalize_status_update_time(data.get("status_update_time"))
        if not task_id:
            raise RuntimeError(f"Omni 创建响应缺少任务 ID: {json.dumps(data, ensure_ascii=False)}")

        query_model = _query_model_from_create_model(effective_model, task_id)
        return (
            task_id,
            status,
            query_model,
            status_update_time,
            json.dumps(data, ensure_ascii=False),
        )


class OmniQueryTask:
    """查询 Omni 视频任务，支持轮询返回视频 URL"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "task_id": ("STRING", {
                    "default": "",
                    "tooltip": "创建接口返回的任务 ID"
                }),
            },
            "optional": {
                "model": ("STRING", {
                    "default": "",
                    "tooltip": "查询模型；留空时从任务ID前缀自动推断"
                }),
                "api_base": ("STRING", {
                    "default": OMNI_DEFAULT_API_BASE,
                    "tooltip": "API 地址"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API Key；留空使用环境变量 KUAI_API_KEY"
                }),
                "wait": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否轮询等待完成"
                }),
                "poll_interval_sec": ("INT", {
                    "default": 10,
                    "min": 5,
                    "max": 90,
                    "tooltip": "轮询间隔（秒）"
                }),
                "timeout_sec": ("INT", {
                    "default": 1800,
                    "min": 60,
                    "max": 9999,
                    "tooltip": "总超时时间（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "task_id": "任务ID",
            "model": "查询模型",
            "api_base": "API地址",
            "api_key": "API密钥",
            "wait": "等待完成",
            "poll_interval_sec": "轮询间隔",
            "timeout_sec": "超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频URL", "原始响应JSON", "任务ID")
    FUNCTION = "query"
    CATEGORY = "KuAi/Omni"

    def query(self, task_id, model="", api_base=OMNI_DEFAULT_API_BASE, api_key="",
              wait=True, poll_interval_sec=10, timeout_sec=1800):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量 KUAI_API_KEY 中设置")

        if not str(task_id or "").strip():
            raise RuntimeError("任务ID不能为空")

        api_base = (api_base or OMNI_DEFAULT_API_BASE).rstrip("/")
        query_model = str(model or "").strip() or _query_model_from_task_id(task_id)

        def once():
            try:
                resp = requests.get(
                    f"{api_base}/v1/video/query",
                    headers=http_headers_auth_only(api_key),
                    params={"id": task_id, "model": query_model},
                    timeout=60,
                )
                if resp.status_code >= 400:
                    detail = extract_error_message_from_response(resp)
                    raise RuntimeError(f"Omni 视频查询失败: {detail}")
                data = resp.json()
            except RuntimeError:
                raise
            except Exception as exc:
                raise RuntimeError(f"Omni 视频查询失败: {exc}")

            status = data.get("status") or "unknown"
            video_url = _extract_video_url(data)
            raw_json = json.dumps(data, ensure_ascii=False)

            if _is_failed_status(status):
                fail_detail = extract_task_failure_detail(data) or data.get("error") or raw_json
                raise RuntimeError(f"Omni 视频任务失败: {fail_detail}")

            if _is_success_status(status) and not video_url:
                missing_detail = extract_task_failure_detail(data) or "任务已完成但未返回视频URL"
                raise RuntimeError(f"Omni 视频查询失败: {missing_detail}")

            return status, video_url, raw_json, task_id

        if not wait:
            return once()

        deadline = time.time() + int(timeout_sec)
        last_raw = ""
        while time.time() < deadline:
            status, video_url, raw_json, returned_task_id = once()
            last_raw = raw_json
            if _is_success_status(status):
                return status, video_url, raw_json, returned_task_id
            time.sleep(int(poll_interval_sec))

        return ("timeout", "", last_raw or json.dumps({"error": "timeout"}, ensure_ascii=False), task_id)


class OmniCreateAndWait:
    """创建 Omni 视频并轮询等待完成"""

    @classmethod
    def INPUT_TYPES(cls):
        inputs = OmniCreateVideo.INPUT_TYPES()
        query_optional = dict(OmniQueryTask.INPUT_TYPES()["optional"])
        query_optional.pop("model", None)
        query_optional.pop("api_base", None)
        query_optional.pop("api_key", None)
        query_optional.pop("wait", None)
        inputs["optional"].update(query_optional)
        return inputs

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频URL", "原始响应JSON", "任务ID")
    FUNCTION = "run"
    CATEGORY = "KuAi/Omni"

    def run(self, **kwargs):
        create_inputs = OmniCreateVideo.INPUT_TYPES()
        create_keys = set(create_inputs["required"].keys()) | set(create_inputs["optional"].keys())
        creator_kwargs = {key: value for key, value in kwargs.items() if key in create_keys}

        creator = OmniCreateVideo()
        task_id, _status, query_model, _status_update_time, _raw = creator.create(**creator_kwargs)

        querier = OmniQueryTask()
        return querier.query(
            task_id=task_id,
            model=query_model,
            api_base=creator_kwargs.get("api_base", OMNI_DEFAULT_API_BASE),
            api_key=creator_kwargs.get("api_key", ""),
            wait=True,
            poll_interval_sec=kwargs.get("poll_interval_sec", 10),
            timeout_sec=kwargs.get("timeout_sec", 1800),
        )


NODE_CLASS_MAPPINGS = {
    "OmniCreateVideo": OmniCreateVideo,
    "OmniQueryTask": OmniQueryTask,
    "OmniCreateAndWait": OmniCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "OmniCreateVideo": "🎬 Omni 创建视频",
    "OmniQueryTask": "🔍 Omni 查询轮询",
    "OmniCreateAndWait": "⚡ Omni 一键生成视频",
}
