"""Gemini 节点集合"""

from .gemini_understanding import GeminiImageUnderstanding, GeminiVideoUnderstanding

NODE_CLASS_MAPPINGS = {
    "GeminiImageUnderstanding": GeminiImageUnderstanding,
    "GeminiVideoUnderstanding": GeminiVideoUnderstanding,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GeminiImageUnderstanding": "🔍 Gemini 图片理解",
    "GeminiVideoUnderstanding": "🎬 Gemini 视频理解",
}
