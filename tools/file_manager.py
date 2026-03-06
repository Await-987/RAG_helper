import os
import sys
import time
from pathlib import Path
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent

# 将根目录加入 sys.path 以确保能正常 import tools
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from tools.qdrant import QdrantDB, QdrantDB_Init
    from qdrant_client import models
except ImportError as e:
    print(f"❌ 导入失败，请确保在根目录运行或 sys.path 设置正确: {e}")
    sys.exit(1)
# ===============================================

COLLECTION_NAME = "database" 
STORED_DIR = BASE_DIR / "data" / "stored_files"

def get_accurate_stats():
    """
    通过底层 client 直接读取数据，绕过任何可能存在的业务层缓存
    """
    try:
        db = QdrantDB(input=QdrantDB_Init(collection_name=COLLECTION_NAME))
        client = db.storage_instance._client
        
        # 1. 获取数据库点数
        count_result = client.count(collection_name=COLLECTION_NAME)
        total_chunks = count_result.count
        
        # 2. 获取所有点的 payload 以统计各文件分布
        stats = {}
        if total_chunks > 0:
            scroll_result = client.scroll(
                collection_name=COLLECTION_NAME,
                limit=10000,
                with_payload=True,
                with_vectors=False
            )[0]
            
            for point in scroll_result:
                tag = point.payload.get("Original_file", "未知文件/残留数据")
                stats[tag] = stats.get(tag, 0) + 1
                
        return stats, total_chunks
    except Exception as e:
        logger.error(f"获取数据库统计失败: {e}")
        return {}, 0

def list_files_ui():
    if not STORED_DIR.exists():
        print(f"\n❌ 路径错误: 找不到存储目录 {STORED_DIR}")
        return []

    # 获取本地文件
    local_files = [f for f in os.listdir(STORED_DIR) if os.path.isfile(STORED_DIR / f)]
    
    # 获取数据库实时统计
    db_stats, total_chunks = get_accurate_stats()
    
    print("\n" + "═"*85)
    print(f"  {'编号':<6} {'切片数 (Chunk)':<18} {'文件名'}")
    print("─" * 85)
    
    file_info_list = []
    # 记录哪些 tag 在数据库里但本地已经没了（幽灵数据）
    tags_in_db = set(db_stats.keys())
    
    # 1. 显示本地存在的文件及其在库里的切片
    for idx, name in enumerate(local_files):
        target_path = STORED_DIR / name
        file_tag = str(target_path).split(".")[0]
        
        chunk_count = db_stats.get(file_tag, 0)
        print(f"  [{idx:<4}] {chunk_count:<18} {name}")
        
        file_info_list.append({
            "type": "local",
            "name": name, 
            "tag": file_tag, 
            "path": target_path
        })
        if file_tag in tags_in_db:
            tags_in_db.remove(file_tag)

    # 2. 显示数据库里残留但本地已删除的“幽灵切片”
    if tags_in_db:
        print("─" * 85)
        print("  ⚠️ 以下数据在数据库中有残留，但本地文件已不存在 (建议清理):")
        start_idx = len(file_info_list)
        for i, ghost_tag in enumerate(tags_in_db):
            idx = start_idx + i
            count = db_stats[ghost_tag]
            # 简化显示路径，只取最后一部分
            display_tag = ghost_tag.split(os.sep)[-1]
            print(f"  [{idx:<4}] {count:<18} [残留] {display_tag}")
            file_info_list.append({
                "type": "ghost",
                "name": display_tag,
                "tag": ghost_tag,
                "path": None
            })
    
    print("─" * 85)
    print(f"  📊 数据库总真实切片数: {total_chunks}")
    print("═"*85 + "\n")
    return file_info_list

def main():
    while True:
        file_info = list_files_ui()
        
        prompt = "👉 输入编号删除 | [r] 刷新 | [q] 退出: "
        cmd = input(prompt).strip().lower()
        
        if cmd == 'q':
            print("已退出。")
            break
        elif cmd == 'r':
            continue
        elif cmd.isdigit():
            idx = int(cmd)
            if 0 <= idx < len(file_info):
                target = file_info[idx]
                confirm = input(f"⚠️ 确认清理 '{target['name']}' 的所有数据吗？(y/n): ")
                if confirm.lower() == 'y':
                    try:
                        # 删除数据库切片
                        db = QdrantDB(input=QdrantDB_Init(collection_name=COLLECTION_NAME))
                        db.delete_by_file_name(target['tag'])
                        
                        # 如果本地文件存在则删除
                        if target['path'] and target['path'].exists():
                            os.remove(target['path'])
                            print(f"✅ 本地文件及数据库切片已清理。")
                        else:
                            print(f"✅ 数据库残留切片已清理。")
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"❌ 删除失败: {e}")
            else:
                print("❌ 编号超出范围。")
        else:
            print("❌ 无效输入。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序终止。")