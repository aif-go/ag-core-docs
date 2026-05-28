---
tags:
  - ag-core
  - ag-log
  - agslog
  - toplogger
  - lifecycle
---

# TopLogger 生命周期

TopLogger 从 `init()` 创建到 `Build()` 替换经历了三个阶段。

## 第一阶段：init（占位期）

```
TopLogger
  └── Handler: ReplaceableHandler("agslog_top")
        └── internal: slog.Default().Handler() (text → stderr)
```

- 此时 `slog.SetDefault` **未调用**
- `slog.Default()` 仍然是 Go 标准库的默认值
- 所有日志（包括框架内部日志）此时输出到 stderr

**此阶段可执行的调用：**

```go
agslog.TopLogger().Info("hello")  // 输出到 stderr（text 格式）
agslog.GetSlogByName("anything")  // 见下
```

## 第二阶段：Build 前（降级期）

在 `Builder.Build()` 之前，应用可以调用 `BindAgSlogProperties` / `AddHandlers` / `AddHandlerFactorys` / `AddMiddlewares` 配置 Builder，但 **TopLogger 本身仍然处于占位状态**。

### 此阶段 GetSlogByName 的行为

如果在 Build 之前调用 `GetSlogByName("myLog")`：

```go
// 第一次调用 → namedLogger miss
// getNamedHandler("myLog") → resolveHandler 失败 → 返回 nil
// handler == nil → blogger = TopLogger()
// handler = TopLogger().Handler() = ReplaceableHandler("agslog_top", internal=slog.Default)
// 创建新的 ReplaceableHandler("myLog", internal=ReplaceableHandler("agslog_top", ...))
// 存到 replaceableHandllers
// 创建 slog.New(handler)
// 存到 namedLogger
// 返回
```

结果：

```
myLog Logger
  └── Handler: ReplaceableHandler("myLog")
        └── internal: ReplaceableHandler("agslog_top")
              └── internal: slog.Default().Handler()
```

关键点：
- `replaceableHandllers` 中多了一个 `"myLog"` 条目
- `myLog` 的 handler 链指向了 TopLogger 的 ReplaceableHandler
- 这意味着如果后续 Build 替换了 TopLogger 的内部 handler，`myLog` 也能通过委托链感知变化

## 第三阶段：Build（替换期）

### initTopLogger 的执行

```go
func (b *Builder) initTopLogger() (*slog.Logger, error) {
    // 1. 解析顶层 handler
    topHandlers, err := b.resolveTopHandlers()
    //    - 从 custTopHandlers（程序注册）和 props.TopHandler（配置）解析
    //    - 每个名称通过 resolveHandler 解析（handlersCaches → factories）
```

假设配置了 `topHandler: ["zap1"]`，且 zap1 handler 通过 slogzap 注册：

```
resolveTopHandlers()
  └─ resolveHandler("zap1")
       ├─ handlersCaches 查找 → miss（zap1 通过 factory 机制注册）
       └─ 遍历 factories
            └─ 匹配 factory Name="zap1"
                 └─ factory.GetHandler(resolveHandler)
                      ├─ resolveHandler 递归解析子 handler（无）
                      ├─ slogzap.NewZapHandler() → 创建 zap handler
                      └─ 缓存到 handlersCaches
```

```go
    // 2. 组合 handler
    // 单 handler → 直接用；多 handler → slogmulti.Fanout
    var rhandler slog.Handler
    if len(topHandlers) > 1 {
        rhandler = slogmulti.Fanout(topHandlers...)
    } else {
        rhandler = topHandlers[0]
    }

    // 3. 应用中间件
    if len(b.middlewares) > 0 {
        rhandler = slogmulti.Pipe(b.middlewares...).Handler(rhandler)
    }

    // 4. 包装 NamedHandler（如果尚未 Named）
    rhandler = b.wrapNamedHandlerIfNeed(topLoggerName, rhandler)
    // → NamedHandler("agslog_top", {zap1 handler})

    // 5. 替换 TopLogger 的处理器
    topLog := TopLogger()
    thandler := topLog.Handler()
    th, ok := thandler.(*ReplaceableHandler)
    if ok {
        if !th.IsMatchesName() {
            th.ReplaceHandler(rhandler)   // ★ 原子替换！
        }
    }

    // 6. 可选：替换 slog 全局默认
    if b.props.IsDefault {
        slog.SetDefault(topLog)
    }

    return topLog, nil
}
```

### 替换后的结构

```
TopLogger（同一个实例，引用不变！）
  └── Handler: ReplaceableHandler("agslog_top")
        └── 内部指针已替换为 → NamedHandler("agslog_top")
              └── zap1 handler（实际的日志引擎）
```

**所有持有 TopLogger 引用的代码不需要任何改动**，这是 ReplaceableHandler 的核心价值。

### 后置替换 tryReplaceNamedHandler

Build 完成后立即执行：

```go
func (b *Builder) tryReplaceNamedHandler() {
    b.replaceableHandllers.Range(func(k, v any) bool {
        if k == topLoggerName { return true }  // 跳过

        rh, ok := v.(*ReplaceableHandler)
        if !ok { return true }

        if rh.IsMatchesName() { return true }  // 已匹配，跳过

        name := rh.Name()
        h, err := b.resolveHandler(name)  // 重新解析
        if err != nil {
            h = TopLogger().Handler()     // 降级到 TopLogger
        }

        rh.ReplaceHandler(h)  // ★ 原子替换
        return true
    })
}
```

这个过程遍历所有在 Build **之前**通过 `GetSlogByName` 创建的 Logger，将其 handler 从降级指向替换为真实 handler。

### 替换效果示意

**替换前**（Build 前创建了 myLog）：

```
myLog Logger
  └── ReplaceableHandler("myLog") → ReplaceableHandler("agslog_top") → slog.Default handler
```

**替换后**：

```
myLog Logger（同一个实例）
  └── ReplaceableHandler("myLog") → NamedHandler("myLog")
        └── (根据 myLog 在配置中对应的 handler)
             └── zap1 handler
```

## 完整 TopLogger 状态演变

| 阶段 | TopLogger 的 Handler | slog.Default | 可调用性 |
|------|---------------------|--------------|----------|
| `init()` 后 | ReplaceableHandler → text → stderr | 未修改 | ✅ |
| Build 前（配置期） | 同上 | 同上 | ✅（降级到 stderr） |
| `Build()` 中 | 被替换为真实 handler 链 | 可选替换 | ✅ |
| `tryReplaceNamedHandler` 后 | 同上 | 同上 | ✅（所有 Logger 激活） |

## 关键观察

1. **Logger 实例不变**：`TopLogger()` 返回的指针在 `init()` 后从未改变。改变的是其 Handler 内部指针。

2. **Build 前 GetSlogByName 可工作**：即使 Build 尚未执行，`GetSlogByName` 返回的 Logger 也是可调用的（降级到 slog.Default），不会 panic 或返回 nil。

3. **后置替换覆盖率**：只有在 Build **前**调用过 `GetSlogByName(name)` 的 Logger 才会被后置替换。Build 之后的首次调用直接创建正确 handler。

4. **WithAttrs/WithGroup 快照问题**：如果在 Build **前**调用了 `logger.With("k", "v")`，返回的 Logger 的 handler 是**旧 handler 的快照**，即使后续替换了原 Logger，这个派生 Logger 仍然指向旧 handler。
