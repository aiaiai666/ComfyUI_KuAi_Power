import { app } from "../../scripts/app.js";

const HAPPYHORSE_UNIFIED_NODES = new Set([
  "HappyHorseVideoCreate",
  "HappyHorseVideoAndWait",
]);

const ALWAYS_SHOW = new Set([
  "model",
  "prompt",
  "resolution",
  "duration",
  "watermark",
  "api_key",
  "api_base",
  "timeout",
  "create_timeout",
  "poll_interval_sec",
  "wait_timeout_sec",
  "save_video",
  "save_dir",
  "filename_prefix",
  "download_timeout",
]);

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function setWidgetVisible(widget, visible) {
  if (!widget) return;
  widget.hidden = !visible;
  widget.disabled = !visible;
  widget.computeSize = visible ? undefined : () => [0, -4];
}

function referenceImageCount(node) {
  const countWidget = getWidget(node, "reference_image_count");
  const value = Number.parseInt(countWidget?.value ?? 1, 10);
  if (Number.isNaN(value)) return 1;
  return Math.min(9, Math.max(1, value));
}

function refreshNode(node) {
  try {
    node.setSize(node.computeSize());
  } catch (error) {
    // Older ComfyUI/LiteGraph builds may not support computeSize for all nodes.
  }
  app.graph?.setDirtyCanvas(true, true);
}

function updateHappyHorseWidgets(node) {
  const model = getWidget(node, "model")?.value || "happyhorse-1.0-t2v";
  const refCount = referenceImageCount(node);

  for (const widget of node.widgets || []) {
    let visible = ALWAYS_SHOW.has(widget.name);

    if (widget.name === "ratio") {
      visible = model !== "happyhorse-1.0-i2v";
    } else if (widget.name === "reference_image_count") {
      visible = model === "happyhorse-1.0-r2v";
    } else {
      const match = widget.name.match(/^image_url_(\d)$/);
      if (match) {
        const index = Number.parseInt(match[1], 10);
        visible = model === "happyhorse-1.0-i2v" ? index === 1 : model === "happyhorse-1.0-r2v" && index <= refCount;
      }
    }

    setWidgetVisible(widget, visible);
  }

  refreshNode(node);
}

function wrapCallback(widget, node) {
  if (!widget || widget.__happyhorseWrapped) return;
  const original = widget.callback;
  widget.callback = function (...args) {
    const result = original?.apply(this, args);
    setTimeout(() => updateHappyHorseWidgets(node), 0);
    return result;
  };
  widget.__happyhorseWrapped = true;
}

app.registerExtension({
  name: "KuAi.HappyHorseDynamicUI",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!HAPPYHORSE_UNIFIED_NODES.has(nodeData.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = onNodeCreated?.apply(this, args);
      wrapCallback(getWidget(this, "model"), this);
      wrapCallback(getWidget(this, "reference_image_count"), this);
      setTimeout(() => updateHappyHorseWidgets(this), 0);
      return result;
    };
  },
});