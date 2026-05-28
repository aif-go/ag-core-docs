---
tags:
  - ag-core
  - ag-log
  - agslog
  - named-handler
  - replaceable-handler
  - handler-factory
---

# NamedHandler 体系

agslog 围绕 handler 的命名和可替换性，设计了三个核心类型：

| 类型 | 接口 | 核心能力 |
|------|------|----------|
| `NamedHandler` | `INamedHandler` | 为 handler 添加名称标识 |
| `ReplaceableHandler` | `INamedHandler` | 运行时原子替换内部 handler |
| `HandlerFactory` | — | 延迟创建 + 循环检测 + 自动命名 |

## INamedHandler 接口

```go
type INamedHandler interface {
    slog.Handler
    Name() string                    // 获取 handler 名称
    Original() slog.Handler          // 剥除包装，获取原始 handler
}
```

这个接口是 agslog 的基石——所有 handler 都被抽象为「有名称的 handler」。

## NamedHandler — 命名包装

### 结构

```go
type NamedHandler struct {
    name    string
    Handler slog.Handler  // 被包装的 handler
}
```

### 行为

`Handle` 方法中，将**起始 handler 名称**写入 Context：

```go
func (n *NamedHandler) Handle(ctx context.Context, r slog.Record) error {
    startName := ctx.Value(HandlerStartCtxKey{})
    if startName == nil {
        startName = n.name
        ctx = context.WithValue(ctx, HandlerStartCtxKey{}, startName)
    }
    return n.Handler.Handle(ctx, r)
}
```

**只有链上第一个 NamedHandler 写入 Context**。后续的 NamedHandler 不再覆写。这意味着 `HandlerStartNameFromContext(ctx)` 返回的是**最外层 handler 的名称**。

### WithAttrs / WithGroup

```go
func (n *NamedHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
    return &NamedHandler{
        name:    n.name,
        Handler: n.Handler.WithAttrs(attrs),
    }
}
```

派生新的 NamedHandler，保留名称。**名称随属性传播**。

## ReplaceableHandler — 可替换包装

### 结构

```go
type ReplaceableHandler struct {
    name    string
    handler atomic.Pointer[slog.Handler]
}
```

使用 `atomic.Pointer` 实现无锁的原子读取和替换。

### 核心方法

#### ReplaceHandler — 原子替换

```go
func (rh *ReplaceableHandler) ReplaceHandler(handler slog.Handler) {
    rh.handler.Store(&handler)
}
```

这是热替换的入口。任何时刻调用此方法，后续的 `Handle`/`Enabled` 调用立即使用新 handler。

#### IsMatchesName — 名称匹配检查

```go
func (rh *ReplaceableHandler) IsMatchesName() bool {
    if handler, ok := (*rh.handler.Load()).(INamedHandler); ok {
        return handler.Name() == rh.name
    }
    return false
}
```

判断内部 handler 的名称与 ReplaceableHandler 自身名称是否一致。用于检测「是否已被替换为同名 handler」。

#### Handle 和 Enabled

```go
func (rh *ReplaceableHandler) Handle(ctx context.Context, r slog.Record) error {
    return (*rh.handler.Load()).Handle(ctx, r)
}
```

每次调用都通过 `atomic.Load` 获取最新 handler。**零开销的线程安全热切换**。

#### WithAttrs / WithGroup 的特殊行为

```go
func (rh *ReplaceableHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
    newHandler := &ReplaceableHandler{name: rh.name}
    current := (*rh.handler.Load()).(slog.Handler)
    ah := current.WithAttrs(attrs)
    newHandler.handler.Store(&ah)
    return newHandler
}
```

**关键细节**：`WithAttrs` 创建**新的 ReplaceableHandler**，其内部 handler 是**当前 handler 快照 + 新属性**。

这意味着：

```go
logger1 := agslog.GetSlogByName("mylog")  // 创建时 handler=A
logger2 := logger1.With("key", "val")      // 快照 A+attrs

// 假设后续 Build 替换了 mylog 的 handler → B
// logger1 的 handler 现在是 B
// logger2 的 handler 仍然是 A（WithAttrs 时的快照）

logger1.Info("msg")  // → B 处理
logger2.Info("msg")  // → A 处理（不受替换影响）
```

**如果不调用 WithAttrs/WithGroup，直接使用 `GetSlogByName` 返回的 Logger，热替换生效。派生后则失效。**

### 在日志链中的位置

```go
Logger
  └── ReplaceableHandler("xxx")    ← 最外层，每个 Logger 的 Handler() 都是它
        └── NamedHandler("xxx")    ← 由 wrapNamedHandlerIfNeed 确保
              └── (zap/fanout/etc handler 链)
```

**每个通过 `GetSlogByName` 创建的 Logger，其 Handler() 一定是 `*ReplaceableHandler`。**

这是热替换能力的保障——如果你直接 `slog.New(someHandler)`，后续就无法替换了。

## HandlerFactory — 延迟创建工厂

### 结构

```go
type HandlerFactory struct {
    Name         string
    instance     INamedHandler                                   // 缓存
    DoGetHandler func(resolve func(string) (slog.Handler, error)) (slog.Handler, error)
    mu           sync.Mutex
}
```

### GetHandler 执行流程

```
GetHandler(resolveHandler)
├── TryLock → 失败返回"循环调用"错误
├── 检查 instance 缓存 → 命中直接返回
├── 调用 DoGetHandler(resolveHandler)
│     └── 在这里可以递归调用 resolveHandler 获取子 handler
├── 检查结果是否为 INamedHandler → 否则自动包装 NamedHandler
├── 缓存 instance
├── 如果工厂 Name 与 handler 名称不同，再包一层 NamedHandler
└── 返回
```

### 循环依赖检测

```go
ok := f.mu.TryLock()  // 非阻塞尝试加锁
if !ok {
    // 锁被占用 → 递归调用了同一个工厂 → 循环
    return nil, fmt.Errorf("maybe circular call")
}
```

考虑下面的场景：

```
配置：
  f1: ["zap1"]     → fanout handler
  f2: ["f1"]       → 嵌套 fanout

resolveHandler("f2")
  → f2 工厂: GetHandler
    → 锁住 f2 的 mutex
    → DoGetHandler 调用 resolveHandler("f1")
      → f1 工厂: GetHandler
        → 锁住 f1 的 mutex
        → DoGetHandler 调用 resolveHandler("zap1")
          → 成功，返回 zap1 handler
        → 缓存，解锁
      → 返回 f1 的 fanout handler
    → 缓存，解锁
  → 返回 f2 的 fanout handler
```

如果配置出现循环（如 `f1: ["f2"], f2: ["f1"]`）：

```
resolveHandler("f1")
  → f1 工厂: TryLock → 成功
  → DoGetHandler 调 resolveHandler("f2")
    → f2 工厂: TryLock → 成功
    → DoGetHandler 调 resolveHandler("f1")
      → f1 工厂: TryLock → ❌ 失败
      → 返回错误 "maybe circular call"
    → 向上传播错误
```

### 自动命名

如果 `DoGetHandler` 返回的 handler 没有名称，`HandlerFactory` 自动包装：

```go
if nhandler == nil {
    nhandler = NewNamedHandler(name, handler).(INamedHandler)
}
```

如果工厂名称与 handler 内部名称不同，再包一层：

```go
if f.Name != "" {
    handler = NewNamedHandler(f.Name, handler)  // 强制用工厂名
}
```

双重包装下结构：

```
NamedHandler("f1")           ← 工厂名强制包
  └── NamedHandler("zap1")   ← 子 handler 自带的名称
        └── zap handler
```

## 三者的配合关系

```
Factory 负责「延迟创建」
  → GetHandler 创建出 handler 实例
  → 缓存到 handlersCaches
  → 用于 resolveTopHandlers / resolveHandler 等

NamedHandler 负责「命名追踪」
  → 记录 handler 的名称
  → 写入 Context
  → 支持按名称路由

ReplaceableHandler 负责「热替换」
  → 包装在每个 Logger 的 Handler() 位置
  → 由 tryReplaceNamedHandler 触发替换
  → 无锁 atomic 操作，运行时零开销
```
