"""批量图片上传节点 - 从本地目录读取图片并上传获取URL"""

import os
import json
import requests
from pathlib import Path
from PIL import Image
import io

# 导入工具函数
import sys
parent_dir = Path(__file__).parent.parent / "Sora2"
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

try:
    from kuai_utils import http_headers_multipart, extract_error_message_from_response
except ImportError:
    import importlib.util
    utils_path = parent_dir / "kuai_utils.py"
    spec = importlib.util.spec_from_file_location("kuai_utils", utils_path)
    utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(utils)
    http_headers_multipart = utils.http_headers_multipart
    extract_error_message_from_response = utils.extract_error_message_from_response


class BatchImageUploader:
    """批量上传本地目录中的图片到图床"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "directory_path": ("STRING", {
                    "default": "/root/ComfyUI/input/grok/demo1",
                    "multiline": False,
                    "tooltip": "图片目录的完整路径（例如：/root/ComfyUI/input/grok/demo1）"
                }),
            },
            "optional": {
                "upload_url": ("STRING", {
                    "default": "https://imageproxy.zhongzhuan.chat/api/upload",
                    "tooltip": "图床API地址"
                }),
                "format": (["jpeg", "png", "webp"], {
                    "default": "jpeg",
                    "tooltip": "上传图片格式"
                }),
                "quality": ("INT", {
                    "default": 90,
                    "min": 1,
                    "max": 100,
                    "tooltip": "图片质量(1-100)"
                }),
                "timeout": ("INT", {
                    "default": 30,
                    "min": 1,
                    "max": 1200,
                    "tooltip": "单个图片上传超时时间(秒)"
                }),
                "max_images": ("INT", {
                    "default": 100,
                    "min": 1,
                    "max": 1000,
                    "tooltip": "最大上传图片数量"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "directory_path": "图片目录路径",
            "upload_url": "图床URL",
            "format": "格式",
            "quality": "质量",
            "timeout": "超时",
            "max_images": "最大数量",
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("图片URL列表", "上传详情", "成功数量")
    FUNCTION = "batch_upload"
    CATEGORY = "KuAi/Utils"

    def batch_upload(self, directory_path, upload_url="https://imageproxy.zhongzhuan.chat/api/upload",
                    format="jpeg", quality=90, timeout=30, max_images=100):
        """批量上传目录中的图片"""

        # 构建完整路径
        full_path = Path(directory_path.strip())

        if not full_path.exists():
            raise RuntimeError(f"目录不存在: {full_path}")

        if not full_path.is_dir():
            raise RuntimeError(f"路径不是目录: {full_path}")

        print(f"[ComfyUI_KuAi_Power] 批量上传图片: {full_path}")

        # 查找所有图片文件（支持常见格式）
        image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif'}
        image_files = []

        for file_path in sorted(full_path.iterdir()):
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                image_files.append(file_path)

        if not image_files:
            raise RuntimeError(f"目录中没有找到图片文件: {full_path}")

        # 限制数量
        if len(image_files) > max_images:
            print(f"[ComfyUI_KuAi_Power] 警告：找到 {len(image_files)} 个图片，限制为 {max_images} 个")
            image_files = image_files[:max_images]

        print(f"[ComfyUI_KuAi_Power] 找到 {len(image_files)} 个图片文件")

        # 批量上传
        uploaded_urls = []
        upload_details = []
        success_count = 0
        failed_count = 0

        for idx, image_path in enumerate(image_files, start=1):
            try:
                print(f"[ComfyUI_KuAi_Power] 上传 {idx}/{len(image_files)}: {image_path.name}")

                # 读取并转换图片
                pil_image = Image.open(image_path)

                # 转换为RGB（如果需要）
                if pil_image.mode not in ('RGB', 'RGBA'):
                    pil_image = pil_image.convert('RGB')

                # 保存到内存缓冲区
                buf = io.BytesIO()
                save_format = format.upper()
                if save_format == 'JPEG':
                    # JPEG 不支持透明度
                    if pil_image.mode == 'RGBA':
                        # 创建白色背景
                        background = Image.new('RGB', pil_image.size, (255, 255, 255))
                        background.paste(pil_image, mask=pil_image.split()[3])
                        pil_image = background
                    pil_image.save(buf, format='JPEG', quality=quality)
                else:
                    pil_image.save(buf, format=save_format, quality=quality)

                buf.seek(0)

                # 上传
                files = {
                    "file": (
                        f"{image_path.stem}.{'jpg' if format=='jpeg' else format}",
                        buf,
                        f"image/{'jpeg' if format=='jpeg' else format}"
                    )
                }

                resp = requests.post(
                    upload_url,
                    headers=http_headers_multipart(),
                    files=files,
                    timeout=int(timeout)
                )

                if resp.status_code >= 400:
                    detail = extract_error_message_from_response(resp)
                    raise RuntimeError(f"上传失败: {detail}")

                data = resp.json()
                url = data.get("url", "")

                if not url:
                    raise RuntimeError(f"上传响应缺少 url 字段: {json.dumps(data, ensure_ascii=False)}")

                uploaded_urls.append(url)
                upload_details.append(f"✓ {image_path.name} -> {url}")
                success_count += 1

                print(f"[ComfyUI_KuAi_Power]   成功: {url}")

            except Exception as e:
                error_msg = f"✗ {image_path.name}: {str(e)}"
                upload_details.append(error_msg)
                failed_count += 1
                print(f"[ComfyUI_KuAi_Power]   失败: {str(e)}")

        # 生成结果
        urls_json = json.dumps(uploaded_urls, ensure_ascii=False)

        details_text = f"""批量上传完成
总计: {len(image_files)} 个图片
成功: {success_count} 个
失败: {failed_count} 个

上传详情:
""" + "\n".join(upload_details)

        print(f"\n[ComfyUI_KuAi_Power] 批量上传完成: 成功 {success_count}/{len(image_files)}")

        return (urls_json, details_text, success_count)


NODE_CLASS_MAPPINGS = {
    "BatchImageUploader": BatchImageUploader,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BatchImageUploader": "📤 批量上传本地图片（legacy）",
}

