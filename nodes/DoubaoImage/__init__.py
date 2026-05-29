"""Doubao image generation and editing nodes."""

from .doubao_image import DoubaoImageEdit, DoubaoImageGenerate, DoubaoImageGenerateEdit


NODE_CLASS_MAPPINGS = {
    "DoubaoImageGenerateEdit": DoubaoImageGenerateEdit,
    "DoubaoImageGenerate": DoubaoImageGenerate,
    "DoubaoImageEdit": DoubaoImageEdit,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DoubaoImageGenerateEdit": "豆包图片生成/编辑",
    "DoubaoImageGenerate": "豆包图片生成",
    "DoubaoImageEdit": "豆包图片编辑",
}
