# ComfyUI KuAi Power

[![GitHub](https://img.shields.io/badge/GitHub-kegeai888%2FComfyUI__KuAi__Power-blue?logo=github)](https://github.com/kegeai888/ComfyUI_KuAi_Power)

ComfyUI 节点扩展，提供对 Sora2、Veo3、Grok 视频生成模型、Nano Banana 图像生成以及 AI 脚本生成功能的支持。

> **GitHub 仓库**: [https://github.com/kegeai888/ComfyUI_KuAi_Power](https://github.com/kegeai888/ComfyUI_KuAi_Power)
>
> **仓库地址**: https://github.com/kegeai888/ComfyUI_KuAi_Power
>
> **用户使用手册**: [./用户使用手册.md](./用户使用手册.md)

> **API 服务**: [kuai.host](https://api.kuai.host/register?aff=z2C8) | **国内镜像**: [videos.kuai.host](https://videos.kuai.host/) | **国内镜像**: [nbnb.kuai.host](https://nbnb.kuai.host/) | **视频教程**: [Bilibili](https://www.bilibili.com/video/BV1umCjBqEpt/)

> 可配合[本地一键包「CNB钞能力一键包-free」来使用](https://pan.quark.cn/s/987bd66a6197)

`https://pan.quark.cn/s/987bd66a6197 提取码：AJFP`

## 🚀 快速开始

### 1. 安装依赖
```bash
# 进入插件目录
cd ComfyUI/custom_nodes/ComfyUI_KuAi_Power
# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 API Key
在节点参数中直接填写，或创建 `.env` 文件并设置环境变量 `KUAI_API_KEY=your_api_key_here`。

### 3. 重启 ComfyUI
重启后，即可在右键菜单或 `Ctrl+Shift+K` 快捷面板中找到新节点。

---

## ✨ 核心功能

所有节点均提供全中文界面，分类清晰，易于使用。

### 🚀 Veo 视频生成 (`KuAi/Veo3`)
新一代视频模型，支持文生视频和图生视频。推荐优先使用 **⚡ Veo3 目录批量图生视频（一键闭环）**，单节点即可完成目录扫描、上传、生成、轮询和下载。

| 节点名称 | 功能简介 |
| :--- | :--- |
| **🎬 Veo 文生视频** | 仅通过文本提示词创建视频。 |
| **🖼️ Veo 图生视频** | 使用 1-3 张参考图和提示词创建视频。 |
| **🔍 Veo 查询任务** | 查询指定任务的状态和结果。 |
| **⚡ Veo 一键文生视频** | 提交任务并自动等待视频生成完成。 |
| **⚡ Veo 一键图生视频** | 提交带参考图的任务并等待完成。 |
| **📋 Veo3 批量图片转任务列表（legacy）** | 旧三节点流程的一环（批量上传 URL 转任务）；新项目建议改用一键闭环节点。 |
| **⚡ Veo3 文生视频（10路并发）** | 10 路并发文生视频，大幅提升批量处理速度。 |
| **⚡ Veo3 图生视频（10路并发）** | 10 路并发图生视频，支持批量处理。 |
| **📦 Veo3 CSV 并发批量处理器（legacy）** | 旧三节点流程的一环（并发执行与下载）；新项目建议改用一键闭环节点。 |
| **⚡ Veo3 目录批量图生视频（一键闭环）** | 🆕 单节点完整闭环：扫描本地目录 → 并发上传 → 并发图生视频 → 轮询 → 下载 MP4。 |

### 🤖 Grok 视频生成 (`KuAi/Grok`)
xAI 推出的视频生成模型，支持文生视频和图生视频，提供 6 秒和 10 秒两种模型选择。推荐优先使用 **⚡ Grok 目录批量图生视频（一键闭环）**，单节点即可完成目录扫描、上传、生成、轮询和下载。

| 节点名称 | 功能简介 |
| :--- | :--- |
| **🤖 Grok 创建视频** | 提交视频生成任务（支持可选图片）。 |
| **📝 Grok 文生视频** | 纯文本生成视频，无需图片输入。 |
| **🎬 Grok 图生视频** | 使用图片和提示词生成视频。 |
| **🔍 Grok 查询视频** | 查询任务状态和结果。 |
| **⚡ Grok 一键生成视频** | 提交任务并自动等待完成。 |
| **⚡ Grok 文生视频（一键）** | 文生视频一键生成，自动等待完成。 |
| **⚡ Grok 图生视频（一键）** | 图生视频一键生成，自动等待完成。 |
| **📦 Grok 批量处理器** | 通过 CSV 文件批量生成视频。 |
| **📋 Grok 批量图片转任务列表（legacy）** | 旧三节点流程的一环（批量上传 URL 转任务）；新项目建议改用一键闭环节点。 |
| **⚡ Grok 文生视频（10路并发）** | 10 路并发文生视频，大幅提升批量处理速度。 |
| **⚡ Grok 图生视频（10路并发）** | 10 路并发图生视频，支持批量处理。 |
| **📦 Grok CSV 并发批量处理器（legacy）** | 旧三节点流程的一环（并发执行与下载）；新项目建议改用一键闭环节点。 |
| **⚡ Grok 目录批量图生视频（一键闭环）** | 🆕 单节点完整闭环：扫描本地目录 → 并发上传 → 并发图生视频 → 轮询 → 下载 MP4。 |

**模型选择**：
- **grok-video-3 (6秒)**：标准模型，生成 6 秒视频
- **grok-video-3-10s (10秒)**：10 秒视频专用模型

### 🎬 Sora2 视频生成 (`KuAi/Sora2`)
强大的图生视频模型，支持视频生成、角色创建、视频编辑和批量处理。

| 节点名称 | 功能简介 |
| :--- | :--- |
| **🎥 创建视频任务** | 提交图生视频任务。 |
| **📝 文生视频** | 仅通过文本提示词创建视频。 |
| **🔍 查询任务状态** | 查询指定任务的状态和结果。 |
| **⚡ 一键生成视频** | 提交任务并自动等待视频生成完成。 |
| **👤 创建角色** | 从视频中提取角色，用于后续视频生成。 |
| **🎬 编辑视频** | 基于已生成的视频进行二次编辑（Remix）。 |
| **📦 Sora2 批量处理器** | 通过 CSV 文件批量生成视频，支持文生视频和图生视频。 |

### 📝 AI 脚本生成 (`KuAi/ScriptGenerator`)
利用大语言模型自动为您的产品生成专业的视频脚本/提示词。

| 节点名称 | 功能简介 |
| :--- | :--- |
| **📦 产品信息构建器** | 将产品信息结构化，为 AI 生成做准备。 |
| **🤖 AI 生成提示词** | 根据产品信息，调用 AI 生成专业级的 Sora 提示词。 |

### 🍌 Nano Banana 图像生成 (`KuAi/NanoBanana`)
基于 Google Gemini 模型的多模态图像生成，支持文生图、图生图、多轮对话和批量处理。

| 节点名称 | 功能简介 |
| :--- | :--- |
| **🍌 Nano Banana Pro 多功能** | 统一的多模态图像生成接口，支持单/多图生成、参考图、搜索增强、系统提示词。 |
| **🍌 Nano Banana 多轮对话** | 支持基于对话历史的迭代图像生成和编辑，支持系统提示词。 |
| **📦 NanoBanana 批量处理器** | 通过 CSV 文件批量生成或编辑图像，自动保存结果和元数据。 |

### 🛠️ 其他工具

| 节点名称 | 分类 | 功能简介 |
| :--- | :--- | :--- |
| **UploadToImageHost** | `KuAi/Utils` | 将本地图片上传到图床并返回 URL。 |
| **DeepseekOCRToPrompt**| `KuAi/Utils` | 提取图片中的文本内容。 |
| **CSV 批量读取器** | `KuAi/Utils` | 读取 CSV 文件并解析为批量任务数据。 |

---

## 💡 工作流示例

### 示例 1: Veo 文生视频
```
(输入提示词) → VeoText2VideoAndWait → (获取视频URL)
```

### 示例 2: Sora2 产品视频生成
```
LoadImage → UploadToImageHost → ProductInfoBuilder → SoraPromptFromProduct → SoraCreateAndWait
```

### 示例 3: Nano Banana 图像生成
```
NanoBananaAIO → (输入提示词和参数) → (获取图像 + 思考过程 + 引用来源)
```

### 示例 4: 多轮对话图像编辑
```
NanoBananaMultiTurnChat → "Create a perfume bottle" → "Make it elegant" → "Add flowers"
```

### 示例 5: 批量图像生成
```
CSVBatchReader (读取 CSV 文件) → NanoBananaBatchProcessor (批量处理) → (自动保存图像和元数据)
```

**CSV 模板下载**:
- [空白模板](./workflows/nanobana_batch_template_blank.csv)
- [文生图模板](./workflows/nanobana_batch_template_text2image.csv)
- [图生图模板](./workflows/nanobana_batch_template_image2image.csv)
- [中文模板](./workflows/nanobana_batch_template_chinese.csv)
- [模板使用说明](./workflows/CSV_TEMPLATES_README.md)

**详细指南**: [NanoBanana 批量处理使用指南](./NANOBANA_BATCH_GUIDE.md)

---

## 🔧 开发与排错

### 文件结构
```
ComfyUI_KuAi_Power/
├── nodes/
│   ├── Sora2/             # Sora2 节点
│   ├── Veo3/              # Veo 节点
│   ├── NanoBanana/        # Nano Banana 图像生成节点
│   └── Utils/             # 工具节点
├── web/
│   └── kuaipower_panel.js # 前端快捷面板
├── __init__.py
├── CLAUDE.md              # 详细技术文档
└── README.md
```

### 运行诊断脚本
如果遇到节点不显示等问题，请先运行诊断脚本。
```bash
python diagnose.py
```

### 常见问题
- **节点不显示?** 确认依赖已安装并重启 ComfyUI。检查控制台有无报错。
- **API 调用失败?** 检查 API Key 是否正确，网络是否通畅。

---

## 📄 许可证
MIT License
