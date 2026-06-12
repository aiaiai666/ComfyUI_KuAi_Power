import io
import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests


DEFAULT_API_BASE = "https://ai.kegeai.top"
IMAGE_GENERATIONS_PATH = "/v1/images/generations"

MODELS = [
    "doubao-seedream-5-0-260128",
    "doubao-seedream-4-5-251128",
    "doubao-seedream-4-0-250828",
    "doubao-seedream-3-0-t2i-250415",
    "doubao-seededit-3-0-i2i-250628",
]
SIZE_MODES = ["preset", "custom", "adaptive"]
RESOLUTIONS = ["1K", "2K", "3K", "4K"]
SEQUENTIAL_MODES = ["disabled", "auto"]
OUTPUT_FORMATS = ["jpeg", "png"]
RESPONSE_FORMATS = ["url"]


@dataclass(frozen=True)
class ModelCapability:
    supports_images: bool
    requires_image: bool
    max_images: int
    resolutions: tuple[str, ...]
    supports_custom_size: bool
    size_fixed: str | None
    supports_seed: bool
    default_guidance_scale: float
    supports_sequential: bool
    supports_output_format: bool


MODEL_CAPABILITIES = {
    "doubao-seedream-5-0-260128": ModelCapability(True, False, 14, ("2K", "3K"), True, None, False, 2.5, True, True),
    "doubao-seedream-4-5-251128": ModelCapability(True, False, 14, ("2K", "4K"), True, None, False, 2.5, True, False),
    "doubao-seedream-4-0-250828": ModelCapability(True, False, 14, ("1K", "2K", "4K"), True, None, False, 2.5, True, False),
    "doubao-seedream-3-0-t2i-250415": ModelCapability(False, False, 0, (), True, None, True, 2.5, False, False),
    "doubao-seededit-3-0-i2i-250628": ModelCapability(True, True, 1, (), False, "adaptive", True, 5.5, False, False),
}


def env_or(value: str, env_name: str) -> str:
    if value and str(value).strip():
        return str(value).strip()
    return os.environ.get(env_name, "").strip()


def http_headers_auth_only(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def extract_error_message_from_response(resp) -> str:
    try:
        data = resp.json()
    except Exception:
        data = None

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            for key in ("message", "msg", "detail", "reason"):
                value = _clean_text(error.get(key))
                if value:
                    return value
        for key in ("message", "msg", "detail", "reason", "error_message"):
            value = _clean_text(data.get(key))
            if value:
                return value

    text = _clean_text(getattr(resp, "text", ""))
    return text or f"HTTP {getattr(resp, 'status_code', 'unknown')}"


def _clean_text(value) -> str:
    return str(value or "").strip()


def _collect_image_urls(image_count: int, image_urls: list[str]) -> list[str]:
    count = int(image_count)
    if count < 0 or count > 14:
        raise RuntimeError("图片数量必须在 0 到 14 之间")
    selected = [_clean_text(url) for url in image_urls[:count]]
    if any(not url for url in selected):
        raise RuntimeError(f"前 {count} 个图片URL不能为空")
    return selected


def _validate_seed(seed: int) -> int:
    value = int(seed)
    if value < -1 or value > 2147483647:
        raise RuntimeError("seed 必须在 -1 到 2147483647 之间")
    return value


def _validate_guidance_scale(guidance_scale: float) -> float:
    value = float(guidance_scale)
    if value < 1 or value > 10:
        raise RuntimeError("guidance_scale 必须在 1 到 10 之间")
    return value


def _resolve_size(model: str, capability: ModelCapability, size_mode: str, resolution: str, custom_size: str) -> str:
    if capability.size_fixed:
        return capability.size_fixed
    if not capability.resolutions and capability.supports_custom_size:
        return _normalize_custom_size(custom_size)
    if size_mode == "preset":
        if resolution not in capability.resolutions:
            raise RuntimeError(f"模型 {model} 不支持分辨率 {resolution}")
        return resolution
    if size_mode == "custom":
        if not capability.supports_custom_size:
            raise RuntimeError(f"模型 {model} 不支持自定义尺寸")
        return _normalize_custom_size(custom_size)
    if size_mode == "adaptive":
        raise RuntimeError(f"模型 {model} 不支持 adaptive 尺寸")
    raise RuntimeError(f"不支持的尺寸模式: {size_mode}")


def _normalize_custom_size(custom_size: str) -> str:
    value = _clean_text(custom_size)
    if not value:
        raise RuntimeError("自定义尺寸不能为空，例如 2048x2048")
    normalized = value.lower().replace("×", "x")
    parts = normalized.split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise RuntimeError("自定义尺寸必须使用 宽x高 格式，例如 2048x2048")
    return normalized


def build_payload(
    *,
    model,
    prompt,
    image_count,
    image_urls,
    size_mode,
    resolution,
    custom_size,
    seed,
    guidance_scale,
    sequential_image_generation,
    max_images,
    output_format,
    response_format,
    watermark,
):
    model = _clean_text(model)
    prompt = _clean_text(prompt)
    if model not in MODEL_CAPABILITIES:
        raise RuntimeError(f"不支持的豆包图片模型: {model}")
    if not prompt:
        raise RuntimeError("提示词不能为空")

    capability = MODEL_CAPABILITIES[model]
    urls = _collect_image_urls(image_count, image_urls)

    if not capability.supports_images and urls:
        raise RuntimeError("seedream 3.0 只支持文生图，不支持图片输入")
    if capability.requires_image and len(urls) != 1:
        raise RuntimeError("seededit 3.0 仅支持单图编辑，请提供且只提供 1 张图片")
    if len(urls) > capability.max_images:
        raise RuntimeError(f"模型 {model} 最多支持 {capability.max_images} 张图片")

    payload = {
        "model": model,
        "prompt": prompt,
        "size": _resolve_size(model, capability, size_mode, resolution, custom_size),
        "response_format": response_format,
        "watermark": bool(watermark),
    }

    if len(urls) == 1:
        payload["image"] = urls[0]
    elif len(urls) > 1:
        payload["image"] = urls

    if capability.supports_seed:
        payload["seed"] = _validate_seed(seed)
        payload["guidance_scale"] = _validate_guidance_scale(guidance_scale)

    if capability.supports_sequential:
        if sequential_image_generation not in SEQUENTIAL_MODES:
            raise RuntimeError(f"不支持的组图模式: {sequential_image_generation}")
        payload["sequential_image_generation"] = sequential_image_generation
        if sequential_image_generation == "auto":
            max_images_int = int(max_images)
            if max_images_int < 1 or max_images_int > 15:
                raise RuntimeError("max_images 必须在 1 到 15 之间")
            payload["sequential_image_generation_options"] = {"max_images": max_images_int}

    if capability.supports_output_format:
        if output_format not in OUTPUT_FORMATS:
            raise RuntimeError(f"不支持的输出格式: {output_format}")
        payload["output_format"] = output_format

    return payload


def extract_created_and_urls(data: dict) -> tuple[str, list[str]]:
    created = str(data.get("created", ""))
    urls = []
    for item in data.get("data") or []:
        if isinstance(item, dict):
            url = _clean_text(item.get("url"))
            if url:
                urls.append(url)
    if not urls:
        raise RuntimeError(f"响应中没有图片URL: {json.dumps(data, ensure_ascii=False)}")
    return created, urls


def validate_public_image_url(url: str) -> str:
    clean = _clean_text(url)
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError("图片下载地址必须是公网 http/https URL")

    host = parsed.hostname or ""
    try:
        addresses = socket.getaddrinfo(host, None)
    except Exception as exc:
        raise RuntimeError(f"图片下载地址域名解析失败: {exc}")

    for item in addresses:
        ip = ipaddress.ip_address(item[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise RuntimeError("图片下载地址不能指向内网、本机或保留地址")
    return clean


def get_public_image_response(url: str, timeout: int, max_redirects: int = 5):
    current_url = validate_public_image_url(url)
    for _ in range(max_redirects + 1):
        resp = requests.get(current_url, timeout=int(timeout), allow_redirects=False)
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("Location")
            if not location:
                raise RuntimeError("图片下载地址重定向缺少 Location")
            current_url = validate_public_image_url(urljoin(current_url, location))
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("图片下载地址重定向次数过多")


def download_image_as_tensor(url: str, timeout: int):
    import numpy as np
    import torch
    from PIL import Image

    try:
        resp = get_public_image_response(url, timeout)
        image = Image.open(io.BytesIO(resp.content)).convert("RGB")
        arr = np.array(image).astype(np.float32) / 255.0
        return torch.from_numpy(arr)[None, ...]
    except Exception as exc:
        raise RuntimeError(f"下载生成图片失败: {url}，错误: {exc}")


def run_generation(payload: dict, api_key: str, api_base: str, timeout: int):
    resolved_key = env_or(api_key, "KUAI_API_KEY")
    if not resolved_key:
        raise RuntimeError("API Key 未配置，请在节点参数或 KUAI_API_KEY 环境变量中设置")

    endpoint = f"{str(api_base or DEFAULT_API_BASE).rstrip('/')}{IMAGE_GENERATIONS_PATH}"
    resp = requests.post(
        endpoint,
        json=payload,
        headers=http_headers_auth_only(resolved_key),
        timeout=int(timeout),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"豆包图片生成失败: {extract_error_message_from_response(resp)}")

    data = resp.json()
    created, urls = extract_created_and_urls(data)
    tensors = [download_image_as_tensor(url, timeout) for url in urls]
    try:
        import torch

        image = torch.cat(tensors, dim=0)
    except Exception as exc:
        raise RuntimeError(f"多张返回图片尺寸不一致，无法合并为 IMAGE batch: {exc}")
    return image, "\n".join(urls), created, json.dumps(data, ensure_ascii=False)


class _BaseDoubaoImage:
    CATEGORY = "KuAi/DoubaoImage"
    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("图片", "图片URL", "创建时间", "原始响应JSON")
    FUNCTION = "generate"

    @classmethod
    def INPUT_LABELS(cls):
        labels = {
            "prompt": "提示词",
            "model": "模型",
            "custom_model": "自定义模型",
            "size_mode": "尺寸模式",
            "resolution": "分辨率",
            "custom_size": "自定义尺寸",
            "watermark": "水印",
            "api_key": "API密钥",
            "image_count": "图片数量",
            "seed": "随机种子",
            "guidance_scale": "提示词权重",
            "sequential_image_generation": "组图模式",
            "max_images": "最多生成图片数",
            "output_format": "输出格式",
            "response_format": "返回格式",
            "api_base": "API地址",
            "timeout": "超时",
        }
        labels.update({f"image_url_{i}": f"图片URL {i}" for i in range(1, 15)})
        return labels

    @classmethod
    def _common_optional_inputs(cls):
        optional = {
            "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型名（留空使用下拉模型）"}),
            "image_count": ("INT", {"default": 0, "min": 0, "max": 14, "tooltip": "使用前 N 个图片URL。文生图填 0。"}),
        }
        optional.update({
            f"image_url_{i}": ("STRING", {"default": "", "forceInput": True, "tooltip": f"第 {i} 张参考图片URL，来自传图到临时图床节点"})
            for i in range(1, 15)
        })
        optional.update({
            "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
            "guidance_scale": ("FLOAT", {"default": 2.5, "min": 1.0, "max": 10.0, "step": 0.1}),
            "sequential_image_generation": (SEQUENTIAL_MODES, {"default": "disabled"}),
            "max_images": ("INT", {"default": 3, "min": 1, "max": 15}),
            "output_format": (OUTPUT_FORMATS, {"default": "jpeg"}),
            "response_format": (RESPONSE_FORMATS, {"default": "url"}),
            "api_base": ("STRING", {"default": DEFAULT_API_BASE}),
            "timeout": ("INT", {"default": 120, "min": 1, "max": 1800}),
        })
        return optional

    def _run_from_args(
        self,
        prompt,
        model,
        size_mode,
        resolution,
        custom_size,
        watermark,
        api_key,
        custom_model="",
        image_count=0,
        seed=-1,
        guidance_scale=2.5,
        sequential_image_generation="disabled",
        max_images=3,
        output_format="jpeg",
        response_format="url",
        api_base=DEFAULT_API_BASE,
        timeout=120,
        **kwargs,
    ):
        image_urls = [kwargs.get(f"image_url_{i}", "") for i in range(1, 15)]
        effective_model = (custom_model or "").strip() or model
        payload = build_payload(
            model=effective_model,
            prompt=prompt,
            image_count=image_count,
            image_urls=image_urls,
            size_mode=size_mode,
            resolution=resolution,
            custom_size=custom_size,
            seed=seed,
            guidance_scale=guidance_scale,
            sequential_image_generation=sequential_image_generation,
            max_images=max_images,
            output_format=output_format,
            response_format=response_format,
            watermark=watermark,
        )
        return run_generation(payload, api_key, api_base, timeout)


class DoubaoImageGenerateEdit(_BaseDoubaoImage):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "model": (MODELS, {"default": "doubao-seedream-5-0-260128"}),
                "size_mode": (SIZE_MODES, {"default": "preset"}),
                "resolution": (RESOLUTIONS, {"default": "2K"}),
                "custom_size": ("STRING", {"default": "2048x2048"}),
                "watermark": ("BOOLEAN", {"default": False}),
                "api_key": ("STRING", {"default": ""}),
            },
            "optional": cls._common_optional_inputs(),
        }

    def generate(self, prompt, model, size_mode, resolution, custom_size, watermark, api_key, **kwargs):
        return self._run_from_args(prompt, model, size_mode, resolution, custom_size, watermark, api_key, **kwargs)


class DoubaoImageGenerate(_BaseDoubaoImage):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "model": ([
                    "doubao-seedream-5-0-260128",
                    "doubao-seedream-4-5-251128",
                    "doubao-seedream-4-0-250828",
                    "doubao-seedream-3-0-t2i-250415",
                ], {"default": "doubao-seedream-5-0-260128"}),
                "size_mode": (["preset", "custom"], {"default": "preset"}),
                "resolution": (RESOLUTIONS, {"default": "2K"}),
                "custom_size": ("STRING", {"default": "2048x2048"}),
                "watermark": ("BOOLEAN", {"default": False}),
                "api_key": ("STRING", {"default": ""}),
            },
            "optional": cls._common_optional_inputs(),
        }

    def generate(self, prompt, model, size_mode, resolution, custom_size, watermark, api_key, **kwargs):
        return self._run_from_args(prompt, model, size_mode, resolution, custom_size, watermark, api_key, image_count=0, **kwargs)


class DoubaoImageEdit(_BaseDoubaoImage):
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "", "multiline": True}),
                "model": ([
                    "doubao-seedream-5-0-260128",
                    "doubao-seedream-4-5-251128",
                    "doubao-seedream-4-0-250828",
                    "doubao-seededit-3-0-i2i-250628",
                ], {"default": "doubao-seedream-5-0-260128"}),
                "size_mode": (SIZE_MODES, {"default": "preset"}),
                "resolution": (RESOLUTIONS, {"default": "2K"}),
                "custom_size": ("STRING", {"default": "2048x2048"}),
                "watermark": ("BOOLEAN", {"default": False}),
                "api_key": ("STRING", {"default": ""}),
                "image_count": ("INT", {"default": 1, "min": 1, "max": 14}),
                "image_url_1": ("STRING", {"default": "", "forceInput": True}),
            },
            "optional": {
                "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型名（留空使用下拉模型）"}),
                **{
                    f"image_url_{i}": ("STRING", {"default": "", "forceInput": True})
                    for i in range(2, 15)
                },
                "seed": ("INT", {"default": -1, "min": -1, "max": 2147483647}),
                "guidance_scale": ("FLOAT", {"default": 5.5, "min": 1.0, "max": 10.0, "step": 0.1}),
                "sequential_image_generation": (SEQUENTIAL_MODES, {"default": "disabled"}),
                "max_images": ("INT", {"default": 3, "min": 1, "max": 15}),
                "output_format": (OUTPUT_FORMATS, {"default": "jpeg"}),
                "response_format": (RESPONSE_FORMATS, {"default": "url"}),
                "api_base": ("STRING", {"default": DEFAULT_API_BASE}),
                "timeout": ("INT", {"default": 120, "min": 1, "max": 1800}),
            },
        }

    def generate(self, prompt, model, size_mode, resolution, custom_size, watermark, api_key, image_count, image_url_1, **kwargs):
        kwargs["image_url_1"] = image_url_1
        return self._run_from_args(prompt, model, size_mode, resolution, custom_size, watermark, api_key, image_count=image_count, **kwargs)
