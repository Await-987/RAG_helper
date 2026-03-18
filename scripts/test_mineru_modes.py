#!/usr/bin/env python
"""
MinerU 解析模式测试工具

测试 MinerU 的 pipeline / VLM 两种解析模式，分析输出结构，
可对比两种模式在元素数量和类型分布上的差异。

用途：
  - 验证 MinerU 解析是否正常工作
  - 对比 pipeline 和 VLM 模式的提取质量
  - 查看公式、表格、图片的提取结果

用法:
    python scripts/test_mineru_modes.py <pdf路径>
    python scripts/test_mineru_modes.py <pdf路径> --backend pipeline
    python scripts/test_mineru_modes.py <pdf路径> --compare
"""
import sys
import argparse
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.mineru_toolkit import MineruComponent


def print_section(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def analyze_output(data, backend):
    """分析 MinerU 输出的结构与内容"""
    print_section(f"{backend} 模式 - 输出分析")

    types = [d.get("type") for d in data if isinstance(d, dict)]
    type_dist = Counter(types)

    print(f"\n总元素数: {len(data)}")
    print("\n类型分布:")
    for t, count in type_dist.most_common():
        print(f"  {t}: {count}")

    for content_type in ["equation", "table", "image"]:
        if content_type not in type_dist:
            continue
        print_section(f"{backend} 模式 - {content_type} 内容预览")
        shown = 0
        for item in data:
            if item.get("type") != content_type or shown >= 3:
                continue
            shown += 1
            print(f"\n[样本 {shown}]")
            if content_type == "equation" and "text" in item:
                print(f"公式: {item['text'][:200]}")
            elif content_type == "table":
                if "table_caption" in item:
                    print(f"表格标题: {item['table_caption'][:100]}")
                if item.get("table_body"):
                    print(f"表格内容(前200字符): {item['table_body'][:200]}...")
            elif content_type == "image" and "image_caption" in item:
                print(f"图片描述: {item['image_caption'][:150]}")
            print(f"字段列表: {list(item.keys())}")

    return type_dist


def compare_outputs(pipeline_data, vlm_data):
    """对比两种模式的类型分布"""
    print_section("模式对比分析")

    p_types = Counter([d.get("type") for d in pipeline_data if isinstance(d, dict)])
    v_types = Counter([d.get("type") for d in vlm_data if isinstance(d, dict)])

    print(f"\n{'类型':<15} {'Pipeline':<12} {'VLM':<12} {'差异':<10}")
    print("-" * 50)
    for t in sorted(set(p_types) | set(v_types)):
        p, v = p_types.get(t, 0), v_types.get(t, 0)
        diff = v - p
        print(f"{t:<15} {p:<12} {v:<12} {'+' + str(diff) if diff > 0 else str(diff):<10}")


def run_backend(pdf_path: str, backend: str):
    """运行指定后端并返回解析数据"""
    print_section(f"测试 {backend} 模式")
    print(f"PDF 路径: {pdf_path}")

    mineru = MineruComponent()
    result = mineru.run(pdf_file_path=pdf_path, parse_method="auto", backend=backend)

    if result.status != "success":
        print(f"失败: {result.error}")
        return None

    print(f"成功 - 获取到 {len(result.data)} 个元素")
    return result.data


def main():
    parser = argparse.ArgumentParser(description="测试 MinerU 解析模式")
    parser.add_argument("pdf_path", help="PDF 文件路径")
    parser.add_argument(
        "--backend",
        choices=["pipeline", "vlm-transformers"],
        default="vlm-transformers",
        help="解析后端（默认: vlm-transformers）",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="同时运行 pipeline 和 VLM 两种模式并对比结果",
    )
    args = parser.parse_args()

    pdf_path = str(Path(args.pdf_path).resolve())
    if not Path(pdf_path).exists():
        print(f"文件不存在: {pdf_path}")
        sys.exit(1)

    if args.compare:
        print_section("对比 Pipeline 和 VLM 两种模式")
        pipeline_data = run_backend(pdf_path, "pipeline")
        if not pipeline_data:
            sys.exit(1)
        vlm_data = run_backend(pdf_path, "vlm-transformers")
        if not vlm_data:
            sys.exit(1)
        compare_outputs(pipeline_data, vlm_data)
    else:
        data = run_backend(pdf_path, args.backend)
        if not data:
            sys.exit(1)
        analyze_output(data, args.backend)

    print_section("完成")
    print("\n观察要点:")
    print("1. VLM 模式是否识别了更多类型的元素")
    print("2. 公式、表格、图片的描述是否更准确")
    print("3. 是否有新增的内容类型")


if __name__ == "__main__":
    main()
