---
tags:
  - ag-core
  - core-framework
  - ag-service
  - architecture
  - overview
---

# AgService — 服务调用链框架

> 路径：`ag/ag_service/` | Endpoint 中间件责任链 + 调用信息上下文传递

## 概述

AgService 提供一个**通用的服务调用中间件框架**，抽象出 `Endpoint` 概念（请求→响应），通过中间件责任链实现关注点分离。它不绑定任何传输协议——Hertz、Kitex、甚至本地方法调用都可以使用这套中间件体系。

## 在代码生成体系中的位置

AgService 是整个 aggo 代码生成管线中的**中间层**，连接生成的业务代码与协议适配层：

```
                    ┌──────────────────────────┐
                    │    proto 定义文件          │
                    └──────────┬───────────────┘
                               │ aggo proto -p service
                               ▼
┌─────────────────────────────────────────────────────────┐
│  internal/svcgen/            (代码生成)                  │
│    ├── ServiceInfo + CallInfo        ← 调用信息          │
│    ├── StudentServiceProxy           ← 嵌入 AgService   │
│    │     └── BuildEndpointChain      ─── 使用 AgService │
│    └── zfx_*.go                      ← FX 注册          │
├─────────────────────────────────────────────────────────┤
│  ag/ag_service/                    (框架)                │
│    ├── AgServiceProxyBase         ← 代理基类             │
│    ├── AgServiceBuilder           ← 链构建器             │
│    ├── Endpoint / Middleware       ← 核心抽象             │
│    └── ServiceInfo / CallInfo      ← 调用元信息           │
├─────────────────────────────────────────────────────────┤
│  internal/adpgen/                 (协议适配)             │
│    ├── kitex/* → 调用 StudentService 接口                │
│    └── hertz/* → 调用 StudentService 接口                │
└─────────────────────────────────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────────┐
                    │  internal/service/*.go    │
                    │  （业务实现，实现接口）      │
                    └──────────────────────────┘
```

### 运行期调用链

```
客户端请求 (HTTP/gRPC)
    │
    ▼
Hertz/Kitex Handler (adpgen)
    │  调用 student.StudentService 接口
    ▼
StudentServiceProxy (svcgen)
    │  GetEndpoint → 获得 middleware 链
    ▼
Middleware1 (事务、日志、认证...)
    │
    ▼
Middleware2
    │
    ▼
... MiddlewareN
    │
    ▼
Actual Handler → internal/service/xxx.go
```

## 核心类型

| 类型 | 用途 |
|------|------|
| `Endpoint` | 调用端点：`func(ctx, req) (resp, error)` |
| `MiddlewareFunc` | 中间件：`func(next Endpoint) Endpoint` — 洋葱模型 |
| `Middleware` | 新体系中间件：`func(method, ctx, req, next) (resp, error)` — 带 method 名 |
| `ServiceInfo` | 服务元信息：包名、服务名、Handler 类型 |
| `CallInfo` | 调用级信息：服务信息、方法名、流类型、标签、额外数据 |
| `AgServiceBuilder` | 调用链构建器：合并中间件 → 排序 → 包装 |
| `AgServiceProxyBase` | 服务代理基类：Endpoint 注册与获取 |

详见 [[01-Endpoint与中间件]]。

## CallInfo 上下文传递

`CallInfo` 携带调用级别的元信息（服务名、方法名、标签、额外数据），通过内置中间件 `callInfoCtxBindMw` 注入 context，后续中间件可通过 `GetCallInfoFromContext` 获取。

详见 [[02-CallInfo与上下文]]。

## 在 svcgen 中的使用模式

生成的 `internal/svcgen/agservice_<svc>_proxy.go` 中，ag_service 的组件被如下使用（以 demo 项目为例）：

### 1. 创建 ServiceInfo

```go
// svcgen/agservice_studentservice_proxy.go
var StudentServiceServiceInfo = ag_service.NewServiceInfo(
    "student",              // packageName（来自 proto 的 package）
    "StudentService",       // serviceName（来自 proto service 的 GoName）
    (*student.StudentService)(nil),  // handlerType（接口类型）
)
```

### 2. 为每个方法创建 CallInfo

```go
var StudentServiceCreateStudentCallInfo = ag_service.NewCallInfo(
    StudentServiceServiceInfo,
    "CreateStudent",  // 方法名
    false,            // clientStreaming
    false,            // serverStreaming
)

var StudentServiceCallInfos = map[string]*ag_service.CallInfo{
    "CreateStudent": StudentServiceCreateStudentCallInfo,
    "GetStudent":    StudentServiceGetStudentCallInfo,
}
```

### 3. 构建 Proxy

```go
type StudentServiceProxy struct {
    ag_service.AgServiceProxyBase        // 嵌入代理基类
    impl *service.StudentServiceImpl
}

func NewStudentServiceProxy(
    impl *service.StudentServiceImpl,
    agServiceBuilder ag_service.AgServiceBuilder,
    mws []ag_service.MiddlewareProvider,
) (student.StudentService, error) {

    p := &StudentServiceProxy{
        AgServiceProxyBase: ag_service.NewAgServiceProxyBase(
            StudentServiceServiceInfo,    // ServiceInfo
            StudentServiceCallInfos,      // CallInfos 表
        ),
    }

    for _, cif := range p.CallInfos {
        // 为每个方法构建 Endpoint 链
        oriEndpoint := getOriginalHandler(cif)       // 原始业务逻辑
        endpoint, _ := agServiceBuilder.BuildEndpointChain(
            cif,                                      // CallInfo
            mws,                                      // 自定义中间件
            oriEndpoint,                              // 实际 handler
        )
        p.RegisterEndpoint(cif.CallName(), endpoint)  // 注册 endpoint
    }
    return p, nil
}

// 代理方法：GetEndpoint → 调用中间件链
func (p *StudentServiceProxy) CreateStudent(ctx context.Context, req *student.CreateStudentRequest) (*student.Student, error) {
    endpoint := p.GetEndpoint("CreateStudent")
    resp, err := endpoint(ctx, req)
    return resp.(*student.Student), err          // 类型断言
}
```

### 4. CallInfo 标签的动态配置

在 `internal/init.go` 中，可以在服务启动前对 CallInfo 设置标签——这些标签在 `BuildEndpointChain` 之前被设置，构建链时被锁定：

```go
// init.go — 在 FX 启动前配置
svcgen.StudentServiceCreateStudentCallInfo.AddTag(agdb.TransactionTag, true)
```

## FX 模块

```go
// zfx_ag_service.go
var FxAgServiceMode = fx.Module("ag_service.agservice",
    fx.Provide(FxNewAgServiceBuilder),
)
```

通过组标记注入自定义组件：

```go
// CallInfo 增强选项
fx.Provide(NewFxAgCallInfoOpt(myCallInfoOpt))

// 全局中间件（三种注入方式）
fx.Provide(NewFxAgGlobalMiddleware(myPrioritizedMw))   // PrioritizedMiddlewareProvider
fx.Provide(NewFxAgGlobalMiddleware(myMwProvider))      // MiddlewareProvider
fx.Provide(NewFxAgGlobalMiddleware(myMwFunc))          // MiddlewareFunc
```

生成的 svcgen 层也使用 FX 组标记将 proxy 注册到全局：

```go
// zfx_agservice_proxy_student.go
func init() {
    AddFxServiceWithProxyOpt(
        fx.Provide(
            service.NewStudentServiceImpl,
            NewStudentServiceProxyWithFxIn,
        ),
    )
}
// zfx_service.go — 收集所有 proxy 注册
func FxServiceWithProxyModule() fx.Option {
    return fx.Module("fx-service-with-proxy", fxServiceWithProxyOpts...)
}
```

## 文件结构

```
ag/ag_service/
├── endpoint.go                        # Endpoint/MiddlewareFunc 定义 + 优先级常量
├── service_middleware.go              # 新体系 Middleware + RegisterHandler
├── agservice_builder.go               # AgServiceBuilder 构建器
├── agservice_proxy.go                 # AgServiceProxyBase 代理基类
├── service_callinfo.go                # ServiceInfo + CallInfo + 上下文绑定
├── service_callinfo_test.go
└── zfx_ag_service.go                  # FX 模块 + 组标记辅助函数
```

## 子模块一览

| 文档 | 内容 |
|------|------|
| [[01-Endpoint与中间件]] | 两套中间件体系、构建链流程、条件中间件、AgServiceProxyBase |
| [[02-CallInfo与上下文]] | ServiceInfo、CallInfo 结构、Tag/Extra、上下文注入与提取 |
