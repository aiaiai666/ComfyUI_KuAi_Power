"""可灵 API 工具函数"""

# 模型列表
KLING_MODELS = [
    "kling-v1",
    "kling-v1-5",
    "kling-v1-6",
    "kling-v2-master",
    "kling-v2-1",
    "kling-v2-1-master",
    "kling-v2-5-turbo",
    "kling-v2-6"
]

# 宽高比列表
KLING_ASPECT_RATIOS = [
    "16:9",
    "9:16",
    "1:1"
]

def parse_kling_response(resp_json):
    """解析可灵 API 响应格式

    可灵格式:
    {
      "code": 0,
      "message": "SUCCEED",
      "data": {
        "task_id": "831922345719271433",
        "task_status": "submitted",
        "created_at": 1766374262370
      }
    }

    返回: (task_id, status, created_at)
    """
    if resp_json.get("code") != 0:
        raise RuntimeError(f"API 错误: {resp_json.get('message', '未知错误')}")

    data = resp_json.get("data", {})
    task_id = data.get("task_id", "")
    status = data.get("task_status", "")
    created_at = data.get("created_at", 0)

    return (task_id, status, created_at)
