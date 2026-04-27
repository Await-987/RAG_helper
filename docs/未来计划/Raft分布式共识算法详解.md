# Raft 分布式共识算法详解

> 本文档详细讲解 Raft 算法及其在 Qdrant 分布式部署中的应用

---

## 一、Raft 是什么

**Raft** 是一种分布式共识算法（Consensus Algorithm），用于让多台服务器在分布式环境中达成一致。

### 1.1 核心目标

在分布式系统中，多个节点需要：
- **数据一致性**：所有节点看到相同的数据
- **可用性**：部分节点故障时系统仍能运行
- **容错性**：少数节点故障不影响整体

### 1.2 为什么叫 Raft

Raft 的设计目标是易于理解（Replicable And Fault-Tolerant），相比于 Paxos 算法，Raft 更容易理解和实现。

---

## 二、解决什么问题

### 2.1 分布式系统的挑战

假设有 3 个数据库节点存储用户数据：

```
节点-A: 用户余额 = 100 元
节点-B: 用户余额 = 100 元
节点-C: 用户余额 = 100 元
```

用户发起转账请求，扣款 50 元：

```
请求到达节点-A → 余额改为 50
请求到达节点-B → 余额改为 50
请求到达节点-C → 网络故障，没收到请求，余额仍是 100
```

**问题**：三个节点数据不一致，用户查询时结果随机。

### 2.2 Raft 的解决方案

Raft 保证：**只要多数节点达成一致，就认为写入成功**。

```
写入流程：
节点-A 收到扣款请求 → 余额改为 50 → 发送复制请求
节点-B 收到复制 → 余额改为 50 → 确认成功
节点-C 没收到复制 → 余额仍是 100

结果：节点-A 和 B 已达成一致（2/3 = 多数）
      → 写入成功，返回用户
      → 节点-C 稍后会自动同步
```

---

## 三、核心概念

### 3.1 节点角色

Raft 集群中的节点有三种角色：

| 角色 | 英文 | 职责 | 数量 |
|------|------|------|------|
| **领导者** | Leader | 处理所有客户端请求，复制日志给 Follower | 1 个 |
| **跟随者** | Follower | 接收 Leader 的日志复制，响应投票请求 | 多个 |
| **候选人** | Candidate | Leader 故障时发起选举，争取成为新 Leader | 临时 |

### 3.2 状态流转

```
            选举超时
    Follower ──────────→ Candidate
       ↑                     │
       │                     │ 获得多数票
       │                     ↓
       └───── Leader ←───────
                 │
                 │ 发现更高任期
                 ↓
            Follower
```

### 3.3 任期（Term）

Raft 将时间划分为多个任期（Term）：

```
Term 1: Leader-A 上任，处理请求
        ↓
Term 2: Leader-A 故障，Candidate-B 选举成功
        ↓
Term 3: Leader-B 故障，Candidate-C 选举成功
```

每个任期只有一个 Leader，任期号单调递增。

---

## 四、工作原理

### 4.1 请求处理流程

**写入请求**：

```
客户端请求写入数据 X
      ↓
Leader 收到请求，写入本地日志（未提交）
      ↓
Leader 将日志复制发送给所有 Follower
      ↓
Follower 收到后写入本地日志，返回确认
      ↓
Leader 收到多数 Follower 确认
      ↓
Leader 提交日志（应用到状态机）
      ↓
Leader 通知 Follower 提交
      ↓
Leader 返回客户端：写入成功
```

**读取请求**：

```
客户端请求读取数据
      ↓
Leader 或 Follower 直接返回本地数据
      ↓
（强一致性场景：必须从 Leader 读）
```

### 4.2 选举流程

当 Leader 故障时，Follower 会发起选举：

```
Step 1: Follower 等待 Leader 心跳超时
        ↓
Step 2: Follower 转为 Candidate，任期号 +1
        ↓
Step 3: Candidate 向其他节点发送投票请求
        ↓
Step 4: 其他节点根据规则投票
        ↓
Step 5: Candidate 收到多数票 → 成为新 Leader
        ↓
Step 6: 新 Leader 开始发送心跳，确立领导地位
```

### 4.3 投票规则

节点投票时遵循以下规则：

| 条件 | 是否投票 |
|------|----------|
| 候选人任期 ≥ 自己任期 | ✅ |
| 候选人日志至少和自己一样新 | ✅ |
| 本任期已投过票 | ❌ |
| 候选人日志比自己旧 | ❌ |

### 4.4 日志复制

Leader 维护两个关键索引：

| 索引 | 说明 |
|------|------|
| **nextIndex** | 对每个 Follower，下一个要发送的日志索引 |
| **matchIndex** | 对每个 Follower，已确认复制的最高日志索引 |

复制流程：

```
Leader 的 log: [1, 2, 3, 4, 5]  nextIndex[Follower-B] = 3

发送: [3, 4, 5] 给 Follower-B

Follower-B 的 log: [1, 2]  → 收到后追加 → [1, 2, 3, 4, 5]

Follower-B 确认: matchIndex[Follower-B] = 5
```

---

## 五、容错能力

### 5.1 故障场景分析

假设 5 节点集群：

```
节点-1: Leader
节点-2: Follower
节点-3: Follower
节点-4: Follower
节点-5: Follower
```

| 故障场景 | 系统状态 | 能否继续服务 |
|----------|----------|--------------|
| 1 个 Follower 故障 | 4/5 正常 | ✅ 正常 |
| Leader 故障 | 重新选举 | ✅ 短暂中断后恢复 |
| 2 个节点故障 | 3/5 正常（多数） | ✅ 正常 |
| 3 个节点故障 | 2/5 正常（少数） | ❌ 无法达成共识 |
| 网络分区 | 多数分区正常 | ✅ 多数分区可用 |

### 5.2 容错公式

**N 节点集群可容忍故障节点数 = (N - 1) / 2**

| 集群规模 | 容错节点数 |
|----------|------------|
| 3 节点 | 1 个 |
| 5 节点 | 2 个 |
| 7 节点 | 3 个 |

---

## 六、Raft 与 Paxos 对比

| 特性 | Raft | Paxos |
|------|------|-------|
| **理解难度** | 较容易 | 非常困难 |
| **实现难度** | 较简单 | 复杂 |
| **角色划分** | 明确（Leader/Follower） | 不明确 |
| **日志顺序** | 强顺序 | 需额外维护 |
| **性能** | 相当 | 相当 |
| **应用场景** | etcd, Consul, TiKV, Qdrant | Google Chubby, Spanner |

---

## 七、Qdrant 中的 Raft 应用

### 7.1 Qdrant 分布式架构

Qdrant 使用 Raft 实现分布式集群：

```
┌─────────────────────────────────────────────────┐
│              Qdrant Raft Cluster                 │
│                                                  │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐     │
│   │ Node-1  │    │ Node-2  │    │ Node-3  │     │
│   │ (Leader)│───→│(Follower)│───→│(Follower)│    │
│   └─────────┘    └─────────┘    └─────────┘     │
│                                                  │
│   向量数据通过 Raft 复制到所有节点                │
└─────────────────────────────────────────────────┘
```

### 7.2 配置示例

```yaml
# qdrant/config.yaml（分布式模式）
cluster:
  enabled: true
  
  # P2P 通信端口
  p2p:
    port: 6335
    
  # Raft 配置
  consensus:
    tick_period_ms: 100           # 心跳周期
    election_timeout_ms: 1000     # 选举超时
    commit_timeout_ms: 50         # 提交超时
    max_messages_per_tick: 100    # 每周期最大消息数
    
  # 初始集群配置
  initial_peers:
    - "qdrant-1:6335"
    - "qdrant-2:6335"
    - "qdrant-3:6335"

storage:
  performance:
    optimize_for_retrieval: true  # 优化检索性能
```

### 7.3 Docker Compose 部署

```yaml
# Qdrant 3节点集群
services:
  qdrant-1:
    image: qdrant/qdrant:latest
    container_name: qdrant-1
    hostname: qdrant-1
    environment:
      - QDRANT__CLUSTER__ENABLED=true
    volumes:
      - ./data/qdrant-1:/qdrant/storage
      - ./config/cluster.yaml:/qdrant/config/production.yaml
    ports:
      - "6333:6333"
      - "6335:6335"
      
  qdrant-2:
    image: qdrant/qdrant:latest
    container_name: qdrant-2
    hostname: qdrant-2
    environment:
      - QDRANT__CLUSTER__ENABLED=true
    volumes:
      - ./data/qdrant-2:/qdrant/storage
      - ./config/cluster.yaml:/qdrant/config/production.yaml
    expose:
      - "6333"
      - "6335"
      
  qdrant-3:
    image: qdrant/qdrant:latest
    container_name: qdrant-3
    hostname: qdrant-3
    environment:
      - QDRANT__CLUSTER__ENABLED=true
    volumes:
      - ./data/qdrant-3:/qdrant/storage
      - ./config/cluster.yaml:/qdrant/config/production.yaml
    expose:
      - "6333"
      - "6335"
```

### 7.4 Qdrant 集群特性

| 特性 | 说明 |
|------|------|
| **数据分片** | Collection 可分布在不同节点 |
| **副本复制** | 每个分片有多个副本（Raft 保证一致性） |
| **读写分离** | 写入必须通过 Leader，读取可从任意节点 |
| **故障转移** | Leader 故障自动选举新 Leader |
| **负载均衡** | 读取请求可分布到多个节点 |

---

## 八、什么时候需要 Raft 集群

### 8.1 决策矩阵

| 因素 | 单实例足够 | 需要 Raft 集群 |
|------|------------|----------------|
| **向量数量** | <1000万 | >1000万 |
| **可用性要求** | 允许短暂中断 | 必须 24/7 可用 |
| **容灾要求** | 无 | 需跨机房/跨区域 |
| **并发 QPS** | <100 | >1000 |
| **预算** | 低 | 高（多节点成本） |
| **运维能力** | 低 | 高（需维护集群） |

### 8.2 本项目的判断

**当前不需要 Raft 集群**。

原因：
- 向量数据量不大（电力行业文档）
- 单 Qdrant 实例性能足够（毫秒级检索）
- 多 Backend 并发瓶颈在 LLM，不在 Qdrant
- 增加集群复杂度高，收益低

### 8.3 未来何时考虑

当出现以下情况时，再考虑 Qdrant 集群：

1. **数据量超过单机容量**
   - 向量数 > 1000万
   - 单机内存不足

2. **高可用成为刚需**
   - 服务不允许任何中断
   - 需跨机房灾备

3. **检索性能成为瓶颈**
   - 单实例 QPS 不够
   - 需要横向扩展检索能力

---

## 九、常见问题

### 9.1 为什么写入必须通过 Leader？

Raft 保证一致性通过 Leader 统一协调：
- 所有写入先到 Leader
- Leader 复制到 Follower
- 多数确认后才提交

如果允许任意节点写入，会出现：
```
节点-A 写入 X → 复制到 B、C
节点-C 同时写入 Y → 复制到 A、B
结果：日志顺序冲突，无法达成一致
```

### 9.2 选举期间服务可用吗？

选举期间（通常几百毫秒）：
- **写入请求**：不可用（无 Leader）
- **读取请求**：可能可用（Follower 可响应，但数据可能不是最新）

强一致性系统会短暂中断，但通常影响很小。

### 9.3 Follower 数据会落后吗？

可能场景：
- 网络延迟导致复制慢
- Follower 刚重启

解决方案：
- Leader 维护 nextIndex，增量复制
- Follower 重启后主动拉取缺失日志

### 9.4 Raft 集群性能如何？

| 操作 | 性能特点 |
|------|----------|
| 写入 | 需复制到多数节点，延迟较高 |
| 读取 | 可从任意节点读，延迟低 |
| 吞吐 | 受限于 Leader 单点，但足够高 |

优化方式：
- 批量写入减少复制次数
- 读取负载均衡到 Follower

---

## 十、总结

### Raft 核心要点

1. **共识算法**：让分布式节点达成一致
2. **角色划分**：Leader 处理写入，Follower 接收复制
3. **多数原则**：多数节点确认才算成功
4. **容错能力**：N 节点容忍 (N-1)/2 个故障
5. **选举机制**：Leader 故障自动选举新 Leader

### 本项目建议

| 当前 | 未来 |
|------|------|
| 单 Qdrant 实例 | 先验证并发能力 |
| 多 Backend 共享 | 瓶颈在 LLM，不在 Qdrant |
| 无需 Raft 集群 | 数据量/可用性需求变化时再考虑 |

---

## 参考资料

- [Raft 论文原文](https://raft.github.io/raft.pdf)
- [Raft 可视化演示](https://raft.github.io/)
- [Qdrant 分布式文档](https://qdrant.tech/documentation/guides/distributed_deployment/)
- [etcd Raft 实现](https://github.com/etcd-io/etcd)

---

*文档创建日期: 2026-04-20*