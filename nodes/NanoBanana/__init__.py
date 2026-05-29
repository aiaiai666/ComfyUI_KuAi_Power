"""Nano Banana 节点 - 基于 kuai.host API"""

from .nano_banana import NanoBananaAIO, NanoBananaMultiTurnChat
from .batch_processor import NanoBananaBatchProcessor

NODE_CLASS_MAPPINGS = {
    "NanoBananaAIO": NanoBananaAIO,
    "NanoBananaMultiTurnChat": NanoBananaMultiTurnChat,
    "NanoBananaBatchProcessor": NanoBananaBatchProcessor
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NanoBananaAIO": "🍌 Nano Banana Pro 多功能",
    "NanoBananaMultiTurnChat": "🍌 Nano Banana 多轮对话",
    "NanoBananaBatchProcessor": "📦 NanoBanana 批量处理器"
}
