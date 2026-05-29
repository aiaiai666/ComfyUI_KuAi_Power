"""HappyHorse 视频生成节点集合"""

from .happyhorse import (
    HappyHorseI2VAndWait,
    HappyHorseQueryTask,
    HappyHorseR2VAndWait,
    HappyHorseT2VAndWait,
    HappyHorseVideoAndWait,
    HappyHorseVideoCreate,
)


NODE_CLASS_MAPPINGS = {
    "HappyHorseVideoCreate": HappyHorseVideoCreate,
    "HappyHorseQueryTask": HappyHorseQueryTask,
    "HappyHorseVideoAndWait": HappyHorseVideoAndWait,
    "HappyHorseI2VAndWait": HappyHorseI2VAndWait,
    "HappyHorseR2VAndWait": HappyHorseR2VAndWait,
    "HappyHorseT2VAndWait": HappyHorseT2VAndWait,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "HappyHorseVideoCreate": "🐎 HappyHorse 创建视频",
    "HappyHorseQueryTask": "🔍 HappyHorse 查询任务",
    "HappyHorseVideoAndWait": "⚡ HappyHorse 一键生视频",
    "HappyHorseI2VAndWait": "🖼️ HappyHorse 图生视频 i2v",
    "HappyHorseR2VAndWait": "🖼️ HappyHorse 参考生视频 r2v",
    "HappyHorseT2VAndWait": "🎬 HappyHorse 文生视频 t2v",
}
