---
tags:
  - ag-core
  - future
  - agnacos
  - optimization
  - nacos
  - upgrade
---

# nacos-sdk-go v2 升级影响评估

> 记录日期：2026-06-10 | 状态：评估中
> 关联：[[../未来优化/04-AgNacos大量短连接问题|AgNacos 大量短连接问题]]

## 背景

当前 ag-core 依赖 `nacos-sdk-go v1.1.5`，存在大量短连接问题（见 [[04-AgNacos大量短连接问题]]）。升级到 v2 可从根本上解决——v2 的 naming client 采用 gRPC（HTTP/2）替代 HTTP，天然支持多路复用长连接。

## v2 核心变化

### 短连接修复机制

| 组件 | v1 | v2 |
|------|----|----|
| Naming client 协议 | HTTP only | **gRPC（主）** + HTTP（回退） |
| Config client 协议 | HTTP | HTTP（不变） |
| HTTP agent 连接池 | 无显式配置（依赖 DefaultTransport） | 同样无显式配置 |

v2 的 HTTP agent **仍然每次 `new http.Client{}`**，并未修复 HTTP 层连接池。但因为最频繁的 naming 请求（心跳每秒、服务刷新每秒）全部迁移到了 gRPC 长连接通道，整体短连接问题自然消失。

### gRPC 切换逻辑

临时实例（`Ephemeral=true`）走 gRPC，持久实例走 HTTP 回退：
```
NamingProxyDelegate.getExecuteClientProxy()
    ├── instance.Ephemeral == true  → grpcClientProxy
    └── instance.Ephemeral == false → httpClientProxy
```

> ⚠️ **注意**：v2 的 HTTP 层并未做连接池优化。`http_agent.createClient()` 每次仍 `new http.Client{}`，与 v1 行为一致。两版本都依赖 Go 的 `http.DefaultTransport` 做基础连接复用。真正消除短连接的是 naming client 整体从 HTTP 迁移到了 gRPC（HTTP/2 长连接）。

## 接口兼容性矩阵

### 无变化（直接兼容）

| 接口 | 说明 |
|------|------|
| `NacosClientParam.ClientConfig` | v1/v2 都是 `*ClientConfig` |
| `NewServerConfig(ip, port, opts...)` | 签名完全相同 |
| `NewClientConfig(opts...)` | 签名完全相同 |
| `IHttpAgent` | 6 个方法签名完全相同 |
| `IConfigClient.GetConfig` | 签名相同 |
| `IConfigClient.ListenConfig` | 签名相同 |
| `IConfigClient.PublishConfig` | 签名相同 |
| `INamingClient.SelectInstances` | `vo.SelectInstancesParam` 完全相同 |
| `INamingClient.GetService` | 参数结构兼容 |
| `vo.ConfigParam` | 所有字段相同 |
| `vo.SelectInstancesParam` | 字段完全相同 |
| `model.Instance` 核心字段 | Ip / Port / Weight / Enable / Metadata 完全相同 |

### 有变化（需适配）

| 接口 | v1 | v2 | 影响 |
|------|----|----|------|
| Module path | `nacos-sdk-go` | `nacos-sdk-go/v2` | 所有 import 需替换 |
| `ServerConfig` | 4 字段 | **+GrpcPort** | 创建 ServerConfig 时需设置 |
| `INamingClient.RegisterInstance` | 位置参数 `(svc, grp, inst)` | 结构体 `RegisterInstanceParam` | 仅 direct caller 受影响 |
| `model.Instance` | 13 字段含 `Valid`/`Marked` | 11 字段（移除 `Valid`/`Marked`，新增心跳属性） | 使用 `Valid` 的地方需调整 |

## 分模块影响分析

### 1. agnacos/config — ⭐ 低影响

| 改动点 | 说明 |
|--------|------|
| import 路径 | `nacos-sdk-go` → `nacos-sdk-go/v2` |
| `BuildServerConfig` | `ServerConfig` 新增 `GrpcPort`，默认 = Port + 1000 |
| `NewConfigClient` | 参数 `NacosClientParam` 兼容 |

**改动文件**：
- `config/config.go` — import
- `config/ag_conf_nacos.go` — import
- `config/nacos_watcher.go` — import
- `common/serverclient_properties.go` — `BuildServerConfig` 补 GrpcPort

### 2. agnacos/naming — ⭐ 低影响

| 改动点 | 说明 |
|--------|------|
| import 路径 | 同上 |
| `BuildServerConfig` | 同上补 GrpcPort |

**改动文件**：
- `naming/naming.go` — import

> `naming.go` 只做 client 创建，不直接调 `RegisterInstance` 等方法，签名变化不影响。

### 3. ag-kitex — ⭐ 低影响

| 改动点 | 说明 |
|--------|------|
| import 路径 | `nacos-sdk-go` → `nacos-sdk-go/v2` |
| `SelectInstances` | 签名完全相同，无需改动 |
| `model.Instance` | 只用 `Ip/Port/Weight/Enable/Metadata`，v2 全有 |

**改动文件**：
- `client/ag_nacos_resolver.go` — import

### 4. ag-hertz — ❌ 高影响（有阻塞）

| 问题 | 说明 |
|------|------|
| 依赖链 | `discovery_nacos.go` → `hertz-contrib/registry/nacos` → nacos-sdk-go v1 |
| 类型冲突 | v2 `INamingClient` ≠ v1 `INamingClient`（不同 import path，Go 视为不同类型） |
| 结果 | **无法将 v2 client 传给 hertz-contrib 的 resolver** |

**`discovery_nacos.go` 当前实现**：
```go
func NewResolver(param *Param, props *Properties) discovery.Resolver {
    return rnacos.NewNacosResolver(
        param.NamingClient,  // ← 这里类型冲突
        rnacos.WithResolverCluster(props.Nacos.Cluster),
        rnacos.WithResolverGroup(props.Nacos.Group),
    )
}
```

**解决方案**：

| 方案 | 做法 | 推荐 |
|------|------|------|
| A | ag-hertz 绕开 hertz-contrib，复用 ag-kitex 的 `AgNacosResolver` | ⭐ **推荐** |
| B | 等 `hertz-contrib/registry/nacos` 发布 v2 兼容版 | 不可控 |
| C | fork hertz-contrib 自行适配 | 维护成本高 |

方案 A 最可行：ag-kitex 的 `AgNacosResolver` 已经直接封装了 naming client，不依赖 kitex-contrib，只需实现 `discovery.Resolver` 接口即可同时用于 kitex 和 hertz。

## 升级步骤建议

1. **agnacos/common**：`BuildServerConfig` 补 `GrpcPort`，import 路径替换
2. **agnacos/config + naming**：import 路径替换
3. **ag-kitex**：import 路径替换
4. **ag-hertz**：重构为复用 `AgNacosResolver`
5. 全量回归测试

## 风险总结

| 模块 | 改动量 | 风险 | 测试重点 |
|------|--------|------|----------|
| agnacos/config | import + GrpcPort | 低 | 远程配置拉取、监听回调 |
| agnacos/naming | import + GrpcPort | 低 | 服务注册发现 |
| ag-kitex | import 替换 | 低 | SelectInstances 返回数据正确性 |
| ag-hertz | resolver 层重构 | 中 | 服务发现路由、负载均衡 |
