---
tags:
  - ag-core
  - ag-log
  - fanout
---

# 扇出 fanout — 按名称路由到多个 Handler

> 子包：`ag/ag_log/fanout/` | 基于 `samber/slog-multi` 的 Fanout 复合

## 职责

`fanout` 模块提供**名称驱动的日志扇出能力**：将一个日志记录同时分发到多个已命名的 handler。与配置中心联动，通过 `aglog.fanout.logs.{名称}` 定义复合 handler。

## 数据结构

### AgSlogFanoutProperties

```go
type AgSlogFanoutProperties struct {
    Logs map[string][]string  // 复合名称 → 子 handler 名称列表
}
```

配置路径：`aglog.fanout`

```yaml
aglog:
  fanout:
    logs:
      f1: ["zap1", "zap2"]   # 同时写入 zap1 和 zap2
      f2: ["f1"]              # 嵌套：f2 = fanout([f1])
      f3: ["f2"]              # 链式嵌套：f3 → f2 → f1 → zap1+zap2
      gftest: ["zap1"]        # 单一路由
```

## 核心逻辑

### NewFanoutHandlerFactorys

遍历 `props.Logs`，为每个复合名称创建 `HandlerFactory`：

```go
for name, handlers := range props.Logs {
    factory := agslog.NewHandlerFactory(
        name,
        getDoGetHandlerFunc(handlerscopy),
    )
    factories = append(factories, factory)
}
```

### getDoGetHandlerFunc — 延迟解析子 handler

```go
func getDoGetHandlerFunc(fanoutHandlerNames []string) func(getHandler func(string) (slog.Handler, error)) (slog.Handler, error) {
    return func(getHandler func(string) (slog.Handler, error)) (slog.Handler, error) {
        subHandlers := make([]slog.Handler, 0)
        for _, handlerName := range fanoutHandlerNames {
            subhandler, err := getHandler(handlerName)
            if err != nil { return nil, err }
            subHandlers = append(subHandlers, subhandler)
        }
        fanoutHandler := slogmulti.Fanout(subHandlers...)
        return fanoutHandler, nil
    }
}
```

- 使用 `slogmulti.Fanout()` 进行实际分发
- 通过 `getHandler` 回调（来自 `Builder.resolveHandler`）递归解析子 handler
- 支持多层嵌套（如 `f3 → f2 → f1 → zap1+zap2`）

## 嵌套场景分析

```
配置：
  f1: [zap1, zap2]    → 同时写入两个文件
  f2: [f1]            → 等价于 f1
  f3: [f2]            → 等价于 f1

实际 fanout 结构：
  f3 = Fanout(f2)
     = Fanout(Fanout(f1))
        = Fanout(Fanout(Fanout(zap1, zap2)))
```

每层 fanout 都会把记录广播给所有子 handler，所以嵌套只是概念上的组织方式，运行时性能无差异。

## Handler 工厂注册到 FX

```go
var FxAgSlogFanoutProvide = fx.Provide(
    BindAgSLogFanoutProperties,
    fx.Annotate(
        NewFanoutHandlerFactorys,
        fx.ResultTags(`group:"agslog.factorys"`),
    ),
)
```

- 绑定配置 → 生成 `[][]*HandlerFactory`，通过 group tag 注入到 `FxInAgSlogBuilderParams.Factoryss`
- Builder 通过 `AddHandlerFactoryss` 统一注册

## 使用示例

```go
// 获取 fanout handler 创建的 logger
logger := agslog.GetSlogByName("f1")
logger.Info("这条日志会同时写入 zap1 和 zap2")
```

## 注意事项

| 要点 | 说明 |
|------|------|
| 名称解析 | fanout 依赖的 handler 名称必须在配置中已定义（如 zap1、zap2） |
| 循环引用 | HandlerFactory 的 `TryLock` 机制可检测循环 fanout |
| 性能 | 同步阻塞：所有子 handler 写入完成才返回 |
| 配置为空 | `props.Logs` 为空时不创建任何 factory，不会阻塞启动 |
| 配置故障 | 绑定失败返回 `nil, nil`，不中断应用启动 |
