# @ wangpei
import os
from tools import MineruComponent
from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input
from typing import *
mineru_tool = MineruComponent()
from pathlib import Path

def preprocess(data: list, chunk_min_size: int = 400, overlap_size: int = 50) -> List[str]:
    type2key = {
        'text': 'text',
        'equation': 'text',
        'image': 'image_caption',
        'table': 'table_caption',
    }

    table_body = 'table_body'

    new_chunks = []

    idx = 0
    while idx < len(data):
        new_chunk = ''
        while len(new_chunk) < chunk_min_size and idx < len(data):
            # chunk_type = data[idx]['type']
            # chunk_key = type2key[chunk_type]
            # @qiaoyu：20260126修改：处理未知类型报错，遇到 discarded 或其他未知类型就直接跳过，不会 KeyError
            chunk_type = data[idx].get('type')
            if chunk_type not in type2key:
                idx += 1
                continue
            chunk_key = type2key[chunk_type]

            if isinstance(data[idx][chunk_key], str):
                new_chunk += data[idx][chunk_key]
            elif isinstance(data[idx][chunk_key], List):
                new_chunk += ','.join(data[idx][chunk_key])
            if chunk_type == 'table' and table_body in data[idx]:
                new_chunk += data[idx][table_body]
            idx += 1

        new_chunk += '\n'
        new_chunks.append(new_chunk)
        if idx >= len(data):
            return new_chunks
        temp_chunk = ''
        while len(temp_chunk) < overlap_size:
            # chunk_type = data[idx - 1]['type']
            # chunk_key = type2key[chunk_type]
            # @qiaoyu：20260126修改：overlap 阶段遇到未知类型，直接停止回退
            chunk_type = data[idx - 1].get('type')
            if chunk_type not in type2key:
                break
            chunk_key = type2key[chunk_type]
            if isinstance(data[idx - 1][chunk_key], str):
                temp_chunk += data[idx - 1][chunk_key]
            elif isinstance(data[idx - 1][chunk_key], List):
                temp_chunk += ','.join(data[idx - 1][chunk_key])
            if chunk_type == 'table' and table_body in data[idx - 1]:
                temp_chunk += data[idx - 1][table_body]
            idx -= 1
        if len(new_chunk) - len(temp_chunk) < 10:
            idx += 1
    #@qiaoyu：20260126修改兜底：外层 while 正常结束时也要返回
    return new_chunks


def load_and_store_file(
    file_path: str,
    collection_name: str,
    dpi: int = 150,
    meta_data: Optional[dict] = None
) -> bool:

    file_name = os.path.basename(file_path)
    pre_path = Path(__file__).absolute().parent.parent
    file_name = os.path.join(pre_path, "data", "stored_files", file_name)
    recognized_text = mineru_tool.run(pdf_file_path=file_name)
    qdrant_init = QdrantDB_Init(collection_name=collection_name)
    recognized_text = preprocess(data = recognized_text.data)

    db = QdrantDB(input=qdrant_init)
    file_name = file_name.split(".")[0]
    save_input = save2Qdrant_Input(
        text=recognized_text,
        origin_file=file_name,
        meta_data=meta_data
    )
    db.save2Qdrant(input=save_input)
    return True


def load_multiple_files(
    file_paths: list[str],
    collection_name: str,
    dpi: int = 150,
    meta_data: Optional[dict] = None
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
            meta_data=meta_data
        )
        if success:
            results["success"].append(file_path)
        else:
            results["failed"].append(file_path)
    return results

