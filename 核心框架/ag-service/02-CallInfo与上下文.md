---
tags:
  - ag-core
  - ag-service
  - callinfo
  - serviceinfo
  - context
  - architecture
---

# CallInfo 与上下文

> 路径：`service_callinfo.go` | 调用信息传递 + 上下文绑定

## ServiceInfo — 服务级信息

`ServiceInfo` 描述一个 RPC 服务的元信息，在服务初始化时创建，所有方法共享：

```go
// service_callinfo.go:24-29
type ServiceInfo struct {
    packageName string        // 包名
    serviceName string        // 服务名
    handlerType interface{}   // Handler 类型（反射用）
}
```

```go
si := NewServiceInfo("mypackage", "UserService", &UserServiceHandler{})
```

| 字段 | 用途 | 示例 |
|------|------|------|
| `packageName` | proto 包名或其他标识 | `user.v1` |
| `serviceName` | 服务名 | `UserService` |
| `handlerType` | Handler 类型实例（用于反射注册） | `&UserServiceHandler{}` |

## CallInfo — 调用级信息

`CallInfo` 携带某一次服务调用的上下文信息，在构建 Endpoint 链时创建，通过 context 向下传递：

```go
// service_callinfo.go:40-51
type CallInfo struct {
    serviceInfo     *ServiceInfo       // 所属服务
    callName        string             // 方法名
    clientStreaming bool               // 客户端流
    serverStreaming bool               // 服务端流
    Extra           map[string]interface{}  // 额外数据
    tag             sync.Map                // 线程安全标签

    locked bool
    mu     sync.RWMutex
}
```

### 创建

```go
cinfo := NewCallInfo(si, "CreateUser", false, false)
```

### Tag 机制

`tag` 使用 `sync.Map` 实现，支持任意类型的键值，用于在中间件之间传递临时数据：

```go
// 设置
cinfo.AddTag("user_id", 12345)
cinfo.AddTag("auth_level", "admin")

// 获取
level := cinfo.GetTag("auth_level")

// 检查
if cinfo.HasTag("user_id") { ... }
```

- `AddTag` 在键已存在时返回 `ErrTagKeyExist`（不允许覆盖）
- `locked` 状态下 `AddTag` 返回 `ErrCallInfoLocked`

### Extra 机制

`Extra` 使用普通 `map[string]interface{}`，受 RWMutex 保护：

```go
cinfo.AddExtra("trace_id", "abc123")
traceId := cinfo.GetExtra("trace_id")
```

`AddExtra` 在键已存在时返回 `ErrExtraKeyExist`。Tag 和 Extra 的区别：

| | Tag | Extra |
|---|-----|-------|
| 键类型 | `interface{}` | `string` |
| 并发安全 | `sync.Map` | `RWMutex` |
| 设计目的 | 中间件间临时传递 | 结构化扩展数据 |
| 锁定后 | 不可写入 | 不可写入 |

### 锁定机制

`CallInfo` 在 `buildEndpointChain()` 中被锁定（`lock()`），锁定后：

```go
func (ci *CallInfo) lock() {
    ci.mu.Lock()
    ci.locked = true
    ci.mu.Unlock()
}
```

锁定后 `AddTag` 和 `AddExtra` 返回错误。这保证了在链构建完成之后，调用信息是不可变的。

## 上下文传递

### 绑定

`callInfoCtxBindMw` 是内置的优先级中间件（`math.MinInt`，最高优先级），确保 CallInfo 最早注入 context：

```go
// service_callinfo.go:92-115
func callInfoCtxBindMw(cinfo *CallInfo) PrioritizedMiddlewareProvider {
    return &SimplePrioritizedMiddleware{
        Order: math.MinInt,
        Mw: func(next Endpoint) Endpoint {
            return func(ctx context.Context, req interface{}) (interface{}, error) {
                ctx = context.WithValue(ctx, agServiceCallInfoKey{}, cinfo)
                return next(ctx, req)
            }
        },
    }
}
```

这个中间件由 `buildEndpointChain` 自动添加（`agservice_builder.go:62`），使用者无需手动注入。

### 提取

```go
// service_callinfo.go:118-124
func GetCallInfoFromContext(ctx context.Context) *CallInfo {
    if rmd, ok := ctx.Value(agServiceCallInfoKey{}).(*CallInfo); ok {
        return rmd
    }
    return nil
}
```

任何中间件或 Handler 都可以从 context 中提取 CallInfo：

```go
func myMiddleware(next Endpoint) Endpoint {
    return func(ctx context.Context, req interface{}) (interface{}, error) {
        ci := GetCallInfoFromContext(ctx)
        if ci != nil {
            slog.Info("call", "service", ci.ServiceInfo().ServiceName(),
                "method", ci.CallName())
        }
        return next(ctx, req)
    }
}
```

## 数据流

### svcgen 中的实际创建

在 aggo 生成的 `internal/svcgen/` 层中，ServiceInfo 和 CallInfo 在包级别变量中创建：

```go
// internal/svcgen/agservice_studentservice_proxy.go
// 包级别变量，在服务启动前初始化
var StudentServiceServiceInfo = ag_service.NewServiceInfo(
    "student",               // packageName (proto package)
    "StudentService",        // serviceName (proto service GoName)
    (*student.StudentService)(nil),
)

var StudentServiceCreateStudentCallInfo = ag_service.NewCallInfo(
    StudentServiceServiceInfo,
    "CreateStudent",
    false,  // clientStreaming
    false,  // serverStreaming
)

var StudentServiceGetStudentCallInfo = ag_service.NewCallInfo(
    StudentServiceServiceInfo,
    "GetStudent",
    false,
    false,
)

var StudentServiceCallInfos = map[string]*ag_service.CallInfo{
    "CreateStudent": StudentServiceCreateStudentCallInfo,
    "GetStudent":    StudentServiceGetStudentCallInfo,
}
```

### init 阶段：CallInfo 标签配置

`internal/init.go` 中可以在建立代理链之前对 CallInfo 设置标签。这是**关键设计点**——标签必须在 `BuildEndpointChain`（锁定 CallInfo）之前设置：

```go
// internal/init.go
package internal

import (
    "agaidevdemo/internal/svcgen"
    "gitlab.allinfinance.com/aifgo/ag-core/contribute/agdb"
)

func init() {
    // 在 BuildEndpointChain 之前设置标签
    svcgen.StudentServiceCreateStudentCallInfo.AddTag(agdb.TransactionTag, true)
}
```

执行顺序：

```
程序启动 init() 执行链
    │
    ├── 1. svcgen 包 init(): 创建 ServiceInfo + CallInfo（包变量初始化）
    │
    ├── 2. internal/init.go: 配置标签（AddTag/AddExtra）  ← 此时还可修改
    │
    ├── 3. FX 容器启动 → NewStudentServiceProxy
    │      └── BuildEndpointChain(cinfo, mws, handler)
    │            ├── callInfoCtxBindMw(cinfo)   ← 自动添加
    │            └── lock()                     ← 锁定，不可再修改
    │
    └── 4. 服务就绪，开始接受请求
```

```
服务初始化
    │
    ├── NewServiceInfo(pkg, svc, handlerType)  ← 全局唯一
    │
    ├── NewCallInfo(si, "MethodA", ...)         ← 每个方法一个
    │     └── AddTag / AddExtra                   ← 构建前添加元数据
    │
    └── BuildEndpointChain(cinfo, mws, handler)
          └── callInfoCtxBindMw(cinfo)            ← 自动添加（锁定 CallInfo）
          └── lock()                              ← 锁定，不可再修改
          └── 返回 Endpoint

运行期
    │
    ├── Endpoint(ctx, req)
    │     └── ctx ← (含 CallInfo)
    │
    ├── Middleware1: GetCallInfoFromContext(ctx)  ← 读取元数据
    ├── Middleware2: GetCallInfoFromContext(ctx)
    └── Actual Handler: GetCallInfoFromContext(ctx)
```

## CallInfo 与条件中间件

CallInfo 的标签（Tag）条件中间件配合使用。`MiddleWareCondition` 接口接收 CallInfo 参数，根据其中的标签决定是否激活：

```go
// 来自 agdb 的事务中间件
type TransactionMiddlewareProvider struct{}

func (m *TransactionMiddlewareProvider) Condition(callInfo *ag_service.CallInfo) bool {
    txTag := callInfo.GetTag(agdb.TransactionTag)
    return txTag != nil && txTag.(bool)
}

func (m *TransactionMiddlewareProvider) Middleware() ag_service.MiddlewareFunc {
    return func(next ag_service.Endpoint) ag_service.Endpoint {
        return func(ctx context.Context, req interface{}) (interface{}, error) {
            // 开启数据库事务...
            return next(ctx, req)
        }
    }
}
```

```
init 中设 Tag → CallInfo.Tag["db.tx"] = true
                     │
                     ▼
BuildEndpointChain → MiddleWareCondition 检查
    │
    ├── GetTag("db.tx") == true  → 添加事务中间件
    └── GetTag("db.tx") == false → 跳过事务中间件
```

## 注意事项

- **CallInfo 不可在 Handler 中修改**：锁定后 AddTag/AddExtra 都会失败。如果想传递 Handler 层面的数据，使用 context 直接设置
- **Tag 键不能重复**：`AddTag` 在键已存在时返回错误。使用 `HasTag` 先检查，或按约定使用命名空间前缀（如 `"db.tx"`、`"auth.user"`）
- **`callInfoCtxBindMw` 自动注入**：不需要手动添加 CallInfo 绑定的中间件
- **`ServiceInfo` 可共享**：多个 CallInfo 可以指向同一个 ServiceInfo 实例
