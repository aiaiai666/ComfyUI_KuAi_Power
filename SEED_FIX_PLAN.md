# Seed 参数修复清单

## ✓ 已修复
- Veo3/veo3.py: VeoText2Video, VeoImage2Video - seed 移到 optional

## ⏳ 需要修复（seed 从 required → optional）

### Grok/grok.py
- GrokCreateVideo
- GrokText2Video  
- GrokImage2Video
- GrokImage2VideoUnified

### Sora2/sora2.py
- SoraCreateVideo
- SoraText2Video

### Kling/kling.py
- KlingText2Video
- KlingImage2Video

### Grok/grok_videos.py
- GrokVideosCreateVideo

### HappyHorse/happyhorse.py
- HappyHorseVideoCreate

## 修复方法（参考 GrokImageVideoGenerate）

### 1. INPUT_TYPES 改动
```python
# 从 required 中移除 seed
"required": { ... },

# 添加到 optional
"optional": {
    ...
    "seed": ("INT", {"default": 0, "min": 0, "max": 2147483647, "tooltip": "随机种子；改变 seed 可避免重复提交"}),
}
```

### 2. 方法签名保持不变（seed 已作为默认参数）

### 3. Payload 中的 seed 处理
- 不使用 `control_after_generate`
- 直接发送给 API：`"seed": int(seed) if seed else 0`

### 关键区别
- **control_after_generate: True** = ComfyUI 内部控制，**不发送**给 API（如 GPTImage）
- **无 control_after_generate** = 直接发送给 API（如 GrokImageVideoGenerate）
