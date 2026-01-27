# MinerU 升级 & Embedding 模型变更（含验证证据）


## 1. MinerU 升级
### 1.1 变更内容
- MinerU 版本升级：2.2.2 → 2.7.1（README 已记录）
- `config/mineru.json` 将 pipeline 模型目录由 cache 目录切换为项目本地目录（例如 `models/mineru/...`），便于离线/内网部署与环境一致性。


### 1.2 变更目标
- 提升 PDF 解析质量（复杂版式、表格、公式）
- 统一模型版本与部署方式，减少环境差异导致的不一致



---


## 2. Embedding 模型变更（决策过程）
### 2.1 初始方案：旧本地 embedding
- 旧实现使用本地 `SentenceTransformerEncoder`，模型路径由环境变量 `conan_path` 指定。
- 在最初测试阶段怀疑旧本地 embedding 可能导致入库/检索异常，因此做了对照验证。


### 2.2 对照验证阶段：临时在线 embedding（OpenAI）
- 临时切换为 `OpenAIEmbedding(text-embedding-3-small)` 作为对照组，用于排除“本地 embedding 本身异常”的可能性。
- 该阶段不满足“必须本地化/离线部署”的要求，仅用于排障。


### 2.3 最终落地：回归更强本地 embedding（已完成）
 embedding 必须本地化部署，因此最终回归本地 embedding，并升级为更强模型：
- 本地模型：`models/bge-base-zh-v1.5`
- 代码实现：`SentenceTransformerEncoder(model_name=<本地路径>)`
- 模型权重不提交 git（建议 `.gitignore` 忽略 `models/`），通过下载/部署方式准备。


**运行时验证证据：**
在当前环境执行：
```powershell
python -c "from agents.backend_model import backend_embedding_model; m=backend_embedding_model(); print(type(m)); print(m.get_output_dim())"

输出示例：
SentenceTransformerEncoder
768

## 3. 对向量库的影响（必须告知）

Embedding 切换=向量空间变化：

旧向量与新查询向量不可比，召回会退化/失效
建议：

使用新 collection 验证

上线时按 collection 维度重建索引/重新入库

用固定 query 集合做回归对比（Recall@K / MRR@K / latency）

## 4. 相关文件

README.md

config/mineru.json

agents/backend_model.py

.gitignore