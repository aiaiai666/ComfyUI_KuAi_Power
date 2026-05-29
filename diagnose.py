"""快速诊断脚本 - 检查所有配置和依赖"""

import sys
from pathlib import Path

def check_file_structure():
    """检查文件结构"""
    print("=" * 70)
    print("1. 文件结构检查")
    print("=" * 70)
    
    base_dir = Path(__file__).parent
    required_files = [
        "nodes/Sora2/__init__.py",
        "nodes/Sora2/kuai_utils.py",
        "nodes/Sora2/script_generator.py",
        "nodes/Sora2/sora2.py",
        "web/kuaipower_panel.js",
        "__init__.py",
        "requirements.txt",
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = base_dir / file_path
        if full_path.exists():
            print(f"   ✅ {file_path}")
        else:
            print(f"   ❌ {file_path} - 文件不存在！")
            all_exist = False
    
    print()
    return all_exist

def check_dependencies():
    """检查依赖"""
    print("=" * 70)
    print("2. 依赖检查")
    print("=" * 70)
    
    required_modules = {
        "requests": "requests",
        "PIL": "pillow",
        "numpy": "numpy",
        "pydantic": "pydantic",
        "pydantic_settings": "pydantic-settings",
    }
    
    all_installed = True
    for module_name, package_name in required_modules.items():
        try:
            __import__(module_name)
            print(f"   ✅ {package_name}")
        except ImportError:
            print(f"   ❌ {package_name} - 未安装！")
            all_installed = False
    
    print()
    return all_installed

def check_imports():
    """检查模块导入"""
    print("=" * 70)
    print("3. 模块导入检查")
    print("=" * 70)
    
    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))
    
    # 检查 kuai_utils
    try:
        from nodes.Sora2.kuai_utils import env_or, http_headers_json, http_headers_auth_only
        _ = (env_or, http_headers_json, http_headers_auth_only)
        print("   ✅ nodes.Sora2.kuai_utils")
    except Exception as e:
        print(f"   ❌ nodes.Sora2.kuai_utils - {e}")
        return False
    
    # 检查 script_generator
    try:
        from nodes.Sora2.script_generator import (
            ProductInfoBuilder,
            SoraPromptFromProduct,
        )
        print("   ✅ nodes.Sora2.script_generator (2 节点)")
    except Exception as e:
        print(f"   ❌ nodes.Sora2.script_generator - {e}")
        return False
    
    # 检查 sora2
    try:
        from nodes.Sora2.sora2 import (
            SoraCreateVideo,
            SoraQueryTask,
            SoraCreateAndWait
        )
        print("   ✅ nodes.Sora2.sora2 (3 节点)")
    except Exception as e:
        print(f"   ❌ nodes.Sora2.sora2 - {e}")
        return False
    
    # 检查 Sora2 __init__
    try:
        from nodes.Sora2 import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
        print(f"   ✅ nodes.Sora2 (统一导出 {len(NODE_CLASS_MAPPINGS)} 节点)")
    except Exception as e:
        print(f"   ❌ nodes.Sora2 - {e}")
        return False
    
    print()
    return True

def check_node_structure():
    """检查节点结构"""
    print("=" * 70)
    print("4. 节点结构检查")
    print("=" * 70)
    
    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))
    
    try:
        from nodes.Sora2 import NODE_CLASS_MAPPINGS
        
        required_attrs = ["INPUT_TYPES", "RETURN_TYPES", "FUNCTION", "CATEGORY"]
        all_valid = True
        
        for node_name, node_class in NODE_CLASS_MAPPINGS.items():
            missing = []
            for attr in required_attrs:
                if not hasattr(node_class, attr):
                    missing.append(attr)
            
            if missing:
                print(f"   ❌ {node_name} - 缺少: {', '.join(missing)}")
                all_valid = False
            else:
                category = getattr(node_class, "CATEGORY", "")
                print(f"   ✅ {node_name} ({category})")
        
        print()
        return all_valid
        
    except Exception as e:
        print(f"   ❌ 无法加载节点: {e}")
        print()
        return False

def check_categories():
    """检查节点分类"""
    print("=" * 70)
    print("5. 节点分类检查")
    print("=" * 70)
    
    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))
    
    try:
        from nodes.Sora2 import NODE_CLASS_MAPPINGS
        
        categories = {}
        for node_name, node_class in NODE_CLASS_MAPPINGS.items():
            category = getattr(node_class, "CATEGORY", "Unknown")
            if category not in categories:
                categories[category] = []
            categories[category].append(node_name)
        
        for category, nodes in categories.items():
            print(f"\n   📁 {category} ({len(nodes)} 节点):")
            for node in nodes:
                print(f"      - {node}")
        
        print()
        
        # 检查分类命名
        valid_categories = all(cat.startswith("KuAi/") for cat in categories.keys())
        if valid_categories:
            print("   ✅ 所有分类都以 'KuAi/' 开头")
        else:
            print("   ⚠️  部分分类不以 'KuAi/' 开头")
        
        print()
        return True
        
    except Exception as e:
        print(f"   ❌ 无法检查分类: {e}")
        print()
        return False

def main():
    """主诊断流程"""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "ComfyUI_KuAi_Power 诊断工具" + " " * 25 + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    results = []
    
    # 运行所有检查
    results.append(("文件结构", check_file_structure()))
    results.append(("依赖安装", check_dependencies()))
    results.append(("模块导入", check_imports()))
    results.append(("节点结构", check_node_structure()))
    results.append(("节点分类", check_categories()))
    
    # 总结
    print("=" * 70)
    print("诊断总结")
    print("=" * 70)
    
    all_passed = True
    for check_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"   {check_name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    
    if all_passed:
        print("🎉 所有检查通过！节点应该可以在 ComfyUI 中正常运行。")
        print()
        print("下一步：")
        print("   1. 启动 ComfyUI")
        print("   2. 检查控制台输出中的 [ComfyUI_KuAi_Power] 日志")
        print("   3. 按 Ctrl+Alt+F 打开节点面板")
        print("   4. 测试节点功能")
    else:
        print("⚠️  部分检查未通过，请根据上述错误信息进行修复。")
        print()
        print("常见解决方案：")
        print("   1. 安装缺失的依赖: pip install -r requirements.txt")
        print("   2. 检查文件路径和导入语句")
        print("   3. 确保所有 .py 文件语法正确")
    
    print()
    print("=" * 70)

if __name__ == "__main__":
    main()
