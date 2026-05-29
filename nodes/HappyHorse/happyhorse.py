"""HappyHorse 视频生成节点。"""

import hashlib
import ipaddress
import json
import os
import re
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


HAPPYHORSE_MODELS = ["happyhorse-1.0-i2v", "happyhorse-1.0-r2v", "happyhorse-1.0-t2v"]
HAPPYHORSE_RESOLUTIONS = ["720P", "1080P"]
HAPPYHORSE_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4"]
DEFAULT_API_BASE = "https://ai.kegeai.top"
CREATE_PATH = "/alibailian/api/v1/services/aigc/video-generation/video-synthesis"
SUCCESS_STATES = {"SUCCEEDED", "COMPLETED"}
FAILED_STATES = {"FAILED", "ERROR", "CANCELED", "CANCELLED", "FAIL"}
RUNNING_STATES = {"PENDING", "RUNNING", "QUEUED", "SCHEDULED", "SUBMITTED"}
COMFY_ROOT = Path(__file__).resolve().parents[4]


def env_or(value: str, env_name: str) -> str:
    if value and str(value).strip():
        return str(value).strip()
    return os.environ.get(env_name, "").strip()


def http_headers_auth_only(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def json_get(data: dict, path: str, default=None):
    cur = data
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _first_non_empty(*values) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_error_message_from_json(data) -> str:
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        msg = _first_non_empty(error.get("message"), error.get("msg"), error.get("detail"), error.get("reason"))
        if msg:
            return msg
    return _first_non_empty(
        data.get("message"), data.get("msg"), data.get("detail"), data.get("reason"),
        data.get("error_message"), data.get("failure_reason"), data.get("fail_reason"),
        json_get(data, "output.message", ""), json_get(data, "output.failure_reason", ""),
        json_get(data, "output.error_message", ""), json_get(data, "error.message", ""),
    )


def extract_error_message_from_response(resp) -> str:
    try:
        data = resp.json()
    except Exception:
        data = None
    msg = extract_error_message_from_json(data) if data is not None else ""
    if msg:
        return msg
    return str(getattr(resp, "text", "") or f"HTTP {getattr(resp, 'status_code', 'unknown')}").strip()


def normalize_status(status: str) -> str:
    return str(status or "").strip().upper()


def _validate_http_url(url: str, label: str) -> str:
    clean = str(url or "").strip()
    if not clean:
        raise RuntimeError(f"{label}不能为空")
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"{label}必须以 http:// 或 https:// 开头")
    return clean


def validate_download_url(url: str) -> str:
    clean = _validate_http_url(url, "视频URL")
    host = urlparse(clean).hostname or ""
    try:
        addresses = socket.getaddrinfo(host, None)
    except Exception as exc:
        raise RuntimeError(f"视频URL域名解析失败: {exc}")
    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise RuntimeError("视频URL不能指向内网或本机地址")
    return clean


def get_public_url(url: str, timeout=60, stream=False, max_redirects=5):
    current = validate_download_url(url)
    for _ in range(int(max_redirects) + 1):
        resp = requests.get(current, timeout=int(timeout), stream=stream, allow_redirects=False)
        if getattr(resp, "is_redirect", False) or getattr(resp, "is_permanent_redirect", False):
            location = resp.headers.get("Location", "")
            resp.close()
            if not location:
                raise RuntimeError("视频URL重定向缺少 Location")
            current = requests.compat.urljoin(current, location)
            current = validate_download_url(current)
            continue
        return resp
    raise RuntimeError("视频URL重定向次数过多")


def _validate_common(model, resolution, ratio, duration):
    if model not in HAPPYHORSE_MODELS:
        raise RuntimeError(f"模型不支持: {model}")
    if resolution not in HAPPYHORSE_RESOLUTIONS:
        raise RuntimeError(f"分辨率不支持: {resolution}")
    try:
        duration_int = int(duration)
    except Exception:
        raise RuntimeError("时长必须为 3～15 的整数")
    if duration_int < 3 or duration_int > 15:
        raise RuntimeError("时长必须为 3～15 的整数")
    if model in {"happyhorse-1.0-t2v", "happyhorse-1.0-r2v"} and ratio not in HAPPYHORSE_RATIOS:
        raise RuntimeError(f"宽高比不支持: {ratio}")
    return duration_int


def build_payload(model, prompt, image_urls, resolution, ratio, duration, watermark):
    duration_int = _validate_common(model, resolution, ratio, duration)
    prompt_clean = str(prompt or "").strip()
    urls = [str(u or "").strip() for u in (image_urls or []) if str(u or "").strip()]

    if model == "happyhorse-1.0-t2v":
        if not prompt_clean:
            raise RuntimeError("提示词不能为空")
        payload = {"model": model, "input": {"prompt": prompt_clean}, "parameters": {"resolution": resolution, "ratio": ratio, "duration": duration_int, "watermark": bool(watermark)}}
    elif model == "happyhorse-1.0-i2v":
        if not urls:
            raise RuntimeError("首帧图片URL不能为空")
        first_url = _validate_http_url(urls[0], "首帧图片URL")
        input_payload = {"media": [{"type": "first_frame", "url": first_url}]}
        if prompt_clean:
            input_payload["prompt"] = prompt_clean
        payload = {"model": model, "input": input_payload, "parameters": {"resolution": resolution, "duration": duration_int, "watermark": bool(watermark)}}
    else:
        if not prompt_clean:
            raise RuntimeError("提示词不能为空")
        if not 1 <= len(urls) <= 9:
            raise RuntimeError("参考图数量必须为 1～9")
        media = [{"type": "reference_image", "url": _validate_http_url(u, f"参考图URL {idx}")} for idx, u in enumerate(urls, 1)]
        payload = {"model": model, "input": {"prompt": prompt_clean, "media": media}, "parameters": {"resolution": resolution, "ratio": ratio, "duration": duration_int, "watermark": bool(watermark)}}
    return payload


def create_task(api_base, api_key, payload, timeout=60):
    endpoint = f"{str(api_base or DEFAULT_API_BASE).rstrip('/')}{CREATE_PATH}"
    resp = requests.post(endpoint, json=payload, headers=http_headers_auth_only(api_key), timeout=int(timeout))
    if resp.status_code >= 400:
        raise RuntimeError(f"HappyHorse 视频任务创建失败: {extract_error_message_from_response(resp)}")
    data = resp.json()
    output = data.get("output") or {}
    task_id = str(output.get("task_id") or data.get("task_id") or "").strip()
    status = str(output.get("task_status") or data.get("task_status") or "").strip()
    if not task_id:
        raise RuntimeError(f"HappyHorse 创建响应缺少任务ID: {json.dumps(data, ensure_ascii=False)}")
    return task_id, status, data


def query_task(api_base, api_key, task_id, timeout=60):
    if not str(task_id or "").strip():
        raise RuntimeError("任务ID不能为空")
    endpoint = f"{str(api_base or DEFAULT_API_BASE).rstrip('/')}/alibailian/api/v1/tasks/{str(task_id).strip()}"
    resp = requests.get(endpoint, headers=http_headers_auth_only(api_key), timeout=int(timeout))
    if resp.status_code >= 400:
        raise RuntimeError(f"HappyHorse 视频任务查询失败: {extract_error_message_from_response(resp)}")
    data = resp.json()
    output = data.get("output") or {}
    status = str(output.get("task_status") or data.get("task_status") or "")
    video_url = str(output.get("video_url") or data.get("video_url") or "")
    orig_prompt = str(output.get("orig_prompt") or data.get("orig_prompt") or "")
    actual_prompt = str(output.get("actual_prompt") or data.get("actual_prompt") or "")
    normalized = normalize_status(status)
    if normalized in FAILED_STATES:
        raise RuntimeError(f"HappyHorse 视频任务失败: {extract_error_message_from_json(output) or extract_error_message_from_json(data) or json.dumps(data, ensure_ascii=False)}")
    if normalized in SUCCESS_STATES and not video_url.strip():
        raise RuntimeError("HappyHorse 视频任务已完成但未返回视频URL")
    return status, video_url, orig_prompt, actual_prompt, data


def wait_for_task(api_base, api_key, task_id, poll_interval_sec=10, timeout_sec=1800):
    elapsed = 0
    last = ("", "", "", "", {})
    while elapsed < int(timeout_sec):
        time.sleep(int(poll_interval_sec))
        elapsed += int(poll_interval_sec)
        last = query_task(api_base, api_key, task_id)
        if normalize_status(last[0]) in SUCCESS_STATES:
            return last
    raise RuntimeError(f"HappyHorse 视频生成超时（等待了 {int(timeout_sec)} 秒），任务ID: {task_id}，最后状态: {last[0]}")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w\-.]+", "_", str(value or "happyhorse"), flags=re.UNICODE).strip("._")
    return cleaned or "happyhorse"


def resolve_output_path(save_dir, filename, comfy_root=None):
    root = Path(comfy_root or COMFY_ROOT).resolve()
    save_dir_str = str(save_dir or "output/happyhorse").replace("\\", "/").strip("/")
    if not save_dir_str:
        save_dir_str = "output/happyhorse"
    if Path(save_dir_str).is_absolute() or ".." in Path(save_dir_str).parts:
        raise RuntimeError("保存目录不能包含绝对路径或 ..")
    if not (save_dir_str == "output" or save_dir_str.startswith("output/")):
        raise RuntimeError("保存目录必须位于 output/ 下")
    out_dir = (root / save_dir_str).resolve()
    output_root = (root / "output").resolve()
    if output_root != out_dir and output_root not in out_dir.parents:
        raise RuntimeError("保存目录必须位于 output/ 下")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = (out_dir / _safe_filename(filename)).resolve()
    if out_dir != path.parent:
        raise RuntimeError("文件名非法")
    return path


def download_video(video_url, save_dir="output/happyhorse", filename_prefix="happyhorse", task_id="", timeout=1800):
    safe_url = validate_download_url(video_url)
    url_hash = hashlib.sha256(safe_url.encode("utf-8")).hexdigest()[:8]
    task_short = _safe_filename(str(task_id or "task")[:7])
    filename = f"{_safe_filename(filename_prefix)}_{task_short}_{url_hash}.mp4"
    path = resolve_output_path(save_dir, filename)
    resp = get_public_url(safe_url, timeout=int(timeout), stream=True)
    resp.raise_for_status()
    try:
        with open(path, "wb") as handle:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    finally:
        resp.close()
    return str(path.relative_to(COMFY_ROOT)).replace("\\", "/")


def _all_image_urls_from_kwargs(kwargs):
    return [kwargs.get(f"image_url_{i}", "") for i in range(1, 10)]


def _first_n_image_urls(kwargs, count):
    count_int = int(count)
    if count_int < 1 or count_int > 9:
        raise RuntimeError("参考图数量必须为 1～9")
    urls = [str(kwargs.get(f"image_url_{i}", "") or "").strip() for i in range(1, count_int + 1)]
    if any(not u for u in urls):
        raise RuntimeError(f"前 {count_int} 个参考图URL不能为空")
    return urls


class _BaseHappyHorse:
    CATEGORY = "KuAi/HappyHorse"

    @classmethod
    def _save_inputs(cls):
        return {
            "save_video": ("BOOLEAN", {"default": True, "tooltip": "是否自动下载保存视频"}),
            "save_dir": ("STRING", {"default": "output/happyhorse", "tooltip": "保存目录，必须位于 output/ 下"}),
            "filename_prefix": ("STRING", {"default": "happyhorse", "tooltip": "保存文件名前缀"}),
            "download_timeout": ("INT", {"default": 1800, "min": 5, "max": 9999, "tooltip": "下载超时（秒）"}),
        }

    @classmethod
    def _api_wait_inputs(cls):
        return {
            "api_key": ("STRING", {"default": "", "tooltip": "API 密钥（留空使用环境变量 KUAI_API_KEY）"}),
            "api_base": ("STRING", {"default": DEFAULT_API_BASE, "tooltip": "API 地址"}),
            "create_timeout": ("INT", {"default": 60, "min": 5, "max": 600, "tooltip": "创建任务超时（秒）"}),
            "poll_interval_sec": ("INT", {"default": 10, "min": 1, "max": 120, "tooltip": "轮询间隔（秒）"}),
            "wait_timeout_sec": ("INT", {"default": 1800, "min": 30, "max": 9999, "tooltip": "等待总超时（秒）"}),
        }

    @classmethod
    def _api_wait_inputs_without_key(cls):
        inputs = dict(cls._api_wait_inputs())
        inputs.pop("api_key", None)
        return inputs

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model": "模型", "prompt": "提示词", "first_frame_url": "首帧图URL", "reference_image_count": "参考图数量",
            **{f"image_url_{i}": f"图片URL {i}" for i in range(1, 10)}, "resolution": "分辨率", "ratio": "宽高比", "duration": "时长", "watermark": "水印",
            "api_key": "API密钥", "api_base": "API地址", "timeout": "超时", "create_timeout": "创建超时", "poll_interval_sec": "轮询间隔", "wait_timeout_sec": "等待超时",
            "save_video": "保存视频", "save_dir": "保存目录", "filename_prefix": "文件名前缀", "download_timeout": "下载超时", "task_id": "任务ID", "wait": "等待完成",
        }

    def _require_api_key(self, api_key):
        resolved = env_or(api_key, "KUAI_API_KEY")
        if not resolved:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量 KUAI_API_KEY 中设置")
        return resolved

    def _create_wait_download(self, payload, api_key, api_base, create_timeout, poll_interval_sec, wait_timeout_sec, save_video, save_dir, filename_prefix, download_timeout):
        api_key = self._require_api_key(api_key)
        task_id, create_status, create_raw = create_task(api_base, api_key, payload, create_timeout)
        if normalize_status(create_status) in SUCCESS_STATES:
            status, video_url, orig, actual, raw = query_task(api_base, api_key, task_id)
        else:
            status, video_url, orig, actual, raw = wait_for_task(api_base, api_key, task_id, poll_interval_sec, wait_timeout_sec)
        local_path = download_video(video_url, save_dir, filename_prefix, task_id, download_timeout) if save_video and video_url else ""
        return (task_id, status, video_url, local_path, orig, actual, json.dumps(raw or create_raw, ensure_ascii=False))


class HappyHorseVideoCreate(_BaseHappyHorse):
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "原始响应JSON")
    FUNCTION = "create"

    @classmethod
    def INPUT_TYPES(cls):
        required = {
            "model": (HAPPYHORSE_MODELS, {"default": "happyhorse-1.0-t2v", "tooltip": "HappyHorse 模型"}),
            "prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "视频提示词"}),
            "reference_image_count": ("INT", {"default": 1, "min": 1, "max": 9, "tooltip": "r2v 使用前 N 张参考图"}),
            "resolution": (HAPPYHORSE_RESOLUTIONS, {"default": "1080P", "tooltip": "分辨率"}),
            "ratio": (HAPPYHORSE_RATIOS, {"default": "16:9", "tooltip": "宽高比（t2v/r2v）"}),
            "duration": ("INT", {"default": 5, "min": 3, "max": 15, "tooltip": "时长（秒）"}),
            "watermark": ("BOOLEAN", {"default": False, "tooltip": "是否添加 Happy Horse 水印"}),
            "api_key": ("STRING", {"default": "", "tooltip": "API 密钥（留空使用 KUAI_API_KEY）"}),
        }
        optional = {
            **{f"image_url_{i}": ("STRING", {"default": "", "forceInput": True, "tooltip": f"公网图片 URL {i}"}) for i in range(1, 10)},
            "api_base": ("STRING", {"default": DEFAULT_API_BASE}),
            "timeout": ("INT", {"default": 60, "min": 5, "max": 600}),
        }
        return {"required": required, "optional": optional}

    def create(self, model, prompt, reference_image_count, resolution, ratio, duration, watermark, api_key, image_url_1="", image_url_2="", image_url_3="", image_url_4="", image_url_5="", image_url_6="", image_url_7="", image_url_8="", image_url_9="", api_base=DEFAULT_API_BASE, timeout=60):
        kwargs = locals()
        image_urls = _first_n_image_urls(kwargs, reference_image_count) if model == "happyhorse-1.0-r2v" else _all_image_urls_from_kwargs(kwargs)
        payload = build_payload(model, prompt, image_urls, resolution, ratio, duration, watermark)
        task_id, status, raw = create_task(api_base, self._require_api_key(api_key), payload, timeout)
        return (task_id, status, json.dumps(raw, ensure_ascii=False))


class HappyHorseQueryTask(_BaseHappyHorse):
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("状态", "视频URL", "原始提示词", "实际提示词", "原始响应JSON")
    FUNCTION = "query"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"task_id": ("STRING", {"default": "", "tooltip": "任务 ID"})}, "optional": {"wait": ("BOOLEAN", {"default": True}), "poll_interval_sec": ("INT", {"default": 10, "min": 1, "max": 120}), "timeout_sec": ("INT", {"default": 1800, "min": 30, "max": 9999}), "api_key": ("STRING", {"default": ""}), "api_base": ("STRING", {"default": DEFAULT_API_BASE})}}

    def query(self, task_id, wait=True, poll_interval_sec=10, timeout_sec=1800, api_key="", api_base=DEFAULT_API_BASE):
        api_key = self._require_api_key(api_key)
        result = wait_for_task(api_base, api_key, task_id, poll_interval_sec, timeout_sec) if wait else query_task(api_base, api_key, task_id)
        status, video_url, orig, actual, raw = result
        return (status, video_url, orig, actual, json.dumps(raw, ensure_ascii=False))


class HappyHorseVideoAndWait(HappyHorseVideoCreate):
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "本地视频路径", "原始提示词", "实际提示词", "原始响应JSON")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        data = super().INPUT_TYPES()
        optional = {**data.get("optional", {}), **cls._api_wait_inputs(), **cls._save_inputs()}
        optional.pop("timeout", None)
        optional.pop("api_key")
        data["optional"] = optional
        return data

    def run(self, model, prompt, reference_image_count, resolution, ratio, duration, watermark, api_key, image_url_1="", image_url_2="", image_url_3="", image_url_4="", image_url_5="", image_url_6="", image_url_7="", image_url_8="", image_url_9="", api_base=DEFAULT_API_BASE, create_timeout=60, poll_interval_sec=10, wait_timeout_sec=1800, save_video=True, save_dir="output/happyhorse", filename_prefix="happyhorse", download_timeout=1800):
        kwargs = locals()
        image_urls = _first_n_image_urls(kwargs, reference_image_count) if model == "happyhorse-1.0-r2v" else _all_image_urls_from_kwargs(kwargs)
        payload = build_payload(model, prompt, image_urls, resolution, ratio, duration, watermark)
        return self._create_wait_download(payload, api_key, api_base, create_timeout, poll_interval_sec, wait_timeout_sec, save_video, save_dir, filename_prefix, download_timeout)


class HappyHorseT2VAndWait(_BaseHappyHorse):
    RETURN_TYPES = HappyHorseVideoAndWait.RETURN_TYPES
    RETURN_NAMES = HappyHorseVideoAndWait.RETURN_NAMES
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"default": "", "multiline": True}), "resolution": (HAPPYHORSE_RESOLUTIONS, {"default": "720P"}), "ratio": (HAPPYHORSE_RATIOS, {"default": "16:9"}), "duration": ("INT", {"default": 5, "min": 3, "max": 15}), "watermark": ("BOOLEAN", {"default": False}), "api_key": ("STRING", {"default": ""})}, "optional": {**cls._api_wait_inputs_without_key(), **cls._save_inputs()}}

    def run(self, prompt, resolution="720P", ratio="16:9", duration=5, watermark=False, api_key="", api_base=DEFAULT_API_BASE, create_timeout=60, poll_interval_sec=10, wait_timeout_sec=1800, save_video=True, save_dir="output/happyhorse", filename_prefix="happyhorse_t2v", download_timeout=1800):
        payload = build_payload("happyhorse-1.0-t2v", prompt, [], resolution, ratio, duration, watermark)
        return self._create_wait_download(payload, api_key, api_base, create_timeout, poll_interval_sec, wait_timeout_sec, save_video, save_dir, filename_prefix, download_timeout)


class HappyHorseI2VAndWait(_BaseHappyHorse):
    RETURN_TYPES = HappyHorseVideoAndWait.RETURN_TYPES
    RETURN_NAMES = HappyHorseVideoAndWait.RETURN_NAMES
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"default": "", "multiline": True}), "resolution": (HAPPYHORSE_RESOLUTIONS, {"default": "720P"}), "duration": ("INT", {"default": 5, "min": 3, "max": 15}), "watermark": ("BOOLEAN", {"default": False}), "api_key": ("STRING", {"default": ""})}, "optional": {"first_frame_url": ("STRING", {"default": "", "forceInput": True, "tooltip": "公网首帧图片 URL"}), **cls._api_wait_inputs_without_key(), **cls._save_inputs()}}

    def run(self, prompt="", resolution="720P", duration=5, watermark=False, api_key="", first_frame_url="", api_base=DEFAULT_API_BASE, create_timeout=60, poll_interval_sec=10, wait_timeout_sec=1800, save_video=True, save_dir="output/happyhorse", filename_prefix="happyhorse_i2v", download_timeout=1800):
        payload = build_payload("happyhorse-1.0-i2v", prompt, [first_frame_url], resolution, "16:9", duration, watermark)
        return self._create_wait_download(payload, api_key, api_base, create_timeout, poll_interval_sec, wait_timeout_sec, save_video, save_dir, filename_prefix, download_timeout)


class HappyHorseR2VAndWait(_BaseHappyHorse):
    RETURN_TYPES = HappyHorseVideoAndWait.RETURN_TYPES
    RETURN_NAMES = HappyHorseVideoAndWait.RETURN_NAMES
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prompt": ("STRING", {"default": "[Image 1]中的主体自然运动", "multiline": True}), "reference_image_count": ("INT", {"default": 1, "min": 1, "max": 9}), "resolution": (HAPPYHORSE_RESOLUTIONS, {"default": "720P"}), "ratio": (HAPPYHORSE_RATIOS, {"default": "16:9"}), "duration": ("INT", {"default": 5, "min": 3, "max": 15}), "watermark": ("BOOLEAN", {"default": False}), "api_key": ("STRING", {"default": ""})}, "optional": {**{f"image_url_{i}": ("STRING", {"default": "", "forceInput": True, "tooltip": f"公网参考图 URL {i}"}) for i in range(1, 10)}, **cls._api_wait_inputs_without_key(), **cls._save_inputs()}}

    def run(self, prompt, reference_image_count, resolution="720P", ratio="16:9", duration=5, watermark=False, api_key="", image_url_1="", image_url_2="", image_url_3="", image_url_4="", image_url_5="", image_url_6="", image_url_7="", image_url_8="", image_url_9="", api_base=DEFAULT_API_BASE, create_timeout=60, poll_interval_sec=10, wait_timeout_sec=1800, save_video=True, save_dir="output/happyhorse", filename_prefix="happyhorse_r2v", download_timeout=1800):
        urls = _first_n_image_urls(locals(), reference_image_count)
        payload = build_payload("happyhorse-1.0-r2v", prompt, urls, resolution, ratio, duration, watermark)
        return self._create_wait_download(payload, api_key, api_base, create_timeout, poll_interval_sec, wait_timeout_sec, save_video, save_dir, filename_prefix, download_timeout)
