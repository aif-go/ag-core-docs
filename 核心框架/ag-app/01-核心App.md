---
tags:
  - ag-core
  - ag-app
  - lifecycle
---

# 核心 App — 结构与生命周期

> 源码：`ag/ag_app/app.go`

## App 结构

```go
type App struct {
    name    string               // 应用名称
    Servers []ag_server.Server   // 服务列表
    Logger  *slog.Logger         // 日志实例
    cancel  context.CancelFunc   // 应用级 context 取消函数
    ctx     context.Context      // 应用级 context
}
```

每个 App 实例包含：
- **多个 Server**：同时运行 HTTP、RPC、Watcher 等不同协议的服务
- **一个 Logger**：共享的应用级日志
- **独立的 context**：`Start()` 时创建，`Stop()` 时取消，贯穿服务生命周期

## 创建方式

### Option 模式

```go
func NewApp(opts ...Option) (*App, func()) {
    a := &App{}
    for _, opt := range opts {
        opt(a)
    }
    // cleanup 函数（用于 wire 等工具）
    cleanup := func() {
        time.Sleep(time.Second)
    }
    return a, cleanup
}
```

### Options

| Option | 作用 |
|--------|------|
| `WithServer(servers ...ag_server.Server)` | 注入服务列表 |
| `WithName(name string)` | 设置应用名称 |
| `WithLogger(logger *slog.Logger)` | 设置日志实例 |

### 使用示例

```go
app, cleanup := ag_app.NewApp(
    ag_app.WithName("my-service"),
    ag_app.WithServer(httpServer),
    ag_app.WithLogger(slog.Default()),
)
defer cleanup()
```

## 运行模式

### 模式 A：`Run()` — 信号驱动（独立应用）

```go
func (a *App) Run(ctx context.Context) error {
    a.Start(ctx)        // 启动所有 Server
    // 等待信号或 context 取消
    signals := make(chan os.Signal, 1)
    signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
    select {
    case <-signals:
        a.Logger.Info("Received termination signal")
    case <-ctx.Done():
        a.Logger.Info("Context canceled")
    }
    a.Stop(ctx)         // 优雅关闭
    return nil
}
```

完整生命周期：

```
Run() 调用
  │
  ├─ Start(ctx)
  │    └─ 所有 Server 在 goroutine 中启动
  │
  ├─ 阻塞等待
  │    ├─ SIGINT / SIGTERM → 收到退出信号
  │    └─ ctx.Done()      → 外部取消
  │
  └─ Stop(ctx)
       └─ 逐个关闭 Server（context 取消）
```

### 模式 B：`Start()` + `Stop()`（FX 模式）

仅供 FX 生命周期管理使用，见 [03-FX集成](03-FX集成.md)。

## Start — 服务启动

```go
func (a *App) Start(ctx context.Context) error {
    // ★ 关键：从 context.Background() 创建独立生命周期 ctx
    // FX 传入的 ctx 只在 Start 阶段有效（有超时），不能用于服务运行期
    vctx := context.WithValue(context.Background(), AppNameKey, a.name)
    cctx, cancel := context.WithCancel(vctx)
    a.cancel = cancel
    a.ctx = cctx

    for _, srv := range a.Servers {
        srv := srv
        go func() {
            err := srv.Start(a.ctx)
            if err != nil {
                // 启动失败 → log.Fatal（硬退出）
                slog.Error("Server start failed", "error", err)
                log.Fatal(err)
            }
        }()
    }
    slog.Info("servers started")
    return nil
}
```

### 启动时序

```
Start(ctx_from_fx)
  │
  ├─ 创建独立 ctx: context.WithValue(context.Background(), AppNameKey, name)
  │    ★ 含义：FX 的 ctx 只在 Start 阶段有效（含超时），
  │      但服务本身需要长期运行的 context，所以从 Background 创建
  │
  ├─ context.WithCancel(vctx) → 保存 cancel
  │
  ├─ for each server:
  │    └─ go srv.Start(a.ctx)  ← 每个服务在自己的 goroutine 中运行
  │
  └─ 返回 nil（不等待 server 启动完成）
```

### 设计特点

1. **goroutine 并行启动**：所有 Server 同时启动，互不阻塞
2. **不等待启动完成**：`Start()` 在 for 循环启动完 goroutine 后立即返回
3. **启动失败 ≈ 硬退出**：目前使用 `log.Fatal(err)`，改为更优雅的错误处理（见 TODO）
4. **ctx 分离**：FX 传入的 ctx 只用于 Start 阶段的超时控制，服务使用独立的 `context.Background()` 衍生 ctx

## Stop — 优雅关闭

```go
func (a *App) Stop(ctx context.Context) error {
    defer a.cancel()            // 取消应用级 context

    var rerr error
    for _, srv := range a.Servers {
        err := srv.Stop(a.ctx)  // 使用应用级 ctx 关闭
        if err != nil {
            rerr = fmt.Errorf("%w,%w", rerr, err)
        }
    }
    return rerr
}
```

关闭顺序：**逐个串行**，累积所有错误返回。

## 注意事项

| 要点 | 说明 |
|------|------|
| **Start 不等待** | `Start()` 启动 goroutine 后立即返回，不确认服务是否就绪 |
| **log.Fatal 硬退出** | 服务启动失败会直接 `os.Exit`，`fx.Shutdowner` 等其他关闭逻辑不会执行 |
| **Stop 串行** | 服务关闭是串行的，大量服务时关闭时间可能较长 |
| **ctx 分离** | 服务运行时使用 `context.Background()` 衍生 ctx，与 FX Start 超时 ctx 解耦 |
| **Run 阻塞** | `Run()` 是阻塞调用，适合 `main()` 中直接使用 |
