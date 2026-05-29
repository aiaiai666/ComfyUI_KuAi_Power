"""文本显示节点"""


class ShowText:
    """显示文本内容的节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {
                    "forceInput": True,
                    "tooltip": "要显示的文本内容"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "text": "文本",
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("文本",)
    FUNCTION = "show"
    CATEGORY = "KuAi/Utils"
    OUTPUT_NODE = True

    def show(self, text):
        """显示文本"""
        # 兼容不同前端/主题对 UI 字段名的处理差异
        # 同时返回 string 与 text，确保在 ComfyUI 中可见
        return {"ui": {"string": [text], "text": [text]}, "result": (text,)}


NODE_CLASS_MAPPINGS = {
    "ShowText": ShowText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ShowText": "📄 显示文本",
}
