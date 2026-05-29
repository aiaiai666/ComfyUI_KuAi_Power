from .grok_image import GrokImageGenerate, GrokImageEdit

NODE_CLASS_MAPPINGS = {
    "GrokImageGenerate": GrokImageGenerate,
    "GrokImageEdit": GrokImageEdit,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GrokImageGenerate": "🖼️ Grok-image文生图",
    "GrokImageEdit": "🎨 Grok-image图片编辑",
}
