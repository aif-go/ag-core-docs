---
tags:
  - ag-core
  - ag_service
  - bug
  - optimization
  - discussion
---

# Service Panic 错误栈丢失

> 讨论日期：2026-06-23 | 状态：待定

## 问题

Service 层发生 panic（如空指针）时，原始错误堆栈被吞掉，日志中只留字符串，无法定位代码位置。

## 丢失链路

```
biz Handler panic（如 nil pointer dereference）
  │
  ▼
Kitex 内置 recovery 捕获 → 转为 error("nil pointer dereference")
  │  ← 原始堆栈在此丢失
  ▼
生成的 service proxy（tpl_serviceproxy.go L145）
  → slog.Error("failed to handle request!", "error", err)
  │
  ▼
slogzap 桥接 → zap.AddStacktrace(ErrorLevel)
  ← 堆栈指向 slogzap bridge 内部，非业务代码行
```

两层丢失：

| 层 | 位置 | 原因 |
|---|------|------|
| ① Panic 捕获 | Kitex 内置 recovery | 只返回错误字符串，不打印堆栈 |
| ② slog.Error 堆栈 | slogzap 桥接 | `zap.AddStacktrace` 捕获的是 bridge 内部调用栈 |

## 建议方案

在 `ag/ag_service/` 下新增独立的 `recovery_middleware.go`，在 `RegisterHandler` 中**自动插入为最外层包装**，不依赖任何中间件注册。

核心逻辑：

```go
func recoveryWrapper(method string, ctx context.Context, req interface{},
    next func(context.Context, interface{}) (interface{}, error),
) (res interface{}, err error) {
    defer func() {
        if r := recover(); r != nil {
            stack := make([]byte, 4096)
            n := runtime.Stack(stack, false)
            slog.Error("panic recovered in request",
                "method", method,
                "err", r,
                "stack", string(stack[:n]),
            )
            err = fmt.Errorf("panic recovered: %v", r)
        }
    }()
    return next(ctx, req)
}
```

### 优点

- 无需显式注册中间件，`RegisterHandler` 自动生效
- 捕获业务代码真实堆栈（`runtime.Stack`）
- 不影响其他模块，不涉及 `tpl_serviceproxy.go` 模板
- `loggingMiddleware` 装不装都生效

### 待定事项

- `RegisterHandler` 的改造方式（内嵌 vs 包装返回结果）
- 是否需要可配置开关（默认开启、可禁用）
