import io
import json

import numpy as np
import requests
import torch
from PIL import Image

from ..Sora2.kuai_utils import env_or, extract_error_message_from_response, http_headers_auth_only

MODELS = [
    "grok-4.2-image",
    "grok-4.1-image",
    "grok-4-image",
    "grok-3-image",
    "grok-imagine-image",
    "grok-imagine-image-pro",
]

SIZES = ["960x960", "720x1280", "1280x720", "1168x784", "784x1168"]
ASPECT_RATIOS = ["1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2", "9:19.5", "19.5:9", "9:20", "20:9", "1:2", "2:1", "auto"]
RESPONSE_FORMATS = ["url", "b64_json"]
RESOLUTIONS = ["1k", "2k"]
QUALITIES = ["low", "medium", "high"]


def _download_image_as_tensor(url: str, timeout: int) -> torch.Tensor:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    pil = Image.open(io.BytesIO(resp.content)).convert("RGB")
    arr = np.array(pil).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def _extract_image_url(data: dict) -> str:
    items = data.get("data") or []
    if not items:
        raise RuntimeError(f"响应中没有图片数据: {json.dumps(data, ensure_ascii=False)}")
    url = str((items[0] or {}).get("url", "")).strip()
    if not url:
        raise RuntimeError(f"响应中缺少图片URL: {json.dumps(data, ensure_ascii=False)}")
    return url


def _multipart_form_fields(payload: dict) -> list[tuple[str, tuple[None, str]]]:
    return [(key, (None, str(value))) for key, value in payload.items()]


class GrokImageGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "图像生成提示词"}),
                "model": (MODELS, {"default": "grok-4.2-image", "tooltip": "模型选择"}),
                "size": (SIZES, {"default": "960x960", "tooltip": "输出图像尺寸"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
            },
            "optional": {
                "api_base": ("STRING", {"default": "https://api.kegeai.top", "tooltip": "API服务器地址"}),
                "timeout": ("INT", {"default": 120, "min": 1, "max": 1800, "tooltip": "超时时间(秒)"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "size": "尺寸",
            "api_key": "API密钥",
            "api_base": "API地址",
            "timeout": "超时",
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("图像", "图片URL", "原始响应")
    FUNCTION = "generate"
    CATEGORY = "KuAi/GrokImage"

    def generate(self, prompt, model, size, api_key, api_base="https://api.kegeai.top", timeout=120):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")
        if not str(prompt).strip():
            raise RuntimeError("提示词不能为空")

        payload = {"model": model, "prompt": prompt, "size": size}
        try:
            resp = requests.post(
                f"{api_base.rstrip('/')}/v1/images/generations",
                json=payload,
                headers=http_headers_auth_only(api_key),
                timeout=timeout,
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok-image文生图失败: {detail}")
            data = resp.json()
            url = _extract_image_url(data)
            image = _download_image_as_tensor(url, timeout)
            return (image, url, json.dumps(data, ensure_ascii=False))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Grok-image文生图失败: {str(exc)}")


class GrokImageEdit:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("STRING", {"default": "", "tooltip": "由图床节点输出的图片URL"}),
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "图像编辑提示词"}),
                "model": (MODELS, {"default": "grok-4.2-image", "tooltip": "模型选择"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
            },
            "optional": {
                "aspect_ratio": (ASPECT_RATIOS, {"default": "auto", "tooltip": "输出宽高比"}),
                "response_format": (RESPONSE_FORMATS, {"default": "url", "tooltip": "返回格式"}),
                "resolution": (RESOLUTIONS, {"default": "2k", "tooltip": "输出分辨率"}),
                "quality": (QUALITIES, {"default": "high", "tooltip": "输出质量"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成数量"}),
                "api_base": ("STRING", {"default": "https://api.kegeai.top", "tooltip": "API服务器地址"}),
                "timeout": ("INT", {"default": 120, "min": 1, "max": 1800, "tooltip": "超时时间(秒)"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image": "图片URL",
            "prompt": "提示词",
            "model": "模型",
            "api_key": "API密钥",
            "aspect_ratio": "宽高比",
            "response_format": "返回格式",
            "resolution": "分辨率",
            "quality": "质量",
            "n": "生成数量",
            "api_base": "API地址",
            "timeout": "超时",
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("图像", "图片URL", "原始响应")
    FUNCTION = "edit"
    CATEGORY = "KuAi/GrokImage"

    def edit(
        self,
        image,
        prompt,
        model,
        api_key,
        aspect_ratio="auto",
        response_format="url",
        resolution="2k",
        quality="high",
        n=1,
        api_base="https://api.kegeai.top",
        timeout=120,
    ):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")
        image = str(image).strip()
        if not image:
            raise RuntimeError("图片URL不能为空")
        if not str(prompt).strip():
            raise RuntimeError("提示词不能为空")

        data_payload = {
            "image": image,
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "response_format": response_format,
            "resolution": resolution,
            "quality": quality,
            "n": int(n),
        }
        try:
            resp = requests.post(
                f"{api_base.rstrip('/')}/v1/images/edits",
                files=_multipart_form_fields(data_payload),
                headers=http_headers_auth_only(api_key),
                timeout=timeout,
            )
            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"Grok-image图片编辑失败: {detail}")
            data = resp.json()
            url = _extract_image_url(data)
            image_tensor = _download_image_as_tensor(url, timeout)
            return (image_tensor, url, json.dumps(data, ensure_ascii=False))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Grok-image图片编辑失败: {str(exc)}")
