"""图片 URL 下载保存节点"""

import base64
import hashlib
import io
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..Sora2.kuai_utils import get_public_url


MAX_IMAGE_BYTES = 80 * 1024 * 1024


def _comfy_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _safe_output_dir(save_dir: str) -> Path:
    if not str(save_dir or "").strip():
        raise ValueError("图片保存目录不能为空")
    root = _comfy_root().resolve()
    target = (root / str(save_dir or "")).resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"图片保存目录必须在 ComfyUI 目录内: {save_dir}")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _split_urls(image_url: str) -> list:
    urls = [line.strip() for line in str(image_url or "").replace("\r", "\n").split("\n")]
    return [url for url in urls if url]


def _ext_from_content_type(content_type: str) -> str:
    content_type = str(content_type or "").lower()
    if "jpeg" in content_type or "jpg" in content_type:
        return "jpg"
    if "webp" in content_type:
        return "webp"
    if "gif" in content_type:
        return "gif"
    return "png"


def _ext_from_image(content: bytes, fallback: str) -> str:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
            image_format = str(image.format or "").lower()
    except UnidentifiedImageError as exc:
        raise RuntimeError("下载内容不是有效图片") from exc
    except Exception as exc:
        raise RuntimeError(f"图片校验失败: {exc}") from exc

    if image_format == "jpeg":
        return "jpg"
    if image_format in {"png", "webp", "gif"}:
        return image_format
    return fallback


def _download_url(url: str, timeout: int) -> tuple[bytes, str]:
    resp = get_public_url(url, timeout=int(timeout), label="图片URL", stream=True)
    try:
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if content_type and not content_type.lower().startswith("image/"):
            raise RuntimeError(f"图片URL返回的不是图片内容: {content_type}")

        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_IMAGE_BYTES:
            raise RuntimeError("图片超过 80MB，已停止下载")

        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise RuntimeError("图片超过 80MB，已停止下载")
            chunks.append(chunk)
        content = b"".join(chunks)
        ext = _ext_from_image(content, _ext_from_content_type(content_type))
        return content, ext
    finally:
        resp.close()


def _decode_data_url(url: str) -> tuple[bytes, str]:
    try:
        header, b64 = url.split(",", 1)
    except ValueError as exc:
        raise RuntimeError("data URL 格式错误") from exc

    compact_b64 = "".join(str(b64).split())
    if (len(compact_b64) * 3) // 4 > MAX_IMAGE_BYTES:
        raise RuntimeError("图片超过 80MB，已停止解码")

    try:
        content = base64.b64decode(compact_b64, validate=True)
    except Exception as exc:
        raise RuntimeError(f"data URL base64 解码失败: {exc}") from exc
    if len(content) > MAX_IMAGE_BYTES:
        raise RuntimeError("图片超过 80MB，已停止解码")

    fallback = "png"
    header_lower = header.lower()
    if "jpeg" in header_lower or "jpg" in header_lower:
        fallback = "jpg"
    elif "webp" in header_lower:
        fallback = "webp"
    elif "gif" in header_lower:
        fallback = "gif"
    return content, _ext_from_image(content, fallback)


def _read_image_bytes(url: str, timeout: int) -> tuple[bytes, str]:
    if url.startswith("data:"):
        return _decode_data_url(url)
    return _download_url(url, timeout)


def _next_path(output_dir: Path, prefix: str, index: int, url: str, ext: str) -> Path:
    clean_prefix = "".join(c for c in str(prefix or "image_url") if c.isalnum() or c in ("_", "-")) or "image_url"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
    base = f"{clean_prefix}_{index}_{stamp}_{digest}"
    path = output_dir / f"{base}.{ext}"
    suffix = 1
    while path.exists():
        path = output_dir / f"{base}_{suffix}.{ext}"
        suffix += 1
    return path


class DownloadImageURLSave:
    """通过图片 URL 下载保存图片"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image_url": ("STRING", {"default": "", "multiline": True, "tooltip": "图片 URL，多个 URL 用换行分隔"}),
            },
            "optional": {
                "save_dir": ("STRING", {"default": "output/gpt_image2", "tooltip": "保存目录，相对于 ComfyUI 根目录"}),
                "filename_prefix": ("STRING", {"default": "gptimage2_url", "tooltip": "文件名前缀"}),
                "timeout": ("INT", {"default": 1800, "min": 5, "max": 9999, "tooltip": "下载超时(秒)"}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image_url": "图片URL",
            "save_dir": "保存目录",
            "filename_prefix": "文件名前缀",
            "timeout": "超时",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("本地路径", "文件名", "状态")
    FUNCTION = "download"
    OUTPUT_NODE = True
    CATEGORY = "KuAi/配套能力"

    def download(self, image_url, save_dir="output/gpt_image2", filename_prefix="gptimage2_url", timeout=1800):
        urls = _split_urls(image_url)
        if not urls:
            raise RuntimeError("图片URL不能为空")

        root = _comfy_root()
        output_dir = _safe_output_dir(save_dir)
        paths = []
        names = []
        for index, url in enumerate(urls, start=1):
            content, ext = _read_image_bytes(url, timeout)
            path = _next_path(output_dir, filename_prefix, index, url, ext)
            path.write_bytes(content)
            paths.append(str(path.relative_to(root)))
            names.append(path.name)
            print(f"[DownloadImageURLSave] 保存图片: {path}")

        return ("\n".join(paths), "\n".join(names), f"下载成功: {len(paths)} 张")


NODE_CLASS_MAPPINGS = {
    "DownloadImageURLSave": DownloadImageURLSave,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DownloadImageURLSave": "💾 下载图片 URL 保存",
}
