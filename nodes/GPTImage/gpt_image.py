"""GPT Image 2 节点 - 文生图和图片编辑"""

import io
import requests
import numpy as np
import torch
from PIL import Image

from ..Sora2.kuai_utils import (
    env_or,
    http_headers_auth_only,
    http_headers_multipart,
    raise_for_bad_status,
    download_public_url_bytes,
)

MODELS = ["gpt-image-2"]
EDIT_MODELS = ["gpt-image-2"]
RATIO_LABELS = {
    "1:1": "正方形",
    "1:2": "竖版长图",
    "2:1": "横版长图",
    "2:3": "竖版",
    "3:2": "横版",
    "9:16": "手机竖版",
    "16:9": "宽屏横版",
    "3:4": "竖版",
    "4:3": "横版",
    "4:5": "竖版海报",
    "5:4": "横版海报",
    "21:9": "电影宽屏",
    "9:21": "超长竖版",
}
SIZE_OPTIONS = [
    ("1K", "1:1", "1024x1024"),
    ("1K", "1:2", "1024x2048"),
    ("1K", "2:1", "2048x1024"),
    ("1K", "2:3", "1024x1536"),
    ("1K", "3:2", "1536x1024"),
    ("1K", "9:16", "864x1536"),
    ("1K", "16:9", "1536x864"),
    ("1K", "3:4", "768x1024"),
    ("1K", "4:3", "1024x768"),
    ("1K", "4:5", "1024x1280"),
    ("1K", "5:4", "1280x1024"),
    ("1K", "21:9", "2016x864"),
    ("1K", "9:21", "864x2016"),
    ("2K", "1:1", "2048x2048"),
    ("2K", "1:2", "1344x2688"),
    ("2K", "2:1", "2688x1344"),
    ("2K", "2:3", "1360x2048"),
    ("2K", "3:2", "2048x1360"),
    ("2K", "9:16", "1152x2048"),
    ("2K", "16:9", "2048x1152"),
    ("2K", "3:4", "1536x2048"),
    ("2K", "4:3", "2048x1536"),
    ("2K", "4:5", "2048x2560"),
    ("2K", "5:4", "2560x2048"),
    ("2K", "21:9", "2688x1152"),
    ("2K", "9:21", "1152x2688"),
    ("4K", "1:1", "2880x2880"),
    ("4K", "1:2", "1920x3840"),
    ("4K", "2:1", "3840x1920"),
    ("4K", "2:3", "2336x3520"),
    ("4K", "3:2", "3520x2336"),
    ("4K", "9:16", "2160x3840"),
    ("4K", "16:9", "3840x2160"),
    ("4K", "3:4", "2480x3312"),
    ("4K", "4:3", "3312x2480"),
    ("4K", "4:5", "2576x3216"),
    ("4K", "5:4", "3216x2576"),
    ("4K", "21:9", "3840x1648"),
    ("4K", "9:21", "1648x3840"),
]
SIZES = ["auto（默认）"] + [
    f"{tier} {pixels}（{ratio}｜{RATIO_LABELS[ratio]}）"
    for tier, ratio, pixels in SIZE_OPTIONS
]
SIZE_MAP = {
    "auto（默认）": "auto",
    **{
        f"{tier} {pixels}（{ratio}｜{RATIO_LABELS[ratio]}）": pixels
        for tier, ratio, pixels in SIZE_OPTIONS
    },
    # Legacy labels kept so existing saved workflows continue to execute.
    "1024x1024（1:1｜正方形）": "1024x1024",
    "1536x1024（3:2｜横版）": "1536x1024",
    "1024x1536（2:3｜竖版）": "1024x1536",
    "2048x2048（1:1｜2K正方形）": "2048x2048",
    "2048x1152（16:9｜2K横版）": "2048x1152",
    "3840x2160（16:9｜4K横版）": "3840x2160",
    "2160x3840（9:16｜4K竖版）": "2160x3840",
}
FORMATS = ["png", "jpeg", "webp"]
RESPONSE_FORMATS = ["url", "b64_json"]
QUALITY_OPTIONS = ["auto", "low", "medium", "high"]
EDIT_IMAGE_URL_COUNT = 16


def _extract_urls(data: dict) -> list:
    # Standard OpenAI format: {"data": [{"url": "..."}]} or {"data": [{"b64_json": "..."}]}
    items = data.get("data") or []
    if items:
        urls = [item["url"].strip() for item in items if item.get("url")]
        if urls:
            return urls
        b64s = [f"data:image/png;base64,{item['b64_json']}" for item in items if item.get("b64_json")]
        if b64s:
            return b64s
    # Fallback: choices[0].message.content
    choices = data.get("choices") or []
    if choices:
        urls = [c["message"]["content"].strip() for c in choices if c.get("message", {}).get("content")]
        if urls:
            return urls
    raise RuntimeError(f"响应中没有图像数据: {data}")


def _url_to_tensor(url: str, timeout: int) -> torch.Tensor:
    if url.startswith("data:"):
        import base64
        content = base64.b64decode(url.split(",", 1)[1])
    else:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        content = resp.content
    pil = Image.open(io.BytesIO(content)).convert("RGB")
    arr = np.array(pil).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None,]


def _collect_image_urls(*image_urls) -> list:
    return [str(url).strip() for url in image_urls if str(url or "").strip()]


def _edit_image_url_inputs() -> dict:
    return {
        f"image_url_{i}": (
            "STRING",
            {
                "default": "",
                "forceInput": True,
                "tooltip": f"图片URL {i}（可选参考图）",
            },
        )
        for i in range(1, EDIT_IMAGE_URL_COUNT + 1)
    }


class GPTImage2Generate:
    """GPT Image 2 文生图节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "图像描述提示词"}),
                "model": (MODELS, {"default": "gpt-image-2", "tooltip": "模型选择"}),
                "size": (SIZES, {"default": "auto（默认）", "tooltip": "图像尺寸（分辨率、比例与用途）"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成数量（1-10张）"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
            },
            "optional": {
                "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型名（留空使用下拉模型）"}),
                "api_base": ("STRING", {"default": "https://ai.kegeai.top", "tooltip": "API服务器地址"}),
                "format": (FORMATS, {"default": "png", "tooltip": "输出格式（png、jpeg、webp）"}),
                "quality": (QUALITY_OPTIONS, {"default": "auto", "tooltip": "图像质量（low、medium、high、auto）"}),
                "timeout": ("INT", {"default": 1800, "min": 30, "max": 9999, "tooltip": "超时时间(秒)"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True, "tooltip": "ComfyUI workflow random seed; refreshes each queued task and is not sent to the GPT Image 2 API."}),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "seed": "随机种子",
            "prompt": "提示词",
            "model": "模型",
            "size": "图像尺寸（分辨率/比例）",
            "n": "生成数量（输出图片张数）",
            "custom_model": "自定义模型",
            "api_key": "API密钥",
            "api_base": "API地址",
            "format": "输出格式（png/jpeg/webp）",
            "quality": "图像质量（清晰度等级）",
            "timeout": "超时",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "图片URL")
    FUNCTION = "generate"
    CATEGORY = "KuAi/GPTImage"

    def generate(self, prompt, model, size, n, api_key, custom_model="", api_base="https://ai.kegeai.top", format="png", quality="auto", timeout=1800, seed=0, **kwargs):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量 KUAI_API_KEY 中设置")
        if not prompt.strip():
            raise RuntimeError("提示词不能为空")

        effective_model = (custom_model or "").strip() or model
        image_format = format
        payload = {
            "model": effective_model,
            "prompt": prompt,
            "n": n,
            "size": SIZE_MAP.get(size, size),
            "format": image_format,
            "quality": quality,
        }
        resp = requests.post(
            f"{api_base.rstrip('/')}/v1/images/generations",
            json=payload,
            headers=http_headers_auth_only(api_key),
            timeout=timeout,
        )
        raise_for_bad_status(resp, "GPTImage文生图失败")
        data = resp.json()

        urls = _extract_urls(data)
        tensors = [_url_to_tensor(u, timeout) for u in urls]
        image_tensor = torch.cat(tensors, dim=0)
        print(f"[GPTImage] 文生图完成，生成 {len(urls)} 张图像")
        return (image_tensor, "\n".join(urls))


class GPTImage2Edit:
    """GPT Image 2 图片编辑节点（支持最多16张图片URL）"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                **_edit_image_url_inputs(),
                "prompt": ("STRING", {"multiline": True, "default": "", "tooltip": "编辑描述提示词"}),
                "model": (EDIT_MODELS, {"default": "gpt-image-2", "tooltip": "模型选择"}),
                "custom_model": ("STRING", {"default": "", "tooltip": "自定义模型名（留空使用下拉模型）"}),
                "size": (SIZES, {"default": "auto（默认）", "tooltip": "输出图像尺寸（分辨率、比例与用途）"}),
                "n": ("INT", {"default": 1, "min": 1, "max": 10, "tooltip": "生成数量（输出图片张数，1-10张）"}),
                "api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"}),
                "quality": (QUALITY_OPTIONS, {"default": "auto", "tooltip": "图像质量（可选 low、medium、high、auto）"}),
                "background": (["auto", "transparent", "opaque"], {"default": "auto", "tooltip": "背景透明度（auto 自动、transparent 透明、opaque 不透明）"}),
                "moderation": (["auto", "low"], {"default": "auto", "tooltip": "内容审核级别（auto 默认、low 较宽松）"}),
                "api_base": ("STRING", {"default": "https://ai.kegeai.top", "tooltip": "API服务器地址"}),
                "timeout": ("INT", {"default": 1800, "min": 30, "max": 9999, "tooltip": "超时时间(秒)"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True, "tooltip": "ComfyUI workflow random seed; refreshes each queued task and is not sent to the GPT Image 2 API."}),
                "response_format": (RESPONSE_FORMATS, {"default": "url", "tooltip": "返回格式：url 或 b64_json"}),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            **{f"image_url_{i}": f"图片URL {i}（参考图）" for i in range(1, EDIT_IMAGE_URL_COUNT + 1)},
            "prompt": "编辑提示词（修改要求）",
            "model": "模型（GPT Image 2）",
            "custom_model": "自定义模型",
            "size": "图像尺寸（分辨率/比例）",
            "n": "生成数量（输出图片张数）",
            "api_key": "API密钥",
            "quality": "图像质量（清晰度等级）",
            "background": "背景（透明/不透明）",
            "moderation": "内容审核（安全级别）",
            "api_base": "API地址",
            "timeout": "超时（秒）",
            "seed": "随机种子",
            "response_format": "返回格式",
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("图像", "图片URL")
    FUNCTION = "edit"
    CATEGORY = "KuAi/GPTImage"

    def edit(self, image_url_1="", prompt="", model="gpt-image-2", custom_model="", size="auto（默认）", n=1, api_key="",
             image_url_2="", image_url_3="", image_url_4="",
             quality="auto", background="auto", moderation="auto",
             api_base="https://ai.kegeai.top", timeout=1800, seed=0, response_format="url", **kwargs):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量 KUAI_API_KEY 中设置")
        if not prompt.strip():
            raise RuntimeError("提示词不能为空")

        image_urls = _collect_image_urls(
            image_url_1,
            image_url_2,
            image_url_3,
            image_url_4,
            *(kwargs.get(f"image_url_{i}", "") for i in range(5, EDIT_IMAGE_URL_COUNT + 1)),
        )
        if not image_urls:
            raise RuntimeError("至少需要提供一张图片URL")

        files = []
        for i, url in enumerate(image_urls):
            content = download_public_url_bytes(url, timeout=timeout, label=f"图片URL {i + 1}")
            files.append(("image[]", (f"image_{i}.png", content, "image/png")))

        effective_model = (custom_model or "").strip() or model
        form_data = {
            "model": effective_model,
            "prompt": prompt,
            "n": str(n),
            "size": SIZE_MAP.get(size, size),
            "quality": quality,
            "background": background,
            "moderation": moderation,
            "response_format": response_format,
        }

        resp = requests.post(
            f"{api_base.rstrip('/')}/v1/images/edits",
            files=files,
            data=form_data,
            headers=http_headers_multipart(api_key),
            timeout=timeout,
        )
        raise_for_bad_status(resp, "GPTImage图片编辑失败")
        data = resp.json()

        urls = _extract_urls(data)
        tensors = [_url_to_tensor(u, timeout) for u in urls]

        image_tensor = torch.cat(tensors, dim=0)
        print(f"[GPTImage] 图片编辑完成，输入{len(image_urls)}张图，生成{len(urls)}张图像")
        return (image_tensor, "\n".join(urls))
