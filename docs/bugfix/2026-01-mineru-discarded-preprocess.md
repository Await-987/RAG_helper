# 📝 PR 1：修复 preprocess 函数处理未知类型时的 KeyError 崩溃
## 1. 简要描述 (Summary)
修复了 preprocess 函数在解析 PDF 时，因遇到 MinerU 输出的 discarded 等未定义数据类型而抛出 KeyError 异常的问题。

## 2. 问题定位 (Root Cause)
在处理复杂格式 PDF 时，MinerU 会输出 discarded 类型项（如页眉、页脚等辅助信息）。

报错原因：type2key 字典属于硬编码白名单，未包含 discarded 键，直接访问导致 KeyError。

## 3. 变更说明 (Changes)
引入类型校验：在访问 type2key 前增加 if chunk_type not in type2key 判断。

安全跳过：若遇到未知类型，执行 idx += 1 并 continue 跳过，确保核心提取逻辑不中断。

重叠逻辑同步优化：在回退循环（Overlap）中增加同样的类型检查，遇未知类型直接 break 停止回退，防止索引错位。

## 4. 验证证明 (Evidence)
运行 tests/smoke_mineru_debug_and_retrieve.py：

修复前：在 Step 2 报错 KeyError: 'discarded'。

修复后：成功跳过无效类型，4 个 PDF 均完成入库并顺利通过检索断言。


# 📝 PR 2：增强 preprocess 函数逻辑完整性，修复潜在的 None 返回值
## 1. 简要描述 (Summary)
优化了 preprocess 函数的返回逻辑，确保在所有执行路径下均能返回已生成的文本块列表（List[str]），消除了返回 None 的潜在风险。

## 2. 逻辑漏洞描述 (Problem)
现状：原代码的 return 语句完全嵌套在 while 循环内部的 if idx >= len(data) 判断中。

风险：如果 while 循环因条件不再满足而正常终止（例如所有数据项都被跳过），程序会跳过循环内的 return 直接走到函数末尾，导致 Python 默认返回 None。这会导致下游 save2Qdrant_Input 模块因接收到空值而崩溃。

## 3. 变更说明 (Changes)
补全兜底返回：在函数体最末尾增加 return new_chunks 语句。

逻辑对齐：确保函数契约始终满足 -> List[str] 的要求，增强了数据处理链路的连贯性。

## 4. 验证证明 (Verification)
通过构造极端测试用例（如全无效数据列表 [{"type": "discarded"}]）进行验证：

修复前：函数返回 None。

修复后：函数返回预期的初始块列表（如 ['\n']），is None? 检查结果为 False。



# 📝 PR 3: MinerU 升级与 Embedding 模型变更说明文档
## 1. MinerU 解析引擎升级
1.1 核心变更
版本更迭：MinerU 版本由 2.2.2 升级至 2.7.1。

配置优化：更新 config/mineru.json，将 Pipeline 模型路径由系统缓存目录（Cache）迁移至项目本地路径（如 models/mineru/...）。

1.2 变更收益
解析质量提升：显著增强对复杂版式、多线表格及学术公式的提取精度。

环境一致性：通过本地化模型管理，支持内网/离线部署，消除环境差异导致的解析结果不一致。

## 2. Embedding 模型变更
2.1 方案演变路径
为了实现高性能与私有化部署的平衡，本项目经历了三个阶段的选型验证：

初始方案（旧本地模型）：基于 SentenceTransformerEncoder，路径依赖环境变量 conan_path。经测试发现该方案在复杂语义捕捉上存在局限。

对照验证（在线 API）：临时引入 OpenAIEmbedding (text-embedding-3-small) 作为基准对照组。

目的：排除代码框架逻辑干扰，验证向量库通路是否正常。

结论：确认了在线模型在特定场景下的检索上限，但因不符合“离线部署”的安全要求，仅作为实验参考。

最终落地（高性能本地模型）：回归并升级本地 Embedding 方案。

选型：采用 models/bge-base-zh-v1.5。

部署：使用 SentenceTransformerEncoder 加载本地权重，模型权重文件通过 .gitignore 排除，需手动部署至 models/ 目录。

2.2 运行时验证 (Validation Evidence)
通过以下命令验证模型已正确加载并适配业务维度：

PowerShell

python -c "from agents.backend_model import backend_embedding_model; m=backend_embedding_model(); print(f'Model Type: {type(m)}'); print(f'Output Dimension: {m.get_output_dim()}')"
预期输出：

Model Type: SentenceTransformerEncoder

Output Dimension: 768


## 3. 涉及文件清单
README.md：记录版本变更说明。

config/mineru.json：模型本地化路径配置。

agents/backend_model.py：Embedding 模型加载逻辑。

.gitignore：排除大体积模型权重文件。