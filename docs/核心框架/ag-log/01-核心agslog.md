---
tags:
  - ag-core
  - ag-log
  - agslog
  - builder
  - named-handler
---

# 核心 agslog — Builder、NamedHandler、HandlerFactory

> 子包：`ag/ag_log/agslog/` | 核心构造器与 handler 基础设施

## 功能一览

| 概念 | 结构/类型 | 说明 |
|------|-----------|------|
| 全局顶层 Logger | `TopLogger()` | 全局唯一的 `*slog.Logger`，通过 `atomic.Pointer` 安全访问 |
| 日志构造器 | `Builder` | 组装 handler 链、工厂、中间件，调用 `Build()` 完成初始化 |
| 命名 Handler | `NamedHandler` | 为任意 `slog.Handler` 添加名称标识 |
| 可替换 Handler | `ReplaceableHandler` | 运行时原子替换底层 handler（无需新建 logger） |
| Handler 工厂 | `HandlerFactory` | 延迟创建 + 缓存 + 循环依赖检测 |
| 名称解析器 | `GetSlogByName` | 按名称获取或懒创建 `*slog.Logger` |

## 顶层 Logger 设计

`agslog` 在 `init()` 中初始化全局的：
- **TopLogger** — 默认指向 `slog.Default()` 的 `atomic.Pointer`
- **DefaultBuilder** — 供后续配置覆盖

```go
// 获取全局顶层 Logger（推荐应用入口使用）
logger := agslog.TopLogger()

// 获取默认 Builder
builder := agslog.DefaultBuilder()
```

### 初始化流程

```
init() ─→ newBuilder() ─→ 创建 TopLogger（atomic.Pointer）
                           └→ builder.Store(b)

应用启动 ─→ Builder.WithProperties(props)
           → Builder.AddHandlers(handlers...)
           → Builder.AddHandlerFactorys(factories...)
           → Builder.AddMiddlewares(middlewares...)
           → Builder.Build()
                ├── resolveTopHandlers() — 按 props.TopHandler 名称解析
                ├── 单 handler → 直接用；多 handler → slogmulti.Fanout
                ├── 应用中间件 slogmulti.Pipe
                ├── 包装 NamedHandler(name="agslog_top")
                ├── 替换原子指针中的 ReplaceableHandler
                └── 若 props.IsDefault → slog.SetDefault(topLog)
```

## Builder 详解

Builder 是整个日志系统的控制中心，负责把所有组件拼装起来。

### 核心字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `props` | `*AgSlogProperties` | 配置：`IsDefault`（是否替换 slog 全局默认）、`TopHandler`（顶层 handler 名称列表） |
| `custTopHandlers` | `[]slog.Handler` | 编程注册的顶层 handler（优先级高于配置） |
| `handlersCaches` | `sync.Map` | 已解析的 handler 缓存（名称 → `slog.Handler`） |
| `handlers` | `sync.Map` | 已构建的命名 handler（经过中间件和 NamedHandler 包装） |
| `namedLogger` | `sync.Map` | 已创建的 Logger 缓存（名称 → `*slog.Logger`） |
| `replaceableHandllers` | `sync.Map` | 可替换 handler 缓存（用于运行时热替换） |
| `factories` | `[]*HandlerFactory` | Handler 工厂列表（延迟创建） |
| `middlewares` | `[]slogmulti.Middleware` | 中间件列表 |

### Handler 解析优先级

```
resolveHandler(hname)
   1. handlersCaches 中直接查找已注册的 handler
   2. 遍历 factories，匹配 f.Name == hname，调用 f.GetHandler(resolveHandler)
      → 递归解析子依赖
      → 结果缓存到 handlersCaches
```

### GetSlogByName — 名称解析（带双重检查锁）

```go
func (b *Builder) GetSlogByName(hname string) *slog.Logger
```

1. 首次检查 `namedLogger` 缓存 → 命中直接返回
2. 加锁（`logMu`）→ 二次检查（双重检查锁定）
3. 调用 `getNamedHandler(hname)` 解析 handler（优先从 `handlers` 缓存取，否则 `resolveHandler` 解析）
4. handler 经过中间件 `Pipe` → `wrapNamedHandlerIfNeed`（包装 NamedHandler）
5. 创建 `ReplaceableHandler` 包装 handler（支持后续热替换）
6. 创建 `*slog.Logger`，缓存到 `namedLogger`
7. 非 `topLoggerName` 的 handler 存入 `replaceableHandllers`

### tryReplaceNamedHandler — 热替换

`Build()` 完成后调用，遍历所有 `replaceableHandllers`：
- 跳过 `topLoggerName`
- 跳过已匹配（handler 名称与缓存名称一致）的
- 重新 `resolveHandler` 解析新 handler
- 原子替换 `ReplaceableHandler` 内部指针

## NamedHandler — 命名包装

```go
type NamedHandler struct {
    name    string
    Handler slog.Handler
}
```

实现 `INamedHandler` 接口：

```go
type INamedHandler interface {
    slog.Handler
    Name() string           // 获取名称
    Original() slog.Handler // 获取原始 handler（剥除包装）
}
```

在 `Handle()` 方法中，还会将 handler 名称写入 Context（`HandlerStartCtxKey`），供后续中间件或下游 handler 获取。

## ReplaceableHandler — 运行时热替换

```go
type ReplaceableHandler struct {
    name    string
    handler atomic.Pointer[slog.Handler]
}
```

关键能力：**在不新建 `*slog.Logger` 的前提下，替换 handler 实例**。

```go
rh := NewReplaceableHandler("mylog", textHandler)
// 运行时替换
rh.ReplaceHandler(jsonHandler) // 原子操作
```

`WithAttrs`/`WithGroup` 行为：新 handler 快照当前 handler 状态并包装，不影响原始 handler。

## HandlerFactory — 延迟创建与循环检测

```go
type HandlerFactory struct {
    Name         string
    instance     INamedHandler  // 缓存已创建的实例
    DoGetHandler func(func(handlerName string) (slog.Handler, error)) (slog.Handler, error)
    mu           sync.Mutex
}
```

- **懒加载**：`GetHandler` 首次调用时通过 `DoGetHandler` 创建，后续直接返回缓存
- **循环依赖检测**：使用 `sync.Mutex.TryLock` 在递归调用中检测循环，返回错误而非死锁
- **自动命名**：如果创建结果不是 `INamedHandler`，自动包装为 `NamedHandler`

### 使用示例

```go
factory := agslog.NewHandlerFactory(
    "myhandler",
    func(getHandler func(string) (slog.Handler, error)) (slog.Handler, error) {
        // getHandler 可以递归获取其他 handler
        // 例如从 fanout 场景下获取子 handler
        subHandler, _ := getHandler("zap1")
        return myHandler(subHandler), nil
    },
)
```

## AgSlogProperties — 配置绑定

| 配置路径 | 字段 | 默认值 | 说明 |
|----------|------|--------|------|
| `aglog.IsDefault` | `IsDefault` | `true` | 是否调用 `slog.SetDefault` |
| `aglog.topHandler` | `TopHandler` | `nil` | 顶层 handler 名称列表（空则使用 slog 默认） |

```yaml
aglog:
  isDefault: false
  topHandler:
    - "zap1"
    - "zap2"
```

## 代码示例

### 纯代码构建（无 FX）

```go
builder := agslog.NewBuilder()
builder.RegTopHandler(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
    Level: slog.LevelInfo,
}))
logger, _ := builder.Build()
logger.Info("hello", "key", "value")
```

### 按名称获取 Logger

```go
// 在模块初始化时
logger := agslog.GetSlogByName("mymodule")
// logger 是 ReplaceableHandler 包装的，后续可热替换
```
