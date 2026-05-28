---
tags:
  - ag-core
  - future
  - lifecycle
  - optimization
  - discussion
---

# App 生命周期优化 — 初始化与清理钩子

> 讨论日期：2026-05-27 | 状态：待定

## 问题

当前 `ag_app.App` 只有两个阶段：`Start()` 和 `Stop()`。但实际应用需要更细粒度的生命周期控制：

```
现有：Start → goroutine 启动 Server → （立即返回） → Stop → 关闭 Server
需求：init → start → ready → stop → cleanup
```

## 现状分析

### App.Start 代码

```go
func (a *App) Start(ctx context.Context) error {
    cctx, cancel := context.WithCancel(context.Background())
    a.cancel = cancel
    a.ctx = cctx

    for _, srv := range a.Servers {
        go func() {
            err := srv.Start(a.ctx)
            if err != nil { log.Fatal(err) }
        }()
    }
    slog.Info("servers started")   // ★ 此时 Server 可能还没起来
    return nil
}
```

三个问题：

1. **「servers started」是假的** — goroutine 刚 spawn 就打印了，没有确认服务已就绪
2. **启动失败 = 硬退出** — `log.Fatal` 导致 FX OnStop 不会执行
3. **没有初始化/清理阶段** — DB 连接、日志 flush 无处安放

### 已有能力：FX Lifecycle

```go
lc.Append(fx.Hook{
    OnStart: func(ctx context.Context) error { ... },
    OnStop:  func(ctx context.Context) error { ... },
})
```

FX 已提供：
- 按依赖顺序执行 OnStart
- 逆序执行 OnStop
- 超时控制（`fx.StartTimeout`）
- 错误回滚（hook 失败 → 执行已成功的 OnStop）

但问题是：**业务开发者需要理解 FX 的 Provide 依赖排序才能用好它**，缺乏语义化的启动阶段接口。

## 优化方案讨论

### 方案 A：App Lifecycle 内置钩子（推荐）

给 `App` 增加 4 阶段 hook 队列：

```go
type App struct {
    initHooks    []func(context.Context) error  // Start 前，顺序
    readyHooks   []func(context.Context) error  // 所有 Server 就绪后，顺序
    cleanupHooks []func(context.Context) error  // Stop 后，逆序
    // ... 现有字段
}
```

#### 业务用法

```go
app := &ag_app.App{}

// 1. 初始化（Start 之前）
app.OnInit(func(ctx context.Context) error {
    db, err := gorm.Open(...)
    if err != nil { return err }
    return nil
})

// 2. 服务就绪后（所有 Server 启动完成）
app.OnReady(func(ctx context.Context) error {
    return registry.Register("my-service", ip, port)
})

// 3. 清理（Stop 之后）
app.OnCleanup(func(ctx context.Context) error {
    slog.Info("flushing logs...")
    time.Sleep(100 * time.Millisecond)
    return db.Close()
})
```

#### 新时序

```
App.Start(ctx)
  │
  ├─ initHooks (顺序)
  │    ├─ DB 连接池初始化
  │    ├─ 证书加载
  │    ├─ 配置校验
  │    └─ 缓存预热
  │
  ├─ startHooks (goroutine 并行)
  │    ├─ HTTP Server 启动
  │    ├─ gRPC Server 启动
  │    └─ Watcher Server 启动
  │
  ├─ 等待所有 Server 启动完成（含启动超时）
  │
  ├─ readyHooks (顺序)
  │    ├─ 健康检查
  │    ├─ 服务注册（Nacos）
  │    └─ 指标上报
  │
  └─ 返回 nil

App.Stop(ctx)
  │
  ├─ stopHooks (串行)
  │    ├─ HTTP Server 优雅关闭
  │    ├─ gRPC Server 关闭
  │    └─ Watcher Server 关闭
  │
  ├─ cleanupHooks (逆序)
  │    ├─ 服务反注册
  │    ├─ 日志刷盘
  │    ├─ 连接池关闭
  │    └─ 资源释放
  │
  └─ cancel() → Server goroutine 退出
```

#### 与 Server 接口关系

Server 接口保持不变，`App` 自动将 `srv.Start()` 注册为 startHook：

```go
func (a *App) WithServer(srv ag_server.Server) {
    a.startHooks = append(a.startHooks, func(ctx context.Context) error {
        go func() { srv.Start(ctx) }()
        return nil             // 非阻塞
    })
    a.stopHooks = append(a.stopHooks, srv.Stop)
}
```

#### 等待 Server 就绪

新 `Start()` 需要等待 Server 确认就绪：

```go
func (a *App) Start(ctx context.Context) error {
    // 1. 初始化
    for _, hook := range a.initHooks {
        if err := hook(ctx); err != nil {
            return fmt.Errorf("init failed: %w", err)
        }
    }

    // 2. 启动 Server
    for _, hook := range a.startHooks {
        go hook(ctx)
    }

    // 3. 等待 Server 就绪（含超时）
    if err := a.waitServersReady(ctx); err != nil {
        return fmt.Errorf("servers not ready: %w", err)
    }

    // 4. 就绪钩子
    for _, hook := range a.readyHooks {
        if err := hook(ctx); err != nil {
            return fmt.Errorf("ready hook failed: %w", err)
        }
    }

    slog.Info("app started")
    return nil
}
```

需要定义「就绪」的含义：

```go
type Server interface {
    Start(context.Context) error
    Stop(context.Context) error
    // 可选：启动后通知通道
    ReadyChan() <-chan struct{}
}
```

或者更简单的做法：Server 在 `Start()` 中阻塞直到可以服务（如 `http.ListenAndServe`），就绪 = `Start()` 返回前的瞬间。但这样无法区分「正在运行」和「启动失败」。

---

### 方案 B：纯 FX Hook（零成本）

不改 App，完全依赖 `fx.Lifecycle` 控制顺序：

```go
fx.Provide(
    func(lc fx.Lifecycle) *DB {
        db := &DB{}
        lc.Append(fx.Hook{
            OnStart: func(ctx context.Context) error {
                return db.Connect()     // 依赖顺序保证在 Server 前
            },
            OnStop: func(ctx context.Context) error {
                return db.Close()       // 逆序保证在 Server 后
            },
        })
        return db
    },
)
```

**优点**：零改动，FX 原生支持超时和回滚
**缺点**：依赖 Provide 顺序，语义不直观；没有「就绪」屏障

---

### 方案 C：Server 接口扩展

```go
type Server interface {
    Init(context.Context) error      // 新增
    Start(context.Context) error
    Stop(context.Context) error
    Cleanup(context.Context) error   // 新增
}
```

App 统一调度四个阶段。

**优点**：每个 Server 自管生命周期
**缺点**：非 Server 的初始化（如 DB）无处安放；改接口影响所有现有实现

---

## 方案对比

| 维度 | 方案 A（App Lifecycle） | 方案 B（纯 FX） | 方案 C（Server 扩展） |
|------|------------------------|----------------|---------------------|
| 实现成本 | 中等 | 零成本 | 低 |
| 侵入性 | 低（不破现有接口） | 无 | 中（改 Server 接口） |
| 分阶段语义 | ✅ 4 阶段清晰 | ❌ 隐式依赖顺序 | ✅ 每 Server 自管 |
| 非 Server 初始化 | ✅ Init/Cleanup | ✅ 但靠 order | ❌ |
| 就绪屏障 | ✅ | ❌ | ❌ |
| Server 启动失败处理 | ✅ 可优雅回退 | ✅ FX 回退 | 需 App 层补充 |
| 与 FX 兼容 | 语义化封装，底层仍用 FX | — | 可共存 |

## 初步结论

**倾向方案 A**，理由：

1. **语义化 API**：`app.OnInit` / `app.OnReady` / `app.OnCleanup` 比 FX Provide 顺序更直观
2. **就绪屏障**：解决当前 `Start()` 不等待 Server 启动的问题
3. **非 Server 资源**：DB、日志、证书等不属于任何 Server，需要独立入口
4. **向后兼容**：现有 Server 接口和 App 用法无需修改
5. **底层仍可用 FX**：App Lifecycle 钩子内部注册为 `fx.Hook`，复用 FX 的超时和回滚

## 待讨论

- 就绪等待机制如何实现？通道还是超时轮询？
- init hook 超时由谁控制（App 参数 / FX StartTimeout）？
- Server 启动失败是否回滚已初始化的资源？
- cleanup hook 执行顺序的依赖关系如何表达？
- 是否需要在 App 层面支持 `OnInit` 等方法的并发注册？
