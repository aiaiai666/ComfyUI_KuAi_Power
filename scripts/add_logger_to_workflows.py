#!/usr/bin/env python3
"""为批量工作流添加详细日志显示节点"""

import json
import os
from pathlib import Path


def add_logger_node_to_workflow(workflow_path):
    """为工作流添加批量日志显示节点"""

    print(f"\n处理工作流: {workflow_path}")

    # 读取工作流
    with open(workflow_path, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 找到并发处理器节点
    processor_node = None
    processor_type = None
    for node in workflow['nodes']:
        if 'ConcurrentProcessor' in node['type']:
            processor_node = node
            processor_type = node['type']
            break

    if not processor_node:
        print("  ⚠️  未找到并发处理器节点，跳过")
        return False

    print(f"  ✓ 找到处理器节点: {processor_type} (ID: {processor_node['id']})")

    # 检查是否已经有 BatchProcessLogger 节点
    has_logger = any(node['type'] == 'BatchProcessLogger' for node in workflow['nodes'])
    if has_logger:
        print("  ⚠️  已存在日志节点，跳过")
        return False

    # 获取下一个节点 ID 和链接 ID
    next_node_id = workflow['last_node_id'] + 1
    next_link_id = workflow['last_link_id'] + 1

    # 创建新的日志显示节点
    logger_node = {
        "id": next_node_id,
        "type": "BatchProcessLogger",
        "pos": [processor_node['pos'][0] + 550, processor_node['pos'][1] + 450],
        "size": [500, 400],
        "flags": {},
        "order": processor_node['order'] + 1,
        "mode": 0,
        "inputs": [
            {
                "localized_name": "处理报告JSON",
                "name": "report_json",
                "type": "STRING",
                "link": next_link_id
            },
            {
                "localized_name": "详细模式",
                "name": "verbose",
                "shape": 7,
                "type": "BOOLEAN",
                "widget": {"name": "verbose"},
                "link": None
            }
        ],
        "outputs": [
            {
                "localized_name": "格式化日志",
                "name": "格式化日志",
                "type": "STRING",
                "links": None
            }
        ],
        "title": "📊 批量处理详细日志",
        "properties": {
            "aux_id": "kegeai888/ComfyUI_KuAi_Power",
            "Node name for S&R": "BatchProcessLogger"
        },
        "widgets_values": [True],
        "color": "#232",
        "bgcolor": "#353"
    }

    # 添加新节点
    workflow['nodes'].append(logger_node)

    # 更新处理器节点的输出（添加第三个输出）
    if len(processor_node['outputs']) == 2:
        processor_node['outputs'].append({
            "localized_name": "详细报告JSON",
            "name": "详细报告JSON",
            "type": "STRING",
            "slot_index": 2,
            "links": [next_link_id]
        })

    # 添加链接
    workflow['links'].append([
        next_link_id,
        processor_node['id'],
        2,  # 第三个输出
        next_node_id,
        0,  # 第一个输入
        "STRING"
    ])

    # 更新工作流元数据
    workflow['last_node_id'] = next_node_id
    workflow['last_link_id'] = next_link_id

    # 保存工作流
    with open(workflow_path, 'w', encoding='utf-8') as f:
        json.dump(workflow, f, ensure_ascii=False, indent=None)

    print(f"  ✅ 已添加日志节点 (ID: {next_node_id})")
    return True


def main():
    """主函数"""
    workflow_dir = Path("/root/ComfyUI/user/default/workflows/0-批量veo3-grok3")

    if not workflow_dir.exists():
        print(f"❌ 工作流目录不存在: {workflow_dir}")
        return

    print("=" * 70)
    print("为批量工作流添加详细日志显示节点")
    print("=" * 70)

    # 处理所有工作流文件
    workflow_files = list(workflow_dir.glob("*.json"))
    updated_count = 0

    for workflow_file in workflow_files:
        if workflow_file.name.startswith('.'):
            continue

        try:
            if add_logger_node_to_workflow(workflow_file):
                updated_count += 1
        except Exception as e:
            print(f"  ❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 70)
    print(f"完成！共更新 {updated_count} 个工作流")
    print("=" * 70)


if __name__ == "__main__":
    main()
