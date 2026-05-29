"""批量处理日志显示节点"""

import json
from .batch_logger import format_batch_report


class BatchProcessLogger:
    """批量处理日志格式化显示节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "report_json": ("STRING", {
                    "forceInput": True,
                    "tooltip": "批量处理报告 JSON（来自并发处理器）"
                }),
            },
            "optional": {
                "verbose": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否显示详细信息"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "report_json": "处理报告JSON",
            "verbose": "详细模式",
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("格式化日志",)
    FUNCTION = "format_log"
    CATEGORY = "KuAi/Utils"

    def format_log(self, report_json, verbose=True):
        """格式化批量处理日志"""
        try:
            # 尝试解析 JSON
            report_data = json.loads(report_json)

            # 格式化报告
            formatted_log = format_batch_report(report_data, verbose=verbose)

            print(formatted_log)

            return (formatted_log,)

        except json.JSONDecodeError as e:
            error_msg = f"❌ JSON 解析失败: {str(e)}"
            print(error_msg)
            return (error_msg,)
        except Exception as e:
            error_msg = f"❌ 日志格式化失败: {str(e)}"
            print(error_msg)
            return (error_msg,)


NODE_CLASS_MAPPINGS = {
    "BatchProcessLogger": BatchProcessLogger,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BatchProcessLogger": "📊 批量处理日志显示",
}
