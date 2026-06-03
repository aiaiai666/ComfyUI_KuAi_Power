import { app } from "../../scripts/app.js";

const OMNI_NODES = new Set([
  "OmniCreateVideo",
]);

const CONTROLLED_WIDGETS = new Set([
  "image_1",
  "image_2",
  "image_3",
  "input_reference",
]);

function getWidget(node, name) {
  return node.widgets?.find((widget) => widget.name === name);
}

function generationType(node) {
  const value = String(getWidget(node, "type")?.value ?? "1").trim();
  const match = value.match(/^\s*([1-4])/);
  return match ? Number.parseInt(match[1], 10) : 1;
}

function setWidgetEnabled(widget, enabled) {
  if (!widget) return;
  widget.disabled = !enabled;
  widget.readonly = !enabled;

  const element = widget.element || widget.inputEl;
  if (element) {
    element.disabled = !enabled;
  }
}

function updateWidgetColors(widget, enabled) {
  if (!widget) return;
  if (!widget.__omniOriginalColors) {
    widget.__omniOriginalColors = {
      color: widget.color,
      text_color: widget.text_color,
      secondary_text_color: widget.secondary_text_color,
    };
  }

  const original = widget.__omniOriginalColors;
  widget.color = enabled ? original.color : "#4b5563";
  widget.text_color = enabled ? original.text_color : "#9ca3af";
  widget.secondary_text_color = enabled ? original.secondary_text_color : "#6b7280";
}

function updateOmniWidgets(node) {
  const type = generationType(node);

  const enabledByName = {
    image_1: type === 2 || type === 3,
    image_2: type === 2 || type === 3,
    image_3: type === 3,
    input_reference: type === 4,
  };

  for (const widget of node.widgets || []) {
    if (!CONTROLLED_WIDGETS.has(widget.name)) continue;
    const enabled = Boolean(enabledByName[widget.name]);
    setWidgetEnabled(widget, enabled);
    updateWidgetColors(widget, enabled);
  }

  app.graph?.setDirtyCanvas(true, true);
}

function wrapCallback(widget, node) {
  if (!widget || widget.__omniWrapped) return;
  const original = widget.callback;
  widget.callback = function (...args) {
    const result = original?.apply(this, args);
    setTimeout(() => updateOmniWidgets(node), 0);
    return result;
  };
  widget.__omniWrapped = true;
}

app.registerExtension({
  name: "KuAi.OmniDynamicUI",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!OMNI_NODES.has(nodeData.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = onNodeCreated?.apply(this, args);
      wrapCallback(getWidget(this, "type"), this);
      setTimeout(() => updateOmniWidgets(this), 0);
      return result;
    };
  },
});
