---
tags:
  - ag-core
  - ag-log
  - async
  - worker-pool
---

# 异步日志 async — Worker 池 + 队列

> 子包：`ag/ag_log/async/` | 基于 goroutine 的异步日志处理

## 职责

`async` 模块将原本同步阻塞的 `slog.Handler` 包装为**异步非阻塞**的 handler。应用调用 `logger.Info()` 立即返回，实际日志写入在后台 worker 中异步完成。

## 架构

```
AsyncHandler.Handle()
  ├── sync.Pool.Get() → logTask
  ├── record.Clone()  → 并发安全
  ├── workerGroup.Submit(task)
  │     ├── drop_new: 队列满则丢弃新日志（不阻塞）
  │     ├── block_wait: 队列满则阻塞等待
  │     └── drop_old: 队列满则丢弃最旧的日志
  └── 异步 worker 处理
        ├── handle.Handle() → 写入 zap/text 等
        └── taskPool.Put()  → 回收
```

## 数据结构

### AsyncGlobalProperties（配置 — `aglog.async`）

```go
type AsyncGlobalProperties struct {
    Groups map[string]AsyncGroupConfig  // Worker 组定义（可复用）
    Logs   map[string]AsyncLogConfig    // 异步日志实例定义
}
```

### AsyncGroupConfig（Worker 组配置）

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `Worker` | `int` | `1` | 并发 Worker 数量 |
| `Queue` | `int` | `10000` | 环形队列容量 |
| `FullStrategy` | `string` | `"drop_new"` | 队列满时策略 |
| `ShutdownTimeout` | `time.Duration` | `"1s"` | 关闭超时 |

### AsyncLogConfig（日志实例配置）

| 字段 | 说明 |
|------|------|
| `Group` | 引用哪个 WorkerGroup（名称） |
| `Log` | 引用哪个原始 handler（名称） |

## 三种满策略

| 策略 | `Submit()` 行为 | 适用场景 |
|------|----------------|----------|
| `drop_new` | 队列满 → 丢弃当前日志，`Dropped++` | 高吞吐、可丢日志 |
| `block_wait` | 队列满 → 阻塞直到有空位 | 关键日志不可丢 |
| `drop_old` | 队列满 → 丢弃最旧的日志再插入 | 同时保证新日志写入和数据新鲜度 |

## 核心组件

### AsyncHandler

`AsyncHandler` 是 `slog.Handler` 的一个装饰器，拦截 `Handle()` 方法将日志任务提交到 worker 池：

```go
func (h *AsyncHandler) Handle(ctx context.Context, r slog.Record) error {
    task := taskPool.Get().(*logTask)
    task.ctx = ctx
    task.record = r.Clone()     // 必须 Clone！原始 Record 由 slog 复用
    task.handler = h.original
    return h.workerGroup.Submit(task)
}
```

关键设计：
- **`sync.Pool` 回收 `logTask`**：降低 GC 压力，减少堆分配
- **`record.Clone()`**：确保并发安全。slog 的 `Handle` 调用方（`*slog.Logger`）会在调用后复用 `Record`，异步场景必须深拷贝
- **`original` handler 引用**：AsyncHandler 不自带写入能力，委托给底层 handler（如 zap）

### WorkerGroup

Worker 池 + 环形队列，是异步日志的核心引擎：

```go
type WorkerGroup struct {
    config    *AsyncGroupConfig
    logQueue  chan *logTask          // 有缓冲队列
    workers   []*worker              // worker goroutine 列表
    shutdownChan chan struct{}
    doneChan     chan struct{}
    stats     *WorkerStats           // 统计：Queued/Processed/Dropped/Errors/Refs
    refCount  atomic.Int64           // 引用计数（共享机制）
}
```

### Worker 运行逻辑（批处理优化）

```go
for {
    // 1. 阻塞等待第一个任务
    select {
    case task := <-wg.logQueue:
        w.processTask(task)
    case <-wg.shutdownChan:
        return
    }
    // 2. 非阻塞批量处理剩余任务
    for {
        select {
        case task := <-wg.logQueue:
            w.processTask(task)
        default:
            goto nextLoop  // 队列空，退出批处理
        }
    }
}
```

这种"先阻塞等一个，再非阻塞批量处理"的模式减少了上下文切换，提高了吞吐量。

### WorkerGroupManager（全局单例）

```go
var globalManager = &WorkerGroupManager{
    groups: make(map[string]*WorkerGroup),
}

func GetWorkerGroup(name string, config *AsyncGroupConfig) *WorkerGroup
func ReleaseWorkerGroup(name string)
```

- **按名称共享**：同名的 `WorkerGroup` 全局只创建一个，通过 `Ref()/Unref()` 引用计数管理生命周期
- **线程安全**：`sync.RWMutex` 保护

### 统计信息

```go
type WorkerStats struct {
    Queued    atomic.Int64  // 入队总数
    Processed atomic.Int64  // 成功处理总数
    Dropped   atomic.Int64  // 丢弃总数
    Errors    atomic.Int64  // 处理出错总数
    Refs      atomic.Int64  // 引用计数
}
```

可通过 `AsyncHandler.GetStats()` 获取。

## 配置示例

```yaml
aglog:
  topHandler:
    - "asynclog1"
  async:
    groups:
      logg1:
        worker: 2
        queue: 1000
        fullStrategy: "drop_new"
    logs:
      asynclog1:
        group: logg1
        log: zap1
  zap:
    logs:
      zap1:
        log_level: debug
        console: true
        stdout: true
```

## 使用示例

```go
// 在 FX 应用启动后
logger := agslog.GetSlogByName("asynclog1")
// logger.Handler() → ReplaceableHandler → AsyncHandler → zap1

// 异步写入，不阻塞业务 goroutine
logger.Info("这条日志异步写入")

// 获取异步处理统计
if asyncH, ok := logger.Handler().(*agslog.ReplaceableHandler); ok {
    if h, ok := asyncH.Original().(*async.AsyncHandler); ok {
        stats := h.GetStats()
        fmt.Printf("queued=%d processed=%d dropped=%d errors=%d\n",
            stats.Queued.Load(), stats.Processed.Load(),
            stats.Dropped.Load(), stats.Errors.Load())
    }
}
```

## 性能基准

基准测试（4 workers, 100K 队列, `drop_new` 策略）：

| 测试 | 操作数/op | 纳秒/op | 分配/op |
|------|-----------|---------|---------|
| 单次 Handle | ~4.6M | 260ns | ~264B, 7 allocs |
| 带属性 Handle | — | ~730ns | ~264B, 7 allocs |
| 通过 Logger 写入 | — | 接近原生 slog | 同 slog |
| 高并发并行 | ~3.2M | ~367ns | — |

## 注意事项

| 要点 | 说明 |
|------|------|
| **必须 Clone Record** | `Handle()` 中 `r.Clone()` 是必须的，否则并发不安全 |
| 队列容量 | 过小的 Queue + 突发流量 = Drop 激增 |
| Worker 数量 | 不建议超过 CPU 核数，IO 密集场景可适当调大 |
| Drop 静默 | `drop_new` 策略下日志丢弃是静默的（仅统计计数），关键日志建议用 `block_wait` |
| 应用关闭 | 使用 `fx.Shutdowner` 或 `WorkerGroup.Stop()` 确保关闭前完成已入队日志 |
| Level 过滤 | `Enabled()` 仍调用原始 handler，级别过滤在提交前已完成 |
