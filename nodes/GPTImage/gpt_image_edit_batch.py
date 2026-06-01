"""GPT Image 2 batch image edit node."""

import time
import concurrent.futures

import requests

from ..Sora2.kuai_utils import (
    env_or,
    http_headers_multipart,
    download_public_url_bytes,
)
from .gpt_image import SIZE_MAP, _extract_urls
from .gpt_image_batch import (
    RESULT_COLUMNS,
    _download_image,
    _error_text,
    _input_csv_files,
    _is_retryable,
    _read_csv,
    _resolve_csv_path,
    _write_result_csv,
    _comfy_root,
)

EDIT_IMAGE_URL_COUNT = 16
EDIT_REQUIRED_COLUMNS = ["prompt", "model", "size", "n"]
EDIT_OPTIONAL_DEFAULTS = {
    "format": "png",
    "quality": "auto",
    "background": "auto",
    "moderation": "auto",
}


def _collect_row_image_urls(row: dict) -> list:
    urls = []
    for i in range(1, EDIT_IMAGE_URL_COUNT + 1):
        url = str(row.get(f"image_url_{i}") or "").strip()
        if url:
            urls.append(url)
    return urls


def _post_edit(row: dict, image_urls: list, api_key: str, api_base: str, timeout: int) -> list:
    files = []
    for i, url in enumerate(image_urls):
        content = download_public_url_bytes(url, timeout=timeout, label=f"image_url_{i + 1}")
        files.append(("image[]", (f"image_{i}.png", content, "image/png")))

    form_data = {
        "model": row["model"],
        "prompt": row["prompt"],
        "n": str(row["n"]),
        "size": SIZE_MAP.get(row["size"], row["size"]),
        "format": row["format"],
        "quality": row["quality"],
        "background": row["background"],
        "moderation": row["moderation"],
    }
    resp = requests.post(
        f"{api_base.rstrip('/')}/v1/images/edits",
        files=files,
        data=form_data,
        headers=http_headers_multipart(api_key),
        timeout=timeout,
    )
    if resp.status_code >= 400:
        message = _error_text(resp)
        err = requests.HTTPError(message)
        err.response = resp
        raise err
    return _extract_urls(resp.json())


def _process_one(row_index: int, row: dict, defaults: dict) -> dict:
    output = dict(row)
    output.update({name: "" for name in RESULT_COLUMNS})

    normalized = {}
    for name in EDIT_REQUIRED_COLUMNS:
        normalized[name] = str(row.get(name) or "").strip()
    missing = [name for name, value in normalized.items() if not value]
    if missing:
        output["status"] = "失败"
        output["error_reason"] = f"CSV 缺少必填参数: {', '.join(missing)}"
        return output

    image_urls = _collect_row_image_urls(row)
    if not image_urls:
        output["status"] = "失败"
        output["error_reason"] = "至少需要填写 image_url_1 到 image_url_16 中的一列"
        return output

    for name, default in EDIT_OPTIONAL_DEFAULTS.items():
        normalized[name] = str(row.get(name) or default).strip() or default

    try:
        normalized["n"] = max(1, min(10, int(normalized["n"])))
    except ValueError:
        output["status"] = "失败"
        output["error_reason"] = f"n 不是有效数字: {normalized['n']}"
        return output

    timeout = int(str(row.get("timeout") or defaults["request_timeout"]).strip())
    output_prefix = str(row.get("output_prefix") or f"gpt_image2_edit_{row_index}").strip()
    output_prefix = output_prefix or f"gpt_image2_edit_{row_index}"
    attempts = defaults["retry_count"] + 1
    last_error = ""

    for attempt in range(1, attempts + 1):
        try:
            urls = _post_edit(
                normalized,
                image_urls,
                defaults["api_key"],
                defaults["api_base"],
                timeout,
            )
            local_paths = []
            file_names = []
            for image_index, url in enumerate(urls, start=1):
                local_path, filename = _download_image(
                    url,
                    defaults["save_dir"],
                    output_prefix,
                    image_index,
                    defaults["download_timeout"],
                )
                local_paths.append(local_path)
                file_names.append(filename)

            output["status"] = "成功"
            output["image_urls"] = "\n".join(urls)
            output["local_paths"] = "\n".join(local_paths)
            output["file_names"] = "\n".join(file_names)
            return output
        except Exception as exc:
            last_error = str(exc)
            if attempt >= attempts or not _is_retryable(exc):
                break
            time.sleep(defaults["retry_interval"])

    output["status"] = "失败"
    output["error_reason"] = last_error
    return output


class GPTImage2BatchEdit:
    """GPT Image 2 CSV batch image edit node."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "csv_file": (_input_csv_files(), {
                    "tooltip": "上传或选择 input 目录中的 CSV",
                    "image_upload": True,
                    "editable": True,
                }),
                "csv_path": ("STRING", {"default": "", "tooltip": "CSV 完整路径"}),
                "api_key": ("STRING", {"default": "", "tooltip": "留空使用 KUAI_API_KEY"}),
                "api_base": ("STRING", {"default": "https://ai.kegeai.top"}),
                "save_dir": ("STRING", {"default": "output/gpt_image2_edit_batch"}),
                "batch_size": ("INT", {"default": 10, "min": 1, "max": 20}),
                "request_timeout": ("INT", {"default": 1800, "min": 30, "max": 9999}),
                "download_timeout": ("INT", {"default": 1800, "min": 30, "max": 9999}),
                "retry_count": ("INT", {"default": 3, "min": 0, "max": 10}),
                "retry_interval": ("INT", {"default": 3, "min": 0, "max": 120}),
            },
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "csv_file": "CSV文件",
            "csv_path": "CSV路径",
            "api_key": "API密钥",
            "api_base": "API地址",
            "save_dir": "图片保存目录",
            "batch_size": "并发数",
            "request_timeout": "请求超时",
            "download_timeout": "下载超时",
            "retry_count": "重试次数",
            "retry_interval": "重试间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("处理报告", "结果CSV路径", "图片保存目录", "成功数量", "失败数量")
    FUNCTION = "process"
    CATEGORY = "KuAi/GPTImage"

    def process(self, csv_file="", csv_path="", api_key="", api_base="https://ai.kegeai.top",
                save_dir="output/gpt_image2_edit_batch", batch_size=10, request_timeout=1800,
                download_timeout=1800, retry_count=3, retry_interval=3):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请填写 api_key 或设置 KUAI_API_KEY")

        source = _resolve_csv_path(csv_file, csv_path)
        fieldnames, rows = _read_csv(source)
        total = len(rows)
        defaults = {
            "api_key": api_key,
            "api_base": api_base,
            "save_dir": save_dir,
            "request_timeout": request_timeout,
            "download_timeout": download_timeout,
            "retry_count": retry_count,
            "retry_interval": retry_interval,
        }

        print(f"[GPTImage2BatchEdit] 开始处理 {total} 条任务，并发数 {batch_size}")
        results = []
        for batch_start in range(0, total, batch_size):
            batch = rows[batch_start: batch_start + batch_size]
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
                future_map = {
                    executor.submit(_process_one, batch_start + local_i + 1, row, defaults): batch_start + local_i + 1
                    for local_i, row in enumerate(batch)
                }
                for future in concurrent.futures.as_completed(future_map):
                    results.append(future.result())

        results.sort(key=lambda item: item.get("_row_number", 0))
        _write_result_csv(source, fieldnames, results)

        success = [row for row in results if row.get("status") == "成功"]
        failed = [row for row in results if row.get("status") != "成功"]
        abs_save_dir = str(_comfy_root() / save_dir)
        lines = [
            "GPT-Image2批量编辑图片完成",
            f"总计: {total}",
            f"成功: {len(success)}",
            f"失败: {len(failed)}",
            f"结果CSV: {source}",
            f"图片目录: {abs_save_dir}",
        ]
        if failed:
            lines.append("失败记录:")
            for row in failed:
                lines.append(f"行 {row.get('_row_number', '')}: {row.get('error_reason', '')}")
        report = "\n".join(lines)
        print(report)
        return (report, str(source), abs_save_dir, len(success), len(failed))


NODE_CLASS_MAPPINGS = {
    "GPTImage2BatchEdit": GPTImage2BatchEdit,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GPTImage2BatchEdit": "🖼️ GPT-Image2批量编辑图片",
}
