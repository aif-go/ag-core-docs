|---
tags:
  - ag-core
  - contribute
  - agrmq
  - rabbitmq
  - architecture
  - design
---

# AgRMQ — RabbitMQ 集成方案讨论

> 日期：2026-06-24 | 状态：讨论中

## 背景

ag-core 已有 Kafka 消息队列集成（`agsarama`，`contribute/agsarama/`），但尚未支持 RabbitMQ。需要进行 RabbitMQ 集成方案讨论。

## 现状

| 消息中间件 | 状态 | 包名 | 位置 |
|-----------|------|------|------|
| Kafka | ✅ 已集成 | `agsarama` | `contribute/agsarama/` |
| RabbitMQ | ❌ 不存在 | — | — |

## 设计约束

- **不以 agsarama 为模板**。RabbitMQ 的机制（AMQP 协议、Connection/Channel 模型、Exchange/Queue/Binding、ACK 生命周期）与 Kafka 差异很大，不应硬套 agsarama 的"配置封装层"思路。
- **基于 Go 主流 RabbitMQ 客户端库**（当前生态首选 `github.com/rabbitmq/amqp091-go`，即原 `streadway/amqp` 的社区维护 fork）。
- **对标 Spring AMQP**。核心目标是实现与 Spring AMQP 相同抽象级别但又符合 Go 语言习惯的封装能力。

## RabbitMQ 集成的核心问题域

```
┌─────────────────────────────────────────────────┐
│                  agrmq 要解决什么                   │
├─────────────────────────────────────────────────┤
│                                                   │
│  ① 连接管理（Connection 的创建 / 重连 / 心跳）        │
│     - amqp091-go 的 Connection 复用                │
│     - 自动重连 + 通知上层                           │
│     - 优雅关闭                                     │
│                                                   │
│  ② Channel 生命周期                                │
│     - Channel 是 AMQP 的核心操作单元                 │
│     - 需要在重连后重建 Channel                      │
│     - 生产/消费用不同的 Channel 策略                  │
│                                                   │
│  ③ 拓扑声明（Exchange / Queue / Binding）           │
│     - RabbitMQ 独有的概念，Kafka 没有                │
│     - 启动时声明，失败时不要重复声明                   │
│     - 代码定义 vs 配置定义                           │
│                                                   │
│  ④ 生产（Publish）                                 │
│     - 相对简单：routing_key + exchange + body        │
│     - 关注：Publish Confirms、事务                   │
│                                                   │
│  ⑤ 消费（Consume）                                 │
│     - 最重的部分                                    │
│     - Delivery 处理 → ACK/NACK → 重试/死信           │
│     - QoS (prefetch)                                │
│     - 优雅关闭（消费完再关）                          │
│     - 错误恢复                                      │
│                                                   │
└─────────────────────────────────────────────────┘
```

---

## 对标 Spring AMQP 可行性评估

### 总览

| 领域 | Spring AMQP 组件 | Go 可行性 | 难度 | 项目实用度 |
|------|-----------------|-----------|------|-----------|
| 连接管理 | CachingConnectionFactory | ✅ 完全可行 | 低 | 高 |
| 消息发送 | RabbitTemplate / convertAndSend | ✅ 完全可行 | 中 | 高 |
| 消息消费 | @RabbitListener + ListenerContainer | ✅ 可行（注册式替代注解式） | 高 | 高 |
| 拓扑声明 | RabbitAdmin + @Bean Queue/Exchange/Binding | ✅ 完全可行 | 中 | 高 |
| 消息转换 | MessageConverter（Jackson/Simple） | ✅ 完全可行 | 低 | 高 |
| 重试 + 死信 | RetryTemplate + RepublishMessageRecoverer | ✅ 完全可行 | 中 | 高 |
| AMQP 事务 | RabbitTransactionManager | ⚠️ 可实现但实用性低 | 高 | 低 |
| 并发管理 | ThreadPoolTaskExecutor | ✅ 完全可行 | 低 | 高 |
| 消费者 exclusive | ExclusiveConsumer | ✅ 完全可行 | 低 | 中 |
| 批量消费 | BatchMessageListener | ✅ 完全可行 | 中 | 中 |
| RPC 模式 | convertSendAndReceive | ✅ 完全可行 | 中 | 中 |

### 逐项分析

#### 1. CachingConnectionFactory — 连接管理 ✅ 完全可行

**难度：低 | 工作量：~150 行 | 核心逻辑**

- **Connection 创建**：封装 `amqp091.Dial()`，支持 URI / TLS / SASL 多种认证
- **Channel 缓存**：用 `sync.Pool` 或自定义池管理 Channel 复用
- **自动重连**：监听 `Connection.NotifyClose()`，触发重连 → 重建所有 Channel → 恢复消费
- **优雅关闭**：等待消费完成 → 关闭 Channel → 关闭 Connection

比 Spring 更简洁的原因：
  - Spring 需要 `SingleConnectionFactory → CachingConnectionFactory → PublisherCallbackChannel` 多层继承
  - Go 一个 `ConnectionManager` struct 搞定

**关键注意事项：**
- `amqp091-go` 的 Connection 或 Channel 断开后**不可复用**，必须重建
- 重连后需要重建所有消费者订阅（`Consume()` 返回的 delivery channel 会关闭）
- Channel 非线程安全，每一个 goroutine 应使用独占 Channel（或加锁保护）

---

#### 2. RabbitTemplate — 泛型 Producer ✅ 完全可行

**难度：中 | 工作量：~200 行 | 核心逻辑**

Spring RabbitTemplate 的核心流程：
```
Object → MessageConverter → AMQP Message → Channel.Publish
                                  ↓
                          Publish Confirms ← channel.NotifyPublishConfirms
```

**Go 方案设计：**

```go
// 泛型生产者
type Producer[T any] struct {
    ch     *amqp091.Channel
    conv   MessageConverter[T]
    conf   <-chan amqp091.Confirmation  // Publish Confirms
}

func (p *Producer[T]) Publish(ctx context.Context, msg T, opts ...PublishOption) error {
    body, err := p.conv.Marshal(msg)
    // 提取 options: exchange, routingKey, mandatory, immediate, headers
    return p.ch.PublishWithContext(ctx, exchange, key, mandatory, immediate, amqp091.Publishing{
        ContentType: p.conv.ContentType(),
        Body:        body,
        Headers:     headers,
    })
}

// RPC 模式
func (p *Producer[T]) Request(ctx context.Context, msg T, timeout time.Duration) (*amqp091.Delivery, error)
```

**核心能力覆盖：**
| Spring RabbitTemplate | Go Producer[T] |
|----------------------|----------------|
| `convertAndSend(ex, rk, msg)` | `Publish(ctx, msg, WithRoutingKey(rk), WithExchange(ex))` |
| `convertSendAndReceive(ex, rk, msg)` | `Request(ctx, msg, timeout)` |
| `setConfirmCallback(cb)` | 内置 Publish Confirms + 错误处理 |
| `setReturnCallback(cb)` | `WithMandatory(true)` + NotifyReturn |
| `setMessageConverter(c)` | 泛型 `MessageConverter[T]` 注入 |

**Go 优势：**
- 泛型保证类型安全，Spring 的 `Object` 参数需要在运行时转换
- Option 模式让 API 可扩展，不产生 `convertAndSend` 的几十个重载

---

#### 3. @RabbitListener — 声明式消费 🔄 可用注册式替代

**难度：高 | 工作量：~350 行 | 最复杂的模块**

Spring 通过注解 + 反射 + BeanPostProcessor 实现声明式消费。Go 无注解，需用**结构体注册式**替代：

```go
// 方案：Go 结构体注册（等价于 @RabbitListener）
type ConsumerGroup struct {
    Queue        string
    Exchange     string
    RoutingKey   string  // 声明绑定
    Concurrency  int     // 并发数（等价于 concurrency = "3-10"）
    Prefetch     int     // QoS
    AutoAck      bool
    Retry        *RetryPolicy
    Handler      MessageHandler  // 业务处理器
}

// 注册方式（二选一或兼用）：

// A. 函数式注册（轻量）
consumer := agrmq.NewConsumer("order.paid",
    agrmq.WithConcurrency(5),
    agrmq.WithHandler(OrderPaidHandler{}),
)

// B. 结构体声明 + fx 组标签（适合复杂场景）
fx.Provide(fx.Annotate(
    func() agrmq.ConsumerGroup {
        return agrmq.ConsumerGroup{
            Queue:       "order.paid",
            Concurrency: 5,
            Prefetch:    10,
            Handler:     OrderPaidHandler{},
        }
    },
    fx.ResultTags(`group:"agrmq_consumers"`),
))

// 处理器接口——业务方只需实现它
type MessageHandler interface {
    Handle(ctx context.Context, msg Delivery) error
}

// 框架自动管理：
// - Consume 注册
// - goroutine 分派
// - ACK/NACK
// - 重试/死信
// - 优雅退出
```

**消费容器生命周期设计：**
```
fx.Invoke 阶段
    │
    ▼
启动容器 ──► Consume() ──► delivery channel
    │                            │
    │                      ┌─────┴─────┐
    │                      ▼           ▼
    │                  goroutine-1   goroutine-N
    │                  (QoS 控制)    (QoS 控制)
    │
fx.Shutdown 阶段
    ▼
优雅关闭 ──► 停止接收消息 → 等待处理完成 → ACK 未确认 → 关闭 Channel
```

**⚠️ 主要复杂度来源：**
1. **重连态恢复**：Connection 断开后需重新 `Consume()` 注册
2. **QoS 与并发控制**：`basicQos` 配合 goroutine 池的协调
3. **优雅关闭**：信号 → 停止 Consume → 等 inflight 完成 → 关闭
4. **幂等性消费**：At-least-once 语义 + 重复检测是可选的

---

#### 4. RabbitAdmin — 拓扑声明 ✅ 完全可行

**难度：中 | 工作量：~250 行 | 启动时一次性工作**

**设计：** 参考 [Better way to declare RabbitMQ topology #1](https://www.rabbitmq.com/blog/2024/05/28/better-way-declare-topology)（RabbitMQ 官方推荐的拓扑声明方式）

```yaml
agrmq:
  topology:
    exchanges:
      - name: order.event
        type: topic
        durable: true
    queues:
      - name: order.paid
        durable: true
        arguments:
          x-dead-letter-exchange: order.dlx
          x-dead-letter-routing-key: order.paid.dead
        bindings:
          - exchange: order.event
            routing_key: "order.paid.#"
```

启动时 `fx.Invoke` 阶段自动 Apply：
```
解析 YAML → 生成声明顺序排序(Exchange→Queue→Binding) → 串行 Apply
```

**等价代码式 API**（也提供）：
```go
topo := agrmq.NewTopology().
    AddExchange("order.event", amqp.ExchangeTopic).
    AddQueue("order.paid", WithDLQ("order.dlx")).
    AddBinding("order.paid", "order.event", "order.paid.#")
```

**关键注意事项：**
- Exchange → Queue → Binding 的顺序：必须先声明 Exchange 再绑定 Queue
- `QueueDeclarePassive` vs `QueueDeclare`：生产环境首次部署 vs 重复启动
- 幂等声明：`QueueDeclare` 是幂等的，但参数变更会报错（需要 migration 策略）

---

#### 5. MessageConverter ✅ 完全可行

**难度：低 | 工作量：~80 行 | 模板代码为主**

```go
type MessageConverter[T any] interface {
    Marshal(v T) ([]byte, error)
    Unmarshal(data []byte) (T, error)
    ContentType() string
}

// 内置实现
type JSONMessageConverter[T any] struct{}  // ContentType: application/json
type StringMessageConverter struct{}        // ContentType: text/plain
// ProtoMessageConverter[T proto.Message]   // ContentType: application/x-protobuf
```

Go 泛型让转换器类型安全——不需要 Spring 中 `Message → Object` 的强制类型转换。

---

#### 6. RetryTemplate + MessageRecoverer ✅ 完全可行

**难度：中 | 工作量：~150 行 | 错误处理链**

```
消费收到消息
    │
    ▼
Handle(ctx, msg) → error
    │                  │
    │  err == nil      │  err != nil
    │                  ▼
    │              重试策略
    │           attempts < max
    │                  │
    │           ┌──────┴──────┐
    │           │             │
    │       重试等待    重试耗尽
    │           │             │
    │           ▼             ▼
    │      再次 Handle    ErrorRecoverer
    │                        │
    │                  ┌─────┴──────┐
    │                  ▼            ▼
    │               NACK+DLQ     Log + ACK
    │               (转发死信)    (吞掉)
    │
    ▼
  msg.Ack(false)
```

**策略链设计：**
```go
type RetryPolicy struct {
    MaxAttempts  int
    Backoff      time.Duration
    Multiplier   float64       // 指数退避系数
    MaxBackoff   time.Duration
    OnExhausted  ErrorRecoverer // 重试耗尽后的最终处理
}

// 内置 ErrorRecoverer：
// - RepublishToDLQ(exchange, routingKey) — 转发死信
// - LogAndDiscard() — 记录日志后确认
// - NackAndRequeue(maxRetries) — 重新入队
```

---

#### 7. AmqpTransactionManager ⚠️ 不推荐实现

**实用度评估：低 | 不列入核心范围**

**原因：**
1. **性能代价大**：RabbitMQ 事务模式比 Confirms 模式慢 2-3 倍（2000 vs 20000 msg/s）
2. **Go 缺少事务抽象**：Spring 有 `PlatformTransactionManager`，Go 无对应接口
3. **真正的问题不同**：跨 DB + MQ 一致性需用 **Outbox Pattern** 解决

**补偿方案（推荐）：**
```go
// Outbox Pattern 支持
type OutboxPublisher[T any] struct {
    db  *gorm.DB
    mq  Producer[T]
}

func (p *OutboxPublisher[T]) PublishAtomic(ctx context.Context, msg T) error {
    // 1. 开启 DB 事务
    // 2. 写入业务表 + outbox 记录（同事务）
    // 3. 异步轮询 outbox → 投递 MQ → 删除记录
    // = DB + MQ 最终一致性
}
```

---

#### 8. 并发管理 ✅ Go 有天然优势

**难度：低 | 天然优势**

| 特性 | Spring | Go |
|------|--------|-----|
| 线程成本 | ~1MB/线程 | ~4KB/goroutine |
| 并发抽象 | ThreadPoolTaskExecutor | goroutine + channel |
| 消息分派 | 阻塞队列 + Worker | channel range |

```go
// Go 消费容器的核心循环——比 Spring 的线程池 + 队列管理简单得多
func (c *consumer) start(concurrency int) {
    msgs, _ := c.ch.Consume(c.queue, "", false, false, false, false, nil)
    sem := make(chan struct{}, concurrency) // 信号量控制并发数
    for d := range msgs {
        sem <- struct{}{}
        go func(d amqp091.Delivery) {
            defer func() { <-sem }()
            c.handleWithRetry(c.ctx, d)
        }(d)
    }
}
```

---

## 复杂度与工作量总评

### 各模块复杂度

| 模块 | 复杂度 | 预估代码行 | 关键风险 |
|------|--------|-----------|---------|
| 连接管理 | 🔵 低 | ~150 | 重连态恢复语义 |
| 泛型 Producer | 🟡 中 | ~200 | Publish Confirms 异步处理 |
| 消费容器 | 🔴 高 | ~350 | 重连后恢复消费、优雅关闭 |
| 拓扑声明 | 🟡 中 | ~250 | 启动顺序、已有声明冲突 |
| MessageConverter | 🟢 低 | ~80 | 模板代码，基本无风险 |
| 重试策略 | 🟡 中 | ~150 | 死信循环检测 |
| 并发管理 | 🟢 低 | ~50 | goroutine 泄露防范 |
| FX 集成 | 🟢 低 | ~80 | 生命周期顺序 |
| **合计** | | **~1,310** | |

### 整体可行性

| 维度 | 评估 |
|------|------|
| **技术可行性** | ✅ 所有核心模块均可实现，无技术壁垒 |
| **进度可行性** | 核心代码约 1,300 行，属于中等体量组件，可在合理周期内完成 |
| **维护成本** | 低。核心逻辑集中在 7-8 个文件，无复杂继承链 |
| **对标充分性** | 覆盖 Spring AMQP 95% 日常使用场景，未被覆盖的（AMQP 事务）是实际项目中很少使用的能力 |
| **与 ag-core 整合** | 自然。ag_conf 配置绑定、fx 生命周期、fx group tag 扩展，与现有模式一致 |

---

## 封装层次方案（待决策）

按隔离度分三层，从轻到重：

| 层次 | 封装内容 | 复杂度 | 覆盖模块 |
|------|---------|--------|---------|
| **L1 — 连接管理** | Connection 创建/重连 + Channel 池 + `ag_conf` 配置 | 轻量 | 连接管理 |
| **L2 — 生产+消费框架** | L1 + 泛型 Producer/Consumer + ACK 管理 + 优雅关闭 | 适中 | 连接管理、Producer、Consumer、重试、Converter、并发 |
| **L3 — 声明式拓扑** | L2 + YAML 声明 Exchange/Queue/Binding + 消费 Handler 路由 | 较重 | 以上全部 + 拓扑声明 |

- **L1** — 对标 agsarama 的最浅层：只管连接配置，Producer/Consumer 由业务方自行管理。
- **L2** — 最推荐的"性价比"区间。封装 AMQP 原生的 Producer/Consumer，连接恢复、QoS、ACK、优雅关闭由框架处理。
- **L3** — 声明式拓扑管理，适合微服务场景基础设施即配置。

### 建议路径

```
实施阶段               交付产物
─────────             ─────────
Phase 1: L1+L2       agrmq 核心包（连接 + 生产 + 消费 + 重试）
Phase 2: L3          拓扑声明（YAML/code 式 + FX 集成）
Phase 3: 高级特性     批量消费、RPC、监控指标（可选）
```

---

## 集成思路：架构概览

### 包结构

```
contribute/agrmq/
├── config.go           # Config 结构体 + NewDefaultConfig + ag_conf 绑定
├── connection.go       # ConnectionManager（连接池 + 重连 + Channel 管理）
├── producer.go         # Producer[T] 泛型生产者（Publish / Request）
├── consumer.go         # 消费容器（Consume / 并发 / 优雅关闭）
├── topology.go         # 拓扑声明器（Exchange / Queue / Binding）
├── converter.go        # MessageConverter 接口 + JSON/Proto/String 实现
├── retry.go            # RetryPolicy + ErrorRecoverer
├── fx.go               # FxAgrmqModule + FxAgrmqGroupTag
├── opts.go             # PublishOption / ConsumerOption / TbInfoOpt 类似风格
├── docs/               # 使用文档
└── test/               # 集成测试（需 RabbitMQ 实例）
```

### 数据流

```
┌──────────────────────────────────────────────────────┐
│                    业务代码                            │
├──────────────────────────────────────────────────────┤
│                                                        │
│  Produce:                                              │
│    producer.Publish(ctx, orderEvent)                   │
│         │                                              │
│         ▼                                              │
│    Producer[T] ──┬── MessageConverter.Marshal          │
│                  └── Channel.PublishWithContext         │
│                                                        │
│  Consume:                                              │
│    consumer.Register("order.paid", handler)            │
│         │                                              │
│         ▼                                              │
│    Consumer ──┬── channel.Consume                      │
│               ├── goroutine pool                       │
│               ├── Handle → ACK/NACK                    │
│               └── RetryPolicy → ErrorRecoverer         │
│                                                        │
└──────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌────────────────┐       ┌────────────────┐
│ ConnectionMgr  │──────▶│  TopologyDecl  │
│ (重连/心跳)     │       │ (声明 EX/Q/B)   │
└────────────────┘       └────────────────┘
         │
         ▼
┌────────────────┐
│ amqp091-go     │──▶ RabbitMQ Broker
└────────────────┘
```

### 与 ag-core 现有机制的整合

| 整合点 | 方式 |
|--------|------|
| **配置** | `ag_conf.IBinder.Bind(cfg, "agrmq")` 从 YAML 绑定配置 |
| **DI** | `fx.Module("fx_agrmq_base")` 注入 `ConnectionManager`、`Producer[T]` 等 |
| **扩展** | `fx.ResultTags("group:\"agrmq\"")` 提供 ConfigOption 扩展 |
| **生命周期** | `fx.Lifecycle` 管理 Connection 的启动/优雅关闭 |

---

## 后续

需讨论确认封装层次，再进入详细设计。
