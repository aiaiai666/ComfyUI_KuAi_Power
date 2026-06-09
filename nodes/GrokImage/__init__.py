from .grok_image import GrokImageGenerate, GrokImageEdit
from .grok_image_video import GrokImageVideoGenerate

NODE_CLASS_MAPPINGS = {
    "GrokImageGenerate": GrokImageGenerate,
    "GrokImageEdit": GrokImageEdit,
    "GrokImageVideoGenerate": GrokImageVideoGenerate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokImageGenerate": "🖼️ Grok-image文生图",
    "GrokImageEdit": "🎨 Grok-image图片编辑",
    "GrokImageVideoGenerate": "🎬 grok-image视频生成",
}
