"""可灵视频生成节点"""

from .kling import (
    KlingText2Video,
    KlingImage2Video,
    KlingQueryTask,
    KlingText2VideoAndWait,
    KlingImage2VideoAndWait,
)
from .batch_processor import KlingBatchProcessor

NODE_CLASS_MAPPINGS = {
    "KlingText2Video": KlingText2Video,
    "KlingImage2Video": KlingImage2Video,
    "KlingQueryTask": KlingQueryTask,
    "KlingText2VideoAndWait": KlingText2VideoAndWait,
    "KlingImage2VideoAndWait": KlingImage2VideoAndWait,
    "KlingBatchProcessor": KlingBatchProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KlingText2Video": "🎞️ 可灵文生视频",
    "KlingImage2Video": "🎞️ 可灵图生视频",
    "KlingQueryTask": "🔍 可灵查询任务",
    "KlingText2VideoAndWait": "⚡ 可灵文生视频（一键）",
    "KlingImage2VideoAndWait": "⚡ 可灵图生视频（一键）",
    "KlingBatchProcessor": "📦 可灵批量处理",
}
