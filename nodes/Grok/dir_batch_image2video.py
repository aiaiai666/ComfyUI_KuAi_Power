"""Grok 目录批量图生视频（一键闭环）

完整链路：扫描本地目录 → 并发上传图片 → 并发图生视频 → 轮询 → 下载 MP4
单节点完成全部操作，无需串联多个节点。
"""

import json
import os
import io
import time
import hashlib
import requests
import concurrent.futures
from pathlib import Path
from PIL import Image

from ..Sora2.kuai_utils import env_or, http_headers_multipart
from .grok import GrokCreateVideo as _GrokCreateVideo
from .grok import GrokQueryVideo as _GrokQueryVideo


# ─────────────────────────────────────────────
# 内部工具
# ─────────────────────────────────────────────

_IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
_LOG_TAG = "[GrokDirBatch]"


def _natural_sort_key(path: Path):
    """按文件名中的数字排序：1.png < 2.png < 10.png"""
    import re
    return [int(c) if c.isdigit() else c.lower()
            for c in re.split(r'(\d+)', path.stem)]


def _scan_images(directory: str, max_images: int) -> list[Path]:
    """扫描目录中的图片文件，按自然数字排序"""
    d = Path(directory.strip())
    if not d.exists():
        raise RuntimeError(f"目录不存在: {d}")
    if not d.is_dir():
        raise RuntimeError(f"路径不是目录: {d}")

    files = [f for f in d.iterdir()
             if f.is_file() and f.suffix.lower() in _IMAGE_EXTS]

    if not files:
        raise RuntimeError(f"目录中没有找到图片: {d}")

    files.sort(key=_natural_sort_key)

    if len(files) > max_images:
        print(f"{_LOG_TAG} 目录共 {len(files)} 张图片，限制为 {max_images} 张")
        files = files[:max_images]

    return files


def _upload_one(image_path: Path, upload_url: str, fmt: str,
                quality: int, timeout: int) -> str:
    """上传单张图片，返回 CDN URL"""
    pil = Image.open(image_path)
    if pil.mode not in ('RGB', 'RGBA'):
        pil = pil.convert('RGB')
    if fmt == 'jpeg' and pil.mode == 'RGBA':
        bg = Image.new('RGB', pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[3])
        pil = bg

    buf = io.BytesIO()
    save_fmt = 'JPEG' if fmt == 'jpeg' else fmt.upper()
    pil.save(buf, format=save_fmt, quality=quality)
    buf.seek(0)

    ext = 'jpg' if fmt == 'jpeg' else fmt
    files = {"file": (f"{image_path.stem}.{ext}", buf, f"image/{fmt}")}
    resp = requests.post(upload_url, headers=http_headers_multipart(),
                         files=files, timeout=timeout)

    if resp.status_code >= 400:
        raise RuntimeError(f"上传失败 HTTP {resp.status_code}: {resp.text[:200]}")

    url = resp.json().get("url", "")
    if not url:
        raise RuntimeError(f"上传响应缺少 url: {resp.text[:200]}")
    return url


def _upload_batch(image_paths: list[Path], upload_url: str, fmt: str,
                  quality: int, timeout: int, workers: int) -> list[dict]:
    """并发上传多张图片，返回 [{index, path, url, error}]"""
    results = []

    def _worker(idx_path):
        idx, path = idx_path
        try:
            url = _upload_one(path, upload_url, fmt, quality, timeout)
            print(f"{_LOG_TAG} [{idx}] 上传成功: {path.name}")
            return {"index": idx, "path": path, "url": url, "error": ""}
        except Exception as e:
            print(f"{_LOG_TAG} [{idx}] 上传失败: {path.name} - {e}")
            return {"index": idx, "path": path, "url": "", "error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, (i, p))
                   for i, p in enumerate(image_paths, 1)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    results.sort(key=lambda r: r["index"])
    return results


def _download_video(video_url: str, save_dir: str, prefix: str,
                    timeout: int) -> str:
    """下载视频到本地，返回相对路径"""
    try:
        comfy_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        out_dir = comfy_root / save_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.md5(video_url.encode()).hexdigest()[:8]
        filepath = out_dir / f"{prefix}_{url_hash}.mp4"
        resp = requests.get(video_url, timeout=timeout, stream=True)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return str(filepath.relative_to(comfy_root))
    except Exception as e:
        print(f"{_LOG_TAG} 下载失败 ({prefix}): {e}")
        return ""


def _process_one(task_idx: int, image_url: str, prompt: str,
                 output_prefix: str,
                 model: str, aspect_ratio: str, size: str,
                 enhance_prompt: bool, custom_model: str,
                 api_key: str, api_base: str,
                 save_dir: str, max_wait: int,
                 poll_interval: int, dl_timeout: int) -> dict:
    """单任务完整流程：提交 → 轮询 → 下载"""
    result = {"idx": task_idx, "prompt": prompt, "status": "error",
              "video_url": "", "local_path": "", "error": ""}
    try:
        # 1. 创建任务
        creator = _GrokCreateVideo()
        task_id, status, _ = creator.create(
            prompt=prompt, model=model, aspect_ratio=aspect_ratio,
            size=size, enhance_prompt=enhance_prompt, api_key=api_key,
            image_urls=image_url, api_base=api_base, custom_model=custom_model,
        )
        result["task_id"] = task_id
        result["status"] = status
        print(f"{_LOG_TAG} [{task_idx}] 已提交 task_id={task_id}")

        # 2. 轮询
        querier = _GrokQueryVideo()
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval
            try:
                _, status, video_url, _, _ = querier.query(
                    task_id, api_key, api_base)
                result["status"] = status
                if status == "completed" and video_url:
                    result["video_url"] = video_url
                    print(f"{_LOG_TAG} [{task_idx}] 生成完成，下载中...")
                    result["local_path"] = _download_video(
                        video_url, save_dir, output_prefix, dl_timeout)
                    return result
                print(f"{_LOG_TAG} [{task_idx}] 进行中 {elapsed}/{max_wait}s")
            except RuntimeError:
                raise
            except Exception as e:
                print(f"{_LOG_TAG} [{task_idx}] 查询出错（重试）: {e}")

        raise RuntimeError(f"超时 ({max_wait}s)")

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "failed"
        print(f"{_LOG_TAG} [{task_idx}] ✗ {e}")
        return result


# ─────────────────────────────────────────────
# 节点
# ─────────────────────────────────────────────

class GrokDirBatchImage2Video:
    """
    Grok 目录批量图生视频（一键闭环）

    单节点完成：扫描目录 → 并发上传 → 并发图生视频 → 轮询 → 下载 MP4
    图片按文件名自然排序（1.png, 2.png, ..., 10.png）
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory_path": ("STRING", {
                    "default": "/root/ComfyUI/input/grok/demo1",
                    "tooltip": "本地图片目录的完整路径"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "视频生成提示词（所有图片共用）"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "model": ([
                    "grok-video-3 (6秒)",
                    "grok-video-3-10s (10秒)",
                    "grok-video-3-15s (15秒)",
                ], {
                    "default": "grok-video-3 (6秒)",
                    "tooltip": "选择 Grok 模型"
                }),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {
                    "default": "3:2",
                    "tooltip": "视频宽高比"
                }),
                "size": (["720P", "1080P"], {
                    "default": "1080P",
                    "tooltip": "视频分辨率"
                }),
                "enhance_prompt": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "自动优化并翻译提示词"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型名称（留空使用上方选择的模型）"
                }),
                "save_dir": ("STRING", {
                    "default": "output/grok",
                    "tooltip": "视频保存目录（相对 ComfyUI 根目录）"
                }),
                "output_prefix": ("STRING", {
                    "default": "grok",
                    "tooltip": "输出文件名前缀（实际文件名: {prefix}_{序号}_{hash}.mp4）"
                }),
                "batch_size": ("INT", {
                    "default": 5, "min": 1, "max": 20,
                    "tooltip": "每批并发任务数（图生视频阶段）"
                }),
                "upload_workers": ("INT", {
                    "default": 5, "min": 1, "max": 20,
                    "tooltip": "并发上传线程数（上传阶段）"
                }),
                "max_images": ("INT", {
                    "default": 100, "min": 1, "max": 500,
                    "tooltip": "最大处理图片数"
                }),
                "upload_url": ("STRING", {
                    "default": "https://imageproxy.zhongzhuan.chat/api/upload",
                    "tooltip": "图床上传地址"
                }),
                "upload_format": (["jpeg", "png", "webp"], {
                    "default": "jpeg",
                    "tooltip": "上传图片格式"
                }),
                "upload_quality": ("INT", {
                    "default": 90, "min": 1, "max": 100,
                    "tooltip": "图片质量"
                }),
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                }),
                "max_wait_time": ("INT", {
                    "default": 1200, "min": 60, "max": 3600,
                    "tooltip": "单任务最大等待时间（秒）"
                }),
                "poll_interval": ("INT", {
                    "default": 10, "min": 5, "max": 60,
                }),
                "download_timeout": ("INT", {
                    "default": 180, "min": 30, "max": 600,
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "directory_path": "图片目录路径",
            "prompt": "提示词",
            "api_key": "API密钥",
            "model": "模型",
            "aspect_ratio": "宽高比",
            "size": "分辨率",
            "enhance_prompt": "优化提示词",
            "custom_model": "自定义模型",
            "save_dir": "视频保存目录",
            "output_prefix": "输出前缀",
            "batch_size": "并发批次大小",
            "upload_workers": "上传并发数",
            "max_images": "最大图片数",
            "upload_url": "图床地址",
            "upload_format": "上传格式",
            "upload_quality": "图片质量",
            "api_base": "API地址",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔",
            "download_timeout": "下载超时",
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("处理报告", "视频保存目录")
    FUNCTION = "run"
    CATEGORY = "KuAi/Grok"

    def run(self, directory_path, prompt, api_key,
            model="grok-video-3 (6秒)", aspect_ratio="3:2", size="1080P",
            enhance_prompt=True, custom_model="",
            save_dir="output/grok", output_prefix="grok",
            batch_size=5, upload_workers=5, max_images=100,
            upload_url="https://imageproxy.zhongzhuan.chat/api/upload",
            upload_format="jpeg", upload_quality=90,
            api_base="https://api.kegeai.top",
            max_wait_time=1200, poll_interval=10, download_timeout=180):

        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置")
        if not prompt.strip():
            raise RuntimeError("提示词不能为空")

        # ── 阶段 1：扫描目录 ──
        print(f"\n{'='*60}")
        print(f"{_LOG_TAG} 阶段 1/3：扫描目录")
        print(f"{'='*60}")

        image_paths = _scan_images(directory_path, max_images)
        print(f"{_LOG_TAG} 找到 {len(image_paths)} 张图片")

        # ── 阶段 2：并发上传 ──
        print(f"\n{'='*60}")
        print(f"{_LOG_TAG} 阶段 2/3：并发上传（{upload_workers} 线程）")
        print(f"{'='*60}")

        upload_results = _upload_batch(
            image_paths, upload_url, upload_format,
            upload_quality, 30, upload_workers)

        # 过滤上传成功的
        uploaded = [r for r in upload_results if r["url"]]
        upload_failed = [r for r in upload_results if not r["url"]]

        if not uploaded:
            raise RuntimeError("所有图片上传失败，无法继续")

        print(f"{_LOG_TAG} 上传完成: 成功 {len(uploaded)}/{len(upload_results)}")
        if upload_failed:
            for r in upload_failed:
                print(f"{_LOG_TAG}   上传失败: {r['path'].name} - {r['error']}")

        # ── 阶段 3：并发图生视频 + 轮询 + 下载 ──
        print(f"\n{'='*60}")
        print(f"{_LOG_TAG} 阶段 3/3：并发图生视频（每批 {batch_size} 路）")
        print(f"{'='*60}")

        all_results = []
        total = len(uploaded)

        for batch_start in range(0, total, batch_size):
            batch = uploaded[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            print(f"\n{_LOG_TAG} 批次 {batch_num}/{total_batches}：提交 {len(batch)} 个任务")

            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as pool:
                future_map = {}
                for item in batch:
                    idx = item["index"]
                    prefix = f"{output_prefix}_{idx}"
                    future = pool.submit(
                        _process_one, idx, item["url"], prompt, prefix,
                        model, aspect_ratio, size, enhance_prompt, custom_model,
                        api_key, api_base, save_dir, max_wait_time,
                        poll_interval, download_timeout)
                    future_map[future] = idx

                for f in concurrent.futures.as_completed(future_map):
                    all_results.append(f.result())

        # ── 生成报告 ──
        all_results.sort(key=lambda r: r["idx"])
        success = [r for r in all_results if r["status"] == "completed"]
        failed = [r for r in all_results if r["status"] != "completed"]

        lines = [
            f"\n{'='*60}",
            f"Grok 目录批量图生视频完成",
            f"目录: {directory_path}",
            f"图片: {len(image_paths)}  上传成功: {len(uploaded)}  "
            f"生成成功: {len(success)}  生成失败: {len(failed)}",
            f"保存目录: {save_dir}",
            f"{'='*60}",
        ]

        if success:
            lines.append("\n✓ 成功:")
            for r in success:
                lines.append(f"  [{r['idx']}] {r.get('local_path', '')}")
        if upload_failed:
            lines.append("\n✗ 上传失败:")
            for r in upload_failed:
                lines.append(f"  [{r['index']}] {r['path'].name}: {r['error']}")
        if failed:
            lines.append("\n✗ 生成失败:")
            for r in failed:
                lines.append(f"  [{r['idx']}] {r.get('error', '')}")

        report = "\n".join(lines)
        print(report)

        comfy_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        abs_save_dir = str(comfy_root / save_dir)

        return (report, abs_save_dir)


# ─────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "GrokDirBatchImage2Video": GrokDirBatchImage2Video,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokDirBatchImage2Video": "⚡ Grok 目录批量图生视频（一键闭环）",
}
