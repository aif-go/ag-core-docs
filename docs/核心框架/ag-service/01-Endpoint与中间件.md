---
tags:
  - ag-core
  - ag-service
  - endpoint
  - middleware
  - architecture
---

# Endpoint 与中间件

> 路径：`endpoint.go` + `agservice_builder.go` + `service_middleware.go` + `agservice_proxy.go`

## 两套中间件体系

ag_service 包含两套并存的中间件体系，它们**不互斥**，服务于不同的抽象层次：

### 旧体系：Endpoint → MiddlewareFunc（洋葱模型）

```go
// endpoint.go:16-18
type Endpoint func(ctx context.Context, req interface{}) (interface{}, error)
type MiddlewareFunc func(next Endpoint) Endpoint
```

构建流程：

```
AgServiceBuilder.BuildEndpointChain(cinfo, customMws, actual)
    │
    ├── 1. 对 CallInfo 执行 callInfoOpts（增强）
    │     如事务标志注入
    │
    ├── 2. 合并中间件列表
    │      globalMWs + customMws
    │
    ├── 3. 锁定 CallInfo（不可再修改）
    │
    ├── 4. 转 PrioritizedMiddlewareProvider
    │      ├── 内置插入 callInfoCtxBindMw（优先级 math.MinInt → 最外层）
    │      ├── MiddleWareCondition 检查 → 不满足条件则跳过
    │      └── 无优先级的 MW → 默认 ServiceInfoMiddlewarePriorityNormal（2000）
    │
    ├── 5. 按优先级排序（数值小 → 先执行）
    │
    └── 6. 从后向前包装 Endpoint（洋葱模型）
           actual → MW[N-1](...MW[1](MW[0](actual))...)
```

### 新体系：Middleware → RegisterHandler

```go
// service_middleware.go:17-21
type Middleware func(
    method string,
    ctx context.Context,
    req interface{},
    next func(context.Context, interface{}) (interface{}, error),
) (interface{}, error)
```

相比旧体系，新体系的中间件**签名中显式传入 `method`**，适合需要根据方法名路由的场景。

```go
// service_middleware.go:51-73
func RegisterHandler(methodName string, prioritizedMws []PrioritizedMiddleware, handler HandlerFunc) HandlerFunc
```

流程：

```
RegisterHandler(method, prioritizedMws, handler)
    │
    ├── 1. 按优先级排序（MiddlewarePriority 常量）
    │
    ├── 2. 提取 Middleware 列表
    │
    └── 3. 从后向前包装（与旧体系相同的洋葱模型）
           handler → MW[N-1](...MW[0](handler))
```

### 两体系对比

| 方面 | 旧体系 | 新体系 |
|------|--------|--------|
| 中间件签名 | `func(next) Endpoint` | `func(method, ctx, req, next)` |
| 优先级范围 | 0~4000（步长 1000） | 0~40（步长 10） |
| 条件过滤 | `MiddleWareCondition` 接口 | 无 |
| CallInfo 绑定 | 内置自动注入 | 需要手动调用 `callInfoCtxBindMw` |
| 返回 | `Endpoint` | `HandlerFunc` |
| 构建器 | `AgServiceBuilder` + `BuildEndpointChain` | `RegisterHandler` 单函数 |
| 典型使用方 | agkitex Suite 构建（服务器/客户端） | 通用 Handler 注册 |

## 优先级常量

旧体系（`endpoint.go`）：

```go
const (
    ServiceInfoMiddlewarePriorityHighest = 0
    ServiceInfoMiddlewarePriorityHigh    = 1000
    ServiceInfoMiddlewarePriorityNormal  = 2000   // 无优先级时的默认值
    ServiceInfoMiddlewarePriorityLow     = 3000
    ServiceInfoMiddlewarePriorityLowest  = 4000
)
```

新体系（`service_middleware.go`）：

```go
const (
    MiddlewarePriorityHighest = 0
    MiddlewarePriorityHigh    = 10
    MiddlewarePriorityNormal  = 20
    MiddlewarePriorityLow     = 30
    MiddlewarePriorityLowest  = 40
)
```

数值越小优先级越高，最先执行（最外层洋葱）。

## 条件中间件

旧体系中，中间件可以实现 `MiddleWareCondition` 接口来根据 `CallInfo` 动态决定是否生效：

```go
type MiddleWareCondition interface {
    Condition(callInfo *CallInfo) bool
}
```

```go
// agservice_builder.go:71-74
if cond, ok := mw.(MiddleWareCondition); ok {
    if !cond.Condition(cinfo) {
        continue  // 不满足条件则跳过此中间件
    }
}
```

使用示例：agdb 的 `TransactionMiddlewareProvider` 通过 `Condition` 判断是否为写操作，只在写入时开启事务中间件。

## 优先级中间件提供者

```go
// endpoint.go:21-27
type PrioritizedMiddlewareProvider interface {
    GetOrder() int              // 优先级值
    Middleware() MiddlewareFunc   // 中间件函数
}

// endpoint.go:29-32
type MiddlewareProvider interface {
    Middleware() MiddlewareFunc
}
```

只有 `PrioritizedMiddlewareProvider` 参与排序；普通的 `MiddlewareProvider` 被包装为 `SimplePrioritizedMiddleware` 使用默认优先级（Normal）。

```go
// endpoint.go:55-66
type SimplePrioritizedMiddleware struct {
    Order int
    Mw    MiddlewareFunc
}
```

## AgServiceProxyBase

```go
// agservice_proxy.go
type AgServiceProxyBase struct {
    ServiceInfo *ServiceInfo
    CallInfos   map[string]*CallInfo
    endpoints   map[string]Endpoint   // 受 RWMutex 保护
}
```

- `RegisterEndpoint(callName, endpoint)` — 注册方法端点
- `GetEndpoint(callName) Endpoint` — 获取方法端点

提供线程安全的 Endpoint 注册/获取，用于在服务初始化阶段注册各方法的 Endpoint 链，运行期通过方法名查找。

## 使用流程

### 代码生成场景（推荐）

aggo proto 自动生成 `internal/svcgen/` 层的代码，开发者只需要：

```go
// 1. 实现业务接口（internal/service/xxx.go）
type StudentServiceImpl struct{}

func (c *StudentServiceImpl) CreateStudent(ctx context.Context, req *student.CreateStudentRequest) (*student.Student, error) {
    // 业务逻辑...
    return resp, nil
}

// 2. FX 自动注入
// svcgen 生成的 init() 函数自动注册：
//   service.NewStudentServiceImpl  → 实现类
//   NewStudentServiceProxyWithFxIn → 带中间件链的 Proxy
```
```

// 3. 可选的：全局中间件
func init() {
    // 注册全局中间件（可选）
    fx.Provide(NewFxAgGlobalMiddleware(myGlobalMw))
}

// 4. 可选的：CallInfo 标签配置
func init() {
    svcgen.StudentServiceCreateStudentCallInfo.AddTag(agdb.TransactionTag, true)
}
```

FX 的组件注入链：

```
fx.Provide(NewStudentServiceImpl)
    │  实现 student.StudentService 接口（不含中间件）
    ▼
NewStudentServiceProxyWithFxIn
    │  依赖 AgServiceBuilder（来自 FxAgServiceMode）
    │  依赖 CustomMws（来自 group 标记）
    │  → BuildEndpointChain(cif, mws, oriEndpoint)
    │  → RegisterEndpoint
    ▼
StudentServiceProxy (student.StudentService)
    │  带中间件链的完整实现
    ▼
adpgen 层依赖 student.StudentService
    ├── kitex: NewServer(handler, opts)
    └── hertz: Router_*(s student.StudentService) *Route
```

## AgServiceProxyBase — 代理基类

```go
// agservice_proxy.go
type AgServiceProxyBase struct {
    ServiceInfo *ServiceInfo                  // 服务信息
    CallInfos   map[string]*CallInfo          // 方法→CallInfo 映射
    endpoints   map[string]Endpoint           // 方法→Endpoint 映射（受 RWMutex 保护）
}
```

### 创建

```go
proxy := ag_service.NewAgServiceProxyBase(serviceInfo, callInfos)
```

### 注册 Endpoint

```go
// BuildEndpointChain 构建完整链路 → 注册
for _, cif := range callInfos {
    endpoint, _ := agServiceBuilder.BuildEndpointChain(cif, mws, actualHandler)
    proxy.RegisterEndpoint(cif.CallName(), endpoint)
}
```

### 调用

```go
func (p *ServiceProxy) CreateMethod(ctx context.Context, req *Request) (*Response, error) {
    endpoint := p.GetEndpoint("CreateMethod")
    resp, err := endpoint(ctx, req)
    return resp.(*Response), err  // 类型断言
}
```

### 对比纯手写

使用 `AgServiceProxyBase` 的好处：

| 方面 | 纯手写 | ProxyBase |
|------|--------|-----------|
| 模板方法 | 每个方法写一次调用逻辑 | `GetEndpoint` 统一获取 |
| 并发安全 | 需要自行加锁 | `RWMutex` 内置 |
| 扩展现有方法 | 新增 proxy 方法 | 只需要注册 endpoint |
| 统一管理 | 散落在多个结构体 | `CallInfos` + `endpoints` 集中管理 |
