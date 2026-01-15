from tools import QdrantDB, QdrantDB_Init

qdrant_init = QdrantDB_Init(collection_name="database")
qdrant_tools = QdrantDB(input=qdrant_init)
print(qdrant_tools.search("供电营业规则"))
qdrant_tools.close()