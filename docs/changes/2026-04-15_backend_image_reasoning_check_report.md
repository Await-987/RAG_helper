# 2026-04-15 后端 / 图片路径 / Reasoning 检查报告

## 1. 报告目的

汇总本次排查中已确认的问题、根因、当前修复状态，以及仍需继续检查的项目，便于后续逐项验证。

---

## 2. 已确认结论

### 2.1 OpenAI-Compatible 接口返回的思考字段

已通过脚本 `scripts/inspect_api_reasoning_field.py` 实测当前 `.env` 配置的模型接口：

- 非流式返回字段：`choices[0].message.reasoning`
- 流式返回字段：`choices[0].delta.reasoning`
- 未发现 `reasoning_content`

结论：

- 当前模型接口主字段是 `reasoning`
- 不能只依赖 `reasoning_content`

相关日志：

- `logs/inspect_api_reasoning_field_20260415_103607.log`

---

### 2.2 CAMEL `chat_agent.py` 原始兼容性问题

原始 CAMEL 代码只兼容：

- `message.reasoning_content`
- `delta.reasoning_content`

不兼容当前接口返回的：

- `message.reasoning`
- `delta.reasoning`

已补丁修复：

- 兼容 `reasoning` 和 `reasoning_content`
- 非流式场景下，允许“只有 reasoning、没有 content”的消息保留
- 同步 / 异步流式都兼容 `delta.reasoning`

修改文件：

- `.venv/src/camel-ai/camel/agents/chat_agent.py`

---

### 2.3 后端 `System message must be at the beginning.` 的根因

报错现象：

```text
Error code: 400 - {'error': {'message': 'System message must be at the beginning.' ...}}
```

根因已确认，不是单一点，而是两处逻辑叠加：

1. `AGENT_MEMORY_ENABLED=false` 时，后端之前仍然会执行 memory restore/save
2. `load_memory_from_path()` 前没有先清空当前 memory，导致 system message 叠加

实际检查到的坏数据：

- 文件：`data/agent_memory/admin/d1a95416-f1a6-455a-9d40-04c7d5f36d0c.json`
- 同一份 memory 中存在多个 `system` 记录，而且不只在首位

示例顺序：

- 索引 0：`system`
- 索引 1：`user`
- 索引 2：`assistant`
- 索引 3：`system`
- 索引 4：`system`

这会导致发给模型的上下文中，system message 出现在中间位置，从而被服务端拒绝。

---

### 2.4 后端已做修复

已修复项：

1. 主聊天 Agent 使用真正的 system message
2. Intent Router 使用真正的 system message
3. Search Rewriter 使用真正的 system message
4. `AGENT_MEMORY_ENABLED=false` 时跳过 memory restore
5. `AGENT_MEMORY_ENABLED=false` 时跳过 memory save
6. memory restore 前先 `clear_memory()`，避免 system 叠加

修改文件：

- `backend/app/core/agent_factory.py`
- `backend/app/services/chat_service.py`

已做语法检查：

```bash
python -m py_compile backend/app/core/agent_factory.py backend/app/services/chat_service.py
python -m py_compile .venv/src/camel-ai/camel/agents/chat_agent.py
```

---

### 2.5 图片路径文件存在性检查

你提到的两个图片文件都在库里，文件本身没有丢失：

- `data/stored_files/mineru_output/DLT 5710-2014 电力建设土建工程施工技术检验规范_13.jpg`
- `data/stored_files/mineru_output/DL／T 5153-2014《火力发电厂厂用电设计技术规程》_231.jpg`

注意：

1. 路径中包含空格，shell 中必须加引号
2. 第二个文件名里的斜杠是全角 `／`，不是半角 `/`

你之前的命令报错不是因为文件不存在，而是因为把 Markdown 文本当成了 shell 命令执行：

```text
[表格](data/stored_files/mineru_output/...)
```

这对 bash 来说不是合法命令。

---

## 3. 当前仍需继续检查的项目

以下项目尚未完全确认，需要继续排查：

### 3.1 前端是否能正确渲染本地 Markdown 图片路径

当前回答里返回的是类似：

```md
![表格](data/stored_files/mineru_output/xxx.jpg)
```

需要确认：

- 前端 Markdown 渲染器是否支持直接访问这种本地相对路径
- 前端是否会把该路径转换成后端可访问 URL
- 浏览器是否能直接请求到 `data/stored_files/mineru_output/...`

风险：

- 即使文件在磁盘存在，前端仍可能无法显示
- 原因可能是没有静态资源映射，或路径未做 URL 转换

---

### 3.2 后端是否提供了图片文件访问接口

需要确认：

- 是否存在专门的文件下载 / 图片访问接口
- 是否存在静态目录映射，把 `data/stored_files/mineru_output/...` 暴露给浏览器
- 如果有接口，聊天回答中的图片路径是否应该输出成接口 URL，而不是磁盘相对路径

---

### 3.3 当前旧会话是否仍携带脏 memory

虽然代码已修复，但以下情况仍可能导致问题复现：

- 后端未重启
- 继续使用已在内存中存在的旧 session
- 旧磁盘 memory 文件没有清理，且未来又重新启用了 memory

建议：

- 重启后端
- 新开一个 session 复测
- 如需继续排查旧 session，可删除对应坏的 memory 文件后再测

---

## 4. 建议的验证顺序

### 4.1 后端验证

1. 重启后端服务
2. 新建一个全新的聊天会话
3. 发送简单寒暄消息，例如“你好”
4. 确认不再出现：

```text
System message must be at the beginning.
```

5. 确认 reasoning 能正常返回并被前端接收

---

### 4.2 图片链路验证

1. 找一条包含图片 Markdown 的回答
2. 在前端页面查看是否显示图片
3. 打开浏览器开发者工具 Network
4. 检查图片请求的 URL
5. 判断失败点属于以下哪类：

- 根本没有发起请求
- 发起了请求，但 URL 错误
- 请求命中后端，但返回 404
- 请求命中后端，但权限/跨域/静态映射有问题

---

## 5. 建议新增的后续检查项

建议继续做以下专项检查：

1. 检查前端 Markdown 图片渲染逻辑，确认本地路径是否被转换
2. 检查后端文件接口或静态映射，确认图片是否可被 HTTP 访问
3. 检查回答生成逻辑，确认图片链接输出格式是否应统一改成前端可访问 URL
4. 检查是否需要清理历史坏 memory 文件，避免后续重新启用 memory 时再次污染上下文

---

## 6. 本次涉及的关键文件

后端修复：

- `backend/app/core/agent_factory.py`
- `backend/app/services/chat_service.py`
- `.venv/src/camel-ai/camel/agents/chat_agent.py`

排查样本：

- `data/agent_memory/admin/d1a95416-f1a6-455a-9d40-04c7d5f36d0c.json`
- `data/stored_files/mineru_output/DLT 5710-2014 电力建设土建工程施工技术检验规范_13.jpg`
- `data/stored_files/mineru_output/DL／T 5153-2014《火力发电厂厂用电设计技术规程》_231.jpg`

诊断脚本：

- `scripts/inspect_api_reasoning_field.py`

诊断日志：

- `logs/inspect_api_reasoning_field_20260415_103607.log`

---

## 7. 结论

当前已经确认：

- 思考字段问题已定位并补丁修复
- `System message must be at the beginning.` 的根因已定位并修复
- 你提到的图片文件本身存在于库中

当前未完全确认：

- 前端是否能把 `data/stored_files/mineru_output/...` 这种磁盘路径正确渲染成可访问图片

下一步最值得做的不是继续查“文件在不在”，而是直接检查“前端渲染链路”和“后端图片访问映射”。
