"""Gemini 图片和视频理解节点"""

import os
import io
import json
import tempfile
import requests

from ..Sora2.kuai_utils import (
    env_or,
    to_pil_from_comfy,
    pil_to_base64,
    file_to_base64,
    extract_gemini_text_from_response,
    extract_error_message_from_response,
)


def _save_video_input_to_temp_file(video_input):
    """将 ComfyUI VIDEO 输入保存为临时文件并返回路径"""
    temp_path = None

    # 优先使用 get_stream_source（VideoFromFile）
    if hasattr(video_input, "get_stream_source") and callable(getattr(video_input, "get_stream_source")):
        src = video_input.get_stream_source()
        if isinstance(src, str) and os.path.exists(src):
            return src, False
        if isinstance(src, io.BytesIO):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
                src.seek(0)
                tmp.write(src.read())
                temp_path = tmp.name
            return temp_path, True

    # 兜底：使用 save_to 导出到临时文件（VideoInput 通用能力）
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

    raise RuntimeError("无法从 VIDEO 输入解析视频文件，请检查上游节点输出")


class GeminiImageUnderstanding:
    """Gemini 图片理解节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "tooltip": "输入图片"
                }),
                "prompt": ("STRING", {
                    "default": "请描述这张图片的内容",
                    "multiline": True,
                    "tooltip": "对图片的提问"
                }),
                "model": ([
                    "gemini-3.1-pro-preview",
                    "gemini-3-pro-preview",
                    "gemini-3-flash-preview",
                    "gemini-3-pro-preview-thinking",
                    "gemini-2.5-pro",
                    "gemini-2.5-flash"
                ], {
                    "default": "gemini-3.1-pro-preview",
                    "tooltip": "选择 Gemini 模型"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用上方下拉框模型）"
                }),
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "timeout": ("INT", {
                    "default": 120,
                    "min": 30,
                    "max": 6000,
                    "tooltip": "请求超时时间（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "image": "图片",
            "prompt": "提示词",
            "model": "模型",
            "api_key": "API密钥",
            "custom_model": "自定义模型",
            "api_base": "API地址",
            "timeout": "超时时间"
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("理解结果",)
    FUNCTION = "understand_image"
    CATEGORY = "KuAi/Gemini"

    def understand_image(self, image, prompt, model, api_key="", custom_model="", api_base="https://ai.kegeai.top", timeout=120):
        """理解图片内容"""
        try:
            # 获取 API Key
            api_key = env_or(api_key, "KUAI_API_KEY")
            if not api_key:
                raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

            # 确定使用的模型（custom_model 优先）
            effective_model = (custom_model or "").strip() or model

            # 转换图片为 base64
            pil_image = to_pil_from_comfy(image, index=0)
            image_base64 = pil_to_base64(pil_image, fmt="PNG")

            # 构建请求
            api_base = api_base.rstrip("/")
            url = f"{api_base}/v1beta/models/{effective_model}:generateContent"

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": image_base64
                                }
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "responseModalities": ["TEXT"]
                }
            }

            print(f"[ComfyUI_KuAi_Power] Gemini 图片理解: {prompt[:50]}...")

            # 调用 API
            resp = requests.post(
                url,
                params={"key": api_key},
                json=payload,
                timeout=timeout
            )

            if resp.status_code >= 400:
                error_msg = extract_error_message_from_response(resp)
                raise RuntimeError(f"Gemini 图片理解失败 (HTTP {resp.status_code}): {error_msg}")

            result = resp.json()

            # 提取文本结果
            text_result = extract_gemini_text_from_response(result)

            if not text_result:
                raise RuntimeError(f"Gemini 返回结果为空: {json.dumps(result, ensure_ascii=False)}")

            print(f"[ComfyUI_KuAi_Power] Gemini 图片理解完成，结果长度: {len(text_result)}")

            return (text_result,)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Gemini 图片理解失败: {str(e)}")


class GeminiVideoUnderstanding:
    """Gemini 视频理解节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO", {
                    "tooltip": "输入视频（可连接 ComfyUI 的加载视频节点）"
                }),
                "prompt": ("STRING", {
                    "default": "请用3句话总结这个视频的内容",
                    "multiline": True,
                    "tooltip": "对视频的提问"
                }),
                "model": ([
                    "gemini-3.1-pro-preview",
                    "gemini-3-pro-preview",
                    "gemini-3-flash-preview",
                    "gemini-3-pro-preview-thinking",
                    "gemini-2.5-pro",
                    "gemini-2.5-flash"
                ], {
                    "default": "gemini-3.1-pro-preview",
                    "tooltip": "选择 Gemini 模型"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "video_path": ("STRING", {
                    "default": "",
                    "tooltip": "视频文件路径（兼容旧工作流，优先使用 video 输入）"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用上方下拉框模型）"
                }),
                "api_base": ("STRING", {
                    "default": "https://ai.kegeai.top",
                    "tooltip": "API端点地址"
                }),
                "timeout": ("INT", {
                    "default": 300,
                    "min": 60,
                    "max": 6000,
                    "tooltip": "请求超时时间（秒）"
                }),
                "max_wait_time": ("INT", {
                    "default": 1200,
                    "min": 60,
                    "max": 3600,
                    "tooltip": "最大等待时间（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "video": "视频",
            "video_path": "视频路径",
            "prompt": "提示词",
            "model": "模型",
            "api_key": "API密钥",
            "custom_model": "自定义模型",
            "api_base": "API地址",
            "timeout": "超时时间",
            "max_wait_time": "最大等待时间"
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("理解结果",)
    FUNCTION = "understand_video"
    CATEGORY = "KuAi/Gemini"

    def understand_video(self, video, prompt, model, api_key="", video_path="", custom_model="", api_base="https://ai.kegeai.top", timeout=300, max_wait_time=1200):
        """理解视频内容"""
        temp_video_path = None
        cleanup_temp = False
        try:
            # 获取 API Key
            api_key = env_or(api_key, "KUAI_API_KEY")
            if not api_key:
                raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

            # 确定使用的模型（custom_model 优先）
            effective_model = (custom_model or "").strip() or model

            # 优先使用 VIDEO 输入，兼容旧版 video_path
            resolved_video_path = ""
            if video is not None:
                resolved_video_path, cleanup_temp = _save_video_input_to_temp_file(video)
                temp_video_path = resolved_video_path if cleanup_temp else None
            elif (video_path or "").strip():
                resolved_video_path = video_path.strip()
                if not os.path.exists(resolved_video_path):
                    raise RuntimeError(f"视频文件不存在: {resolved_video_path}")
            else:
                raise RuntimeError("请连接视频输入或提供视频路径")

            # 转换视频为 base64
            print(f"[ComfyUI_KuAi_Power] 正在读取视频文件: {resolved_video_path}")
            video_base64 = file_to_base64(resolved_video_path)

            # 构建请求
            api_base = api_base.rstrip("/")
            url = f"{api_base}/v1beta/models/{effective_model}:generateContent"

            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "video/mp4",
                                    "data": video_base64
                                }
                            },
                            {
                                "text": prompt
                            }
                        ]
                    }
                ]
            }

            print(f"[ComfyUI_KuAi_Power] Gemini 视频理解: {prompt[:50]}...")

            # 调用 API
            resp = requests.post(
                url,
                params={"key": api_key},
                json=payload,
                timeout=timeout
            )

            if resp.status_code >= 400:
                error_msg = extract_error_message_from_response(resp)
                raise RuntimeError(f"Gemini 视频理解失败 (HTTP {resp.status_code}): {error_msg}")

            result = resp.json()

            # 提取文本结果
            text_result = extract_gemini_text_from_response(result)

            if not text_result:
                raise RuntimeError(f"Gemini 返回结果为空: {json.dumps(result, ensure_ascii=False)}")

            print(f"[ComfyUI_KuAi_Power] Gemini 视频理解完成，结果长度: {len(text_result)}")

            return (text_result,)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Gemini 视频理解失败: {str(e)}")
        finally:
            if cleanup_temp and temp_video_path and os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                except Exception:
                    pass

