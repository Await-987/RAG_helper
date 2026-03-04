# @ wangpei
import os
from tools import MineruComponent
from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input
from typing import *
mineru_tool = MineruComponent()
from pathlib import Path

def debug_data_structure(data: list, limit: int = 20, search_keyword: str = None) -> None:
    """调试：打印 data 中前 N 个 item 的结构，并搜索关键词"""
    print("\n" + "="*60)
    print(f"=== DEBUG: MinerU content_list 结构预览 (共 {len(data)} 项) ===")
    if search_keyword:
        print(f"=== 搜索关键词: '{search_keyword}' ===")
    print("="*60)

    table_count = 0
    equation_count = 0
    text_count = 0
    found_items = []  # 存储包含关键词的项

    for i, item in enumerate(data[:limit] if not search_keyword else data):
        item_type = item.get('type')

        # 搜索关键词
        if search_keyword:
            item_str = str(item).lower()
            if search_keyword.lower() in item_str:
                found_items.append((i, item))

        # 非搜索模式下，打印前 limit 项
        if not search_keyword and i < limit:
            print(f"\n[{i}] type={item_type}")

            if item_type == 'table':
                table_count += 1
                caption = item.get('table_caption', [])
                print(f"    - table_caption: {caption}")
                has_body = 'table_body' in item
                print(f"    - has table_body: {has_body}")
                if has_body:
                    body = item['table_body']
                    if isinstance(body, str):
                        print(f"    - table_body 长度: {len(body)}")
                        print(f"    - table_body 前150字符: {body[:150]}...")
                    else:
                        print(f"    - table_body 类型: {type(body)}")
                footnote = item.get('table_footnote', [])
                if footnote:
                    print(f"    - table_footnote: {footnote}")

            elif item_type == 'equation':
                equation_count += 1
                text = item.get('text', '')
                print(f"    - equation (LaTeX): {text[:80]}...")

            elif item_type == 'text':
                text_count += 1
                text = item.get('text', '')
                print(f"    - text: {text[:80]}...")

            elif item_type == 'image':
                caption = item.get('image_caption', [])
                footnote = item.get('image_footnote', [])
                print(f"    - image_caption: {caption}")
                print(f"    - has image_footnote: {bool(footnote)}")

            elif item_type == 'discarded':
                print(f"    - [已丢弃: 页眉页脚等]")

    # 如果搜索模式，打印找到的结果
    if search_keyword and found_items:
        print(f"\n=== 找到 {len(found_items)} 项包含 '{search_keyword}' ===")
        for idx, item in found_items:
            print(f"\n[{idx}] type={item.get('type')}")
            if item.get('type') == 'table':
                caption = item.get('table_caption', [])
                print(f"    - table_caption: {caption}")
                has_body = 'table_body' in item
                print(f"    - has table_body: {has_body}")
                if has_body:
                    body = item['table_body']
                    if isinstance(body, str):
                        print(f"    - table_body 长度: {len(body)}")
                        print(f"    - table_body 内容预览: {body[:200]}...")
            elif item.get('type') == 'text':
                text = item.get('text', '')
                print(f"    - text: {text[:150]}...")

    # 统计信息
    if not search_keyword:
        print("\n" + "="*60)
        print(f"=== 统计: 前{limit}项中 table={table_count}, equation={equation_count}, text={text_count} ===")
        print(f"=== 提示: 如果没找到表格，表格可能在{limit}项之后 ===")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print(f"=== 搜索完成: 找到 {len(found_items)} 项 ===")
        print("="*60 + "\n")


def preprocess(data: list, chunk_min_size: int = 500, overlap_size: int = 100, debug: bool = False, search_keyword: str = None,
                 split_tables: bool = True) -> Tuple[List[str], List[List[str]]]:
    # 调试模式：打印数据结构
    if debug:
        debug_data_structure(data, limit=30, search_keyword=search_keyword)

    # @luxinrong：20260304修改：预处理多标题表格问题
    # 当一个表格有多个标题时，检查后续的空标题表格，将多余的标题分配给后续表格
    def fix_multi_caption_tables(data_list):
        """修复多标题表格问题：将多余的标题分配给后续的空标题表格"""
        fixed_count = 0
        i = 0
        while i < len(data_list):
            item = data_list[i]
            if item.get('type') == 'table':
                caption = item.get('table_caption', [])
                # 检查是否有多余的标题（超过1个，或包含空字符串）
                if len(caption) > 1:
                    # 查找后续的空标题表格
                    j = i + 1
                    extra_captions = caption[1:]  # 第一个标题保留，其余的分配给后续表格
                    while j < len(data_list) and extra_captions:
                        next_item = data_list[j]
                        if next_item.get('type') == 'table':
                            next_caption = next_item.get('table_caption', [])
                            # 如果后续表格是空标题（[] 或 ['']），分配一个标题给它
                            if not next_caption or (len(next_caption) == 1 and next_caption[0] == ''):
                                assigned = extra_captions.pop(0)
                                next_item['table_caption'] = [assigned]
                                fixed_count += 1
                                if debug:
                                    print(f"[FIX] 分配标题给idx={j}: {assigned[:50]}...")
                            else:
                                # 后续表格有标题，停止分配
                                break
                        j += 1
                    # 当前表格只保留第一个标题
                    item['table_caption'] = [caption[0]]
                elif len(caption) == 1 and caption[0] == '':
                    # 处理空字符串标题，改为无标题
                    item['table_caption'] = []
            i += 1

        if debug and fixed_count > 0:
            print(f"[FIX] 共修复了 {fixed_count} 个空标题表格的标题分配问题")
        return data_list

    # 执行多标题表格修复
    data = fix_multi_caption_tables(data)

    print(f"[DEBUG] 开始 chunk 生成，共 {len(data)} 项...")

    type2key = {
        'text': 'text',
        'equation': 'text',
        'image': 'image_caption',
        'table': 'table_caption',
        'list': 'text',           # 新增：支持 list 类型
        'footer': 'text',          # 新增：支持 footer 类型
        'page_number': 'text',     # 新增：支持 page_number 类型
        'code': 'code_body',       # 新增：支持 code 类型
    }

    table_body = 'table_body'

    def extract_equation_content(equation_item, data_list, current_idx):
        """
        提取公式的完整内容：
        - 公式正文（LaTeX）

        注意：不做 lookahead 消费，让 chunk 级别自然组合相邻 text

        返回: (content: str, consumed_count: int)
            content: 提取的内容
            consumed_count: 消费的后续 items 数量（固定为 0）
        """
        latex_text = equation_item.get('text', '')

        if latex_text:
            content = '公式: ' + latex_text
        else:
            content = ''

        return content, 0  # 不消费任何后续 items

    def extract_image_content(image_item):
        """
        提取图片的完整内容：
        - 图片描述（image_caption）
        - 图片脚注（image_footnote）
        """
        content_parts = []

        # 添加图片描述
        caption = image_item.get('image_caption', [])
        if caption:
            content_parts.append('图片: ' + ' '.join(caption))

        # 添加图片脚注
        footnote = image_item.get('image_footnote', [])
        if footnote:
            content_parts.append('图片脚注: ' + ' '.join(footnote))

        return '\n'.join(content_parts)

    def latex_to_plain_text(latex_str: str) -> str:
        """
        将简单的 LaTeX 公式转换为普通文本
        例如: $5 0 0 ~ \mathbf { k V }$ → 500kV
        """
        import re

        # 移除 $...$ 包裹
        text = re.sub(r'\$([^$]*)\$', r'\1', latex_str)

        # 处理常见 LaTeX 命令
        # \mathbf{xxx} 或 \mathbf{ xxx } → xxx
        text = re.sub(r'\\mathbf\s*\{([^}]*)\}', r'\1', text)
        text = re.sub(r'\\mathbf\s*\{\s*([^}]+)\s*\}', r'\1', text)
        # \textit{xxx} → xxx
        text = re.sub(r'\\textit\s*\{([^}]*)\}', r'\1', text)
        # \mathrm{xxx} → xxx
        text = re.sub(r'\\mathrm\s*\{([^}]*)\}', r'\1', text)

        # 处理特殊符号
        # ~ 空格
        text = text.replace('~', ' ')
        # \quad 空格
        text = text.replace(r'\quad', ' ')
        # \qquad 更大空格
        text = text.replace(r'\qquad', ' ')
        # \ (反斜杠+空格) LaTeX 空格命令
        text = re.sub(r'\\(\s+)', ' ', text)

        # 移除花括号内的多余空格 { k V } → kV
        text = re.sub(r'\{\s*([^{}]+)\s*\}', r'\1', text)

        # 移除所有花括号
        text = text.replace('{', '').replace('}', '')

        # 合并连续空格后完全移除（如 "5 0 0" → "500"）
        text = re.sub(r'\s+', '', text)

        # 处理单位和数字的常见组合
        # 例如: kV, MPa, mm, % 等

        return text.strip()

    def extract_table_content(table_item):
        """提取表格的完整内容"""
        content_parts = []

        # 添加表格标题
        caption = table_item.get('table_caption', [])

        if debug and caption:
            print(f"[DEBUG] extract_table_content: 标题长度={len(' '.join(caption))}")
        # 正确处理空标题：[] 或 [''] 都视为无标题
        has_valid_caption = caption and not (len(caption) == 1 and caption[0] == '')

        if has_valid_caption:
            caption_text = ' '.join(caption)

            # 将LaTeX公式转换为普通文本用于向量匹配
            import re
            converted_caption = caption_text
            latex_pattern = r'\$([^$]*)\$'
            latex_matches = re.findall(latex_pattern, caption_text)
            if latex_matches:
                for latex_match in latex_matches:
                    plain_text = latex_to_plain_text(latex_match)
                    if plain_text:
                        # 用转换后的普通文本替换原LaTeX公式
                        converted_caption = converted_caption.replace(f'${latex_match}$', plain_text, 1)

            # 清理多余空格
            converted_caption = re.sub(r'\s+', ' ', converted_caption).strip()

            # 如果转换后有变化，添加转换版本到开头用于向量匹配
            if converted_caption != caption_text:
                content_parts.append(f'表格标题: {converted_caption}')

            # 原始标题（保留完整内容，包括LaTeX）
            content_parts.append(caption_text)
        else:
            # 空标题表格，添加占位符
            content_parts.append('[表格]')

        # 直接添加 table_body 原始内容，不做任何处理
        has_body = table_body in table_item and table_item[table_body]
        if has_body:
            body_content = table_item[table_body]
            if debug:
                print(f"[DEBUG] extract_table_content: table_body 长度={len(body_content)}")
            if body_content and body_content.strip():
                content_parts.append(body_content)
            else:
                content_parts.append('[表格正文为空]')
        else:
            content_parts.append('[无表格正文数据]')

        # 添加表格脚注
        footnote = table_item.get('table_footnote', [])
        if footnote:
            content_parts.append(' '.join(footnote))

        if debug:
            separator = '\n'
            print(f"[DEBUG] extract_table_content: 返回，总长度={len(separator.join(content_parts))}")

        return '\n'.join(content_parts)

    new_chunks = []
    chunk_types = []  # @luxinrong：20260303修改：记录每个 chunk 包含的类型（equation, table 等）

    # 调试：跟踪 chunk 生成
    chunk_debug_info = []

    idx = 0
    chunk_num = 0
    while idx < len(data):
        new_chunk = ''
        types_in_chunk = []  # @luxinrong：20260303修改：当前 chunk 的类型列表
        chunk_start_idx = idx  # 记录 chunk 起始索引

        # 新增：如果当前项是表格，且 split_tables=True，则让表格独立成chunk
        if split_tables and data[idx].get('type') == 'table':
            chunk_type = 'table'
            chunk_key = type2key[chunk_type]
            if debug:
                print(f"[DEBUG] 处理独立表格 idx={idx}/{len(data)}...")
            content = extract_table_content(data[idx])
            new_chunk = content + '\n'
            types_in_chunk.append('table')

            idx += 1
            # 完成当前chunk
            new_chunks.append(new_chunk)
            chunk_types.append(types_in_chunk)

            # 调试：记录
            chunk_debug_info.append({
                'chunk_num': chunk_num,
                'start_idx': chunk_start_idx,
                'end_idx': idx,
                'length': len(new_chunk),
                'types': types_in_chunk.copy(),
                'preview': new_chunk[:100].replace('\n', ' '),
                'is_standalone_table': True
            })
            chunk_num += 1
            continue

        while len(new_chunk) < chunk_min_size and idx < len(data):
            # @luxinrong 20260304修改：如果遇到表格且split_tables=True，跳出内层循环
            if split_tables and data[idx].get('type') == 'table':
                break  # 跳出内层循环，让表格在外层循环中独立处理
            # chunk_type = data[idx]['type']
            # chunk_key = type2key[chunk_type]
            # @luxinrong：20260126修改：处理未知类型报错，遇到 discarded 或其他未知类型就直接跳过，不会 KeyError
            chunk_type = data[idx].get('type')
            if chunk_type not in type2key:
                idx += 1
                continue
            chunk_key = type2key[chunk_type]

            # 提取内容
            content = ''
            skip_count = 0  # 公式需要跳过的后续 items 数量
            if chunk_type == 'table':
                # 表格：提取完整内容（标题+正文+脚注）
                content = extract_table_content(data[idx])
                new_chunk += content
            elif chunk_type == 'equation':
                # 公式：提取完整内容（公式正文+标号+解释），返回需要跳过的 items 数量
                content, skip_count = extract_equation_content(data[idx], data, idx)
                new_chunk += content
            elif chunk_type == 'image':
                # 图片：提取完整内容（描述+脚注）
                content = extract_image_content(data[idx])
                new_chunk += content
            else:
                # 其他类型：按原逻辑处理
                if isinstance(data[idx][chunk_key], str):
                    content = data[idx][chunk_key]
                    new_chunk += content
                elif isinstance(data[idx][chunk_key], List):
                    content = ','.join(data[idx][chunk_key])
                    new_chunk += content

            # @luxinrong：20260303修改：记录类型（equation、table、image 特殊标记）
            if chunk_type in ('equation', 'table', 'image'):
                if chunk_type not in types_in_chunk:
                    types_in_chunk.append(chunk_type)

            idx += 1 + skip_count  # 跳过已被公式消费的后续 items

        # 如果chunk为空（比如因为遇到表格而break），跳过这个chunk
        # 如果split_tables=True且当前item是表格，continue让它在外层循环中被独立处理
        # 避免进入overlap阶段导致死循环
        if split_tables and idx < len(data) and data[idx].get('type') == 'table':
            continue

        if new_chunk.strip():
            new_chunk += '\n'
            new_chunks.append(new_chunk)
            chunk_types.append(types_in_chunk)

            # 调试：记录 chunk 信息
            chunk_debug_info.append({
                'chunk_num': chunk_num,
                'start_idx': chunk_start_idx,
                'end_idx': idx,
                'length': len(new_chunk),
                'types': types_in_chunk.copy(),
                'preview': new_chunk[:100].replace('\n', ' ')
            })
            chunk_num += 1

        # 检查是否已完成所有数据处理
        if idx >= len(data):
            print(f"[DEBUG] 所有数据处理完成，共生成 {len(new_chunks)} 个 chunk，准备返回...")

            # 调试：打印 chunk 生成摘要（在return之前）
            print("\n" + "="*60)
            print(f"=== Chunk 生成摘要 (共 {len(new_chunks)} 个) ===")
            print("="*60)

            # 打印前5个chunk
            print("\n前5个chunk:")
            for info in chunk_debug_info[:5]:
                standalone = " [独立表格]" if info.get('is_standalone_table') else ""
                print(f"  Chunk {info['chunk_num']}: items[{info['start_idx']}:{info['end_idx']}], "
                      f"长度={info['length']}, 类型={info['types']}{standalone}")
                print(f"    预览: {info['preview']}...")

            # 查找独立表格的chunk
            standalone_tables = [info for info in chunk_debug_info if info.get('is_standalone_table')]
            if standalone_tables:
                print(f"\n独立表格chunk (共{len(standalone_tables)}个):")
                for info in standalone_tables:
                    print(f"  Chunk {info['chunk_num']}: items[{info['start_idx']}], "
                          f"长度={info['length']}")
                    print(f"    预览: {info['preview']}...")

            # 查找表27
            table_27_chunks = [info for info in chunk_debug_info if '表27' in info.get('preview', '')]
            if table_27_chunks:
                print(f"\n包含表27的chunk:")
                for info in table_27_chunks:
                    print(f"  Chunk {info['chunk_num']}: items[{info['start_idx']}:{info['end_idx']}], "
                          f"长度={info['length']}")
                    print(f"    完整预览: {new_chunks[info['chunk_num']][:200]}...")

            print("="*60 + "\n")

            return new_chunks, chunk_types  # @luxinrong：20260303修改：返回文本和类型

        temp_chunk = ''
        while len(temp_chunk) < overlap_size:
            # chunk_type = data[idx - 1]['type']
            # chunk_key = type2key[chunk_type]
            # @luxinrong：20260126修改：overlap 阶段遇到未知类型，直接停止回退
            chunk_type = data[idx - 1].get('type')
            if chunk_type not in type2key:
                break
            # @luxinrong：20260304修改：split_tables=True 时，overlap 阶段遇到表格应该停止回退
            # 因为表格会被独立处理，不应该包含在 overlap 中
            if split_tables and chunk_type == 'table':
                break
            chunk_key = type2key[chunk_type]

            # 提取内容（与主逻辑保持一致）
            if chunk_type == 'table':
                content = extract_table_content(data[idx - 1])
                temp_chunk += content
            elif chunk_type == 'equation':
                # 公式：提取完整内容（公式正文+标号+解释）
                # overlap 阶段不需要 skip_count，因为是向后回退
                content, _ = extract_equation_content(data[idx - 1], data, idx - 1)
                temp_chunk += content
            elif chunk_type == 'image':
                # 图片：提取完整内容（描述+脚注）
                content = extract_image_content(data[idx - 1])
                temp_chunk += content
            else:
                if isinstance(data[idx - 1][chunk_key], str):
                    temp_chunk += data[idx - 1][chunk_key]
                elif isinstance(data[idx - 1][chunk_key], List):
                    temp_chunk += ','.join(data[idx - 1][chunk_key])
            idx -= 1
        if len(new_chunk) - len(temp_chunk) < 10:
            idx += 1
    # @luxinrong：20260126修改兜底：外层 while 正常结束时也要返回

    # 调试：打印 chunk 生成摘要
    print("\n" + "="*60)
    print(f"=== Chunk 生成摘要 (共 {len(new_chunks)} 个) ===")
    print("="*60)

    # 打印前5个chunk
    print("\n前5个chunk:")
    for info in chunk_debug_info[:5]:
        standalone = " [独立表格]" if info.get('is_standalone_table') else ""
        print(f"  Chunk {info['chunk_num']}: items[{info['start_idx']}:{info['end_idx']}], "
              f"长度={info['length']}, 类型={info['types']}{standalone}")
        print(f"    预览: {info['preview']}...")

    # 查找独立表格的chunk
    standalone_tables = [info for info in chunk_debug_info if info.get('is_standalone_table')]
    if standalone_tables:
        print(f"\n独立表格chunk (共{len(standalone_tables)}个):")
        for info in standalone_tables:
            print(f"  Chunk {info['chunk_num']}: items[{info['start_idx']}], "
                  f"长度={info['length']}")
            print(f"    预览: {info['preview']}...")

    # 查找表27
    table_27_chunks = [info for info in chunk_debug_info if '表27' in info.get('preview', '')]
    if table_27_chunks:
        print(f"\n包含表27的chunk:")
        for info in table_27_chunks:
            print(f"  Chunk {info['chunk_num']}: items[{info['start_idx']}:{info['end_idx']}], "
                  f"长度={info['length']}")
            print(f"    完整预览: {new_chunks[info['chunk_num']][:200]}...")

    print("="*60 + "\n")

    return new_chunks, chunk_types  # @luxinrong：20260303修改：返回文本和类型


def load_and_store_file(
    file_path: str,
    collection_name: str,
    dpi: int = 200,
    backend: str = "pipeline",  # 可选: "pipeline", "vlm-transformers", "both"
    meta_data: Optional[dict] = None,
    debug: bool = False,  # 调试模式：打印数据结构信息
    search_keyword: str = None,  # 搜索关键词（用于调试）
    split_tables: bool = True  # 表格独立成chunk
) -> bool:

    print(f"\n{'='*60}")
    print(f"=== load_and_store_file 开始处理 ===")
    print(f"文件: {os.path.basename(file_path)}")
    print(f"Backend: {backend}, Debug: {debug}")
    print(f"{'='*60}\n")

    file_name = os.path.basename(file_path)
    pre_path = Path(__file__).absolute().parent.parent
    file_name = os.path.join(pre_path, "data", "stored_files", file_name)

    # @luxinrong：20260303修改：支持混合模式
    if backend == "both":
        # 混合模式：先运行 pipeline 获取表格，再运行 vlm 获取图表/公式
        result_pipeline = mineru_tool.run(
            pdf_file_path=file_name,
            parse_method="auto",
            backend="pipeline",
        )
        result_vlm = mineru_tool.run(
            pdf_file_path=file_name,
            parse_method="auto",
            backend="vlm-transformers",
        )
        # 合并结果：优先使用 pipeline 的 table，其他用 vlm 的
        combined_data = []
        for item in result_pipeline.data or []:
            if item.get('type') == 'table':
                combined_data.append(item)
        for item in result_vlm.data or []:
            if item.get('type') != 'table':
                combined_data.append(item)
        recognized_text = type("MineruResponse", (), {})()
        recognized_text.status = "success"
        recognized_text.data = combined_data
    else:
        recognized_text = mineru_tool.run(
            pdf_file_path=file_name,
            parse_method="auto",
            backend=backend,
        )

    # 保存 content_list.json 用于调试
    import json
    original_filename = os.path.basename(file_path)
    file_basename = os.path.splitext(original_filename)[0]
    content_list_path = os.path.join(pre_path, "data", "stored_files", f"{file_basename}_content_list.json")
    with open(content_list_path, 'w', encoding='utf-8') as f:
        json.dump(recognized_text.data, f, ensure_ascii=False, indent=2)
    print(f"[INFO] content_list 已保存到: {content_list_path}")

    qdrant_init = QdrantDB_Init(collection_name=collection_name)
    # @luxinrong：20260303修改：preprocess 返回 (文本列表, 类型列表)
    print("[DEBUG] 调用 preprocess...")
    text_chunks, type_list = preprocess(data=recognized_text.data, debug=debug, search_keyword=search_keyword, split_tables=split_tables)
    print(f"[DEBUG] preprocess 返回，生成了 {len(text_chunks)} 个 chunk")

    db = QdrantDB(input=qdrant_init)
    file_name = file_name.split(".")[0]

    # @luxinrong：20260303修改：为每个 chunk 构建带类型信息的 meta_data
    chunk_meta_list = []
    for types in type_list:
        chunk_meta = meta_data.copy() if meta_data else {}
        if types:
            chunk_meta['content_types'] = types
        chunk_meta_list.append(chunk_meta)

    # @luxinrong：20260303修改：由于 save2Qdrant 目前不支持每个 chunk 独立的 meta_data，
    # 暂时将类型信息合并到 meta_data（影响：所有 chunk 共享类型列表）
    # 后续如需精确到 chunk 级别的类型，需修改 qdrant.py 的 save2Qdrant 方法
    all_types = []
    for types in type_list:
        all_types.extend(types)
    all_types = list(set(all_types))  # 去重

    final_meta = meta_data.copy() if meta_data else {}
    if all_types:
        final_meta['content_types'] = all_types

    save_input = save2Qdrant_Input(
        text=text_chunks,
        origin_file=file_name,
        meta_data=final_meta
    )
    db.save2Qdrant(input=save_input)

    print(f"\n{'='*60}")
    print(f"=== load_and_store_file 处理完成 ===")
    print(f"文件: {file_name}")
    print(f"生成 chunks 数量: {len(text_chunks)}")
    print(f"内容类型: {all_types}")
    print(f"{'='*60}\n")

    return True


def load_multiple_files(
    file_paths: list[str],
    collection_name: str,
    dpi: int = 150,
    meta_data: Optional[dict] = None,
    debug: bool = False,  # 调试模式
    search_keyword: str = None,  # 搜索关键词
    split_tables: bool = True  # 表格独立成chunk
) -> dict:
    results = {
        "success": [],
        "failed": []
    }

    for i, file_path in enumerate(file_paths, 1):
        success = load_and_store_file(
            file_path=file_path,
            collection_name=collection_name,
            dpi=dpi,
            meta_data=meta_data,
            debug=debug,  # 传递 debug 参数
            search_keyword=search_keyword,  # 传递搜索关键词
            split_tables=split_tables  # 传递 split_tables 参数
        )
        if success:
            results["success"].append(file_path)
        else:
            results["failed"].append(file_path)
    return results


def clear_collection(collection_name: str = "database") -> bool:
    """清空指定collection的所有数据"""
    from tools.qdrant import QdrantDB, QdrantDB_Init
    qdrant_init = QdrantDB_Init(collection_name=collection_name)
    db = QdrantDB(input=qdrant_init)
    db.delete_or_reset_collection(collectionname=collection_name, reset=True)
    print(f"Collection '{collection_name}' 已清空")
    return True

