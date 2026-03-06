# @ wangpei
import os
from tools import MineruComponent
from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input
from typing import *
mineru_tool = MineruComponent()
from pathlib import Path

# 获取项目根目录和图片存储路径
project_root = Path(__file__).absolute().parent.parent
# 图片存储在 data/stored_files/mineru_output 下
MINERU_OUTPUT_DIR = project_root / "data" / "stored_files" / "mineru_output"


# @shengwanying：20260306修改：路径辅助函数，确保跨平台兼容
def get_relative_path(full_path: Path, base_dir: Path = None) -> str:
    """
    获取相对于项目根目录的相对路径，使用 POSIX 风格（正斜杠）

    Args:
        full_path: 完整路径
        base_dir: 基准目录，默认为项目根目录

    Returns:
        相对路径字符串，使用正斜杠分隔
    """
    if base_dir is None:
        base_dir = project_root
    try:
        relative = full_path.relative_to(base_dir)
        return relative.as_posix()  # 使用正斜杠，跨平台兼容
    except ValueError:
        # 如果路径不在 base_dir 下，返回完整路径的 POSIX 格式
        return str(full_path).replace("\\", "/")

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


def preprocess(data: list, chunk_min_size: int = 2000, overlap_size: int = 300, child_size: int = 400, child_overlap: int = 80, debug: bool = False, search_keyword: str = None,
                 split_tables: bool = False) -> List[Dict]:
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
        - 图片路径（img_path）- 供前端展示，使用相对路径
        - 图片描述（image_caption）
        - 图片脚注（image_footnote）

        @shengwanying：20260306修改：使用相对路径，确保跨平台兼容
        """
        content_parts = []

        # 添加图片路径（使用相对路径供前端展示）
        img_path = image_item.get('img_path', '')
        if img_path:
            # 转换为完整路径
            normalized_path = img_path.replace("\\", "/")
            if normalized_path.startswith("mineru_output/"):
                # 提取相对路径部分
                relative_path = normalized_path.replace("mineru_output/", "", 1)
                full_path = MINERU_OUTPUT_DIR / relative_path
            elif os.path.isabs(img_path):
                full_path = Path(img_path)
            else:
                full_path = MINERU_OUTPUT_DIR / img_path

            # @shengwanying：20260306修改：使用相对路径（相对于项目根目录）
            # 这样可以在不同平台间迁移数据
            relative_img_path = get_relative_path(full_path)
            content_parts.append(f'![图片]({relative_img_path})')

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
        """提取表格的完整内容

        @shengwanying：20260306修改：图片路径使用相对路径
        """
        content_parts = []

        # 添加表格图片路径（使用相对路径供前端展示）
        img_path = table_item.get('img_path', '')
        if img_path:
            # 转换为完整路径
            normalized_path = img_path.replace("\\", "/")
            if normalized_path.startswith("mineru_output/"):
                # 提取相对路径部分
                relative_path = normalized_path.replace("mineru_output/", "", 1)
                full_path = MINERU_OUTPUT_DIR / relative_path
            elif os.path.isabs(img_path):
                full_path = Path(img_path)
            else:
                full_path = MINERU_OUTPUT_DIR / img_path

            # @shengwanying：20260306修改：使用相对路径（相对于项目根目录）
            relative_img_path = get_relative_path(full_path)
            content_parts.append(f'![表格]({relative_img_path})')

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

    new_chunks = []  # @shengwanying：20260306修改：原来存 str，现在存 Dict，每条包含 child、parent、types

    # 调试：跟踪 chunk 生成
    chunk_debug_info = []

    idx = 0
    chunk_num = 0
    while idx < len(data):
        new_chunk = ''
        types_in_chunk = []  # @luxinrong：20260303修改：当前 chunk 的类型列表
        chunk_start_idx = idx  # 记录 chunk 起始索引

        while len(new_chunk) < chunk_min_size and idx < len(data):
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

        if new_chunk.strip():
            new_chunk += '\n'
            parent_text = new_chunk

            # ↓ 新增：父chunk切子chunk (@shengwanying：20260306修改)
            children = []
            # 遍历父chunk中的原始items，表格单独成子chunk，其余按child_size切
            segments = []  # list of (text, is_table)
            temp_text = ''
            for _item in data[chunk_start_idx:idx]:
                _type = _item.get('type')
                if _type == 'table':
                    if temp_text.strip():
                        segments.append((temp_text, False))
                        temp_text = ''
                    segments.append((extract_table_content(_item), True))
                elif _type in type2key:
                    _key = type2key[_type]
                    if _type == 'equation':
                        _content, _ = extract_equation_content(_item, data, 0)
                    elif _type == 'image':
                        _content = extract_image_content(_item)
                    elif isinstance(_item.get(_key), str):
                        _content = _item[_key]
                    elif isinstance(_item.get(_key), list):
                        _content = ','.join(_item[_key])
                    else:
                        _content = ''
                    temp_text += _content
            if temp_text.strip():
                segments.append((temp_text, False))

            # 对每个segment切子chunk
            for seg_text, is_table in segments:
                if is_table:
                    # 表格整体作为一个子chunk
                    children.append(seg_text)
                else:
                    # 普通文本按child_size滑动切，overlap=child_overlap
                    start = 0
                    while start < len(seg_text):
                        children.append(seg_text[start:start + child_size])
                        if start + child_size >= len(seg_text):
                            break
                        start += child_size - child_overlap

            for child in children:
                if child.strip():
                    new_chunks.append({
                        'child': child,
                        'parent': parent_text,
                        'types': types_in_chunk.copy()
                    })

            # 调试：记录 chunk 信息
            chunk_debug_info.append({
                'chunk_num': chunk_num,
                'start_idx': chunk_start_idx,
                'end_idx': idx,
                'length': len(new_chunk),
                'types': types_in_chunk.copy(),
                'preview': new_chunk[:100].replace('\n', ' '),
                'child_count': len(children)
            })
            chunk_num += 1

        # 检查是否已完成所有数据处理
        if idx >= len(data):
            print(f"[DEBUG] 所有数据处理完成，共生成 {len(new_chunks)} 个子chunk，准备返回...")

            # 调试：打印 chunk 生成摘要（在return之前）
            print("\n" + "="*60)
            print(f"=== Chunk 生成摘要 (共 {len(new_chunks)} 个子chunk) ===")
            print("="*60)

            # 打印前5个父chunk
            print("\n前5个父chunk:")
            for info in chunk_debug_info[:5]:
                print(f"  父Chunk {info['chunk_num']}: items[{info['start_idx']}:{info['end_idx']}], "
                      f"长度={info['length']}, 类型={info['types']}, 子chunk数={info.get('child_count', 0)}")
                print(f"    预览: {info['preview']}...")

            print("="*60 + "\n")

            return new_chunks  # @shengwanying：20260306修改：返回

        temp_chunk = ''
        while len(temp_chunk) < overlap_size:
            # @luxinrong：20260126修改：overlap 阶段遇到未知类型，直接停止回退
            chunk_type = data[idx - 1].get('type')
            if chunk_type not in type2key:
                break
            # @shengwanying：20260306修改：overlap阶段遇到表格停止回退，避免下一个父chunk从表格中间开始破坏表格结构
            if chunk_type == 'table':
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
    print(f"=== Chunk 生成摘要 (共 {len(new_chunks)} 个子chunk) ===")
    print("="*60)

    # 打印前5个父chunk
    print("\n前5个父chunk:")
    for info in chunk_debug_info[:5]:
        print(f"  父Chunk {info['chunk_num']}: items[{info['start_idx']}:{info['end_idx']}], "
              f"长度={info['length']}, 类型={info['types']}, 子chunk数={info.get('child_count', 0)}")
        print(f"    预览: {info['preview']}...")

    print("="*60 + "\n")

    # @shengwanying：20260306修改：返回 List[Dict]，每条格式：
    # {'child': 子chunk文本（约400字，用于向量检索，表格整体作为一个子chunk）,
    #  'parent': 父chunk文本（约2000字，overlap300，返回给LLM作为上下文）,
    #  'types': 该父chunk包含的内容类型列表，如['table', 'equation']}
    return new_chunks


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

    # 获取项目根目录和文件路径
    # load_files.py 在 tools/ 目录下，需要向上两级到达项目根目录
    project_root = Path(__file__).absolute().parent.parent
    file_name = os.path.basename(file_path)
    file_path = project_root / "data" / "stored_files" / file_name

    # 确保 stored_files 目录存在
    (project_root / "data" / "stored_files").mkdir(parents=True, exist_ok=True)

    # @luxinrong：20260303修改：支持混合模式
    if backend == "both":
        # 混合模式：先运行 pipeline 获取表格，再运行 vlm 获取图表/公式
        result_pipeline = mineru_tool.run(
            pdf_file_path=str(file_path),
            parse_method="auto",
            backend="pipeline",
        )
        result_vlm = mineru_tool.run(
            pdf_file_path=str(file_path),
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
            pdf_file_path=str(file_path),
            parse_method="auto",
            backend=backend,
        )

    # 保存 content_list.json 用于调试
    import json
    original_filename = os.path.basename(file_path)
    file_basename = os.path.splitext(original_filename)[0]

    # content_list 存储到 data/content_lists/ 目录
    content_lists_dir = os.path.join(str(project_root), "data", "content_lists")
    os.makedirs(content_lists_dir, exist_ok=True)
    content_list_path = os.path.join(content_lists_dir, f"{file_basename}_content_list.json")

    with open(content_list_path, 'w', encoding='utf-8') as f:
        json.dump(recognized_text.data, f, ensure_ascii=False, indent=2)
    print(f"[INFO] content_list 已保存到: {content_list_path}")

    qdrant_init = QdrantDB_Init(collection_name=collection_name)
    # @shengwanying：20260306修改：preprocess 返回 List[Dict]（父子chunk）
    print("[DEBUG] 调用 preprocess...")
    chunks = preprocess(data=recognized_text.data, debug=debug, search_keyword=search_keyword, split_tables=split_tables)
    print(f"[DEBUG] preprocess 返回，生成了 {len(chunks)} 个子chunk")

    db = QdrantDB(input=qdrant_init)
    # @shengwanying：20260306修改：使用相对路径，确保跨平台兼容
    # 相对于项目根目录的路径，便于在不同平台间迁移数据
    file_relative_path = (file_path.relative_to(project_root)).as_posix()
    file_tag = file_relative_path
    print(f"[DEBUG] file_tag (相对路径) = {file_tag}")

    # 收集所有类型用于 meta_data
    all_types = list(set(t for chunk in chunks for t in chunk.get('types', [])))
    final_meta = meta_data.copy() if meta_data else {}
    if all_types:
        final_meta['content_types'] = all_types

    # @shengwanying：20260306修改：逐条存入：向量用child，Content用parent
    for chunk in chunks:
        chunk_meta = final_meta.copy()
        chunk_meta['child_content'] = chunk['child']  # 把子chunk也存进payload
        save_input = save2Qdrant_Input(
            text=chunk['parent'],
            origin_file=file_tag,
            meta_data=chunk_meta
        )
        db.save2Qdrant(input=save_input, vector_text=chunk['child'])

    print(f"\n{'='*60}")
    print(f"=== load_and_store_file 处理完成 ===")
    print(f"文件: {os.path.basename(file_path)}")
    print(f"生成子chunk数量: {len(chunks)}")
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


# ==================== 并行处理支持 ====================

def _process_single_file(args):
    """
    多进程worker函数：处理单个PDF文件

    注意：每个子进程会独立初始化mineru_tool和embedding模型
    """
    file_path, collection_name, dpi, meta_data, debug, search_keyword, split_tables = args

    # 每个子进程需要独立创建mineru实例（避免多进程问题）
    from tools import MineruComponent
    mineru_tool_local = MineruComponent()

    try:
        # 获取项目根目录和文件路径
        project_root = Path(__file__).absolute().parent.parent
        file_name = os.path.basename(file_path)
        file_path_full = project_root / "data" / "stored_files" / file_name

        # 确保 stored_files 目录存在
        (project_root / "data" / "stored_files").mkdir(parents=True, exist_ok=True)

        # 调用mineru处理
        recognized_text = mineru_tool_local.run(
            pdf_file_path=str(file_path_full),
            parse_method="auto",
            backend="pipeline",
        )

        if recognized_text.status != "success":
            return {"file": file_path, "success": False, "error": recognized_text.error}

        # 处理数据 - @shengwanying：20260306修改：preprocess 返回 List[Dict]
        chunks = preprocess(
            data=recognized_text.data,
            debug=debug,
            search_keyword=search_keyword,
            split_tables=split_tables
        )

        # 存入Qdrant（每个子进程独立连接）
        from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input
        qdrant_init = QdrantDB_Init(collection_name=collection_name)
        db = QdrantDB(input=qdrant_init)

        # @shengwanying：20260306修改：使用相对路径，确保跨平台兼容
        file_tag = (file_path_full.relative_to(project_root)).as_posix()

        # 收集所有类型用于 meta_data
        all_types = list(set(t for chunk in chunks for t in chunk.get('types', [])))
        final_meta = meta_data.copy() if meta_data else {}
        if all_types:
            final_meta['content_types'] = all_types

        # 逐条存入：向量用child，Content用parent
        for chunk in chunks:
            chunk_meta = final_meta.copy()
            chunk_meta['child_content'] = chunk['child']
            save_input = save2Qdrant_Input(
                text=chunk['parent'],
                origin_file=file_tag,
                meta_data=chunk_meta
            )
            db.save2Qdrant(input=save_input, vector_text=chunk['child'])

        return {"file": file_path, "success": True}

    except Exception as e:
        return {"file": file_path, "success": False, "error": str(e)}


def load_multiple_files_parallel(
    file_paths: list[str],
    collection_name: str,
    dpi: int = 150,
    meta_data: Optional[dict] = None,
    debug: bool = False,
    search_keyword: str = None,
    split_tables: bool = True,
    num_workers: Optional[int] = None,
) -> dict:
    """
    并行处理多个PDF文件（多进程版本）

    Args:
        file_paths: PDF文件路径列表
        collection_name: Qdrant collection名称
        dpi: MinerU处理DPI
        meta_data: 元数据
        debug: 调试模式
        search_keyword: 搜索关键词
        split_tables: 表格独立成chunk
        num_workers: 进程数，默认为CPU核心数

    Returns:
        {"success": [...], "failed": [...]}
    """
    import multiprocessing
    from tqdm import tqdm

    if num_workers is None:
        num_workers = multiprocessing.cpu_count()
        # 限制最大进程数，避免资源耗尽
        num_workers = min(num_workers, 8)

    print(f"\n{'='*60}")
    print(f"并行处理模式：{num_workers} 个进程")
    print(f"文件数量：{len(file_paths)}")
    print(f"{'='*60}\n")

    # 准备参数
    tasks = [
        (fp, collection_name, dpi, meta_data, debug, search_keyword, split_tables)
        for fp in file_paths
    ]

    results = {"success": [], "failed": []}

    # 使用进程池
    with multiprocessing.Pool(processes=num_workers) as pool:
        # 使用imap_unordered获取实时进度
        with tqdm(total=len(file_paths), desc="处理进度", unit="文件") as pbar:
            for result in pool.imap_unordered(_process_single_file, tasks):
                if result["success"]:
                    results["success"].append(result["file"])
                else:
                    results["failed"].append(result["file"])
                    error_msg = result.get("error", "未知错误")
                    pbar.write(f"❌ 失败: {os.path.basename(result['file'])} - {error_msg}")
                pbar.update(1)

    print(f"\n{'='*60}")
    print(f"处理完成！成功: {len(results['success'])}, 失败: {len(results['failed'])}")
    print(f"{'='*60}\n")

    return results

