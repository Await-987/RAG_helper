# RAG 检索能力升级：关键词+向量混合召回、动态 TopK、可选 Rerank 精排，并补充 Smoke / E2E 测试

## 背景 / 问题

当前知识库检索仅使用向量召回（semantic search）且 top_k 固定，存在：

编号/条款/证书号/术语等“字面强约束”问题命中不稳；

固定 top_k 导致：简单问题返回冗余、复杂问题证据不足；

候选排序完全依赖向量相似度，关键段落可能不在前排；

缺少针对检索升级的自动化回归验证（仅靠手测）。

## 本次改动概览
### 1) 混合召回：vector + keyword

新增 keyword 召回通道（BM25-like，本地倒排索引），对 payload 的 Content 字段进行词法检索。

与原有 向量召回通道 合并去重后做归一化融合：

hybrid_score = alpha * vector_norm + (1 - alpha) * keyword_norm

alpha 可调：偏语义 / 偏关键词可按场景配置。

### 2) 动态 TopK / 阈值召回

支持 dynamic_topk=True：根据最终分数阈值过滤，返回“足够相关的所有 chunks”，同时：

至少返回 top_k（兜底）

最多返回 max_results（防爆）

支持显式 score_threshold（0~1）或自适应阈值策略。

### 3) 可选 Rerank 精排（Cross-Encoder）

支持加载本地 reranker（CrossEncoder），通过 .env 控制：

reranker_path=models/<reranker_dir>

rerank 仅作用于候选集合，对候选相关性重新打分并重排，以提升：

标准号/证书号/条款类 query 的 top1 命中质量

未配置 reranker_path 时自动跳过，不影响现有流程。

### 4) 测试与验证

新增/补充 smoke 与真实 PDF 的 e2e 验证脚本：

tests/smoke_retrieval_hybrid_dynamic_rerank.py

合成小样本文本快速验证：keyword / hybrid / dynamic topk / rerank（可选）

tests/smoke_e2e_real_pdfs_hybrid_rerank.py

真实 PDF 端到端验证：MinerU 抽取 → 切分 → 入库 → hybrid 检索 → rerank top1

## 影响范围

检索链路升级：tools/qdrant.py、tools/database_toolkit.py（search_database 行为升级）

可选精排：agents/backend_model.py 增加 backend_reranker_model()（不配置不生效）

测试脚本：新增 tests/ 下 smoke/e2e 脚本（不影响生产）

## 如何验证（复现步骤）
### 1) 快速 smoke（不依赖 PDF）
python tests/smoke_retrieval_hybrid_dynamic_rerank.py

期望输出包含：

keyword_search hits > 0

hybrid_search 返回 top_k

dynamic_topk 高阈值下仍 >= top_k

rerank enabled?（若配置了 reranker_path）

### 2) 真实 PDF E2E
python tests/smoke_e2e_real_pdfs_hybrid_rerank.py <pdf1> <pdf2> <pdf3> <pdf4>

期望：

ingest success

每个 PDF 的 anchor query 均 hybrid hit ok

若启用 rerank：rerank top1 ok

最终打印 ALL DONE ... passed

### 3) 前端手测（Streamlit）
streamlit run run/streamlit.py

上传并导入测试 PDF（建议只导入本次 4 个样本）

问答验证：

证书号 / 软件名称（关键词强）

GB 标准名称 / 能效等级（关键词+语义混合）

电网运行规则 发布/施行/修订（多条件、动态 topk）

论文标题/作者/机构（语义召回）

注：本地 Qdrant（Local）对同一 data/storages 目录不支持多进程并发访问，跑脚本时请关闭 Streamlit，避免 .lock/storage.sqlite 占用。

配置说明（可选）

.env：

conan_path=models/bge-base-zh-v1.5（已有）

reranker_path=models/bge-reranker-base（可选）

LEX_INDEX_TTL_SEC=60（可选，控制倒排索引刷新频率）

风险 & 回滚
风险

本地倒排索引基于 scroll 全量构建：在数据量很大时首次构建会有额外耗时（已做 TTL & count 变化检测减少频繁重建）。

rerank 依赖本地模型与 sentence-transformers，若未配置/缺依赖会自动降级跳过，不影响主流程。

回滚

不配置 reranker_path 可一键关闭 rerank。

如需完全回退检索：DatabaseToolkit.search_database(use_hybrid=False, use_rerank=False, dynamic_topk=False)（或恢复原实现）。


Checklist

 本地 smoke 全绿：smoke_retrieval_hybrid_dynamic_rerank.py

 真实 PDF e2e 全绿：smoke_e2e_real_pdfs_hybrid_rerank.py

 前端导入 + 问答演示通过

 .env 未提交敏感信息（API key / 内网地址等）
