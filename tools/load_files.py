# @ wangpei
import os
import hashlib
import shutil
from tools import MineruComponent
from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input
from typing import *
from loguru import logger

mineru_tool = MineruComponent()
from pathlib import Path

# 获取项目根目录和图片存储路径
project_root = Path(__file__).absolute().parent.parent
# 图片存储在 data/stored_files/mineru_output 下
MINERU_OUTPUT_DIR = project_root / "data" / "stored_files" / "mineru_output"


# ==================== 图片重命名相关函数 ====================

def rename_images_for_document(
    content_list: list,
    document_name: str,
    output_dir: Path = None
) -> tuple[list, dict]:
    """
    重命名图片文件，使其与文档关联

    将 MinerU 生成的哈希命名图片重命名为 "文档名_数字.jpg" 格式
    这样删除文档时可以根据前缀批量删除图片

    Args:
        content_list: MinerU 输出的内容列表
        document_name: 文档名称（不含扩展名）
        output_dir: 图片输出目录，默认为 MINERU_OUTPUT_DIR

    Returns:
        (重命名后的 content_list, 图片重命名映射 dict)
        - 重命名映射: {旧图片名: 新图片名}
    """
    if output_dir is None:
        output_dir = MINERU_OUTPUT_DIR

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 收集所有需要重命名的图片
    image_rename_map = {}  # {旧名: 新名}
    image_counter = {}  # {基础名: 计数器}

    for item in content_list:
        if item.get('type') in ('image', 'table'):
            img_path = item.get('img_path', '')
            if not img_path:
                continue

            # 提取图片文件名（可能包含 mineru_output/ 前缀）
            old_img_name = os.path.basename(img_path)
            if not old_img_name:
                continue

            # 检查图片文件是否存在
            old_img_full_path = output_dir / old_img_name
            if not old_img_full_path.exists():
                logger.warning(f"图片文件不存在: {old_img_full_path}")
                continue

            # 生成新的图片名：文档名_数字.扩展名
            ext = os.path.splitext(old_img_name)[1] or '.jpg'
            base_name = document_name

            # 获取或初始化计数器
            if base_name not in image_counter:
                image_counter[base_name] = 0
            image_counter[base_name] += 1
            new_index = image_counter[base_name]

            # 生成新文件名
            new_img_name = f"{base_name}_{new_index}{ext}"
            new_img_full_path = output_dir / new_img_name

            # 重命名文件
            try:
                shutil.move(str(old_img_full_path), str(new_img_full_path))
                logger.debug(f"图片重命名: {old_img_name} -> {new_img_name}")

                # 记录映射关系
                image_rename_map[old_img_name] = new_img_name

                # 更新 content_list 中的路径
                # 保持相对路径格式：mineru_output/新文件名
                if img_path.startswith('mineru_output/'):
                    item['img_path'] = f"mineru_output/{new_img_name}"
                else:
                    item['img_path'] = f"mineru_output/{new_img_name}"

            except Exception as e:
                logger.error(f"图片重命名失败: {old_img_name} -> {new_img_name}, 错误: {e}")

    logger.info(f"图片重命名完成: 共 {len(image_rename_map)} 个文件")

    return content_list, image_rename_map


def get_document_images(document_name: str, output_dir: Path = None) -> list:
    """
    获取指定文档关联的所有图片文件路径

    Args:
        document_name: 文档名称（不含扩展名）
        output_dir: 图片输出目录

    Returns:
        图片文件路径列表
    """
    if output_dir is None:
        output_dir = MINERU_OUTPUT_DIR

    if not output_dir.exists():
        return []

    # 查找以 "文档名_" 开头的图片文件
    prefix = f"{document_name}_"
    images = []

    for f in output_dir.iterdir():
        if f.is_file() and f.name.startswith(prefix):
            # 检查是否是图片文件
            if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.bmp'):
                images.append(str(f))

    return images


# ==================== 表格摘要缓存 ====================
# 缓存表格摘要，避免重复调用 LLM
_table_summary_cache: Dict[str, str] = {}


def generate_table_summary(table_content: str, table_caption: str = "", use_llm_summary: bool = True) -> str:
    """
    使用 LLM 为表格生成摘要，用于向量检索

    Args:
        table_content: 表格内容（包含标题、body、脚注）
        table_caption: 表格标题（用于优先处理）
        use_llm_summary: 是否使用 LLM 生成摘要，默认开启

    Returns:
        表格摘要（200字以内）
    """
    # 如果不使用 LLM 摘要，直接返回原始内容（截断）
    if not use_llm_summary:
        # 返回截断的原始内容
        return table_content[:400] if len(table_content) > 400 else table_content

    # 生成缓存键（基于内容哈希）
    cache_key = hashlib.md5((table_content + table_caption).encode('utf-8')).hexdigest()

    # 检查缓存
    if cache_key in _table_summary_cache:
        return _table_summary_cache[cache_key]

    # 构建 prompt
    prompt = f"""请为以下表格生成一个简洁的摘要（不超过200字），用于语义检索。

要求：
1. 提取表格的核心信息和关键数据
2. 说明表格展示的主要内容（如参数对比、统计数据、分类信息等）
3. 如果有单位或量级信息，请包含
4. 保持客观，不要添加表格中没有的信息

表格内容：
{table_content[:2000]}{"..." if len(table_content) > 2000 else ""}

请直接输出摘要，不要包含任何解释或格式标记："""

    # 尝试使用本地小模型
    try:
        from agents.backend_model import generate_table_summary_local
        summary = generate_table_summary_local(prompt)

        if summary:
            # 限制摘要长度
            if len(summary) > 250:
                summary = summary[:250] + "..."

            # 缓存结果
            _table_summary_cache[cache_key] = summary
            print(f"[INFO] 本地模型生成表格摘要成功: {summary[:50]}...")
            return summary

    except Exception as e:
        print(f"[WARNING] 本地模型生成表格摘要失败: {e}")

    # 降级：返回原始内容
    print(f"[INFO] 使用原始表格内容作为摘要")
    return table_content[:400] if len(table_content) > 400 else table_content


def clear_table_summary_cache():
    """清空表格摘要缓存"""
    global _table_summary_cache
    _table_summary_cache = {}
    print("[INFO] 表格摘要缓存已清空")


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
                 split_tables: bool = False, use_llm_summary: bool = True, context_size: int = 500) -> List[Dict]:
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

    def extract_context(data_list: list, table_idx: int, direction: str = 'before', max_chars: int = 500) -> str:
        """
        提取表格前后的上下文文本

        Args:
            data_list: 原始数据列表
            table_idx: 表格在列表中的索引
            direction: 'before' 或 'after'
            max_chars: 最大字符数

        Returns:
            上下文文本字符串
        """
        context_parts = []
        current_chars = 0

        if direction == 'before':
            # 向前遍历，直到达到 max_chars
            idx = table_idx - 1
            while idx >= 0 and current_chars < max_chars:
                item = data_list[idx]
                item_type = item.get('type')
                if item_type == 'table':
                    # 遇到另一个表格就停止
                    break
                elif item_type in type2key:
                    # 提取文本内容
                    if item_type == 'equation':
                        content, _ = extract_equation_content(item, data_list, idx)
                    elif item_type == 'image':
                        content = extract_image_content(item)
                    else:
                        key = type2key[item_type]
                        if isinstance(item.get(key), str):
                            content = item[key]
                        elif isinstance(item.get(key), list):
                            content = ','.join(item[key])
                        else:
                            content = ''

                    if content and content.strip():
                        context_parts.insert(0, content)  # 插入到开头保持顺序
                        current_chars += len(content)
                idx -= 1
        else:  # 'after'
            idx = table_idx + 1
            while idx < len(data_list) and current_chars < max_chars:
                item = data_list[idx]
                item_type = item.get('type')
                if item_type == 'table':
                    # 遇到另一个表格就停止
                    break
                elif item_type in type2key:
                    # 提取文本内容
                    if item_type == 'equation':
                        content, _ = extract_equation_content(item, data_list, idx)
                    elif item_type == 'image':
                        content = extract_image_content(item)
                    else:
                        key = type2key[item_type]
                        if isinstance(item.get(key), str):
                            content = item[key]
                        elif isinstance(item.get(key), list):
                            content = ','.join(item[key])
                        else:
                            content = ''

                    if content and content.strip():
                        context_parts.append(content)
                        current_chars += len(content)
                idx += 1

        result = '\n'.join(context_parts)
        # 截断到 max_chars
        if len(result) > max_chars:
            if direction == 'before':
                result = result[-max_chars:]  # 保留后面的部分（靠近表格）
            else:
                result = result[:max_chars]  # 保留前面的部分（靠近表格）
        return result

    new_chunks = []  # @shengwanying：20260306修改：原来存 str，现在存 Dict，每条包含 child、parent、types

    # 调试：跟踪 chunk 生成
    chunk_debug_info = []
    table_count = 0  # 表格计数器

    def create_text_chunks(text_content: str, parent_content: str, types_list: list) -> list:
        """
        为普通文本创建子 chunks

        Args:
            text_content: 文本内容
            parent_content: 父 chunk 内容
            types_list: 类型列表

        Returns:
            子 chunk 字典列表
        """
        chunks = []
        if not text_content.strip():
            return chunks

        # 按 child_size 切分，带 overlap
        start = 0
        while start < len(text_content):
            child = text_content[start:start + child_size]
            if child.strip():
                chunks.append({
                    'child': child,
                    'parent': parent_content,
                    'types': types_list.copy()
                })
            if start + child_size >= len(text_content):
                break
            start += child_size - child_overlap
        return chunks

    def create_table_chunk(table_item: dict, table_idx: int) -> dict:
        """
        创建独立的表格 chunk

        Args:
            table_item: 表格数据项
            table_idx: 表格在 data 中的索引

        Returns:
            表格 chunk 字典
        """
        nonlocal table_count
        table_count += 1

        # 提取表格完整内容
        table_content = extract_table_content(table_item)

        # 提取上下文
        context_before = extract_context(data, table_idx, 'before', context_size)
        context_after = extract_context(data, table_idx, 'after', context_size)

        # 获取表格标题用于摘要生成
        caption = table_item.get('table_caption', [])
        caption_text = ' '.join(caption) if caption else ''

        # 生成 LLM 摘要
        table_summary = generate_table_summary(table_content, caption_text, use_llm_summary)

        if debug:
            print(f"[DEBUG] 创建独立表格 chunk #{table_count}")
            print(f"        标题: {caption_text[:50] if caption_text else '[无标题]'}...")
            print(f"        摘要: {table_summary[:80]}...")
            print(f"        上下文前: {len(context_before)} 字符")
            print(f"        上下文后: {len(context_after)} 字符")

        return {
            'child': table_summary,  # LLM 摘要用于向量检索
            'parent': table_content,  # 完整表格返回给 LLM
            'types': ['table'],
            'is_table': True,
            'context': {
                'before': context_before,
                'after': context_after
            }
        }

    # ==================== 主处理循环 ====================
    # 新逻辑：表格独立处理，与普通文本分离

    idx = 0
    chunk_num = 0
    accumulated_text = ''  # 累积的非表格文本
    accumulated_types = []  # 累积的类型
    chunk_start_idx = 0  # 当前 chunk 起始索引

    while idx < len(data):
        item = data[idx]
        item_type = item.get('type')

        # 跳过未知类型
        if item_type not in type2key:
            idx += 1
            continue

        # ========== 表格独立处理 ==========
        if item_type == 'table':
            # 1. 先保存已累积的非表格内容
            if accumulated_text.strip():
                # 创建普通文本 chunks
                text_chunks = create_text_chunks(
                    accumulated_text,
                    accumulated_text + '\n',
                    accumulated_types
                )
                new_chunks.extend(text_chunks)

                chunk_debug_info.append({
                    'chunk_num': chunk_num,
                    'start_idx': chunk_start_idx,
                    'end_idx': idx,
                    'length': len(accumulated_text),
                    'types': accumulated_types.copy(),
                    'preview': accumulated_text[:100].replace('\n', ' '),
                    'child_count': len(text_chunks),
                    'is_table': False
                })
                chunk_num += 1

                # 重置累积器
                accumulated_text = ''
                accumulated_types = []

            # 2. 创建独立的表格 chunk
            table_chunk = create_table_chunk(item, idx)
            new_chunks.append(table_chunk)

            chunk_debug_info.append({
                'chunk_num': chunk_num,
                'start_idx': idx,
                'end_idx': idx + 1,
                'length': len(table_chunk['parent']),
                'types': ['table'],
                'preview': table_chunk['child'][:100].replace('\n', ' '),
                'child_count': 1,
                'is_table': True
            })
            chunk_num += 1

            # 更新下一个 chunk 的起始索引
            chunk_start_idx = idx + 1
            idx += 1
            continue

        # ========== 非表格内容累积 ==========
        content = ''
        skip_count = 0

        if item_type == 'equation':
            content, skip_count = extract_equation_content(item, data, idx)
        elif item_type == 'image':
            content = extract_image_content(item)
        else:
            key = type2key[item_type]
            if isinstance(item.get(key), str):
                content = item[key]
            elif isinstance(item.get(key), list):
                content = ','.join(item[key])

        if content:
            accumulated_text += content
            if item_type in ('equation', 'image') and item_type not in accumulated_types:
                accumulated_types.append(item_type)

        # 检查是否需要创建父 chunk
        if len(accumulated_text) >= chunk_min_size:
            # 创建普通文本 chunks
            text_chunks = create_text_chunks(
                accumulated_text,
                accumulated_text + '\n',
                accumulated_types
            )
            new_chunks.extend(text_chunks)

            chunk_debug_info.append({
                'chunk_num': chunk_num,
                'start_idx': chunk_start_idx,
                'end_idx': idx + 1,
                'length': len(accumulated_text),
                'types': accumulated_types.copy(),
                'preview': accumulated_text[:100].replace('\n', ' '),
                'child_count': len(text_chunks),
                'is_table': False
            })
            chunk_num += 1

            # overlap 逻辑：保留末尾部分文本
            overlap_text = ''
            overlap_idx = idx
            while len(overlap_text) < overlap_size and overlap_idx >= chunk_start_idx:
                overlap_item = data[overlap_idx]
                overlap_type = overlap_item.get('type')
                if overlap_type == 'table':
                    break  # 不跨越表格
                if overlap_type in type2key:
                    if overlap_type == 'equation':
                        overlap_content, _ = extract_equation_content(overlap_item, data, overlap_idx)
                    elif overlap_type == 'image':
                        overlap_content = extract_image_content(overlap_item)
                    else:
                        key = type2key[overlap_type]
                        if isinstance(overlap_item.get(key), str):
                            overlap_content = overlap_item[key]
                        elif isinstance(overlap_item.get(key), list):
                            overlap_content = ','.join(overlap_item[key])
                        else:
                            overlap_content = ''
                    overlap_text = overlap_content + overlap_text
                overlap_idx -= 1

            # 重置累积器，保留 overlap
            accumulated_text = overlap_text[-overlap_size:] if len(overlap_text) > overlap_size else overlap_text
            accumulated_types = []
            chunk_start_idx = idx + 1

        idx += 1 + skip_count

    # ========== 处理剩余的累积文本 ==========
    if accumulated_text.strip():
        text_chunks = create_text_chunks(
            accumulated_text,
            accumulated_text + '\n',
            accumulated_types
        )
        new_chunks.extend(text_chunks)

        chunk_debug_info.append({
            'chunk_num': chunk_num,
            'start_idx': chunk_start_idx,
            'end_idx': len(data),
            'length': len(accumulated_text),
            'types': accumulated_types.copy(),
            'preview': accumulated_text[:100].replace('\n', ' '),
            'child_count': len(text_chunks),
            'is_table': False
        })

    # ========== 打印调试摘要 ==========
    print(f"[DEBUG] 所有数据处理完成，共生成 {len(new_chunks)} 个子chunk")
    print(f"[DEBUG] 其中表格 chunk: {table_count} 个")

    # 调试：打印 chunk 生成摘要
    print("\n" + "="*60)
    print(f"=== Chunk 生成摘要 (共 {len(new_chunks)} 个子chunk，表格 {table_count} 个) ===")
    print("="*60)

    # 打印前5个父chunk
    print("\n前5个 chunk:")
    for info in chunk_debug_info[:5]:
        table_flag = "📊[表格]" if info.get('is_table') else "📄[文本]"
        print(f"  {table_flag} Chunk {info['chunk_num']}: items[{info['start_idx']}:{info['end_idx']}], "
              f"长度={info['length']}, 类型={info['types']}, 子chunk数={info.get('child_count', 0)}")
        print(f"    预览: {info['preview']}...")

    print("="*60 + "\n")

    # @shengwanying：20260306修改：返回 List[Dict]，每条格式：
    # 普通文本 chunk: {'child': 子chunk, 'parent': 父chunk, 'types': [...]}
    # 表格 chunk: {'child': LLM摘要, 'parent': 完整表格, 'types': ['table'],
    #              'is_table': True, 'context': {'before': ..., 'after': ...}}
    return new_chunks


def load_and_store_file(
    file_path: str,
    collection_name: str,
    dpi: int = 200,
    backend: str = "pipeline",  # 可选: "pipeline", "vlm-transformers", "both"
    meta_data: Optional[dict] = None,
    debug: bool = False,  # 调试模式：打印数据结构信息
    search_keyword: str = None,  # 搜索关键词（用于调试）
    split_tables: bool = True,  # 表格独立成chunk
    use_llm_summary: bool = True,  # 使用 LLM 生成表格摘要
    context_size: int = 500  # 表格上下文大小（字符数）
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

    # ==================== 图片重命名：绑定文档 ====================
    # 将图片从哈希命名改为 "文档名_数字.jpg" 格式
    # 这样删除文档时可以根据前缀批量删除图片
    print(f"[INFO] 开始图片重命名，绑定文档: {file_basename}")
    recognized_text.data, image_rename_map = rename_images_for_document(
        content_list=recognized_text.data,
        document_name=file_basename,
        output_dir=MINERU_OUTPUT_DIR
    )
    print(f"[INFO] 图片重命名完成，共 {len(image_rename_map)} 个图片")

    qdrant_init = QdrantDB_Init(collection_name=collection_name)
    # @shengwanying：20260306修改：preprocess 返回 List[Dict]（父子chunk）
    print("[DEBUG] 调用 preprocess...")
    chunks = preprocess(
        data=recognized_text.data,
        debug=debug,
        search_keyword=search_keyword,
        split_tables=split_tables,
        use_llm_summary=use_llm_summary,
        context_size=context_size
    )
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

    # 统计表格 chunk 数量
    table_count = sum(1 for chunk in chunks if chunk.get('is_table'))

    # @shengwanying：20260306修改：逐条存入：向量用child，Content用parent
    # @luxinrong：20260309新增：表格独立存储，包含上下文信息
    for chunk in chunks:
        chunk_meta = final_meta.copy()
        chunk_meta['child_content'] = chunk['child']  # 把子chunk也存进payload

        # 表格特殊处理：添加表格标记和上下文
        if chunk.get('is_table'):
            chunk_meta['is_table'] = True
            context = chunk.get('context', {})
            if context:
                chunk_meta['context_before'] = context.get('before', '')
                chunk_meta['context_after'] = context.get('after', '')

        save_input = save2Qdrant_Input(
            text=chunk['parent'],
            origin_file=file_tag,
            meta_data=chunk_meta
        )
        db.save2Qdrant(input=save_input, vector_text=chunk['child'])

    print(f"\n{'='*60}")
    print(f"=== load_and_store_file 处理完成 ===")
    print(f"文件: {os.path.basename(file_path)}")
    print(f"生成子chunk数量: {len(chunks)} (其中表格: {table_count})")
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
    split_tables: bool = True,  # 表格独立成chunk
    use_llm_summary: bool = True,  # 使用 LLM 生成表格摘要
    context_size: int = 500  # 表格上下文大小（字符数）
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
            split_tables=split_tables,  # 传递 split_tables 参数
            use_llm_summary=use_llm_summary,  # 传递 use_llm_summary 参数
            context_size=context_size  # 传递 context_size 参数
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
    file_path, collection_name, dpi, meta_data, debug, search_keyword, split_tables, use_llm_summary, context_size = args

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

        # ==================== 图片重命名：绑定文档 ====================
        # 将图片从哈希命名改为 "文档名_数字.jpg" 格式
        file_basename = os.path.splitext(file_name)[0]
        recognized_text.data, image_rename_map = rename_images_for_document(
            content_list=recognized_text.data,
            document_name=file_basename,
            output_dir=MINERU_OUTPUT_DIR
        )

        # 处理数据 - @shengwanying：20260306修改：preprocess 返回 List[Dict]
        chunks = preprocess(
            data=recognized_text.data,
            debug=debug,
            search_keyword=search_keyword,
            split_tables=split_tables,
            use_llm_summary=use_llm_summary,
            context_size=context_size
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
        # @luxinrong：20260309新增：表格独立存储，包含上下文信息
        for chunk in chunks:
            chunk_meta = final_meta.copy()
            chunk_meta['child_content'] = chunk['child']

            # 表格特殊处理：添加表格标记和上下文
            if chunk.get('is_table'):
                chunk_meta['is_table'] = True
                context = chunk.get('context', {})
                if context:
                    chunk_meta['context_before'] = context.get('before', '')
                    chunk_meta['context_after'] = context.get('after', '')

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
    use_llm_summary: bool = True,
    context_size: int = 500,
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
        use_llm_summary: 使用 LLM 生成表格摘要
        context_size: 表格上下文大小（字符数）
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
        (fp, collection_name, dpi, meta_data, debug, search_keyword, split_tables, use_llm_summary, context_size)
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

