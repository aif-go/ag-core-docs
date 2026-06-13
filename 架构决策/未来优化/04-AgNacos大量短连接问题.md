---
tags:
  - ag-core
  - future
  - agnacos
  - optimization
  - bug
  - nacos
---

# AgNacos 优化 — 大量短连接问题

> 记录日期：2026-06-10 | 状态：待修复

## 问题

使用 ag-core 框架连接 Nacos 时，观察到大量 TCP 短连接，连接频繁建立和断开。

## 根因：nacos-sdk-go v1.1.5 每个 HTTP 请求新建 `http.Client`

### 核心代码

**`get.go:37`** / **`post.go:27`**（nacos-sdk-go）：

```go
func get(path string, header http.Header, timeoutMs uint64, ...) (*http.Response, error) {
    client := http.Client{}  // ← 每次调用创建新 client，无连接复用
    client.Timeout = time.Millisecond * time.Duration(timeoutMs)
    resp, errDo := client.Do(request)
    // client 是局部变量，用完即丢弃 → TCP 连接关闭
}
```

`post`、`put`、`delete` 三个函数完全相同的模式。`http.Client{}` 的 `Transport` 为零值，Go 为每个请求创建新的网络连接，用完即释放。

### 请求链路

```
ag-core 业务代码
    ↓
ConfigProxy / NamingProxy
    ↓
NacosServer.ReqApi / ReqConfigApi
    ↓
http_agent.get() / post()        ← 每次都 new http.Client{}
    ↓
net/http (新 TCP 连接)
```

### 高频请求来源

| 机制 | 位置 | 频率 | 端点 |
|------|------|------|------|
| Config 长轮询 | `config_client.go:369` delayScheduler | 每 30s × 每个 DataID 分组 | `POST /nacos/v1/cs/configs/listener` |
| Naming 服务刷新 | `host_reactor.go:159` asyncUpdateService | 每秒 × M 个服务，最多 20 并发 goroutine | `GET /nacos/v1/ns/instance/list` |
| Naming 心跳 | `beat_reactor.go:95` sendInstanceBeat | 每 5s × K 个实例，最多 20 并发 | `PUT /nacos/v1/ns/instance/beat` |
| Config 变更获取 | `config_client.go:453` callListener | 变更时触发 | `GET /nacos/v1/cs/configs` |
| Naming 注册/注销 | `naming_proxy.go` | 启动/停止时 | `POST/DELETE /nacos/v1/ns/instance` |

**估算**：以 3 个服务、每个 2 实例、2 个 DataID 为例，稳态下每秒至少产生约 14 个新 TCP 连接（不含 Config 变更触发）。

## SDK 版本情况

| 版本                | 连接管理                    |
| ----------------- | ----------------------- |
| nacos-sdk-go v1.x | 每次 `http.Client{}`，无连接池 |
| nacos-sdk-go v2.x | naming client 切到 gRPC（HTTP/2 长连接），绕过 HTTP 短连接问题 |

ag-core 当前依赖 `v1.1.5`（`go.mod:21`），`v1.1.6` 也未修复此问题。

## 修复方向

### 方案 A：升到 nacos-sdk-go v2.x

- **优势**：官方支持，连接池开箱即用
- **劣势**：API 不兼容，`config_client.IConfigClient` / `naming_client.INamingClient` 接口变更，`agnacos` 模块需大改

### 方案 B：fork nacos-sdk-go，给 http_agent 加连接池

- **优势**：改动集中，只需改 `get/post/put/delete` 四个函数
- **劣势**：需维护 fork

### 方案 C：在 agnacos 层注入自定义 httpAgent

- **优势**：不改 SDK 源码
- **劣势**：需要实现 `IHttpAgent` 接口并注入到 client 创建流程

```go
// 示例：在 BuildClientConfig 时替换 httpAgent
type PooledHttpAgent struct {
    client *http.Client  // 复用，带连接池
}
```

详细实现见 [agnacos 自定义 HttpAgent 方案](../技术评估/02-agnacos自定义HttpAgent方案.md)。

### 推荐

短期优先考虑方案 C（影响最小），长期推动升级到 v2.x。

> 📐 升级评估详见 [nacos-sdk-go v2 升级影响评估](../技术评估/01-nacos-sdk-v2升级评估.md)
