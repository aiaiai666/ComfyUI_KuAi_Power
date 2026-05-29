import { app } from "../../scripts/app.js";

const DOUBAO_NODES = new Set([
  "DoubaoImageGenerateEdit",
  "DoubaoImageGenerate",
  "DoubaoImageEdit",
]);

const SEEDREAM_3 = "doubao-seedream-3-0-t2i-250415";
const SEEDEDIT_3 = "doubao-seededit-3-0-i2i-250628";
const SEEDREAM_5 = "doubao-seedream-5-0-260128";

const ALWAYS_SHOW = new Set([
  "prompt",
  "model",
  "size_mode",
  "watermark",
  "api_key",
  "api_base",
  "timeout",
]);

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function widgetValue(node, name, fallback) {
  const widget = getWidget(node, name);
  return widget?.value ?? fallback;
}

function setWidgetVisible(widget, visible) {
  if (!widget) return;
  widget.hidden = !visible;
  widget.disabled = !visible;
  widget.computeSize = visible ? undefined : () => [0, -4];
}

function imageCount(node) {
  const raw = Number.parseInt(widgetValue(node, "image_count", 0), 10);
  if (Number.isNaN(raw)) return 0;
  return Math.min(14, Math.max(0, raw));
}

function refreshNode(node) {
  try {
    node.setSize(node.computeSize());
  } catch (error) {
    // Older ComfyUI builds may not expose computeSize for every node.
  }
  app.graph?.setDirtyCanvas(true, true);
}

function updateDoubaoWidgets(node) {
  const model = widgetValue(node, "model", SEEDREAM_5);
  const sizeMode = widgetValue(node, "size_mode", "preset");
  const sequential = widgetValue(node, "sequential_image_generation", "disabled");
  const count = model === SEEDEDIT_3 ? 1 : imageCount(node);

  for (const widget of node.widgets || []) {
    let visible = ALWAYS_SHOW.has(widget.name);

    if (widget.name === "image_count") {
      visible = model !== SEEDREAM_3 && model !== SEEDEDIT_3;
    } else if (/^image_url_\d+$/.test(widget.name)) {
      const index = Number.parseInt(widget.name.replace("image_url_", ""), 10);
      visible = model === SEEDEDIT_3 ? index === 1 : model !== SEEDREAM_3 && index <= count;
    } else if (widget.name === "seed" || widget.name === "guidance_scale") {
      visible = model === SEEDREAM_3 || model === SEEDEDIT_3;
    } else if (widget.name === "sequential_image_generation") {
      visible = model !== SEEDREAM_3 && model !== SEEDEDIT_3;
    } else if (widget.name === "max_images") {
      visible = model !== SEEDREAM_3 && model !== SEEDEDIT_3 && sequential === "auto";
    } else if (widget.name === "output_format") {
      visible = model === SEEDREAM_5;
    } else if (widget.name === "resolution") {
      visible = model !== SEEDREAM_3 && model !== SEEDEDIT_3 && sizeMode === "preset";
    } else if (widget.name === "custom_size") {
      visible = model === SEEDREAM_3 || (model !== SEEDEDIT_3 && sizeMode === "custom");
    } else if (widget.name === "response_format") {
      visible = true;
    }

    setWidgetVisible(widget, visible);
  }

  refreshNode(node);
}

function wrapCallback(widget, node) {
  if (!widget || widget.__doubaoWrapped) return;
  const original = widget.callback;
  widget.callback = function (...args) {
    const result = original?.apply(this, args);
    setTimeout(() => updateDoubaoWidgets(node), 0);
    return result;
  };
  widget.__doubaoWrapped = true;
}

app.registerExtension({
  name: "KuAi.DoubaoImageDynamicUI",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!DOUBAO_NODES.has(nodeData.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = onNodeCreated?.apply(this, args);
      for (const name of ["model", "image_count", "size_mode", "sequential_image_generation"]) {
        wrapCallback(getWidget(this, name), this);
      }
      setTimeout(() => updateDoubaoWidgets(this), 0);
      return result;
    };
  },
});
