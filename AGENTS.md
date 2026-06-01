# AGENTS.md

## 项目定位
- 本项目是 ComfyUI 自定义节点插件 `ComfyUI_KuAi_Power`。
- 主要语言：Python 3.9+；前端扩展：原生 JavaScript。
- 主要能力：接入 KuAi API，提供视频、图像、OCR、上传、下载、批处理、监控等 ComfyUI 节点。
- 开发目标：稳定注册节点、稳定调用 API、稳定返回 ComfyUI 可识别的数据。

## 固定规则
- 中文回复，言简意赅。
- 像原始人一样回复：只说结果，不废话，不客套。技术内容完整保留。
- 如无必要，勿增实体。
- 禁止使用 worktree。
- 默认在 `main` 分支开发；本仓库当前只有 `master` 时，在 `master` 做最小改动。若要切分支或新建分支，先问用户。
- 每次开始实作前先检查 `git status --short`。如果有未提交更改，先问用户是否继续。
- 不碰无关文件，不清理用户改动，不做顺手重构。

## 命令输出
- 任何未知大小或可能很大的命令输出必须截断。
- PowerShell 默认写法：

```powershell
$o = COMMAND 2>&1 | Out-String; $o.Substring(0, [Math]::Min($o.Length, 4000))
```

- 不使用当前环境没有的 `head`。

## Git Push
- 因网络原因，执行 `git push` 必须使用本机代理端口 `10808`。
- 默认 push 写法：

```powershell
git -c http.proxy=http://127.0.0.1:10808 -c https.proxy=http://127.0.0.1:10808 push -u origin master
```

- 只在用户明确要求时 push。

## 项目结构
- `__init__.py`：ComfyUI 插件入口，自动扫描 `nodes/`，合并 `NODE_CLASS_MAPPINGS` 与 `NODE_DISPLAY_NAME_MAPPINGS`，声明 `WEB_DIRECTORY = "./web"`。
- `nodes/`：节点主目录，按能力或模型分组。
- `nodes/Veo3/`、`nodes/Grok/`、`nodes/Sora2/`、`nodes/Kling/`、`nodes/NanoBanana/` 等：模型节点。
- `nodes/Utils/`：上传、下载、CSV、日志、监控、OCR 等配套节点。
- `utils/`：通用工具，如异步执行、HTTP 客户端。
- `web/`：ComfyUI 前端扩展，如快捷面板、动态 UI、预览与实时监控。
- `config.py`：全局配置，使用 `pydantic-settings` 读取 `.env`。
- `diagnose.py`：诊断脚本，检查依赖、导入、节点结构和分类。
- `requirements.txt`：运行依赖。
- `.env.sample`：环境变量示例。

## 节点开发规则
- 每个 ComfyUI 节点类必须保留标准接口：
  - `INPUT_TYPES`
  - `RETURN_TYPES`
  - `FUNCTION`
  - `CATEGORY`
- 新增节点必须导出到所在模块的：
  - `NODE_CLASS_MAPPINGS`
  - `NODE_DISPLAY_NAME_MAPPINGS`
- 新增子目录节点时，同步检查该目录的 `__init__.py` 是否合并映射。
- 节点分类统一使用 `KuAi/...`，除非已有同类模块使用其他固定命名。
- 不随意改节点显示名、输入字段名、返回字段名；这些会影响现有工作流兼容性。
- 改默认参数前先确认影响，尤其是模型名、超时、比例、并发、API 地址。

## API 与配置
- API Key 优先从节点入参读取；为空时使用环境变量 `KUAI_API_KEY`。
- 不硬编码真实密钥、Token、用户路径、私有 URL。
- 默认 API 地址保持现有风格：`https://api.kegeai.top`。
- HTTP 错误要返回用户可读信息，保留上游错误详情。
- 批处理、轮询、下载逻辑必须考虑超时、失败状态、空结果。
- 不新增复杂配置；只有多个节点真实复用时，才放入 `config.py`。

## 前端开发规则
- ComfyUI 前端扩展放在 `web/`。
- 使用现有 `app.registerExtension` 风格。
- 不引入构建工具，除非用户明确要求。
- 不破坏现有快捷面板、动态 UI、视频预览、实时监控。
- 改 UI 时先保证节点原始功能不受影响。

## Demo 工作流规则
- 新增或修改 ComfyUI demo 工作流 JSON 时，顶层 `id` 必须使用合法 UUID，不能使用普通字符串，否则新版 ComfyUI 会报 `Invalid workflow against zod schema: Invalid uuid at "id"`。
- demo 工作流必须至少有一个 `OUTPUT_NODE = True` 的输出节点，并把目标处理节点输出连接过去，否则执行会报 `Prompt has no outputs`。

## 批处理与文件规则
- 批处理节点要保持 CSV 字段兼容。
- 输出文件、日志文件、下载文件不得默认覆盖用户数据。
- 对本地路径处理使用 `pathlib.Path`，避免拼接字符串路径。
- 大批量任务优先复用已有批处理、监控、日志模块。

## 实作前思考
- 先写清楚假设。
- 多种理解并存时，列出差异，不暗自选择。
- 有更简单方案时直接说明。
- 不清楚就停，指出不清楚的点，问用户。

## 简化原则
- 只写满足请求的最少代码。
- 不为单次使用抽象。
- 不加未被要求的灵活性、配置项、功能开关。
- 不为不可能场景写复杂保护。
- 如果 200 行能改成 50 行，重写成 50 行。

## 外科式改动
- 只改和请求直接相关的行。
- 不顺手格式化、改注释、改命名。
- 匹配现有风格，即使不是最佳风格。
- 发现无关死代码，只说明，不删除。
- 自己新增后变成无用的 import、变量、函数，必须清理。

## 任务执行
- 非简单任务先写短计划。
- 计划格式：

```markdown
1. [步骤] -> 验证：[检查]
2. [步骤] -> 验证：[检查]
3. [步骤] -> 验证：[检查]
```

- 复杂任务或 3 步以上任务，写入 `tasks/todo.md`。
- 过程中按实际进度更新 `tasks/todo.md`。
- 用户纠正后，把可复用教训写入 `tasks/lessons.md`。
- 若执行中发现原计划错误，停止并重新计划。

## Sub-agent 使用
- 可并行、无依赖的探索或审查任务，直接使用 sub-agent。
- 一个 sub-agent 只做一个明确任务。
- 探索、审查、重复扫描可交给 sub-agent，主线程保留决策和最终合并。
- 修改代码前仍要遵守工作区状态检查和最小改动规则。

## 验证标准
- 交付前必须证明结果可用。
- 文档类改动：检查文件存在、内容可读、范围正确。
- Python 节点改动：优先运行相关导入检查；必要时运行 `python diagnose.py`。
- 依赖变更：同步检查 `requirements.txt`、`setup.py`。
- 前端改动：在 ComfyUI 或浏览器中验证目标 UI 能加载。
- 修 bug：优先写出或运行能复现问题的检查，再修，再验证通过。
- 未能运行的验证必须说明原因。

## 常用验证命令
```powershell
python diagnose.py
```

```powershell
python -m compileall .
```

```powershell
$o = git diff --stat 2>&1 | Out-String; $o.Substring(0, [Math]::Min($o.Length, 4000))
```

## 回复格式
- 只写：结论、实际改动、原因、验证结果。
- 不写推进过程。
- 不用工程汇报腔。
- 需要对比方案时，列优缺点，并明确推荐项与原因。
- 最终回复面向没看代码的人，清楚直白。
