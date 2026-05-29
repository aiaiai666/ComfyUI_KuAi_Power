import io
import json
import mimetypes
import os
import requests
import sys
import wave
from pathlib import Path
from urllib.parse import unquote

import numpy as np

# 添加父目录到路径以导入 utils
parent_dir = Path(__file__).parent.parent / "Sora2"
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from kuai_utils import http_headers_multipart, extract_error_message_from_response
except ImportError:
    import importlib.util
    utils_path = parent_dir / "kuai_utils.py"
    spec = importlib.util.spec_from_file_location("kuai_utils", utils_path)
    utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(utils)
    http_headers_multipart = utils.http_headers_multipart
    extract_error_message_from_response = utils.extract_error_message_from_response

# 尝试导入 ComfyUI 的 folder_paths
try:
    import folder_paths
    HAS_FOLDER_PATHS = True
except ImportError:
    HAS_FOLDER_PATHS = False
    print("[UploadAudioToHost] 警告: folder_paths 模块不可用，文件上传下拉功能将受限")


class UploadAudioToHost:
    """上传音频到临时图床/文件托管，返回音频URL"""

    @classmethod
    def INPUT_TYPES(cls):
        audio_files = []
        if HAS_FOLDER_PATHS:
            try:
                input_dir = folder_paths.get_input_directory()
                if os.path.exists(input_dir):
                    audio_files = sorted([
                        f for f in os.listdir(input_dir)
                        if f.lower().endswith((".mp3", ".wav"))
                    ])
            except Exception as e:
                print(f"[UploadAudioToHost] 无法读取 input 目录: {e}")

        return {
            "required": {},
            "optional": {
                "audio_file": ("AUDIO", {
                    "tooltip": "可接入“加载音频”的输出“音频”"
                }),
                "audio_select": (audio_files if audio_files else [""], {
                    "tooltip": "从 input 目录选择 mp3/wav 文件"
                }),
                "audio_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "tooltip": "或输入完整音频文件路径（mp3/wav）"
                }),
                "upload_url": ("STRING", {
                    "default": "https://tmpfile.link/api/upload",
                    "tooltip": "上传API地址（需支持音频文件）"
                }),
                "timeout": ("INT", {
                    "default": 30,
                    "min": 1,
                    "max": 300,
                    "tooltip": "超时时间(秒)"
                }),
            }
        }

    @classmethod
    def VALIDATE_INPUTS(cls, audio_file=None, audio_select="", audio_path="", upload_url="", timeout=30):
        return True

    INPUT_IS_LIST = False
    OUTPUT_NODE = False

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("音频URL", "创建时间")
    FUNCTION = "upload"
    CATEGORY = "KuAi/配套能力"

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "audio_file": "音频",
            "audio_select": "音频文件",
            "audio_path": "文件路径",
            "upload_url": "上传URL",
            "timeout": "超时",
        }

    @staticmethod
    def _audio_to_wav_buffer(audio_file):
        if not isinstance(audio_file, dict):
            raise RuntimeError("音频输入格式无效，期望来自“加载音频”节点的 AUDIO 数据")

        waveform = audio_file.get("waveform")
        sample_rate = int(audio_file.get("sample_rate") or 0)
        if waveform is None or sample_rate <= 0:
            raise RuntimeError("音频输入缺少 waveform 或 sample_rate")

        if hasattr(waveform, "detach"):
            arr = waveform.detach().cpu().numpy()
        else:
            arr = np.asarray(waveform)

        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim == 1:
            arr = arr[:, np.newaxis]
        elif arr.ndim == 2:
            if arr.shape[0] <= 8 and arr.shape[1] > arr.shape[0]:
                arr = arr.T
        else:
            raise RuntimeError(f"不支持的音频维度: {arr.shape}")

        arr = np.clip(arr, -1.0, 1.0)
        pcm16 = (arr * 32767.0).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(int(pcm16.shape[1]))
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm16.tobytes())
        buf.seek(0)
        return buf

    @staticmethod
    def _resolve_audio_path(audio_select="", audio_path=""):
        if audio_select and str(audio_select).strip():
            if not HAS_FOLDER_PATHS:
                raise RuntimeError("folder_paths 模块不可用，请使用 audio_path 参数")
            input_dir = folder_paths.get_input_directory()
            path = os.path.join(input_dir, str(audio_select).strip())
            if not os.path.exists(path):
                raise RuntimeError(f"音频文件不存在: {audio_select}")
            return path

        path = (audio_path or "").strip()
        if not path:
            raise RuntimeError("请提供音频（audio_file、audio_select 或 audio_path）")

        if not os.path.isabs(path) and HAS_FOLDER_PATHS:
            input_dir = folder_paths.get_input_directory()
            candidate = os.path.join(input_dir, path)
            if os.path.exists(candidate):
                path = candidate

        if not os.path.exists(path):
            raise RuntimeError(f"音频文件不存在: {path}")
        return path

    @staticmethod
    def _guess_audio_mime(file_path):
        lower = file_path.lower()
        if lower.endswith(".mp3"):
            return "audio/mpeg"
        if lower.endswith(".wav"):
            return "audio/wav"
        guessed, _ = mimetypes.guess_type(file_path)
        return guessed or "application/octet-stream"

    @staticmethod
    def _extract_uploaded_url(upload_url, data):
        """兼容不同上传服务返回格式，提取可访问 URL"""
        if not isinstance(data, dict):
            return ""

        # 通用字段
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

        # 常见嵌套字段（tmpfiles / tmpfile.link 等）
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
                # tmpfiles 站内链接转换为直链下载链接
                if "tmpfiles.org/" in nested_url and "/dl/" not in nested_url:
                    return nested_url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)
                return nested_url

        return ""

    def upload(self, audio_file=None, audio_select="", audio_path="", upload_url="https://tmpfile.link/api/upload", timeout=30):
        files = None

        if audio_file is not None:
            wav_buf = self._audio_to_wav_buffer(audio_file)
            files = {
                "file": ("audio.wav", wav_buf, "audio/wav")
            }
        else:
            file_path = self._resolve_audio_path(audio_select=audio_select, audio_path=audio_path)
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in {".mp3", ".wav"}:
                raise RuntimeError(f"仅支持 mp3/wav 格式，当前文件: {file_path}")
            mime = self._guess_audio_mime(file_path)
            f = open(file_path, "rb")
            try:
                files = {"file": (os.path.basename(file_path), f, mime)}
                resp = requests.post(
                    upload_url,
                    headers=http_headers_multipart(),
                    files=files,
                    timeout=int(timeout)
                )
            finally:
                f.close()

            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"音频上传失败: {detail}")

            data = resp.json()
            url = self._extract_uploaded_url(upload_url, data)
            created = str(data.get("created") or "")
            if not url:
                raise RuntimeError(f"上传响应缺少可用 URL 字段: {json.dumps(data, ensure_ascii=False)}")
            return (url, created)

        try:
            resp = requests.post(
                upload_url,
                headers=http_headers_multipart(),
                files=files,
                timeout=int(timeout)
            )

            if resp.status_code >= 400:
                detail = extract_error_message_from_response(resp)
                raise RuntimeError(f"音频上传失败: {detail}")

            data = resp.json()
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"音频上传失败: {str(e)}")

        url = self._extract_uploaded_url(upload_url, data)
        created = str(data.get("created") or "")
        if not url:
            raise RuntimeError(f"上传响应缺少可用 URL 字段: {json.dumps(data, ensure_ascii=False)}")

        return (url, created)


NODE_CLASS_MAPPINGS = {
    "UploadAudioToHost": UploadAudioToHost,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "UploadAudioToHost": "🎵 上传音频到图床",
}
