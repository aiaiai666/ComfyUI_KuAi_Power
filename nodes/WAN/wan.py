"""WAN 一键生视频节点"""

import json
import time
import requests

from ..Sora2.kuai_utils import (
    env_or,
    http_headers_auth_only,
    extract_error_message_from_response,
    extract_task_failure_detail,
)


class WanCreateAndWait:
    """创建 WAN 视频任务并等待完成（一键）"""

    SUCCESS_STATES = {"SUCCEEDED", "COMPLETED"}
    FAILED_STATES = {"FAILED", "ERROR", "CANCELED", "CANCELLED", "FAIL"}
    RUNNING_STATES = {"PENDING", "RUNNING", "QUEUED", "SCHEDULED", "SUBMITTED"}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ([
                    "wan2.6-i2v-flash",
                    "wan2.6-i2v",
                    "wan2.5-i2v-preview",
                ], {
                    "default": "wan2.6-i2v-flash",
                    "tooltip": "WAN 模型（可被自定义模型覆盖）"
                }),
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "正向提示词"
                }),
                "negative_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "反向提示词"
                }),
                "img_url": ("STRING", {
                    "default": "",
                    "tooltip": "首帧图像 URL"
                }),
                "template": ("STRING", {
                    "default": "none",
                    "tooltip": "视频特效模板（无模板可填 none）"
                }),
                "resolution": (["480P", "720P", "1080P"], {
                    "default": "720P",
                    "tooltip": "视频分辨率"
                }),
                "duration": ("INT", {
                    "default": 5,
                    "min": 1,
                    "max": 60,
                    "tooltip": "视频时长（秒）"
                }),
                "prompt_extend": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "是否开启提示词智能改写"
                }),
                "watermark": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "是否添加 AI 生成水印"
                }),
                "audio": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "当 audio_url 为空时是否自动添加音频"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 2147483647,
                    "tooltip": "随机种子（0 表示随机）"
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "API 密钥（留空使用环境变量 KUAI_API_KEY）"
                }),
            },
            "optional": {
                "audio_url": ("STRING", {
                    "default": "",
                    "tooltip": "音频文件URL（可选，仅 wan2.5-i2v-preview 支持）"
                }),
                "custom_model": ("STRING", {
                    "default": "",
                    "tooltip": "自定义模型（留空使用下拉模型）"
                }),
                "api_base": ("STRING", {
                    "default": "https://api.kegeai.top",
                    "tooltip": "API 端点地址"
                }),
                "max_wait_time": ("INT", {
                    "default": 1200,
                    "min": 30,
                    "max": 7200,
                    "tooltip": "最大等待时间（秒）"
                }),
                "poll_interval": ("INT", {
                    "default": 10,
                    "min": 1,
                    "max": 120,
                    "tooltip": "轮询间隔（秒）"
                }),
            }
        }

    @classmethod
    def INPUT_LABELS(cls):
        return {
            "model": "模型",
            "custom_model": "自定义模型",
            "prompt": "提示词",
            "negative_prompt": "反向提示词",
            "img_url": "首帧图 URL",
            "audio_url": "音频 URL",
            "template": "模板",
            "resolution": "分辨率",
            "duration": "时长",
            "prompt_extend": "智能改写",
            "watermark": "水印",
            "audio": "自动音频",
            "seed": "随机种子",
            "api_key": "API密钥",
            "api_base": "API地址",
            "max_wait_time": "最大等待时间",
            "poll_interval": "轮询间隔",
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("任务ID", "状态", "视频URL", "原始提示词", "增强提示词")
    FUNCTION = "create_and_wait"
    CATEGORY = "KuAi/WAN"

    @staticmethod
    def _normalize_status(status: str) -> str:
        return str(status or "").strip().upper()

    @staticmethod
    def _must_non_empty(value, name_zh: str):
        if not str(value or "").strip():
            raise RuntimeError(f"{name_zh}不能为空")

    def _create_task(self, api_base, api_key, payload):
        endpoint = f"{api_base.rstrip('/')}/alibailian/api/v1/services/aigc/video-generation/video-synthesis"
        resp = requests.post(endpoint, json=payload, headers=http_headers_auth_only(api_key), timeout=60)

        if resp.status_code >= 400:
            detail = extract_error_message_from_response(resp)
            raise RuntimeError(f"WAN 视频任务创建失败: {detail}")

        data = resp.json()
        output = data.get("output") or {}
        task_id = str(output.get("task_id") or "").strip()
        task_status = str(output.get("task_status") or "").strip()

        if not task_id:
            raise RuntimeError(f"WAN 创建响应缺少任务ID: {json.dumps(data, ensure_ascii=False)}")

        return task_id, task_status

    def _query_task(self, api_base, api_key, task_id):
        endpoint = f"{api_base.rstrip('/')}/alibailian/api/v1/tasks/{task_id}"
        resp = requests.get(endpoint, headers=http_headers_auth_only(api_key), timeout=60)

        if resp.status_code >= 400:
            detail = extract_error_message_from_response(resp)
            raise RuntimeError(f"WAN 视频任务查询失败: {detail}")

        data = resp.json()
        output = data.get("output") or {}

        status = str(output.get("task_status") or "")
        video_url = str(output.get("video_url") or "")
        orig_prompt = str(output.get("orig_prompt") or "")
        actual_prompt = str(output.get("actual_prompt") or "")

        normalized = self._normalize_status(status)
        if normalized in self.FAILED_STATES:
            fail_detail = extract_task_failure_detail(output) or extract_task_failure_detail(data)
            if not fail_detail:
                fail_detail = json.dumps(data, ensure_ascii=False)
            raise RuntimeError(f"WAN 视频任务失败: {fail_detail}")

        if normalized in self.SUCCESS_STATES and not video_url.strip():
            raise RuntimeError("WAN 视频任务已完成但未返回视频URL")

        return status, video_url, orig_prompt, actual_prompt

    def create_and_wait(
        self,
        model,
        prompt,
        negative_prompt,
        img_url,
        template,
        resolution,
        duration,
        prompt_extend,
        watermark,
        audio,
        seed,
        api_key,
        audio_url="",
        custom_model="",
        api_base="https://api.kegeai.top",
        max_wait_time=1200,
        poll_interval=10,
    ):
        api_key = env_or(api_key, "KUAI_API_KEY")
        if not api_key:
            raise RuntimeError("API Key 未配置，请在节点参数或环境变量中设置 KUAI_API_KEY")

        api_base = (api_base or "https://api.kegeai.top").strip()
        if not api_base:
            raise RuntimeError("API地址不能为空")

        template = str(template or "").strip() or "none"

        self._must_non_empty(model, "模型")
        self._must_non_empty(prompt, "提示词")
        self._must_non_empty(negative_prompt, "反向提示词")
        self._must_non_empty(img_url, "首帧图URL")
        self._must_non_empty(template, "模板")
        self._must_non_empty(resolution, "分辨率")

        effective_model = (custom_model or "").strip() or str(model).strip()

        audio_url_value = str(audio_url or "").strip()
        if audio_url_value and effective_model != "wan2.5-i2v-preview":
            raise RuntimeError("音频URL 仅支持模型 wan2.5-i2v-preview，请清空音频URL或切换模型")

        input_payload = {
            "prompt": str(prompt),
            "negative_prompt": str(negative_prompt),
            "img_url": str(img_url).strip(),
            "template": template,
        }
        if audio_url_value:
            input_payload["audio_url"] = audio_url_value

        payload = {
            "model": effective_model,
            "input": input_payload,
            "parameters": {
                "resolution": str(resolution).strip(),
                "duration": int(duration),
                "prompt_extend": bool(prompt_extend),
                "watermark": bool(watermark),
                "audio": bool(audio),
                "seed": int(seed),
            },
        }

        print(f"[ComfyUI_KuAi_Power] WAN 创建视频任务: {str(prompt)[:50]}...")
        task_id, create_status = self._create_task(api_base, api_key, payload)
        status = create_status
        video_url = ""
        orig_prompt = ""
        actual_prompt = ""

        normalized = self._normalize_status(status)
        if normalized in self.SUCCESS_STATES:
            status, video_url, orig_prompt, actual_prompt = self._query_task(api_base, api_key, task_id)
            return (task_id, status, video_url, orig_prompt, actual_prompt)

        print(f"[ComfyUI_KuAi_Power] WAN 等待视频生成完成，最多等待 {int(max_wait_time)} 秒...")

        elapsed = 0
        while elapsed < int(max_wait_time):
            time.sleep(int(poll_interval))
            elapsed += int(poll_interval)

            status, video_url, orig_prompt, actual_prompt = self._query_task(api_base, api_key, task_id)
            normalized = self._normalize_status(status)

            if normalized in self.SUCCESS_STATES:
                print("[ComfyUI_KuAi_Power] WAN 视频生成完成！")
                return (task_id, status, video_url, orig_prompt, actual_prompt)

            if normalized not in self.RUNNING_STATES:
                print(f"[ComfyUI_KuAi_Power] WAN 任务状态: {status}（按进行中处理）")

            print(f"[ComfyUI_KuAi_Power] WAN 任务进行中... 已等待 {elapsed}/{int(max_wait_time)} 秒")

        raise RuntimeError(
            f"WAN 视频生成超时（等待了 {int(max_wait_time)} 秒），"
            f"任务ID: {task_id}，最后状态: {status}。可使用任务ID继续查询。"
        )
