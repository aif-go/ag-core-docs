---
tags:
  - ag-core
  - ag-log
  - agslog
  - init
  - lifecycle
---

# agslog init() 初始化详解

> 入口：`ag/ag_log/agslog/agslog.go` 第 33 行

## 源码

```go
var (
    builder   atomic.Pointer[Builder]
    topLogger atomic.Pointer[slog.Logger]
)

func init() {
    b := newBuilder()                       // ① 创建空 Builder
    tlog := b.GetSlogByName(topLoggerName)  // ② 获取 "agslog_top" 的 Logger
    topLogger.Store(tlog)                    // ③ 设为全局 TopLogger
    builder.Store(b)                         // ④ 设为全局 Builder
}
```

## 逐步分析

### ① `newBuilder()` — 创建空 Builder

```go
func newBuilder() *Builder {
    return &Builder{}
}
```

此时 Builder 的所有字段都是零值：
- `props` = `nil`（无配置）
- `custTopHandlers` = `nil`
- `handlersCaches` = 空 sync.Map
- `handlers` = 空 sync.Map
- `namedLogger` = 空 sync.Map
- `replaceableHandllers` = 空 sync.Map
- `factories` = `nil`
- `middlewares` = `nil`

### ② `GetSlogByName("agslog_top")` — 核心递归

这一步最复杂，逐层拆解：

#### 入口

```go
func (b *Builder) GetSlogByName(hname string) *slog.Logger {
    // 第一次检查：namedLogger 为空，miss
    if logger, ok := b.namedLogger.Load(hname); ok {
        return logger.(*slog.Logger)
    }

    b.logMu.Lock()
    defer b.logMu.Unlock()

    // 双重检查锁定（DCLP）：再次检查，仍 miss
    if logger, ok := b.namedLogger.Load(hname); ok {
        return logger.(*slog.Logger)
    }
```

#### handler 解析 — `getNamedHandler("agslog_top")`

```go
func (b *Builder) getNamedHandler(hname string) INamedHandler {
    // ① handlers 缓存 miss（空的 Builder）
    handler, ok := b.handlers.Load(hname)
    if ok { return handler.(INamedHandler) }

    // ② resolveHandler：无 handlersCaches，无 factories → 失败
    rh, err := b.resolveHandler(hname)
    if err != nil {
        slog.Warn(...)  // 输出警告
        return nil      // ⚠️ 返回 nil
    }
    // rh == nil → 继续往下
    ...
}
```

`resolveHandler` 走完两步都找不到：

```go
func (b *Builder) resolveHandler(hname string) (slog.Handler, error) {
    // 1. handlersCaches 查找 → miss（空的）
    // 2. factories 遍历 → 空的
    return nil, fmt.Errorf("handler %s not found", hname)
}
```

所以 `getNamedHandler` 返回 `nil`。

#### 回到 GetSlogByName — handler == nil 的分支

```go
    handler = b.getNamedHandler(hname)  // → nil
    if handler == nil {
        blogger := TopLogger()          // → nil（还没 Store！）
        if hname == topLoggerName || blogger == nil {
            blogger = slog.Default()    // ★ 关键：使用 slog 标准默认
        }
        handler = blogger.Handler()     // → slog.Default().Handler()
    }
```

**为什么这里用 `slog.Default()` 而不是 `TopLogger()`？**

因为此时 `topLogger` 原子指针还没 Store！这是 init 函数内部的第二次调用。`TopLogger()` 返回 `nil`。

`hname == "agslog_top"` 条件满足 → 使用 `slog.Default()`。

`slog.Default().Handler()` 返回的是 Go 标准库默认的 text handler（输出到 stderr）。

#### 创建 ReplaceableHandler 和 Logger

```go
    handler = NewReplaceableHandler(hname, handler)
    // handler = ReplaceableHandler{
    //     name: "agslog_top",
    //     handler: &(slog.Default().Handler())
    // }

    if hname != topLoggerName {
        // 不执行！因为 hname == "agslog_top"
        b.replaceableHandllers.Store(hname, handler)
    }

    logger := slog.New(handler)
    // logger.Handler() = ReplaceableHandler → slog.Default's handler

    b.namedLogger.Store(hname, logger)
    return logger
}
```

### ③ `topLogger.Store(tlog)` — 设置全局 TopLogger

此时 `TopLogger()` 返回的 Logger，其 handler 链是：

```
TopLogger
  └── Handler: ReplaceableHandler("agslog_top")
        └── internal handler: slog.Default().Handler()  (text → stderr)
```

### ④ `builder.Store(b)` — 设置全局 Builder

完成后，全局状态：

```
builder → Builder{empty}    （等待后续配置注入）
topLogger → slog.Logger{ Handler=ReplaceableHandler("agslog_top") → slog.Default's text handler }
```

## init 完成后的状态

| 全局变量 | 值 |
|----------|-----|
| `agslog.TopLogger()` | `*slog.Logger`（handler = ReplaceableHandler → text handler） |
| `agslog.DefaultBuilder()` | 空的 `*Builder`（全字段零值） |
| `namedLogger` | 只有 `"agslog_top"` → 创建的 Logger |
| `replaceableHandllers` | **空的**（跳过 topLoggerName） |

## 关键观察

1. **循环依赖保护**：`getNamedHandler` 在 `hname == topLoggerName` 且 TopLogger 不可用时，使用 `slog.Default()` 而不是 TopLogger 的 handler。避免了 `TopLogger().Handler()` → 访问 handler → 又触发 GetSlogByName → 死循环。

2. **最小可用原则**：init 只创建了一个指向 `slog.Default` 的 Logger，所有 `GetSlogByName` 在 Build 之前都会降级到 `slog.Default`。

3. **ReplaceableHandler 预留了替换入口**：init 创建的 handler 是 `ReplaceableHandler`，后续 `Builder.Build()` 只需替换其内部指针，**不需要新建 Logger 实例**。所有持有 TopLogger 引用的代码，无需任何改动即可使用新的 handler。

4. **Builder 是空的**：factory、handler、middleware 全部未注册，等待 FX 或手动注入。
