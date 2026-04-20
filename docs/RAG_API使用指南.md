# RAG 知识库问答服务 - 使用指南

欢迎使用智能知识库问答服务！本指南帮助您快速接入和使用我们的 RAG（检索增强生成）API。

---

## 快速开始

### 1. 获取访问密钥

联系管理员获取您的专属 **API Key**。这是调用服务的凭证，请妥善保管。

### 2. 服务地址

```
https://your-server.com/api/v1/rag/query    # 智能问答
https://your-server.com/api/v1/rag/search   # 文档检索
```

### 3. 第一次调用

最简单的调用示例（Python）：

```python
import requests

# 发送问题
response = requests.post(
    "https://your-server.com/api/v1/rag/query",
    headers={"X-API-Key": "您的密钥"},
    json={"query": "变压器短路阻抗标准值是多少？"}
)

# 获取答案
result = response.json()
print("答案：", result["answer"])
print("来源：", result["sources"])
```

---

## 两种调用方式

我们提供两种服务，根据您的需求选择：

### 方式一：智能问答（推荐）

**适合场景**：您有一个问题，需要智能答案

**示例问题**：
- "变压器短路阻抗标准值是多少？"
- "电力线路保护配置有哪些要求？"
- "请解释一下无功补偿的作用"

**调用代码**：

```python
response = requests.post(
    "https://your-server.com/api/v1/rag/query",
    headers={"X-API-Key": "您的密钥"},
    json={"query": "您的问题"},
    timeout=120  # 建议120秒超时
)

result = response.json()
```

**返回内容**：

```json
{
  "answer": "根据GB/T 6451-2008标准，变压器短路阻抗...",
  "sources": [
    {"file_name": "GB_T_6451-2008.pdf", "absolute_path": "..."}
  ],
  "images": [
    {"file_name": "文档截图_1.jpg", "absolute_path": "..."}
  ]
}
```

您会得到：
- **answer**：智能生成的答案
- **sources**：答案引用的来源文档
- **images**：答案相关的图片（如有）

---

### 方式二：文档检索

**适合场景**：您需要查找原始文档内容

**调用代码**：

```python
response = requests.post(
    "https://your-server.com/api/v1/rag/search",
    headers={"X-API-Key": "您的密钥"},
    json={
        "query": "变压器绝缘",
        "top_k": 5  # 返回5条结果
    },
    timeout=60
)

result = response.json()
```

**返回内容**：

```json
{
  "total": 3,
  "results": [
    {
      "file_name": "电力变压器试验导则.pdf",
      "content": "变压器绝缘电阻测量是检验...",
      "score": 0.85
    },
    ...
  ]
}
```

您会得到：
- **results**：匹配的文档片段列表
- **content**：原文内容（可直接展示）
- **score**：相关度分数（越高越匹配）

---

## 请求参数说明

### 智能问答参数

| 参数 | 说明 | 是否必填 |
|------|------|----------|
| query | 您的问题 | 必填 |

**示例**：
```json
{"query": "变压器绝缘等级要求是什么？"}
```

### 文档检索参数

| 参数 | 说明 | 是否必填 | 默认值 |
|------|------|----------|--------|
| query | 搜索关键词 | 必填 | - |
| top_k | 返回结果数量（1-20） | 可选 | 5 |

**示例**：
```json
{"query": "绝缘", "top_k": 10}
```

---

## 如何认证

每次请求都需要携带 API Key，有两种方式：

### 方式一：使用 X-API-Key Header（推荐）

```python
headers = {
    "X-API-Key": "您的密钥"
}
```

### 方式二：使用 Authorization Header

```python
headers = {
    "Authorization": "ApiKey 您的密钥"
}
```

---

## 返回结果说明

### 智能问答返回值

| 字段 | 含义 | 用途 |
|------|------|------|
| answer | AI生成的答案 | 直接展示给用户 |
| sources | 来源文档列表 | 可点击查看原文 |
| sources.file_name | 文档名称 | 显示引用来源 |
| sources.absolute_path | 文档路径 | 可用于下载/预览 |
| images | 相关图片列表 | 展示图表、截图等 |
| images.file_name | 图片名称 | 图片文件名 |
| images.absolute_path | 图片路径 | 可用于展示图片 |

### 文档检索返回值

| 字段 | 含义 | 用途 |
|------|------|------|
| total | 结果总数 | 了解匹配数量 |
| results | 结果列表 | 循环展示 |
| file_name | 文档名称 | 显示来源 |
| content | 原文内容 | 直接展示 |
| score | 相关度（0-1） | 排序展示 |
| chunk_type | 片段类型 | text 或 table |

---

## 错误处理

如果调用失败，请检查：

| 错误码 | 含义 | 解决方法 |
|--------|------|----------|
| 401 | 密钥无效 | 确认 API Key 正确 |
| 503 | 服务未配置 | 联系管理员 |
| 500 | 服务器错误 | 稍后重试或联系管理员 |

**示例错误处理**：

```python
if response.status_code == 200:
    # 成功
    result = response.json()
elif response.status_code == 401:
    print("密钥无效，请联系管理员")
elif response.status_code == 503:
    print("服务暂时不可用，请稍后")
else:
    print("服务出错，请联系管理员")
```

---

## 常见使用示例

### 示例1：网页集成

```javascript
// 用户点击"提交问题"按钮时调用
async function askQuestion() {
  const question = document.getElementById('question').value;
  
  const response = await fetch('/api/v1/rag/query', {
    method: 'POST',
    headers: {
      'X-API-Key': '您的密钥',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ query: question })
  });
  
  const result = await response.json();
  
  // 显示答案
  document.getElementById('answer').textContent = result.answer;
  
  // 显示来源
  const sourcesList = result.sources.map(s => s.file_name).join(', ');
  document.getElementById('sources').textContent = '来源：' + sourcesList;
}
```

### 示例2：批量查询

```python
questions = [
    "变压器短路阻抗标准值是多少？",
    "电力线路保护配置有哪些要求？",
    "绝缘配合的基本原则是什么？"
]

for q in questions:
    result = requests.post(
        url, headers=headers, json={"query": q}
    ).json()
    print(f"问题：{q}")
    print(f"答案：{result['answer'][:100]}...")
    print()
```

### 示例3：文档搜索展示

```python
# 搜索相关文档
response = requests.post(
    search_url,
    headers=headers,
    json={"query": "绝缘电阻", "top_k": 10}
)

results = response.json()["results"]

# 按相关度排序展示
for item in sorted(results, key=lambda x: -x["score"]):
    print(f"【{item['file_name']}】相关度: {item['score']:.2f}")
    print(f"内容: {item['content'][:200]}...")
    print("-" * 50)
```

---

## 接入建议

### 用户体验优化

1. **展示来源引用**：让用户知道答案来自哪些文档，增加可信度
2. **显示相关图片**：如果返回了 images，展示图表、截图等视觉内容
3. **错误友好提示**：遇到错误时提示"服务繁忙，请稍后再试"

### 性能建议

1. **问答超时设120秒**：AI生成答案可能需要30-90秒
2. **检索超时设60秒**：纯检索通常较快
3. **避免并发过多**：建议每秒不超过5个请求

---

## 命令行测试

如果您熟悉命令行，可以用 curl 快速测试：

```bash
# 测试问答
curl -X POST "https://your-server.com/api/v1/rag/query" \
  -H "X-API-Key: 您的密钥" \
  -H "Content-Type: application/json" \
  -d '{"query": "变压器短路阻抗标准值是多少？"}'

# 测试检索
curl -X POST "https://your-server.com/api/v1/rag/search" \
  -H "X-API-Key: 您的密钥" \
  -H "Content-Type: application/json" \
  -d '{"query": "绝缘", "top_k": 5}'
```

---

## 常见问题

**Q：我该用哪个接口？**

A：
- 需要答案 → 用 `/query`（智能问答）
- 需要原文 → 用 `/search`（文档检索）

**Q：答案多久能返回？**

A：通常 30-90 秒。复杂问题可能更长，建议设置 120 秒超时。

**Q：返回的图片怎么显示？**

A：images 里包含图片路径，可请求服务器获取图片文件，或在有权限时直接访问路径。

**Q：搜索结果太多怎么办？**

A：调整 top_k 参数，默认返回 5 条，最多可设置 20 条。

**Q：密钥泄露了怎么办？**

A：立即联系管理员更换密钥。

---

## 技术支持

如有问题，请联系：
- **管理员邮箱**：admin@example.com
- **服务状态页面**：https://status.example.com

---

## 更新记录

| 日期 | 更新内容 |
|------|----------|
| 2026-04-17 | 发布使用指南 |