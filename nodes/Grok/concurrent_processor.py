"""Grok 10路并发视频生成节点"""

import time
import requests
import hashlib
import concurrent.futures
from pathlib import Path

from ..Sora2.kuai_utils import env_or
from .grok import GrokText2Video as _GrokText2Video
from .grok import GrokImage2Video as _GrokImage2Video
from .grok import GrokQueryVideo as _GrokQueryVideo

N = 10


# ─────────────────────────────────────────────
# 内部工具函数
# ─────────────────────────────────────────────

def _download(video_url, save_dir, prefix, timeout):
    """下载单个视频到本地"""
    try:
        comfy_root = Path(__file__).parent.parent.parent.parent.parent
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
        print(f"[GrokConcurrent] 下载失败: {e}")
        return ""


def _poll_and_download(task_idx, task_id, api_key, api_base,
                       save_dir, max_wait_time, poll_interval, download_timeout):
    """轮询单个任务直到完成，完成后下载"""
    querier = _GrokQueryVideo()
    elapsed = 0
    while elapsed < max_wait_time:
        time.sleep(poll_interval)
        elapsed += poll_interval
        try:
            # query 返回 (task_id, status, video_url, enhanced_prompt, status_update_time)
            _, status, video_url, _, _ = querier.query(task_id, api_key, api_base)
            if status == "completed" and video_url:
                local = _download(video_url, save_dir, f"grok_{task_idx}", download_timeout)
                print(f"[GrokConcurrent] ✓ 任务{task_idx} 完成: {local}")
                return video_url, local
            print(f"[GrokConcurrent] 任务{task_idx} 进行中... {elapsed}/{max_wait_time}s")
        except RuntimeError:
            raise  # 任务失败，直接上抛
        except Exception as e:
            print(f"[GrokConcurrent] 任务{task_idx} 查询出错（继续重试）: {e}")
    raise RuntimeError(f"任务{task_idx} 超时 ({max_wait_time}s)")


def _worker_text2video(task_idx, prompt, model, aspect_ratio, size, enhance_prompt,
                       api_key, api_base, save_dir, max_wait_time, poll_interval,
                       download_timeout, custom_model):
    creator = _GrokText2Video()
    task_id, _, _ = creator.create(
        prompt=prompt, model=model, aspect_ratio=aspect_ratio, size=size,
        enhance_prompt=enhance_prompt, api_key=api_key, api_base=api_base,
        custom_model=custom_model,
    )
    print(f"[GrokConcurrent] 任务{task_idx} 已提交: {task_id}")
    return _poll_and_download(task_idx, task_id, api_key, api_base,
                              save_dir, max_wait_time, poll_interval, download_timeout)


def _worker_image2video(task_idx, prompt, image_url, model, aspect_ratio, size, enhance_prompt,
                        api_key, api_base, save_dir, max_wait_time, poll_interval,
                        download_timeout, custom_model):
    creator = _GrokImage2Video()
    # create 返回 (task_id, status, enhanced_prompt, status_update_time)
    task_id, _, _, _ = creator.create(
        images=image_url, prompt=prompt, model=model, aspect_ratio=aspect_ratio,
        size=size, enhance_prompt=enhance_prompt, api_key=api_key, api_base=api_base,
        custom_model=custom_model,
    )
    print(f"[GrokConcurrent] 任务{task_idx} 已提交: {task_id}")
    return _poll_and_download(task_idx, task_id, api_key, api_base,
                              save_dir, max_wait_time, poll_interval, download_timeout)


def _run_concurrent(worker_fn, task_args_list):
    """并发执行所有任务，收集结果和错误"""
    results, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=N) as executor:
        future_map = {
            executor.submit(worker_fn, *args): args[0]  # args[0] = task_idx
            for args in task_args_list
        }
        for future in concurrent.futures.as_completed(future_map):
            idx = future_map[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                errors[idx] = str(e)
                print(f"[GrokConcurrent] ✗ 任务{idx} 失败: {e}")
    return results, errors


def _build_report(results, errors, total):
    lines = [f"并发完成: {len(results)}/{total} 成功"]
    for i in range(1, N + 1):
        if i in results:
            lines.append(f"  ✓ 任务{i}: {results[i][1]}")
        elif i in errors:
            lines.append(f"  ✗ 任务{i}: {errors[i]}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 节点：Grok 文生视频 10路并发
# ─────────────────────────────────────────────

class GrokText2Video10Concurrent:
    """Grok 文生视频 10路并发生成节点"""

    @classmethod
    def INPUT_TYPES(cls):
        required = {"api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量）"})}
        for i in range(1, N + 1):
            required[f"prompt_{i}"] = ("STRING", {
                "default": "",
                "multiline": True,
                "tooltip": f"第{i}条提示词（留空跳过该路）"
            })
        return {
            "required": required,
            "optional": {
                "model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)", "grok-video-3-15s (15秒)"],
                          {"default": "grok-video-3 (6秒)"}),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {"default": "3:2"}),
                "size": (["720P", "1080P"], {"default": "720P"}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "api_base": ("STRING", {"default": "https://api.kegeai.top"}),
                "save_dir": ("STRING", {"default": "output/grok", "tooltip": "视频保存目录（相对ComfyUI根目录）"}),
                "max_wait_time": ("INT", {"default": 1200, "min": 60, "max": 3600}),
                "poll_interval": ("INT", {"default": 10, "min": 5, "max": 60}),
                "download_timeout": ("INT", {"default": 1800, "min": 30, "max": 9999}),
                "custom_model": ("STRING", {"default": ""}),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        labels = {"api_key": "API密钥"}
        for i in range(1, N + 1):
            labels[f"prompt_{i}"] = f"提示词 {i}"
        labels.update({
            "model": "模型", "aspect_ratio": "宽高比", "size": "分辨率",
            "enhance_prompt": "提示词增强", "api_base": "API地址",
            "save_dir": "保存目录", "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔", "download_timeout": "下载超时",
            "custom_model": "自定义模型",
        })
        return labels

    RETURN_TYPES = tuple(["STRING"] * N + ["STRING"] * N + ["STRING"])
    RETURN_NAMES = tuple(
        [f"视频URL_{i}" for i in range(1, N + 1)] +
        [f"本地路径_{i}" for i in range(1, N + 1)] +
        ["处理报告"]
    )
    FUNCTION = "run"
    CATEGORY = "KuAi/Grok"

    def run(self, api_key, **kwargs):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")

        model          = kwargs.get("model", "grok-video-3 (6秒)")
        aspect_ratio   = kwargs.get("aspect_ratio", "3:2")
        size           = kwargs.get("size", "720P")
        enhance_prompt = kwargs.get("enhance_prompt", True)
        api_base       = kwargs.get("api_base", "https://api.kegeai.top")
        save_dir       = kwargs.get("save_dir", "output/grok")
        max_wait_time  = kwargs.get("max_wait_time", 1200)
        poll_interval  = kwargs.get("poll_interval", 10)
        download_timeout = kwargs.get("download_timeout", 180)
        custom_model   = kwargs.get("custom_model", "")

        task_args = []
        for i in range(1, N + 1):
            prompt = kwargs.get(f"prompt_{i}", "").strip()
            if prompt:
                task_args.append((i, prompt, model, aspect_ratio, size, enhance_prompt,
                                  api_key, api_base, save_dir, max_wait_time,
                                  poll_interval, download_timeout, custom_model))

        if not task_args:
            raise RuntimeError("至少需要填写一条提示词")

        print(f"\n{'='*60}")
        print(f"[GrokConcurrent] 开始 {len(task_args)} 路并发文生视频")
        print(f"{'='*60}")

        results, errors = _run_concurrent(_worker_text2video, task_args)

        urls  = [results.get(i, ("", ""))[0] for i in range(1, N + 1)]
        paths = [results.get(i, ("", ""))[1] for i in range(1, N + 1)]
        report = _build_report(results, errors, len(task_args))

        return tuple(urls + paths + [report])


# ─────────────────────────────────────────────
# 节点：Grok 图生视频 10路并发
# ─────────────────────────────────────────────

class GrokImage2Video10Concurrent:
    """Grok 图生视频 10路并发生成节点"""

    @classmethod
    def INPUT_TYPES(cls):
        required = {"api_key": ("STRING", {"default": "", "tooltip": "API密钥（留空使用环境变量）"})}
        for i in range(1, N + 1):
            required[f"prompt_{i}"] = ("STRING", {
                "default": "",
                "multiline": True,
                "tooltip": f"第{i}条提示词（留空跳过该路）"
            })
            required[f"image_url_{i}"] = ("STRING", {
                "default": "",
                "multiline": False,
                "tooltip": f"第{i}条图片URL"
            })
        return {
            "required": required,
            "optional": {
                "model": (["grok-video-3 (6秒)", "grok-video-3-10s (10秒)", "grok-video-3-15s (15秒)"],
                          {"default": "grok-video-3 (6秒)"}),
                "aspect_ratio": (["2:3", "3:2", "1:1"], {"default": "3:2"}),
                "size": (["720P", "1080P"], {"default": "720P"}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "api_base": ("STRING", {"default": "https://api.kegeai.top"}),
                "save_dir": ("STRING", {"default": "output/grok", "tooltip": "视频保存目录（相对ComfyUI根目录）"}),
                "max_wait_time": ("INT", {"default": 1200, "min": 60, "max": 3600}),
                "poll_interval": ("INT", {"default": 10, "min": 5, "max": 60}),
                "download_timeout": ("INT", {"default": 1800, "min": 30, "max": 9999}),
                "custom_model": ("STRING", {"default": ""}),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        labels = {"api_key": "API密钥"}
        for i in range(1, N + 1):
            labels[f"prompt_{i}"] = f"提示词 {i}"
            labels[f"image_url_{i}"] = f"图片URL {i}"
        labels.update({
            "model": "模型", "aspect_ratio": "宽高比", "size": "分辨率",
            "enhance_prompt": "提示词增强", "api_base": "API地址",
            "save_dir": "保存目录", "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔", "download_timeout": "下载超时",
            "custom_model": "自定义模型",
        })
        return labels

    RETURN_TYPES = tuple(["STRING"] * N + ["STRING"] * N + ["STRING"])
    RETURN_NAMES = tuple(
        [f"视频URL_{i}" for i in range(1, N + 1)] +
        [f"本地路径_{i}" for i in range(1, N + 1)] +
        ["处理报告"]
    )
    FUNCTION = "run"
    CATEGORY = "KuAi/Grok"

    def run(self, api_key, **kwargs):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置")

        model          = kwargs.get("model", "grok-video-3 (6秒)")
        aspect_ratio   = kwargs.get("aspect_ratio", "3:2")
        size           = kwargs.get("size", "720P")
        enhance_prompt = kwargs.get("enhance_prompt", True)
        api_base       = kwargs.get("api_base", "https://api.kegeai.top")
        save_dir       = kwargs.get("save_dir", "output/grok")
        max_wait_time  = kwargs.get("max_wait_time", 1200)
        poll_interval  = kwargs.get("poll_interval", 10)
        download_timeout = kwargs.get("download_timeout", 180)
        custom_model   = kwargs.get("custom_model", "")

        task_args = []
        for i in range(1, N + 1):
            prompt    = kwargs.get(f"prompt_{i}", "").strip()
            image_url = kwargs.get(f"image_url_{i}", "").strip()
            if prompt and image_url:
                task_args.append((i, prompt, image_url, model, aspect_ratio, size, enhance_prompt,
                                  api_key, api_base, save_dir, max_wait_time,
                                  poll_interval, download_timeout, custom_model))

        if not task_args:
            raise RuntimeError("至少需要填写一条提示词和对应的图片URL")

        print(f"\n{'='*60}")
        print(f"[GrokConcurrent] 开始 {len(task_args)} 路并发图生视频")
        print(f"{'='*60}")

        results, errors = _run_concurrent(_worker_image2video, task_args)

        urls  = [results.get(i, ("", ""))[0] for i in range(1, N + 1)]
        paths = [results.get(i, ("", ""))[1] for i in range(1, N + 1)]
        report = _build_report(results, errors, len(task_args))

        return tuple(urls + paths + [report])


# ─────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────

NODE_CLASS_MAPPINGS = {
    "GrokText2Video10Concurrent": GrokText2Video10Concurrent,
    "GrokImage2Video10Concurrent": GrokImage2Video10Concurrent,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokText2Video10Concurrent": "⚡ Grok 文生视频（10路并发）",
    "GrokImage2Video10Concurrent": "⚡ Grok 图生视频（10路并发）",
}
