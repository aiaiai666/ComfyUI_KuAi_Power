from .gpt_image import GPTImage2Generate, GPTImage2Edit
from .gpt_image_batch import GPTImage2BatchTextGenerate
from .gpt_image_edit_batch import GPTImage2BatchEdit

try:
    from .gpt_image_2_all import GPTImage2AllGenerate, GPTImage2AllEdit
except ImportError:
    GPTImage2AllGenerate = None
    GPTImage2AllEdit = None

NODE_CLASS_MAPPINGS = {
    "GPTImage2Generate": GPTImage2Generate,
    "GPTImage2Edit": GPTImage2Edit,
    "GPTImage2BatchTextGenerate": GPTImage2BatchTextGenerate,
    "GPTImage2BatchEdit": GPTImage2BatchEdit,
    **({
        "GPTImage2AllGenerate": GPTImage2AllGenerate,
        "GPTImage2AllEdit": GPTImage2AllEdit,
    } if GPTImage2AllGenerate and GPTImage2AllEdit else {}),
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GPTImage2Generate": "🖼️ GPT Image 2 文生图",
    "GPTImage2Edit": "🖼️ GPT Image 2 图片编辑",
    "GPTImage2BatchTextGenerate": "🖼️ GPT-Image2批量文生图",
    "GPTImage2BatchEdit": "🖼️ GPT-Image2批量编辑图片",
    **({
        "GPTImage2AllGenerate": "🖼️ gpt-image-2-all生图",
        "GPTImage2AllEdit": "🖼️ gpt-image-2-all编辑图",
    } if GPTImage2AllGenerate and GPTImage2AllEdit else {}),
}
