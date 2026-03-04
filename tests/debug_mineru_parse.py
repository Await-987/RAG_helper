"""
调试 MinerU 解析结果，检查表22的内容
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.mineru_toolkit import MineruComponent
from tools.load_files import preprocess
import json
from pathlib import Path

mineru = MineruComponent()
pdf_path = 'data/stored_files/GB20052-2020 电力变压器能效限定值及能效等级.pdf'

print('=' * 60)
print('1. Pipeline 模式解析')
print('=' * 60)
result_pipeline = mineru.run(pdf_file_path=pdf_path, backend='pipeline')
if result_pipeline.status == 'success':
    print(f'Pipeline: 获取到 {len(result_pipeline.data)} 个元素')
    types_p = {}
    # 检查表22
    table_22_found = []
    for i, item in enumerate(result_pipeline.data):
        t = item.get('type')
        types_p[t] = types_p.get(t, 0) + 1

        # 查找包含"表22"的表格
        if t == 'table':
            caption = item.get('table_caption', '')
            if '22' in caption or '表22' in caption:
                table_22_found.append({
                    'index': i,
                    'caption': caption,
                    'table_body': item.get('table_body', '')[:200]
                })

    print(f'Pipeline 类型分布: {types_p}')
    print(f'Pipeline 找到表22相关: {len(table_22_found)} 个')
    for t in table_22_found[:3]:
        print(f'  - {t["caption"]}')
else:
    print(f'Pipeline 失败: {result_pipeline.error}')

print()
print('=' * 60)
print('2. VLM 模式解析')
print('=' * 60)
result_vlm = mineru.run(pdf_file_path=pdf_path, backend='vlm-transformers')
if result_vlm.status == 'success':
    print(f'VLM: 获取到 {len(result_vlm.data)} 个元素')
    types_v = {}
    # 检查所有 text 中是否有表22
    text_22_found = []
    for i, item in enumerate(result_vlm.data):
        t = item.get('type')
        types_v[t] = types_v.get(t, 0) + 1

        if t == 'text':
            text = item.get('text', '')
            if '表22' in text or '22' in text:
                text_22_found.append({
                    'index': i,
                    'text': text[:150]
                })

    print(f'VLM 类型分布: {types_v}')
    print(f'VLM text 中找到"表22": {len(text_22_found)} 处')
    for t in text_22_found[:3]:
        print(f'  - {t["text"]}')
else:
    print(f'VLM 失败: {result_vlm.error}')

print()
print('=' * 60)
print('3. 混合模式合并结果')
print('=' * 60)

# 合并：Pipeline 的 table，VLM 的其他
combined = []
if result_pipeline.status == 'success':
    for item in result_pipeline.data:
        if item.get('type') == 'table':
            combined.append(item)

if result_vlm.status == 'success':
    for item in result_vlm.data:
        if item.get('type') != 'table':
            combined.append(item)

print(f'合并后总元素数: {len(combined)}')

# 统计合并后的类型
types_combined = {}
for item in combined:
    t = item.get('type')
    types_combined[t] = types_combined.get(t, 0) + 1
print(f'合并后类型分布: {types_combined}')

# 查找合并后的 table 列表
tables_in_combined = [item for item in combined if item.get('type') == 'table']
print(f'合并后的表格数量: {len(tables_in_combined)}')

# 打印所有表格标题
print()
print('所有表格标题:')
for i, t in enumerate(tables_in_combined):
    caption = t.get('table_caption', '')
    body_len = len(t.get('table_body', ''))
    print(f'{i+1}. {caption} (内容长度: {body_len})')

# 保存解析结果
output = {
    'summary': {
        'pdf_file': pdf_path,
        'pipeline_status': result_pipeline.status,
        'vlm_status': result_vlm.status,
        'combined_element_count': len(combined),
        'table_count': len(tables_in_combined),
        'table_captions': [t.get('table_caption', '') for t in tables_in_combined]
    },
    'pipeline': {
        'element_count': len(result_pipeline.data) if result_pipeline.data else 0,
        'type_distribution': types_p,
        'tables': [item for item in (result_pipeline.data or []) if item.get('type') == 'table']
    },
    'vlm': {
        'element_count': len(result_vlm.data) if result_vlm.data else 0,
        'type_distribution': types_v
    },
    'combined': {
        'element_count': len(combined),
        'data': combined
    }
}

output_path = Path('data/stored_files/mineru解析结果.json')
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f'\n解析结果已保存到: {output_path}')
