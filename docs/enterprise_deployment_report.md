# 企业级 RAG 系统部署方案报告

> 本报告基于当前项目代码分析和企业级部署最佳实践，面向电力系统与国家电网业务场景的 RAG 助手项目。

## 一、项目现状评估

### 1.1 当前架构优势

| 方面 | 已完成 | 说明 |
|------|--------|------|
| Qdrant 服务化 | ✅ | 支持 local/server 双模式 |
| Redis 会话索引 | ✅ | 会话元数据已外置 |
| 共享存储路径 | ✅ | SHARED_STORAGE_ROOT 统一入口 |
| Docker Compose | ✅ | 四服务编排 (web/backend/qdrant/redis) |
| 健康检查 | ✅ | backend/qdrant/redis 均有 healthcheck |
| 混合检索 | ✅ | Vector + BM25 + Rerank |
| 流式响应 | ✅ | SSE 支持 |

### 1.2 当前阻塞点

| 问题 | 代码位置 | 企业级影响 |
|------|----------|------------|
| ChatAgent 进程内缓存 | `chat_service.py:self._sessions` | 多副本无法共享会话执行态 |
| Agent Memory 本地文件 | `data/agent_memory/` | 无法跨节点同步 |
| Chat Transcript 本地文件 | `data/chat_sessions/` | 多副本数据不一致 |
| 单 Worker 模式 | `BACKEND_WORKERS=1` | 无法利用多核 CPU |

---

## 二、企业级目标架构

### 2.1 推荐拓扑

```
                                    ┌─────────────────────────────────────┐
                                    │           Ingress / API Gateway     │
                                    │   (Nginx / Kong / Traefik)          │
                                    └─────────────────────────────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
            ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
            │   Frontend    │          │   Frontend    │          │   Frontend    │
            │   (CDN)       │          │   (CDN)       │          │   (CDN)       │
            └───────────────┘          └───────────────┘          └───────────────┘
                    │                           │                           │
                    └───────────────────────────┼───────────────────────────┘
                                                │ /api
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
            ┌───────────────┐          ┌───────────────┐          ┌───────────────┐
            │  Backend-1    │          │  Backend-2    │          │  Backend-3    │
            │  (FastAPI)    │          │  (FastAPI)    │          │  (FastAPI)    │
            │  Pod/Container│          │  Pod/Container│          │  Pod/Container│
            └───────────────┘          └───────────────┘          └───────────────┘
                    │                           │                           │
                    └───────────────────────────┼───────────────────────────┘
                                                │
            ┌───────────────────────────────────┼───────────────────────────────────┐
            │                                   │                                   │
            ▼                                   ▼                                   ▼
    ┌───────────────┐                  ┌───────────────┐                  ┌───────────────┐
    │    Redis      │                  │   Qdrant      │                  │   LLM Gateway │
    │   Cluster     │                  │   Cluster     │                  │  (LiteLLM)    │
    │  (Sentinel)   │                  │  (Raft)       │                  │               │
    └───────────────┘                  └───────────────┘                  └───────────────┘
            │                                   │                                   │
            ▼                                   ▼                                   ▼
    ┌───────────────┐                  ┌───────────────┐                  ┌───────────────┐
    │  PostgreSQL   │                  │   MinIO/S3    │                  │   External    │
    │  (Session DB) │                  │  (File Store) │                  │   LLM APIs    │
    └───────────────┘                  └───────────────┘                  └───────────────┘
```

### 2.2 组件职责

| 组件 | 职责 | 企业级方案 |
|------|------|------------|
| **Ingress** | SSL/TLS、限流、WAF、路由 | Kong / Nginx / Traefik |
| **Frontend** | 静态资源托管 | CDN + 多副本 |
| **Backend** | 业务逻辑、Agent编排 | K8s Deployment (3-5 replicas) |
| **Redis Cluster** | 会话状态、分布式锁、缓存 | Redis Sentinel / Cluster |
| **Qdrant Cluster** | 向量检索、多租户隔离 | Raft 集群 + 分片 |
| **LiteLLM Gateway** | LLM 统一入口、成本追踪 | 独立代理服务 |
| **PostgreSQL** | 持久化数据、审计日志 | 主从复制 |
| **MinIO/S3** | 文件存储、MinerU输出 | 对象存储 |

---

## 三、多租户架构方案

### 3.1 Qdrant 多租户策略对比

| 策略 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **Collection-per-Tenant** | 完全隔离、独立配置、备份简单 | 集合数量多时资源开销大 | 大型企业客户、强合规要求 |
| **Payload Filtering** | 集合数量少、资源效率高 | 查询需带过滤条件、ACL复杂 | 中小客户、数据量适中 |
| **Hybrid** | 大客户独立集合、小客户共享 | 实现复杂度高 | 混合场景 |

### 3.2 推荐方案：Hybrid 多租户

```python
# tools/qdrant.py 改造示意
class QdrantDB:
    def __init__(self, tenant_id: str, tenant_level: str = "standard"):
        self.tenant_id = tenant_id
        self.tenant_level = tenant_level
        
        if tenant_level == "enterprise":
            # 大客户：独立 Collection
            self.collection_name = f"tenant_{tenant_id}"
        else:
            # 小客户：共享 Collection + Payload 过滤
            self.collection_name = "shared_database"
            self.tenant_filter = models.Filter(
                must=[models.FieldCondition(
                    key="tenant_id",
                    match=models.MatchValue(value=tenant_id)
                )]
            )
```

### 3.3 Payload 结构扩展

```python
# 入库时添加租户标识
payload = {
    "Content": text_chunk,
    "Original_file": file_path,
    "tenant_id": tenant_id,          # 新增
    "department_id": department_id,  # 新增（可选）
    "metadata": {
        "is_table": False,
        "child_content": "...",
        "access_level": "public",    # 新增：数据访问级别
    }
}
```

---

## 四、安全性增强方案

### 4.1 认证体系升级

```
当前: JWT (自签发)
          ↓
企业级: OAuth2 / SAML / LDAP 集成
```

**推荐架构：**

```python
# backend/app/core/auth.py
from fastapi.security import OAuth2AuthorizationCodeBearer

# 支持 OIDC (企业微信/钉钉/飞书/AD)
oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl="https://your-idp.com/oauth2/authorize",
    tokenUrl="https://your-idp.com/oauth2/token",
)

# 或 SAML (ADFS)
from python3_saml import SamlClient
saml_client = SamlClient(
    sp_entity_id="rag-assistant",
    idp_metadata_url="https://adfs.company.com/FederationMetadata/2007-06/FederationMetadata.xml",
)
```

### 4.2 RBAC 权限模型

```python
# backend/app/schemas/user.py
class UserRole(str, Enum):
    ADMIN = "admin"          # 系统管理
    KB_ADMIN = "kb_admin"    # 知识库管理
    USER = "user"            # 普通用户
    VIEWER = "viewer"        # 仅查看

class Permission:
    # 知识库权限
    KB_UPLOAD: bool          # 上传文档
    KB_DELETE: bool          # 删除文档
    KB_QUERY: bool           # 查询
    KB_MANAGE: bool          # 管理
    
    # 用户权限
    USER_CREATE: bool        # 创建用户
    USER_DELETE: bool        # 删除用户

# 权限矩阵
ROLE_PERMISSIONS = {
    "admin": {
        "KB_UPLOAD": True, "KB_DELETE": True, "KB_QUERY": True, "KB_MANAGE": True,
        "USER_CREATE": True, "USER_DELETE": True,
    },
    "kb_admin": {
        "KB_UPLOAD": True, "KB_DELETE": True, "KB_QUERY": True, "KB_MANAGE": True,
        "USER_CREATE": False, "USER_DELETE": False,
    },
    "user": {
        "KB_UPLOAD": False, "KB_DELETE": False, "KB_QUERY": True, "KB_MANAGE": False,
    },
    "viewer": {
        "KB_QUERY": True,  # 只能查询
    },
}
```

### 4.3 网络安全

| 层面 | 措施 | 工具/配置 |
|------|------|-----------|
| 边界防护 | WAF、DDoS防护 | Kong / Cloudflare |
| 内部隔离 | Network Policy | K8s NetworkPolicy |
| 数据加密 | TLS 1.3、存储加密 | Secrets管理 |
| API安全 | Rate Limiting、签名验证 | Kong Plugin |

---

## 五、可观测性方案

### 5.1 监控栈

```
┌─────────────────────────────────────────────────────┐
│                    Grafana Dashboard                 │
│    ┌─────────┐    ┌─────────┐    ┌─────────┐        │
│    │ Metrics │    │  Logs   │    │ Traces  │        │
│    └─────────┘    └─────────┘    └─────────┐        │
└─────────────────────────────────────────────────────┘
        │                │                │
        ▼                ▼                ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Prometheus   │  │    Loki       │  │   Tempo       │
│  (Metrics)    │  │    (Logs)     │  │  (Traces)     │
└───────────────┘  └───────────────┘  └───────────────┘
        │                │                │
        └────────────────┼────────────────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ OpenTelemetry │
                 │   Collector   │
                 └───────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
 ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
 │  Backend    │ │   Qdrant    │ │  Redis      │
 │  (OTLP)     │ │  (Metrics)  │ │  (Metrics)  │
 └─────────────┘ └─────────────┘ └─────────────┘
```

### 5.2 关键指标

| 分类 | 指标 | Prometheus 名称 |
|------|------|-----------------|
| **检索性能** | 检索延迟 P50/P95/P99 | `rag_search_latency_seconds` |
| | 检索命中率 | `rag_search_hit_rate` |
| | Rerank 耗时 | `rag_rerank_duration_seconds` |
| **LLM调用** | Token消耗 | `llm_tokens_total{type=input/output}` |
| | 调用延迟 | `llm_request_latency_seconds` |
| | 成本累计 | `llm_cost_total_dollars` |
| | 错误率 | `llm_request_errors_total` |
| **系统健康** | 活跃会话数 | `rag_active_sessions` |
| | Qdrant 点数 | `qdrant_points_count` |
| | 内存使用 | `process_memory_usage_bytes` |
| **业务指标** | 文件入库数 | `rag_files_ingested_total` |
| | 用户查询数 | `rag_queries_total` |

### 5.3 Backend 集成示例

```python
# backend/app/core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

SEARCH_LATENCY = Histogram(
    'rag_search_latency_seconds',
    'Search latency',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

LLM_TOKENS = Counter(
    'llm_tokens_total',
    'LLM token consumption',
    ['model', 'type']  # type: input/output
)

ACTIVE_SESSIONS = Gauge(
    'rag_active_sessions',
    'Number of active chat sessions'
)

# 使用示例
with SEARCH_LATENCY.time():
    results = database_toolkit.search_database(query)
```

---

## 六、LLM Gateway 方案

### 6.1 LiteLLM Proxy 集成

```yaml
# litellm_config.yaml
model_list:
  - model_name: main-chat
    litellm_params:
      model: openai/qwen-plus
      api_base: https://api.aliyun.com/v1
      api_key: os.environ/ALIYUN_API_KEY
  - model_name: main-chat
    litellm_params:
      model: openai/deepseek-chat
      api_base: https://api.deepseek.com/v1
      api_key: os.environ/DEEPSEEK_API_KEY
  - model_name: intent-router
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEY

# 负载均衡：轮询调用多个 provider
router_settings:
  routing_strategy: simple-router  # 或 latency-based-routing
  
# Fallback 配置
fallbacks:
  - main-chat:
      - deepseek-chat
      - gpt-4o-mini
      
# Rate Limiting
litellm_settings:
  drop_params: True
  set_verbose: False
  max_budget: 1000  # 每日预算上限 ($)
  
# 成本追踪
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: postgresql://user:pass@postgres:5432/litellm
```

### 6.2 集成到 Backend

```python
# backend/app/core/model_runtime.py 改造
# 当前: 直接调用 OpenAI API
# 改为: 通过 LiteLLM Proxy

import httpx

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")

async def stream_model_via_litellm(
    model_name: str,
    messages: list,
    **kwargs
):
    """通过 LiteLLM Proxy 调用，获得负载均衡和成本追踪"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{LITELLM_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_MASTER_KEY}"},
            json={
                "model": model_name,
                "messages": messages,
                "stream": True,
                **kwargs
            },
            timeout=60.0,
        )
        # 流式返回...
```

---

## 七、CI/CD 与零停机部署

### 7.1 部署策略

```
开发环境: Docker Compose (单副本)
          ↓
预发环境: Docker Compose (多副本) 或 K8s
          ↓
生产环境: Kubernetes (Deployment + HPA)
```

### 7.2 Kubernetes Deployment

```yaml
# k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rag-backend
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0  # 零停机
  selector:
    matchLabels:
      app: rag-backend
  template:
    spec:
      containers:
      - name: backend
        image: rag-backend:v1.2.0
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
          limits:
            memory: "8Gi"
            cpu: "4"
        env:
        - name: QDRANT_URL
          value: "http://qdrant-cluster:6333"
        - name: REDIS_URL
          value: "redis://redis-cluster:6379/0"
        - name: LITELLM_URL
          value: "http://litellm:4000"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 30
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: rag-backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: rag-backend
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### 7.3 CI Pipeline (GitHub Actions)

```yaml
# .github/workflows/deploy.yaml
name: Deploy RAG Assistant

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    
    - name: Build Backend Image
      run: docker build -f Dockerfile.backend -t rag-backend:${{ github.sha }} .
    
    - name: Build Frontend Image  
      run: docker build -f Dockerfile.frontend -t rag-web:${{ github.sha }} .
    
    - name: Push to Registry
      run: |
        docker push registry.company.com/rag-backend:${{ github.sha }}
        docker push registry.company.com/rag-web:${{ github.sha }}
    
    - name: Deploy to K8s
      run: |
        kubectl set image deployment/rag-backend \
          backend=registry.company.com/rag-backend:${{ github.sha }}
        kubectl rollout status deployment/rag-backend --timeout=300s
    
    - name: Run Smoke Tests
      run: |
        curl -f https://rag.company.com/health
        python scripts/smoke_hybrid_retrieval.py
```

---

## 八、数据管理与备份

### 8.1 Qdrant 备份策略

```bash
# 定时备份脚本
#!/bin/bash
# backup_qdrant.sh

BACKUP_DIR="/backup/qdrant"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建快照
curl -X POST "http://qdrant:6333/collections/database/snapshots/upload"

# 下载快照
curl "http://qdrant:6333/collections/database/snapshots" \
  -o "${BACKUP_DIR}/snapshot_${DATE}.tar"

# 上传到对象存储
aws s3 cp "${BACKUP_DIR}/snapshot_${DATE}.tar" \
  s3://company-backups/qdrant/

# 保留策略：7天内每日备份，4周内每周备份
```

### 8.2 文档版本管理

```python
# tools/load_files.py 改造
def ingest_document(
    file_path: str,
    tenant_id: str,
    version: str = "v1",
    **kwargs
):
    """
    支持文档版本管理：
    - 同一文档不同版本共存
    - 可按版本检索或删除旧版本
    """
    payload = {
        "Content": text_chunk,
        "Original_file": file_path,
        "tenant_id": tenant_id,
        "doc_version": version,        # 新增
        "ingested_at": datetime.now().isoformat(),
    }
    
    # 入库...

def delete_document_version(file_tag: str, version: str = None):
    """删除指定版本或所有版本"""
    filter_condition = models.Filter(
        must=[models.FieldCondition(
            key="Original_file",
            match=models.MatchValue(value=file_tag)
        )]
    )
    if version:
        filter_condition.must.append(
            models.FieldCondition(
                key="doc_version",
                match=models.MatchValue(value=version)
            )
        )
```

---

## 九、改造优先级路线图

### Phase 1：基础增强 (1-2 周)

| 任务 | 改动 | 优先级 |
|------|------|--------|
| LiteLLM Proxy 集成 | 新增独立服务 | P0 |
| Prometheus 指标埋点 | backend/app/core/metrics.py | P0 |
| 日志结构化 | loguru 配置 | P1 |
| 健康检查增强 | /health 详细信息 | P1 |

### Phase 2：会话无状态化 (2-3 周)

| 任务 | 改动 | 优先级 |
|------|------|--------|
| Session 执行态 Redis 存储 | chat_service.py 重构 | P0 |
| Agent Memory 迁移到 Redis | agent_memory.py | P0 |
| Transcript 迁移到 PostgreSQL | chat_sessions 表 | P1 |

### Phase 3：多租户支持 (2-3 周)

| 任务 | 改动 | 优先级 |
|------|------|--------|
| Tenant ID Payload 扩展 | qdrant.py, load_files.py | P0 |
| RBAC 权限模型 | user_service.py | P0 |
| 多租户 API 隔离 | api/v1 路由改造 | P1 |

### Phase 4：K8s 部署 (2-4 周)

| 任务 | 改动 | 优先级 |
|------|------|--------|
| K8s Deployment 编写 | k8s/*.yaml | P0 |
| HPA 自动扩缩容 | HPA 配置 | P1 |
| NetworkPolicy | 网络隔离 | P1 |
| Secrets 管理 | K8s Secrets | P1 |

### Phase 5：安全与合规 (持续)

| 任务 | 改动 | 优先级 |
|------|------|--------|
| OAuth2/SAML 集成 | auth.py | P0 (企业必须) |
| API Gateway | Kong/Traefik | P1 |
| WAF 配置 | 安全规则 | P1 |
| 审计日志 | PostgreSQL 表 | P1 |

---

## 十、成本估算

### 10.1 硬件资源估算 (100-500 用户)

| 组件 | 配置 | 月成本估算 |
|------|------|------------|
| Backend Pods | 3x 4C8G | ~$300 |
| Qdrant Cluster | 3x 8C16G | ~$600 |
| Redis Cluster | 3x 2C4G | ~$150 |
| PostgreSQL | 1x 4C8G | ~$200 |
| LiteLLM Gateway | 1x 2C4G | ~$100 |
| MinIO/S3 | 100GB | ~$20 |
| **LLM Token** | ~100万/月 | ~$500-2000 |
| **总计** | | **~$1800-3300/月** |

### 10.2 LLM 成本优化策略

1. **Intent Router 用小模型** (gpt-4o-mini / qwen-turbo)
2. **缓存高频查询** (Redis 缓存答案)
3. **Rerank 本地模型** (已有 bge-reranker)
4. **Prompt 精简** (减少 input token)
5. **LiteLLM Budget 限制** (预算上限)

---

## 十一、总结与建议

### 当前项目基础优势

- 已完成 Qdrant 服务化、Redis 会话索引、共享存储路径统一
- 混合检索、Rerank、流式响应都已实现
- Docker Compose 编排成熟

### 企业级升级核心要点

1. **最关键改造**：会话执行态无状态化（迁移到 Redis）
2. **必备组件**：LiteLLM Gateway（多 Provider、成本追踪）
3. **安全必备**：OAuth2/SAML 集成 + RBAC
4. **可观测性**：Prometheus + Grafana + OpenTelemetry
5. **基础设施**：从 Docker Compose 迁移到 Kubernetes

### 分阶段推进建议

- 先完成 Phase 1-2（基础增强 + 无状态化），验证 Docker Compose 多副本
- 再完成 Phase 3-4（多租户 + K8s），实现完整企业级能力
- Phase 5 按合规要求逐步落地

---

## 附录：关键代码改动位置

| 改动 | 文件路径 | 改动类型 |
|------|----------|----------|
| 多租户 Payload | `tools/qdrant.py`, `tools/load_files.py` | 扩展 |
| RBAC 权限 | `backend/app/schemas/user.py`, `backend/app/services/user_service.py` | 新增 |
| Prometheus 指标 | `backend/app/core/metrics.py` | 新增 |
| LiteLLM 集成 | `backend/app/core/model_runtime.py` | 改造 |
| Session 无状态化 | `backend/app/services/chat_service.py` | 重构 |
| OAuth2/SAML | `backend/app/core/auth.py` | 新增 |
| K8s 配置 | `k8s/*.yaml` | 新增目录 |
| CI Pipeline | `.github/workflows/deploy.yaml` | 新增 |

---

*文档生成日期: 2026-04-20*