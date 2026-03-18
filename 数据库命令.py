  1. 清空数据库（删除整个 collection）
                                                                                                                                              
  cd /home/ubuntu/rag_project/rag
  python -c "from tools.qdrant import QdrantDB, QdrantDB_Init; db = QdrantDB(input=QdrantDB_Init(collection_name='database'));
  db.storage_instance._client.delete_collection(collection_name='database')"

  2. 清空数据库内容（保留 collection 结构）

  cd /home/ubuntu/rag_project/rag
  python -c "from tools.qdrant import QdrantDB, QdrantDB_Init; db = QdrantDB(input=QdrantDB_Init(collection_name='database'));
  db.storage_instance.clear()"

  3. 批量重建数据库

  cd /home/ubuntu/rag_project/rag

  # 先清空
  python -c "from tools.qdrant import QdrantDB, QdrantDB_Init; db = QdrantDB(input=QdrantDB_Init(collection_name='database'));
  db.storage_instance._client.delete_collection(collection_name='database')"

  # 再批量导入
  source .venv/bin/activate
  nohup python scripts/batch_import.py > import.log 2>&1 &

  # 查看进度
  tail -f import.log

  4. 删除特定文件的记录

  python -c "from tools.qdrant import QdrantDB, QdrantDB_Init; db = QdrantDB(input=QdrantDB_Init(collection_name='database'));
  db.delete_by_file_name('data/stored_files/your_file.pdf')"

  5. 查看数据库统计

  python -c "from backend.app.core.file_catalog import get_database_stats; stats, total = get_database_stats(); print(f'总切片数: {total}');
  print(f'文件数: {len(stats)}')"
