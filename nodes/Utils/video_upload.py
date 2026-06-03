import io
import json
import mimetypes
import os
import requests
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote

# 添加父目录到路径以导入 utils
parent_dir = Path(__file__).parent.parent / "Sora2"
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from kuai_utils import (
        http_headers_multipart,
        extract_error_message_from_json,
        extract_error_message_from_response,
        validate_public_http_url,
    )
except ImportError:
    import importlib.util
    utils_path = parent_dir / "kuai_utils.py"
    spec = importlib.util.spec_from_file_location("kuai_utils", utils_path)
    utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(utils)
    http_headers_multipart = utils.http_headers_multipart
    extract_error_message_from_json = utils.extract_error_message_from_json
    extract_error_message_from_response = utils.extract_error_message_from_response
    validate_public_http_url = utils.validate_public_http_url

try:
    import folder_paths
    HAS_FOLDER_PATHS = True
except ImportError:
    HAS_FOLDER_PATHS = False
    print("[UploadVideoToHost] 警告: folder_paths 模块不可用，文件上传下拉功能将受限")


SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".wmv",
    ".m4v",
    ".mpeg",
    ".mpg",
    ".webm",
    ".avi",
    ".mkv",
}
MAX_VIDEO_UPLOAD_BYTES = 50 * 1024 * 1024


def _input_directory():
    return Path(folder_paths.get_input_directory()).resolve()


def _ensure_input_child(path):
    resolved = Path(path).resolve()
    if HAS_FOLDER_PATHS:
        input_dir = _input_directory()
        try:
            resolved.relative_to(input_dir)
        except ValueError:
            raise RuntimeError("视频文件必须位于 ComfyUI input 目录内")
    return resolved


def _save_video_input_to_temp_file(video_input):
    """将 ComfyUI VIDEO 输入保存为临时文件并返回路径"""
    temp_path = None

    if hasattr(video_input, "get_stream_source") and callable(getattr(video_input, "get_stream_source")):
        src = video_input.get_stream_source()
        if isinstance(src, str) and os.path.exists(src):
            return str(_ensure_input_child(src)), False
        if isinstance(src, io.BytesIO):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                src.seek(0)
                tmp.write(src.read())
                temp_path = tmp.name
            return temp_path, True

    if hasattr(video_input, "save_to") and callable(getattr(video_input, "save_to")):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
            temp_path = tmp.name
        try:
            video_input.save_to(temp_path)
            return temp_path, True
        except Exception:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    raise RuntimeError("无法从 VIDEO 输入解析视频文件，请检查上游“加载视频”节点输出")


class UploadVideoToHost:
    """上传视频到临时图床/文件托管，返回视频URL"""

    @classmethod
    def INPUT_TYPES(cls):
        video_files = []
        if HAS_FOLDER_PATHS:
            try:
                input_dir = folder_paths.get_input_directory()
                if os.path.exists(input_dir):
                    video_files = sorted([
                        f for f in os.listdir(input_dir)
                        if Path(f).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
                    ])
            except Exception as e:
                print(f"[UploadVideoToHost] 无法读取 input 目录: {e}")

        return {
            "required": {},
            "optional": {
                "video": ("VIDEO", {
                    "tooltip": "可连接 ComfyUI 的“加载视频”节点输出"
                }),
                "video_select": (video_files if video_files else [""], {
                    "tooltip": "从 input 目录选择视频文件"
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "或输入完整视频文件路径"
                }),
                "upload_url": ("STRING", {
                    "default": "https://imageproxy.zhongzhuan.chat/api/upload",
                    "tooltip": "临时图床上传API地址"
                }),
                "timeout": ("INT", {
                    "default": 1800,
                    "min": 1,
                    "max": 9999,
                    "tooltip": "超时时间(秒)"
                }),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(cls, video=None, video_select="", video_path="", upload_url="", timeout=1800):
        return True

    INPUT_IS_LIST = False
    OUTPUT_NODE = False

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("视频URL", "创建时间")
    FUNCTION = "upload"
    CATEGORY = "KuAi/配套能力"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "video": "视频",
            "video_select": "视频文件",
            "video_path": "文件路径",
            "upload_url": "图床URL",
            "timeout": "超时",
        }

    @classmethod
    def IS_CHANGED(cls, *args, **kwargs):
        return time.time_ns()

    @staticmethod
    def _resolve_video_path(video_select="", video_path=""):
        if video_select and str(video_select).strip():
            if not HAS_FOLDER_PATHS:
                raise RuntimeError("folder_paths 模块不可用，请使用 video_path 参数")
            path = _ensure_input_child(_input_directory() / str(video_select).strip())
            if not path.exists():
                raise RuntimeError(f"视频文件不存在: {video_select}")
            return str(path)

        clean_path = (video_path or "").strip()
        if not clean_path:
            raise RuntimeError("请提供视频文件（video_select 或 video_path）")

        path = Path(clean_path)
        if HAS_FOLDER_PATHS:
            if not path.is_absolute():
                path = _input_directory() / path
            path = _ensure_input_child(path)
        else:
            path = path.resolve()

        if not path.exists():
            raise RuntimeError(f"视频文件不存在: {path}")
        return str(path)

    @staticmethod
    def _guess_video_mime(file_path):
        lower = file_path.lower()
        if lower.endswith(".mp4") or lower.endswith(".m4v"):
            return "video/mp4"
        if lower.endswith(".mov"):
            return "video/quicktime"
        if lower.endswith(".wmv"):
            return "video/x-ms-wmv"
        if lower.endswith(".webm"):
            return "video/webm"
        if lower.endswith(".avi"):
            return "video/x-msvideo"
        if lower.endswith(".mkv"):
            return "video/x-matroska"
        if lower.endswith(".mpeg") or lower.endswith(".mpg"):
            return "video/mpeg"
        guessed, _ = mimetypes.guess_type(file_path)
        return guessed or "application/octet-stream"

    @staticmethod
    def _validate_video_size(file_path):
        size = os.path.getsize(file_path)
        if size > MAX_VIDEO_UPLOAD_BYTES:
            max_mb = MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)
            actual_mb = size / (1024 * 1024)
            raise RuntimeError(f"视频文件超过 {max_mb}MB，当前约 {actual_mb:.2f}MB，请压缩后再上传")

    @staticmethod
    def _extract_uploaded_url(data):
        if not isinstance(data, dict):
            return ""

        direct = str(
            data.get("url")
            or data.get("download_url")
            or data.get("downloadLink")
            or data.get("downloadLinkEncoded")
            or ""
        ).strip()
        if direct:
            if "downloadLinkEncoded" in data and direct == str(data.get("downloadLinkEncoded") or "").strip():
                try:
                    direct = unquote(direct)
                except Exception:
                    pass
            return direct

        nested = data.get("data")
        if isinstance(nested, dict):
            nested_url = str(
                nested.get("url")
                or nested.get("download_url")
                or nested.get("downloadLink")
                or nested.get("downloadLinkEncoded")
                or ""
            ).strip()
            if nested_url:
                if "downloadLinkEncoded" in nested and nested_url == str(nested.get("downloadLinkEncoded") or "").strip():
                    try:
                        nested_url = unquote(nested_url)
                    except Exception:
                        pass
                if "tmpfiles.org/" in nested_url and "/dl/" not in nested_url:
                    return nested_url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)
                return nested_url

        return ""

    @staticmethod
    def _extract_upload_error(data):
        if not isinstance(data, dict):
            return ""

        status = str(data.get("status") or "").strip().lower()
        if status in {"error", "failed", "failure", "fail"}:
            return extract_error_message_from_json(data) or json.dumps(data, ensure_ascii=False)

        success = data.get("success")
        if success is False:
            return extract_error_message_from_json(data) or json.dumps(data, ensure_ascii=False)

        code = data.get("code")
        if code not in (None, 0, 200, "0", "200"):
            return extract_error_message_from_json(data) or f"服务器返回错误码: {code}"

        error = data.get("error")
        if error:
            return extract_error_message_from_json(data) or str(error)

        return ""

    def upload(self, video=None, video_select="", video_path="", upload_url="https://imageproxy.zhongzhuan.chat/api/upload", timeout=1800):
        temp_video_path = None
        cleanup_temp = False
        try:
            upload_url = validate_public_http_url(upload_url, "视频上传URL")
            if video is not None:
                file_path, cleanup_temp = _save_video_input_to_temp_file(video)
                temp_video_path = file_path if cleanup_temp else None
            else:
                file_path = self._resolve_video_path(video_select=video_select, video_path=video_path)

            ext = Path(file_path).suffix.lower()
            if ext not in SUPPORTED_VIDEO_EXTENSIONS:
                supported = ", ".join(sorted(SUPPORTED_VIDEO_EXTENSIONS))
                raise RuntimeError(f"仅支持常见视频格式 {supported}，当前文件: {file_path}")
            self._validate_video_size(file_path)

            mime = self._guess_video_mime(file_path)
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, mime)}
                try:
                    resp = requests.post(
                        upload_url,
                        headers=http_headers_multipart(),
                        files=files,
                        timeout=int(timeout)
                    )
                    if resp.status_code >= 400:
                        detail = extract_error_message_from_response(resp)
                        raise RuntimeError(f"视频上传失败: {detail}")
                    try:
                        data = resp.json()
                    except Exception as e:
                        text = str(getattr(resp, "text", "") or "").strip()
                        detail = text or str(e)
                        raise RuntimeError(f"视频上传失败: 服务器返回非 JSON: {detail}")
                except RuntimeError:
                    raise
                except Exception as e:
                    raise RuntimeError(f"视频上传失败: {str(e)}")

            server_error = self._extract_upload_error(data)
            if server_error:
                raise RuntimeError(f"视频上传失败: {server_error}")

            url = self._extract_uploaded_url(data)
            created = str(data.get("created") or "")
            if not url:
                raise RuntimeError(f"上传响应缺少可用 URL 字段: {json.dumps(data, ensure_ascii=False)}")

            return (url, created)
        finally:
            if cleanup_temp and temp_video_path and os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                except Exception:
                    pass


NODE_CLASS_MAPPINGS = {
    "UploadVideoToHost": UploadVideoToHost,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UploadVideoToHost": "传视频到临时图床",
}
