"""
只用 Pipeline 模式快速解析，查看表格内容
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.mineru_toolkit import MineruComponent
import json
from pathlib import Path

mineru = MineruComponent()
pdf_path = 'data/stored_files/GB20052-2020 电力变压器能效限定值及能效等级.pdf'

print('Pipeline 模式解析...')
result = mineru.run(pdf_file_path=pdf_path, backend='pipeline')

if result.status == 'success':
    data = result.data
    print(f'总元素数: {len(data)}')

    # 统计类型
    types = {}
    for item in data:
        t = item.get('type')
        types[t] = types.get(t, 0) + 1
    print(f'类型分布: {types}')

    # 找出所有表格
    tables = [item for item in data if item.get('type') == 'table']
    print(f'\n找到 {len(tables)} 个表格\n')

    # 打印所有表格
    for i, table in enumerate(tables):
        caption = table.get('table_caption', '')
        body = table.get('table_body', '')
        print(f'=== 表格 {i+1} ===')
        print(f'标题: {caption}')
        print(f'内容长度: {len(body)}')
        print(f'内容预览: {body[:150]}...')
        print()

    # 查找包含数字22的表格
    table_22 = [t for t in tables if '22' in t.get('table_caption', '')]
    print(f'\n找到包含"22"的表格: {len(table_22)} 个')
    for t in table_22:
        print(f'- {t.get("table_caption", "")}')

    # 保存完整结果
    output = {
        'total_elements': len(data),
        'type_distribution': types,
        'tables': tables,
        'table_count': len(tables)
    }

    output_path = Path('data/stored_files/mineru_Pipeline解析结果.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'完整结果已保存到: {output_path}')
else:
    print(f'解析失败: {result.error}')
