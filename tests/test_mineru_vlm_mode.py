"""
测试 MinerU VLM 模式的简单脚本

用途：
1. 测试 VLM 模式是否能正常工作
2. 对比 VLM 模式和 Pipeline 模式的输出差异
3. 验证公式、表格、图片的提取质量

用法：
    # 测试 VLM 模式（默认）
    python tests/test_mineru_vlm_mode.py data/stored_files/你的文档.pdf

    # 对比两种模式
    python tests/test_mineru_vlm_mode.py data/stored_files/你的文档.pdf --compare
"""

import sys
import os
import json
import argparse
from pathlib import Path
from collections import Counter

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.mineru_toolkit import MineruComponent


def print_section(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def analyze_mineru_output(data, backend):
    """分析 MinerU 输出的结构"""
    print_section(f"{backend} 模式 - 输出分析")

    # 统计类型分布
    types = [d.get("type") for d in data if isinstance(d, dict)]
    type_dist = Counter(types)

    print(f"\n总元素数: {len(data)}")
    print(f"\n类型分布:")
    for t, count in type_dist.most_common():
        print(f"  {t}: {count}")

    # 详细分析每种类型
    for content_type in ["equation", "table", "image"]:
        if content_type in type_dist:
            print_section(f"{backend} 模式 - {content_type} 内容预览")
            count = 0
            for item in data:
                if item.get("type") == content_type and count < 3:
                    count += 1
                    print(f"\n[样本 {count}]")
                    if content_type == "equation" and "text" in item:
                        print(f"公式: {item['text'][:200]}")
                    elif content_type == "table":
                        if "table_caption" in item:
                            print(f"表格标题: {item['table_caption'][:100]}")
                        if "table_body" in item and item["table_body"]:
                            print(f"表格内容(前200字符): {item['table_body'][:200]}...")
                    elif content_type == "image" and "image_caption" in item:
                        print(f"图片描述: {item['image_caption'][:150]}")
                    print(f"完整字段: {list(item.keys())}")

    return type_dist


def compare_outputs(pipeline_data, vlm_data):
    """对比两种模式的输出"""
    print_section("模式对比分析")

    pipeline_types = Counter([d.get("type") for d in pipeline_data if isinstance(d, dict)])
    vlm_types = Counter([d.get("type") for d in vlm_data if isinstance(d, dict)])

    print("\n类型数量对比:")
    print(f"{'类型':<15} {'Pipeline':<12} {'VLM':<12} {'差异':<10}")
    print("-" * 50)
    all_types = set(pipeline_types.keys()) | set(vlm_types.keys())
    for t in sorted(all_types):
        p = pipeline_types.get(t, 0)
        v = vlm_types.get(t, 0)
        diff = v - p
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        print(f"{t:<15} {p:<12} {v:<12} {diff_str:<10}")


def test_single_backend(pdf_path, backend="vlm-transformers"):
    """测试单个后端"""
    print_section(f"测试 {backend} 模式")
    print(f"PDF 路径: {pdf_path}")

    mineru = MineruComponent()
    result = mineru.run(
        pdf_file_path=pdf_path,
        parse_method="auto",
        backend=backend
    )

    if result.status != "success":
        print(f"❌ 失败: {result.error}")
        return None

    print(f"✅ 成功 - 获取到 {len(result.data)} 个元素")
    return result.data


def main():
    parser = argparse.ArgumentParser(description="测试 MinerU VLM 模式")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument("--compare", action="store_true", help="对比 Pipeline 和 VLM 两种模式")
    parser.add_argument("--backend", choices=["pipeline", "vlm-transformers"], default="vlm-transformers",
                       help="选择后端模式")
    args = parser.parse_args()

    pdf_path = args.pdf_path
    if not os.path.exists(pdf_path):
        print(f"❌ 文件不存在: {pdf_path}")
        sys.exit(1)

    # 如果需要对比两种模式
    if args.compare:
        print_section("对比 Pipeline 和 VLM 两种模式")
        pipeline_data = test_single_backend(pdf_path, backend="pipeline")
        if not pipeline_data:
            print("Pipeline 模式测试失败")
            sys.exit(1)

        vlm_data = test_single_backend(pdf_path, backend="vlm-transformers")
        if not vlm_data:
            print("VLM 模式测试失败")
            sys.exit(1)

        compare_outputs(pipeline_data, vlm_data)
    else:
        # 只测试指定模式
        data = test_single_backend(pdf_path, backend=args.backend)
        if not data:
            sys.exit(1)

        analyze_mineru_output(data, args.backend)

    print_section("测试完成")
    print("\n💡 观察要点:")
    print("1. VLM 模式是否识别了更多类型的元素")
    print("2. 公式、表格、图片的描述是否更准确")
    print("3. 是否有新增的内容类型")


if __name__ == "__main__":
    main()
