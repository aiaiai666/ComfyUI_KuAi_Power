"""Grok-image 视频生成节点"""

import json
import time

import requests

from ..Sora2.kuai_utils import (
    ensure_list_from_urls,
    env_or,
    extract_error_message_from_response,
    extract_task_failure_detail,
    http_headers_auth_only,
    http_headers_json,
    json_get,
)


DEFAULT_API_BASE = "https://ai.kegeai.top"
DEFAULT_MODEL = "grok-imagine-video"
MODELS = [DEFAULT_MODEL]
GENERATION_MODES = ["自动", "文生视频", "图生视频", "视频生视频"]
SUCCESS_STATUSES = {"completed", "complete", "success", "succeeded", "succeed", "done"}
FAILED_STATUSES = {"failed", "failure", "error", "cancelled", "canceled", "cancel", "rejected"}


def _status_key(status):
    return str(status or "").strip().lower()


def _first_non_empty(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_task_id(data):
    if not isinstance(data, dict):
        return ""
    return _first_non_empty(
        data.get("id"),
        data.get("task_id"),
        json_get(data, "data.id", ""),
        json_get(data, "data.task_id", ""),
        json_get(data, "result.id", ""),
        json_get(data, "result.task_id", ""),
    )


def _extract_status(data, default="pending"):
    if not isinstance(data, dict):
        return default
    return _first_non_empty(
        data.get("status"),
        json_get(data, "data.status", ""),
        json_get(data, "result.status", ""),
    ) or default


def _extract_video_url(data):
    if not isinstance(data, dict):
        return ""

    direct = _first_non_empty(
        data.get("video_url"),
        data.get("videoUrl"),
        data.get("url"),
        json_get(data, "data.video_url", ""),
        json_get(data, "data.videoUrl", ""),
        json_get(data, "data.url", ""),
        json_get(data, "result.video_url", ""),
        json_get(data, "result.videoUrl", ""),
        json_get(data, "result.url", ""),
        json_get(data, "output.video_url", ""),
        json_get(data, "output.url", ""),
    )
    if direct:
        return direct

    for path in ("videos", "data.videos", "result.videos", "output.videos"):
        values = json_get(data, path, [])
        if isinstance(values, list):
            for item in values:
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    nested = _first_non_empty(item.get("url"), item.get("video_url"), item.get("videoUrl"))
                    if nested:
                        return nested
    return ""


def _extract_enhanced_prompt(data):
    if not isinstance(data, dict):
        return ""
    return _first_non_empty(
        data.get("enhanced_prompt"),
        data.get("actual_prompt"),
        json_get(data, "data.enhanced_prompt", ""),
        json_get(data, "result.enhanced_prompt", ""),
    )


def _extract_status_update_time(data):
    if not isinstance(data, dict):
        return 0
    value = data.get("status_update_time")
    if value is None:
        value = json_get(data, "data.status_update_time", 0)
    try:
        return int(value or 0)
    except Exception:
        return 0


def _normalize_prompt(prompt):
    value = str(prompt or "").strip()
    if not value:
        raise RuntimeError("提示词不能为空")
    return value


def _normalize_mode(mode, input_reference, video):
    clean_mode = str(mode or "自动").strip()
    if clean_mode not in GENERATION_MODES:
        raise RuntimeError("生成模式必须是：自动、文生视频、图生视频、视频生视频")
    if clean_mode != "自动":
        return clean_mode
    if str(video or "").strip():
        return "视频生视频"
    if str(input_reference or "").strip():
        return "图生视频"
    return "文生视频"


def _normalize_seconds(seconds):
    try:
        value = int(seconds)
    except Exception:
        raise RuntimeError("seconds 必须是整数")
    if value < 1:
        raise RuntimeError("seconds 必须大于 0")
    return value


def _normalize_timeout(value, name, minimum=1):
    try:
        result = int(value)
    except Exception:
        raise RuntimeError(f"{name} 必须是整数")
    if result < minimum:
        raise RuntimeError(f"{name} 不能小于 {minimum}")
    return result


def _build_input_reference(*values):
    urls = []
    for value in values:
        for url in ensure_list_from_urls(str(value or "")):
            if url:
                urls.append(url)
    if len(urls) > 6:
        raise RuntimeError("input_reference 最多支持 6 张图片")
    return ",".join(urls)


def _multipart_form_fields(payload):
    return [(key, (None, str(value))) for key, value in payload.items()]


def _check_task_result(data, raw_json):
    status = _extract_status(data, "unknown")
    video_url = _extract_video_url(data)
    status_key = _status_key(status)

    if status_key in FAILED_STATUSES:
        detail = extract_task_failure_detail(data) or data.get("error") or raw_json
        raise RuntimeError(f"Grok-image 视频任务失败: {detail}")

    if status_key in SUCCESS_STATUSES and not video_url:
        detail = extract_task_failure_detail(data) or "任务已完成但未返回 video_url"
        raise RuntimeError(f"Grok-image 视频查询失败: {detail}")

    return status, video_url


class GrokImageVideoGenerate:
    """创建 grok-image 视频任务并轮询返回视频 URL"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "视频生成提示词"}),
                "mode": (GENERATION_MODES, {"default": "自动", "tooltip": "自动按输入 URL 判断；也可手动指定"}),
                "model": (MODELS, {"default": DEFAULT_MODEL, "tooltip": "模型名称"}),
                "seconds": ("INT", {"default": 10, "min": 1, "max": 60, "tooltip": "视频时长（秒）"}),
                "size": ("STRING", {"default": "16:9", "tooltip": "视频比例，例如 16:9"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥；留空使用环境变量 KUAI_API_KEY"}),
            },
            "optional": {
                "input_reference": ("STRING", {"default": "", "forceInput": True, "tooltip": "图片1 URL；由传图到临时图床节点输出"}),
                "input_reference_2": ("STRING", {"default": "", "forceInput": True, "tooltip": "图片2 URL"}),
                "input_reference_3": ("STRING", {"default": "", "forceInput": True, "tooltip": "图片3 URL"}),
                "input_reference_4": ("STRING", {"default": "", "forceInput": True, "tooltip": "图片4 URL"}),
                "input_reference_5": ("STRING", {"default": "", "forceInput": True, "tooltip": "图片5 URL"}),
                "input_reference_6": ("STRING", {"default": "", "forceInput": True, "tooltip": "图片6 URL"}),
                "video": ("STRING", {"default": "", "forceInput": True, "tooltip": "视频 URL；由传视频到临时图床节点输出"}),
                "api_base": ("STRING", {"default": DEFAULT_API_BASE, "tooltip": "API 地址"}),
                "create_timeout": ("INT", {"default": 120, "min": 5, "max": 9999, "tooltip": "创建请求超时（秒）"}),
                "poll_interval_sec": ("INT", {"default": 10, "min": 1, "max": 120, "tooltip": "轮询间隔（秒）"}),
                "wait_timeout_sec": ("INT", {"default": 1800, "min": 30, "max": 9999, "tooltip": "等待总超时（秒）"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "mode": "生成模式",
            "model": "模型",
            "seconds": "时长",
            "size": "比例",
            "api_key": "API密钥",
            "input_reference": "图片1 URL",
            "input_reference_2": "图片2 URL",
            "input_reference_3": "图片3 URL",
            "input_reference_4": "图片4 URL",
            "input_reference_5": "图片5 URL",
            "input_reference_6": "图片6 URL",
            "video": "视频 URL",
            "api_base": "API地址",
            "create_timeout": "创建超时",
            "poll_interval_sec": "轮询间隔",
            "wait_timeout_sec": "等待超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("视频URL", "任务ID", "状态", "增强提示词", "状态更新时间", "原始响应")
    FUNCTION = "generate"
    CATEGORY = "KuAi/GrokImage"

    def _create_task(self, payload, api_key, api_base, timeout):
        try:
            resp = requests.post(
                f"{api_base}/v1/videos",
                files=_multipart_form_fields(payload),
                headers=http_headers_auth_only(api_key),
                timeout=timeout,
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok-image 视频创建失败: {detail}")
            return resp.json()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Grok-image 视频创建失败: {exc}")

    def _query_task(self, task_id, api_key, api_base):
        try:
            resp = requests.get(
                f"{api_base}/v1/video/query",
                params={"id": task_id},
                headers=http_headers_json(api_key),
                timeout=60,
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok-image 视频查询失败: {detail}")
            return resp.json()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Grok-image 视频查询失败: {exc}")

    def generate(
        self,
        prompt,
        mode,
        model,
        seconds,
        size,
        api_key,
        input_reference="",
        input_reference_2="",
        input_reference_3="",
        input_reference_4="",
        input_reference_5="",
        input_reference_6="",
        video="",
        api_base=DEFAULT_API_BASE,
        create_timeout=120,
        poll_interval_sec=10,
        wait_timeout_sec=1800,
    ):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量 KUAI_API_KEY 中设置")

        prompt = _normalize_prompt(prompt)
        seconds = _normalize_seconds(seconds)
        create_timeout = _normalize_timeout(create_timeout, "create_timeout", 5)
        poll_interval_sec = _normalize_timeout(poll_interval_sec, "poll_interval_sec", 1)
        wait_timeout_sec = _normalize_timeout(wait_timeout_sec, "wait_timeout_sec", 1)
        api_base = str(api_base or DEFAULT_API_BASE).rstrip("/")
        image_refs = _build_input_reference(
            input_reference,
            input_reference_2,
            input_reference_3,
            input_reference_4,
            input_reference_5,
            input_reference_6,
        )
        video = str(video or "").strip()
        effective_mode = _normalize_mode(mode, image_refs, video)

        payload = {
            "model": str(model or DEFAULT_MODEL).strip() or DEFAULT_MODEL,
            "prompt": prompt,
            "seconds": seconds,
        }
        clean_size = str(size or "").strip()
        if clean_size:
            payload["size"] = clean_size

        if effective_mode == "图生视频":
            if not image_refs:
                raise RuntimeError("图生视频需要至少 1 个 input_reference 图片 URL")
            payload["input_reference"] = image_refs
        elif effective_mode == "视频生视频":
            if not video:
                raise RuntimeError("视频生视频需要 video 视频 URL")
            payload["video"] = video

        create_data = self._create_task(payload, api_key, api_base, create_timeout)
        task_id = _extract_task_id(create_data)
        create_raw = json.dumps(create_data, ensure_ascii=False)
        if not task_id:
            status, video_url = _check_task_result(create_data, create_raw)
            if _status_key(status) in SUCCESS_STATUSES:
                return (
                    video_url,
                    "",
                    status,
                    _extract_enhanced_prompt(create_data),
                    _extract_status_update_time(create_data),
                    create_raw,
                )
            raise RuntimeError(f"Grok-image 视频创建响应缺少任务ID: {create_raw}")

        deadline = time.time() + wait_timeout_sec
        last_data = create_data
        last_raw = create_raw
        while True:
            data = self._query_task(task_id, api_key, api_base)
            raw = json.dumps(data, ensure_ascii=False)
            status, video_url = _check_task_result(data, raw)
            last_data = data
            last_raw = raw

            if _status_key(status) in SUCCESS_STATUSES:
                return (
                    video_url,
                    task_id,
                    status,
                    _extract_enhanced_prompt(data),
                    _extract_status_update_time(data),
                    raw,
                )

            if time.time() >= deadline:
                break
            time.sleep(poll_interval_sec)

        last_status = _extract_status(last_data, "unknown")
        raise RuntimeError(f"Grok-image 视频生成超时，任务ID: {task_id}，最后状态: {last_status}，最后响应: {last_raw}")


NODE_CLASS_MAPPINGS = {
    "GrokImageVideoGenerate": GrokImageVideoGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokImageVideoGenerate": "🎬 grok-image视频生成",
}
