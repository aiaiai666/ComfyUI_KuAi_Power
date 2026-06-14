"""gpt-image-2-all 节点"""

import base64
import io
import json

import numpy as np
import requests
import torch
from PIL import Image

from ..Sora2.kuai_utils import env_or, http_headers_auth_only, raise_for_bad_status

MODELS = ["gpt-image-2-all"]
SIZES = [
    "1024x1024（1:1）",
    "1536x1024（3:2）",
    "1024x1536（2:3）",
]
SIZE_MAP = {
    "1024x1024（1:1）": "1024x1024",
    "1536x1024（3:2）": "1536x1024",
    "1024x1536（2:3）": "1024x1536",
    # Legacy raw values kept so existing saved workflows continue to run.
    "1024x1024": "1024x1024",
    "1536x1024": "1536x1024",
    "1024x1536": "1024x1536",
}


def _payload_image_to_tensor(image_value: str, timeout: int) -> torch.Tensor:
    """? API ??? base64?data URL ? URL ?? ComfyUI IMAGE tensor"""
    value = str(image_value or "").strip()
    if not value:
        raise RuntimeError("?????????")

    if value.startswith("http://") or value.startswith("https://"):
        resp = requests.get(value, timeout=timeout)
        resp.raise_for_status()
        image_bytes = resp.content
    else:
        if value.startswith("data:"):
            _, _, value = value.partition(",")
        try:
            image_bytes = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise RuntimeError(f"???????? base64 ? URL: {exc}") from exc

    pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(pil).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def _extract_generation_result(payload: dict):
    """? API ????????????"""
    items = payload.get("data") or []
    image_values = []
    for item in items:
        value = (
            item.get("b64_json")
            or item.get("base64")
            or item.get("image_base64")
            or item.get("image")
            or item.get("url")
            or ""
        )
        value = str(value).strip()
        if value:
            image_values.append(value)
    if not image_values:
        raise RuntimeError(f"?????????: {json.dumps(payload, ensure_ascii=False)}")
    return image_values


def _collect_image_urls(*image_urls) -> list:
    return [str(url).strip() for url in image_urls if str(url or "").strip()]


class GPTImage2AllGenerate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "图像描述提示词"}),
                "model": (MODELS, {"default": "gpt-image-2-all", "tooltip": "模型选择"}),
                "size": (SIZES, {"default": "1024x1024（1:1）", "tooltip": "输出图像尺寸（宽x高｜比例）"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成数量"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
            },
            "optional": {
                "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型名（留空使用下拉模型）"}),
                "api_base": ("STRING", {"default": "https://ai.kegeai.top", "tooltip": "API服务器地址"}),
                "timeout": ("INT", {"default": 120, "min": 1, "max": 1800, "tooltip": "超时时间(秒)"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True, "tooltip": "ComfyUI 工作流随机种子；仅用于每次提交任务时刷新执行，不会发送给 gpt-image-2-all API。"}),
                "image_url_1": ("STRING", {"default": "", "forceInput": True, "tooltip": "第1张参考图片URL（来自传图到临时图床节点）"}),
                "image_url_2": ("STRING", {"default": "", "forceInput": True, "tooltip": "第2张参考图片URL（可选）"}),
                "image_url_3": ("STRING", {"default": "", "forceInput": True, "tooltip": "第3张参考图片URL（可选）"}),
                "image_url_4": ("STRING", {"default": "", "forceInput": True, "tooltip": "第4张参考图片URL（可选）"}),
                "image_url_5": ("STRING", {"default": "", "forceInput": True, "tooltip": "第5张参考图片URL（可选）"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "prompt": "提示词",
            "model": "模型",
            "custom_model": "自定义模型",
            "size": "图像尺寸",
            "n": "生成数量",
            "api_key": "API密钥",
            "image_url_1": "参考图URL1",
            "image_url_2": "参考图URL2",
            "image_url_3": "参考图URL3",
            "image_url_4": "参考图URL4",
            "image_url_5": "参考图URL5",
            "api_base": "API地址",
            "timeout": "超时",
            "seed": "随机种子",
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("图像", "图片URL", "revised_prompt", "原始响应")
    FUNCTION = "generate"
    CATEGORY = "KuAi/GPTImage"

    def generate(
        self,
        prompt,
        model,
        size,
        n,
        api_key,
        custom_model="",
        api_base="https://ai.kegeai.top",
        timeout=120,
        seed=0,
        image_url_1="",
        image_url_2="",
        image_url_3="",
        image_url_4="",
        image_url_5="",
    ):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")
        if not prompt.strip():
            raise RuntimeError("提示词不能为空")

        image_urls = _collect_image_urls(image_url_1, image_url_2, image_url_3, image_url_4, image_url_5)
        effective_model = (custom_model or "").strip() or model
        payload = {
            "model": effective_model,
            "size": SIZE_MAP.get(size, size),
            "n": n,
            "prompt": prompt,
            "image": image_urls,
        }
        resp = requests.post(
            f"{api_base.rstrip('/')}/v1/images/generations",
            json=payload,
            headers=http_headers_auth_only(api_key),
            timeout=timeout,
        )
        raise_for_bad_status(resp, "gpt-image-2-all生图失败")
        data = resp.json()

        image_values = _extract_generation_result(data)
        revised = [str(item.get("revised_prompt", "")) for item in (data.get("data") or [])]
        raw = json.dumps(data, ensure_ascii=False)
        image = torch.cat([_payload_image_to_tensor(value, timeout) for value in image_values], dim=0)
        return (image, "\n".join(image_values), "\n".join(revised), raw)


class GPTImage2AllEdit:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_url_1": ("STRING", {"default": "", "tooltip": "第1张图片URL"}),
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "图像编辑提示词"}),
                "model": (MODELS, {"default": "gpt-image-2-all", "tooltip": "模型选择"}),
                "size": (SIZES, {"default": "1024x1024（1:1）", "tooltip": "输出图像尺寸（宽x高｜比例）"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成数量"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
            },
            "optional": {
                "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型名（留空使用下拉模型）"}),
                "image_url_2": ("STRING", {"default": "", "tooltip": "第2张图片URL"}),
                "image_url_3": ("STRING", {"default": "", "tooltip": "第3张图片URL"}),
                "image_url_4": ("STRING", {"default": "", "tooltip": "第4张图片URL"}),
                "image_url_5": ("STRING", {"default": "", "tooltip": "第5张图片URL"}),
                "api_base": ("STRING", {"default": "https://api.kegeai.top", "tooltip": "API服务器地址"}),
                "timeout": ("INT", {"default": 120, "min": 1, "max": 1800, "tooltip": "超时时间(秒)"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True, "tooltip": "ComfyUI 工作流随机种子；仅用于每次提交任务时刷新执行，不会发送给 gpt-image-2-all API。"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image_url_1": "图片URL1",
            "prompt": "提示词",
            "model": "模型",
            "custom_model": "自定义模型",
            "size": "图像尺寸",
            "n": "生成数量",
            "api_key": "API密钥",
            "image_url_2": "图片URL2",
            "image_url_3": "图片URL3",
            "image_url_4": "图片URL4",
            "image_url_5": "图片URL5",
            "api_base": "API地址",
            "timeout": "超时",
            "seed": "随机种子",
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("图像", "图片URL", "revised_prompt", "原始响应")
    FUNCTION = "edit"
    CATEGORY = "KuAi/GPTImage"

    def edit(
        self,
        image_url_1,
        prompt,
        model,
        size,
        n,
        api_key,
        custom_model="",
        image_url_2="",
        image_url_3="",
        image_url_4="",
        image_url_5="",
        api_base="https://api.kegeai.top",
        timeout=120,
        seed=0,
    ):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")
        urls_in = [
            str(image_url_1).strip(),
            str(image_url_2).strip(),
            str(image_url_3).strip(),
            str(image_url_4).strip(),
            str(image_url_5).strip(),
        ]
        image_urls = [url for url in urls_in if url]
        if not image_urls:
            raise RuntimeError("至少需要提供一张图片URL")
        if not prompt.strip():
            raise RuntimeError("提示词不能为空")

        effective_model = (custom_model or "").strip() or model
        payload = {
            "model": effective_model,
            "size": SIZE_MAP.get(size, size),
            "n": n,
            "prompt": prompt,
            "image": image_urls,
        }
        resp = requests.post(
            f"{api_base.rstrip('/')}/v1/images/generations",
            json=payload,
            headers=http_headers_auth_only(api_key),
            timeout=timeout,
        )
        raise_for_bad_status(resp, "gpt-image-2-all编辑图失败")
        data = resp.json()

        image_values = _extract_generation_result(data)
        revised = [str(item.get("revised_prompt", "")) for item in (data.get("data") or [])]
        raw = json.dumps(data, ensure_ascii=False)
        image = torch.cat([_payload_image_to_tensor(value, timeout) for value in image_values], dim=0)
        return (image, "\n".join(image_values), "\n".join(revised), raw)
