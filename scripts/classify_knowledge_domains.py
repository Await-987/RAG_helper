#!/usr/bin/env python3
"""Classify knowledge-base source files by title.

The project stores MinerU content-list JSON files under data/content_lists.
Each file name corresponds to one source document.  This script uses a small
set of deterministic domain rules to summarize the current database coverage.
It intentionally avoids model calls so the result is reproducible in offline
deployment environments.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class DomainRule:
    name: str
    patterns: tuple[str, ...]


DOMAIN_RULES: tuple[DomainRule, ...] = (
    DomainRule("输变电工程综合规范", ("输变电", "变电工程", "送变电", "电网工程", "通用设计", "通用设备")),
    DomainRule("变电站与高压电气", ("变电站", "智能变电站", "GIS", "HGIS", "高压电器", "电气设备", "开关柜", "断路器", "隔离开关", "互感器", "避雷器", "变压器", "电抗器", "电容器", "套管", "绝缘子")),
    DomainRule("输电线路与架空线路", ("输电线路", "架空输电", "架空送电", "架空线路", "杆塔", "导线", "线路工程", "送电线路", "螺旋锚", "机械化施工")),
    DomainRule("配电网与中低压工程", ("配电网", "配电线路", "配电工程", "配电设计", "10kV", "10千伏", "20kV", "20KV", "35kV", "35～", "35~", "低压", "中压")),
    DomainRule("电缆与海底电缆", ("电缆", "海底电缆", "电缆沟", "电缆线路", "敷设")),
    DomainRule("新能源、光伏与储能并网", ("光伏", "风电", "新能源", "分布式电源", "储能", "并网", "源网荷储", "充电", "电化学储能")),
    DomainRule("施工、验收与标准工艺", ("施工", "验收", "标准工艺", "安装", "达标投产", "质量验收", "施工图", "施工许可")),
    DomainRule("项目管理、监理与业主项目部", ("项目部", "监理", "业主项目部", "标准化管理", "管理手册", "建设管理", "项目管理")),
    DomainRule("造价、定额与技经管理", ("造价", "定额", "概预算", "预算", "概算", "估算", "计价", "费用", "技经", "工程量清单", "结算", "取费", "信息价")),
    DomainRule("安全、质量与风险管控", ("安全", "质量", "风险", "反事故", "隐患", "故障", "抗震", "防治", "文明施工")),
    DomainRule("通信、自动化与二次系统", ("通信", "自动化", "二次", "继电保护", "一键顺控", "调度", "电压互感器", "电流互感器")),
    DomainRule("电能质量、防雷与接地", ("电能质量", "谐波", "间谐波", "过电压", "防雷", "接地", "绝缘配合", "火灾自动报警")),
    DomainRule("规划许可、土地与城市建设法规", ("规划许可", "建设工程规划", "土地", "城乡", "城市规划", "国土", "空间规划", "控制线", "用地", "不动产", "农田", "房屋", "征收", "房屋补偿", "绿化", "古树名木", "日照", "地下空间")),
    DomainRule("环保、水保与绿色建造", ("环保", "环境", "水保", "绿色建造", "环境影响", "生态", "六五环境日", "黑土地保护", "排放", "污水", "废水", "水污染", "大气污染", "污染物", "危险废物", "土壤", "噪声", "水土", "节能", "自然保护区")),
    DomainRule("运维、检修与技改", ("运维", "检修", "技术改造", "预防性试验", "运行", "维护")),
    DomainRule("建筑、土建与消防配套", ("建筑", "土建", "混凝土", "钢筋", "砌体", "地基", "基坑", "幕墙", "门窗", "消防", "火灾", "灭火", "防火", "道路照明", "车库", "垃圾处理")),
    DomainRule("发电厂、水电与电力系统基础", ("火力发电厂", "发电厂", "水电", "水轮发电机", "厂用电", "电力系统设计", "电力系统安全稳定", "电力工程制图", "供配电")),
    DomainRule("会议材料、计划与综合文件", ("会议", "工作报告", "实施计划", "实践成果", "文件目录", "汇编", "讲话")),
)


def normalize_title(path: Path) -> str:
    title = path.name
    title = re.sub(r"_content_list\.json$", "", title)
    title = re.sub(r"^\d+[.\-、]?", "", title)
    title = title.replace(" - 副本", "")
    return title.strip()


def classify_title(title: str) -> list[str]:
    matched: list[str] = []
    upper_title = title.upper()
    for rule in DOMAIN_RULES:
        for pattern in rule.patterns:
            pattern_upper = pattern.upper()
            if pattern in title or pattern_upper in upper_title:
                matched.append(rule.name)
                break
    return matched or ["其他/待人工复核"]


def iter_titles(content_lists_dir: Path) -> Iterable[tuple[Path, str]]:
    for path in sorted(content_lists_dir.glob("*_content_list.json")):
        if path.is_file():
            yield path, normalize_title(path)


def build_summary(content_lists_dir: Path, example_limit: int) -> dict:
    per_file: list[dict] = []
    counter: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)

    for path, title in iter_titles(content_lists_dir):
        domains = classify_title(title)
        per_file.append(
            {
                "file": path.name,
                "title": title,
                "domains": domains,
            }
        )
        for domain in domains:
            counter[domain] += 1
            if len(examples[domain]) < example_limit:
                examples[domain].append(title)

    return {
        "content_lists_dir": str(content_lists_dir),
        "total_files": len(per_file),
        "domain_counts": dict(counter.most_common()),
        "domain_examples": {k: examples[k] for k, _ in counter.most_common()},
        "files": per_file,
    }


def write_markdown(summary: dict, output_path: Path) -> None:
    lines = [
        "# 知识库文件领域覆盖分类报告",
        "",
        f"- 数据来源：`{summary['content_lists_dir']}`",
        f"- 文件总数：{summary['total_files']}",
        "- 分类方法：基于文件题名的确定性关键词规则；一个文件可命中多个领域。",
        "",
        "## 领域统计",
        "",
        "| 领域 | 命中文件数 | 示例题名 |",
        "|---|---:|---|",
    ]
    for domain, count in summary["domain_counts"].items():
        examples = "；".join(summary["domain_examples"].get(domain, [])[:3])
        lines.append(f"| {domain} | {count} | {examples} |")

    lines.extend(["", "## 文件明细", ""])
    for item in summary["files"]:
        lines.append(f"- {item['title']}：{'、'.join(item['domains'])}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--content-lists-dir",
        default="data/content_lists",
        help="Directory containing *_content_list.json files.",
    )
    parser.add_argument(
        "--json-output",
        default="data/knowledge_domain_classification.json",
        help="Path to write machine-readable summary.",
    )
    parser.add_argument(
        "--md-output",
        default="data/knowledge_domain_classification.md",
        help="Path to write Markdown summary.",
    )
    parser.add_argument("--example-limit", type=int, default=8)
    args = parser.parse_args()

    content_lists_dir = Path(args.content_lists_dir)
    summary = build_summary(content_lists_dir, args.example_limit)

    json_output = Path(args.json_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_output = Path(args.md_output)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(summary, md_output)

    print(f"Classified {summary['total_files']} files")
    for domain, count in summary["domain_counts"].items():
        print(f"{domain}: {count}")


if __name__ == "__main__":
    main()
