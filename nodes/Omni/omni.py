"""Omni 视频生成节点"""

import json
import re
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
OMNI_DEFAULT_CREATE_MODEL = "omni-flash"
OMNI_DEFAULT_QUERY_MODEL = "omni-flash"
OMNI_LEGACY_CREATE_MODEL = "omni-flash-components"
OMNI_EDIT_MODEL = "omni-flash-edit"
OMNI_MODEL_CHOICES = [OMNI_DEFAULT_CREATE_MODEL, OMNI_LEGACY_CREATE_MODEL, OMNI_EDIT_MODEL]
OMNI_GENERATION_TYPES = [
    "1-文生视频",
    "2-首尾帧",
    "3-垫图参考",
    "4-Omni-Flash 视频编辑",
]
OMNI_ASPECT_RATIOS = ["9:16", "16:9"]
OMNI_SECONDS_PATTERN = re.compile(r"^[1-9][0-9]*$")
OMNI_SIZE_PATTERN = re.compile(r"^[1-9][0-9]{1,4}x[1-9][0-9]{1,4}$")


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
    clean = str(model or "").strip()
    if clean.endswith("-components"):
        return clean[:-len("-components")]
    return clean or _query_model_from_task_id(task_id)


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


def _build_images(*values):
    images = []
    seen = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            images.append(clean)
            seen.add(clean)
    return images


def _normalize_generation_type(value):
    clean = str(value or "1").strip()
    match = re.match(r"^\s*([1-4])(?:\s*[-：: ].*)?\s*$", clean)
    if not match:
        raise RuntimeError("生成类型必须是 1、2、3 或 4")
    generation_type = int(match.group(1))
    if generation_type not in {1, 2, 3, 4}:
        raise RuntimeError("生成类型必须是 1、2、3 或 4")
    return generation_type


def _normalize_seconds(seconds):
    clean = str(seconds or "").strip()
    if not clean:
        return ""
    if not OMNI_SECONDS_PATTERN.match(clean):
        raise RuntimeError('seconds 必须是正整数字符串，例如 "8"')
    return clean


def _normalize_size(size):
    clean = str(size or "").strip()
    if not clean:
        return ""
    if not OMNI_SIZE_PATTERN.match(clean):
        raise RuntimeError("size 必须形如 1280x720")
    return clean


def _normalize_seed(seed):
    value = int(seed)
    if value < 0 or value > 2147483647:
        raise RuntimeError("seed 必须在 0 到 2147483647 之间")
    return value


def _resolve_media_by_type(generation_type, image_1_url="", image_2_url="", image_3_url="", input_reference="",
                           image_1="", image_2="", image_urls=""):
    legacy_images = _build_images(image_1, image_2, *ensure_list_from_urls(image_urls))
    new_images = _build_images(image_1_url, image_2_url, image_3_url)
    if generation_type == 1:
        if legacy_images and not new_images:
            return (3 if len(legacy_images) > 2 else 2), legacy_images, ""
        return 1, [], ""
    if generation_type == 2:
        images = _build_images(image_1_url, image_2_url) or legacy_images[:2]
        return (2 if images else 1), images, ""
    if generation_type == 3:
        images = new_images or legacy_images
        return (3 if images else 1), images, ""
    if generation_type == 4:
        return 4, [], str(input_reference or "").strip()
    return generation_type, [], ""


def _validate_create_inputs(effective_model, generation_type, prompt):
    if not str(prompt or "").strip():
        raise RuntimeError("prompt 不能为空")
    if not str(effective_model or "").strip():
        raise RuntimeError("model 不能为空")


def _build_create_payload(effective_model, prompt, generation_type, aspect_ratio,
                          images, input_reference, enable_upsample, enable_sample, seconds, size, seed):
    payload = {
        "model": effective_model,
        "prompt": str(prompt or "").strip(),
        "type": generation_type,
        "enable_upsample": bool(enable_upsample),
        "enable_sample": bool(enable_sample),
        "seed": _normalize_seed(seed),
    }

    clean_size = _normalize_size(size)
    if clean_size:
        payload["size"] = clean_size
    else:
        clean_aspect_ratio = str(aspect_ratio or "").strip()
        if clean_aspect_ratio:
            if clean_aspect_ratio not in OMNI_ASPECT_RATIOS:
                raise RuntimeError("aspect_ratio 必须是 16:9 或 9:16")
            payload["aspect_ratio"] = clean_aspect_ratio

    clean_seconds = _normalize_seconds(seconds)
    if clean_seconds:
        payload["seconds"] = clean_seconds
    if images:
        payload["images"] = images
    if input_reference:
        payload["input_reference"] = input_reference
    return payload


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
                "model": (OMNI_MODEL_CHOICES, {
                    "default": OMNI_DEFAULT_CREATE_MODEL,
                    "tooltip": "创建模型名"
                }),
                "type": (OMNI_GENERATION_TYPES, {
                    "default": "1-文生视频",
                    "tooltip": "生成类型；实际提交给 API 的值仍为 1、2、3、4"
                }),
                "image_1_url": ("STRING", {
                    "default": "",
                    "tooltip": "图片1链接；由传图到临时图床等节点输出"
                }),
                "image_2_url": ("STRING", {
                    "default": "",
                    "tooltip": "图片2链接；type=2 时作为尾帧"
                }),
                "image_3_url": ("STRING", {
                    "default": "",
                    "tooltip": "图片3链接；type=3 时生效"
                }),
                "input_reference": ("STRING", {
                    "default": "",
                    "tooltip": "Omni-Flash 视频编辑参考视频 URL 或 dataURI；当前仅占位"
                }),
                "aspect_ratio": (["9:16", "16:9"], {
                    "default": "9:16",
                    "tooltip": "视频宽高比；填写 size 时不发送该参数"
                }),
                "enable_upsample": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "升级到 1080p（部分 4K 模型有效）"
                }),
                "enhance_prompt": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "旧工作流兼容参数；当前 Omni API 不发送"
                }),
            },
            "optional": {
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义创建模型；留空使用下拉模型"
                }),
                "size": ("STRING", {
                    "default": "",
                    "tooltip": "自定义尺寸，例如 1280x720；填写后不发送 aspect_ratio"
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
                "seconds": ("STRING", {
                    "default": "8",
                    "tooltip": "视频时长（秒），例如 8"
                }),
                "enable_sample": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Omni-Flash 系列切换 1080p（4K 模型忽略）"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子，0 表示随机"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "type": "生成类型",
            "image_1_url": "图片1链接",
            "image_2_url": "图片2链接",
            "image_3_url": "图片3链接",
            "input_reference": "编辑参考视频",
            "aspect_ratio": "宽高比",
            "enable_upsample": "启用超分",
            "enhance_prompt": "提示词增强",
            "custom_model": "自定义模型",
            "size": "自定义尺寸",
            "api_base": "API地址",
            "api_key": "API密钥",
            "timeout": "超时",
            "seconds": "时长",
            "enable_sample": "切换1080p",
            "seed": "随机种子",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "查询模型", "状态更新时间", "原始响应JSON")
    FUNCTION = "create"
    CATEGORY = "KuAi/Omni"

    def create(self, prompt, model, aspect_ratio, enable_upsample, enhance_prompt=True,
               image_1="", image_2="", image_urls="", custom_model="",
               api_base=OMNI_DEFAULT_API_BASE, api_key="", timeout=1800,
               type="1-文生视频", seconds="8", enable_sample=True,
               seed=0, image_1_url="", image_2_url="", image_3_url="", input_reference="", size=""):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量 KUAI_API_KEY 中设置")

        api_base = (api_base or OMNI_DEFAULT_API_BASE).rstrip("/")
        effective_model = (custom_model or "").strip() or model
        generation_type = _normalize_generation_type(type)
        if generation_type == 4 and effective_model in {OMNI_DEFAULT_CREATE_MODEL, OMNI_LEGACY_CREATE_MODEL}:
            effective_model = OMNI_EDIT_MODEL
        effective_generation_type, images, effective_input_reference = _resolve_media_by_type(
            generation_type=generation_type,
            image_1_url=image_1_url,
            image_2_url=image_2_url,
            image_3_url=image_3_url,
            input_reference=input_reference,
            image_1=image_1,
            image_2=image_2,
            image_urls=image_urls,
        )
        _validate_create_inputs(
            effective_model=effective_model,
            generation_type=generation_type,
            prompt=prompt,
        )

        payload = _build_create_payload(
            effective_model=effective_model,
            prompt=prompt,
            generation_type=effective_generation_type,
            aspect_ratio=aspect_ratio,
            images=images,
            input_reference=effective_input_reference,
            enable_upsample=enable_upsample,
            enable_sample=enable_sample,
            seconds=seconds,
            size=size,
            seed=seed,
        )

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
