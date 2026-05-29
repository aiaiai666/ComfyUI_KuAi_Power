"""WAN 视频生成节点集合"""

from .wan import WanCreateAndWait

NODE_CLASS_MAPPINGS = {
    "WanCreateAndWait": WanCreateAndWait,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WanCreateAndWait": "⚡ WAN 一键生视频",
}
