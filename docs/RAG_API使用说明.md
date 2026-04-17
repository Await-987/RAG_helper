# RAG API 对外接口使用说明

## 概述

本系统提供两个 RAG API 接口：

| 接口 | 说明 | 返回内容 |
|------|------|---------|
| `/rag/query` | 完整 RAG 流程 | AI 生成的答案 + 参考文件路径 + 图片路径 |
| `/rag/search` | 纯检索 | 原文片段（未经 AI 处理）+ 图片路径 |

---

## RAG 流程说明

标准 RAG（检索增强生成）流程：

```
用户问题 → Query改写 → 向量检索 → 重排序 → 原文片段 → 大模型生成 → 答案
           ────────────────────────────────────────────  ──────────────────
                      /rag/search 返回这里                  /rag/query 返回这里
```

- **`/rag/search`**：停在步骤 4，返回检索到的原始文档片段（含图片路径）
- **`/rag/query`**：走完步骤 6，返回 AI 基于原文生成的答案

---

## 图片路径说明

文档中的图片以 Markdown 格式嵌入在 Content 中：
```
![表格](data/stored_files/mineru_output/电力变压器试验导则_4.jpg)
```

API 会自动从 Content 中提取图片路径，转换为绝对路径返回。

---

## 1. 配置 API 密钥

在 `.env` 文件中添加：

```bash
RAG_API_KEY=任意字符串
```

示例：
```bash
RAG_API_KEY=rag-api-key-2026-04-15
```

**密钥说明：**
- 密钥可以是任意字符串，建议使用随机生成的复杂字符串
- 如果未配置 `RAG_API_KEY`，API 会返回 503 错误（服务不可用）
- 密钥需要妥善保管，泄露后任何人都可调用你的 RAG 服务

---

## 2. API 接口规范

### Endpoint 1：完整 RAG 查询

```
POST /api/v1/rag/query
```

**请求体：**
```json
{
  "query": "500kV变压器的绝缘等级要求是什么？"
}
```

**响应体：**
```json
{
  "answer": "根据 GB50229-2019《火力发电厂与变电站设计防火标准》，500kV变压器的绝缘等级要求如下...",
  "sources": [
    {
      "file_name": "GB50229-2019.pdf",
      "absolute_path": "/home/ubuntu/rag_project/rag/data/stored_files/GB50229-2019.pdf"
    }
  ],
  "images": [
    {
      "file_name": "GB50229-2019_3.jpg",
      "absolute_path": "/home/ubuntu/rag_project/rag/data/stored_files/mineru_output/GB50229-2019_3.jpg"
    }
  ],
  "query": "500kV变压器的绝缘等级要求是什么？"
}
```

**字段说明：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `answer` | string | AI 生成的答案文本 |
| `sources` | array | 参考的 PDF 文件列表 |
| `sources[].file_name` | string | 文件名 |
| `sources[].absolute_path` | string | 文件绝对路径 |
| `images` | array | 参考文档中的图片列表 |
| `images[].file_name` | string | 图片文件名 |
| `images[].absolute_path` | string | 图片绝对路径 |
| `query` | string | 原始问题 |

---

### Endpoint 2：纯检索（原文片段）

```
POST /api/v1/rag/search
```

**请求体：**
```json
{
  "query": "变压器绝缘",
  "top_k": 5
}
```

**字段约束：**
- `query`: 必填，长度 1-5000 字符
- `top_k`: 可选，返回结果数量（1-20，默认 5）

**响应体：**
```json
{
  "query": "变压器绝缘",
  "results": [
    {
      "file_name": "电力变压器试验导则.pdf",
      "absolute_path": "/home/ubuntu/rag_project/rag/data/stored_files/电力变压器试验导则.pdf",
      "content": "3.9.3.3被试品温度的测量油浸式变压器测量顶层与底部绝缘油的温度...\n\n![表格](data/stored_files/mineru_output/电力变压器试验导则_4.jpg)",
      "score": 0.6968,
      "chunk_type": "table",
      "images": [
        {
          "file_name": "电力变压器试验导则_4.jpg",
          "absolute_path": "/home/ubuntu/rag_project/rag/data/stored_files/mineru_output/电力变压器试验导则_4.jpg"
        }
      ]
    }
  ],
  "total": 5
}
```

**字段说明：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `results[].content` | string | **原始文档片段**（未经 AI 处理） |
| `results[].score` | float | 相关度分数（越高越相关） |
| `results[].chunk_type` | string | 片段类型：`text` 或 `table` |
| `results[].images` | array | 从 Content 中提取的图片列表 |

---

## 3. 认证方式

支持两种 Header 格式：

```http
X-API-Key: <your-api-key>
```

或

```http
Authorization: ApiKey <your-api-key>
```

---

## 4. 调用示例

### Python 示例

使用项目提供的示例脚本：

```bash
# 完整 RAG 查询（AI 答案）
python scripts/example_rag_api_client.py query --query "变压器绝缘等级要求" --api-key YOUR_KEY

# 纯检索（原文片段）
python scripts/example_rag_api_client.py search --query "变压器绝缘" --top-k 5 --api-key YOUR_KEY
```

### curl 示例

**完整 RAG：**
```bash
curl -X POST "http://localhost:8000/api/v1/rag/query" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "变压器绝缘等级要求"}'
```

**纯检索：**
```bash
curl -X POST "http://localhost:8000/api/v1/rag/search" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"query": "变压器绝缘", "top_k": 5}'
```

---

## 5. 错误响应

| 状态码 | 说明 |
|--------|------|
| 401 | 认证失败：API Key 缺失或无效 |
| 503 | 服务不可用：未配置 RAG_API_KEY |
| 500 | 服务器错误：RAG 查询处理失败 |

---

## 6. 文件清单

| 文件 | 说明 |
|------|------|
| `backend/app/config.py` | RAG_API_KEY 配置项 |
| `backend/app/dependencies.py` | verify_rag_api_key 认证函数 |
| `backend/app/schemas/rag_api.py` | Request/Response 数据模型 |
| `backend/app/api/v1/rag.py` | API endpoint 实现 |
| `backend/app/services/chat_service.py` | query_rag_sync 查询方法 |
| `scripts/example_rag_api_client.py` | Python 调用示例 |

## 1. 配置 API 密钥

### 方式一：环境变量（推荐）

在 `.env` 文件中添加：

```bash
RAG_API_KEY=rag-123
```

### 方式二：启动时传入

```bash
export RAG_API_KEY=rag-123
python backend/run.py --host 0.0.0.0 --port 8000
```

**密钥说明：**
- 密钥可以是任意字符串，建议使用随机生成的复杂字符串
- 如果未配置 `RAG_API_KEY`，API 会返回 503 错误（服务不可用）
- 密钥需要妥善保管，泄露后任何人都可调用你的 RAG 服务

---

## 2. API 接口规范

### Endpoint

```
POST /api/v1/rag/query
```

### 认证方式

支持两种 Header 格式：

```http
X-API-Key: <your-api-key>
```

或

```http
Authorization: ApiKey <your-api-key>
```

### 请求体

```json
{
  "query": "500kV变压器的绝缘等级要求是什么？"
}
```

字段约束：
- `query`: 必填，长度 1-5000 字符

### 响应体

```json
{
  "answer": "根据 GB50229-2019《火力发电厂与变电站设计防火标准》，500kV变压器的绝缘等级要求如下...",
  "sources": [
    {
      "file_name": "GB50229-2019.pdf",
      "absolute_path": "/home/ubuntu/rag_project/rag/data/stored_files/GB50229-2019.pdf"
    },
    {
      "file_name": "DLT5710-2014.pdf",
      "absolute_path": "/home/ubuntu/rag_project/rag/data/stored_files/DLT5710-2014.pdf"
    }
  ],
  "query": "500kV变压器的绝缘等级要求是什么？"
}
```

字段说明：
- `answer`: RAG 生成的答案文本
- `sources`: 参考文件列表（包含文件名和绝对路径）
- `query`: 原始问题（便于日志追溯）

---

## 3. 调用示例

### Python 示例

使用项目提供的示例脚本：

```bash
python scripts/example_rag_api_client.py \
  --query "变压器绝缘等级要求" \
  --api-key rag-api-key-2026-04-15-a1b2c3d4e5f6 \
  --url http://localhost:8000
```

或直接使用 requests：

```python
import requests

url = "http://localhost:8000/api/v1/rag/query"
headers = {"X-API-Key": "rag-api-key-2026-04-15-a1b2c3d4e5f6"}
payload = {"query": "500kV变压器的绝缘等级要求"}

response = requests.post(url, headers=headers, json=payload)
result = response.json()

print("答案:", result["answer"])
for src in result["sources"]:
    print("参考:", src["file_name"], "->", src["absolute_path"])
```

### curl 示例

```bash
curl -X POST "http://localhost:8000/api/v1/rag/query" \
  -H "X-API-Key: rag-api-key-2026-04-15-a1b2c3d4e5f6" \
  -H "Content-Type: application/json" \
  -d '{"query": "变压器绝缘等级要求"}'
```

### 其他语言示例

#### Java (OkHttp)

```java
OkHttpClient client = new OkHttpClient();
String json = "{\"query\": \"变压器绝缘等级要求\"}";
RequestBody body = RequestBody.create(json, MediaType.parse("application/json"));

Request request = new Request.Builder()
    .url("http://localhost:8000/api/v1/rag/query")
    .header("X-API-Key", "rag-api-key-2026-04-15-a1b2c3d4e5f6")
    .post(body)
    .build();

Response response = client.newCall(request).execute();
String result = response.body().string();
```

#### JavaScript (fetch)

```javascript
const response = await fetch('http://localhost:8000/api/v1/rag/query', {
  method: 'POST',
  headers: {
    'X-API-Key': 'rag-123',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ query: '变压器绝缘等级要求' })
});

const result = await response.json();
console.log(result.answer);
```

---

## 4. 错误响应

| 状态码 | 说明 |
|--------|------|
| 401 | 认证失败：API Key 缺失或无效 |
| 503 | 服务不可用：未配置 RAG_API_KEY |
| 500 | 服务器错误：RAG 查询处理失败 |

错误响应示例：

```json
{
  "detail": "Invalid API Key"
}
```

---

## 5. 部署注意事项

1. **生产环境密钥安全**
   - 使用强密钥（建议 32+ 字符随机字符串）
   - 不要将密钥提交到代码仓库
   - 定期更换密钥

2. **网络访问控制**
   - API 默认暴露在 `/api/v1/rag/query`
   - 如需限制访问，可在反向代理层添加 IP 白名单

3. **超时设置**
   - RAG 查询可能需要 30-120 秒（取决于模型响应速度）
   - 调用方建议设置 timeout ≥ 120 秒

---

## 6. 文件清单

| 文件 | 说明 |
|------|------|
| `backend/app/config.py` | RAG_API_KEY 配置项 |
| `backend/app/dependencies.py` | verify_rag_api_key 认证函数 |
| `backend/app/schemas/rag_api.py` | Request/Response 数据模型 |
| `backend/app/api/v1/rag.py` | API endpoint 实现 |
| `backend/app/services/chat_service.py` | query_rag_sync 查询方法 |
| `scripts/example_rag_api_client.py` | Python 调用示例 |