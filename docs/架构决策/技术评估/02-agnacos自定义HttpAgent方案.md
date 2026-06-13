---
tags:
  - ag-core
  - agnacos
  - optimization
  - solution
---

# agnacos 自定义 HttpAgent 方案

> 记录日期：2026-06-10 | 状态：方案阶段
> 关联：[AgNacos 大量短连接问题](../未来优化/04-AgNacos大量短连接问题.md)

## 目标

在 agnacos 层注入自定义 `IHttpAgent`，用共享的 `http.Client` 替代 nacos-sdk-go v1 默认的每次 `new http.Client{}`，缓解 HTTP 层短连接问题。

## 原理

SDK 的私有 `setConfig` 函数（`clients/client_factory.go`）负责创建 `NacosClient` 并设置默认 `HttpAgent`：

```go
// nacos-sdk-go v1.1.5 — 私有函数，无法覆盖
func setConfig(param vo.NacosClientParam) (nacos_client.INacosClient, error) {
    client := &nacos_client.NacosClient{}
    client.SetClientConfig(*param.ClientConfig)
    client.SetServerConfig(param.ServerConfigs)
    if _, _err := client.GetHttpAgent(); _err != nil {
        _ = client.SetHttpAgent(&http_agent.HttpAgent{}) // ← 默认
    }
    return client, nil
}
```

但我们不需要调用它——`INacosClient.SetHttpAgent()` 是导出接口，且 `config_client.NewConfigClient(nc)` 和 `naming_client.NewNamingClient(nc)` 都接受 `INacosClient` 参数。只需手动构造 `NacosClient` 并注入自定义 Agent。

## 实现

### 1. 新增 `common/pooled_agent.go`

```go
// agnacos/common/pooled_agent.go
package common

import (
    "io"
    "net/http"
    "net/url"
    "strings"
    "time"

    "github.com/nacos-group/nacos-sdk-go/common/http_agent"
    "github.com/nacos-group/nacos-sdk-go/util"
    "github.com/pkg/errors"
)

// PooledHttpAgent 使用共享 http.Client，替代 SDK 默认的每次 new http.Client{}
type PooledHttpAgent struct {
    client *http.Client
}

func NewPooledHttpAgent() *PooledHttpAgent {
    return &PooledHttpAgent{
        client: &http.Client{
            Transport: &http.Transport{
                MaxIdleConns:        100,
                MaxIdleConnsPerHost: 50, // Go 默认 2，nacos 高并发下不够
                IdleConnTimeout:     90 * time.Second,
            },
        },
    }
}

func (a *PooledHttpAgent) Get(path string, header http.Header, timeoutMs uint64,
    params map[string]string) (*http.Response, error) {
    if !strings.Contains(path, "?") {
        path = path + "?"
    }
    for key, value := range params {
        path = path + key + "=" + url.QueryEscape(value) + "&"
    }
    if strings.HasSuffix(path, "&") {
        path = path[:len(path)-1]
    }
    a.client.Timeout = time.Duration(timeoutMs) * time.Millisecond
    req, err := http.NewRequest(http.MethodGet, path, nil)
    if err != nil {
        return nil, err
    }
    req.Header = header
    return a.client.Do(req)
}

func (a *PooledHttpAgent) Post(path string, header http.Header, timeoutMs uint64,
    params map[string]string) (*http.Response, error) {
    a.client.Timeout = time.Duration(timeoutMs) * time.Millisecond
    body := util.GetUrlFormedMap(params)
    req, err := http.NewRequest(http.MethodPost, path, strings.NewReader(body))
    if err != nil {
        return nil, err
    }
    req.Header = header
    return a.client.Do(req)
}

func (a *PooledHttpAgent) Put(path string, header http.Header, timeoutMs uint64,
    params map[string]string) (*http.Response, error) {
    a.client.Timeout = time.Duration(timeoutMs) * time.Millisecond
    var body string
    for key, value := range params {
        if len(value) > 0 {
            body += key + "=" + value + "&"
        }
    }
    if strings.HasSuffix(body, "&") {
        body = body[:len(body)-1]
    }
    req, err := http.NewRequest(http.MethodPut, path, strings.NewReader(body))
    if err != nil {
        return nil, err
    }
    req.Header = header
    return a.client.Do(req)
}

func (a *PooledHttpAgent) Delete(path string, header http.Header, timeoutMs uint64,
    params map[string]string) (*http.Response, error) {
    if !strings.HasSuffix(path, "?") {
        path = path + "?"
    }
    for key, value := range params {
        path = path + key + "=" + url.QueryEscape(value) + "&"
    }
    if strings.HasSuffix(path, "&") {
        path = path[:len(path)-1]
    }
    a.client.Timeout = time.Duration(timeoutMs) * time.Millisecond
    req, err := http.NewRequest(http.MethodDelete, path, nil)
    if err != nil {
        return nil, err
    }
    req.Header = header
    return a.client.Do(req)
}

func (a *PooledHttpAgent) RequestOnlyResult(method string, path string, header http.Header,
    timeoutMs uint64, params map[string]string) string {
    var response *http.Response
    var err error
    switch method {
    case http.MethodGet:
        response, err = a.Get(path, header, timeoutMs, params)
    case http.MethodPost:
        response, err = a.Post(path, header, timeoutMs, params)
    case http.MethodPut:
        response, err = a.Put(path, header, timeoutMs, params)
    case http.MethodDelete:
        response, err = a.Delete(path, header, timeoutMs, params)
    default:
        return ""
    }
    if err != nil || response == nil {
        return ""
    }
    if response.StatusCode != 200 {
        return ""
    }
    bytes, errRead := io.ReadAll(response.Body)
    defer response.Body.Close()
    if errRead != nil {
        return ""
    }
    return string(bytes)
}

func (a *PooledHttpAgent) Request(method string, path string, header http.Header,
    timeoutMs uint64, params map[string]string) (*http.Response, error) {
    switch method {
    case http.MethodGet:
        return a.Get(path, header, timeoutMs, params)
    case http.MethodPost:
        return a.Post(path, header, timeoutMs, params)
    case http.MethodPut:
        return a.Put(path, header, timeoutMs, params)
    case http.MethodDelete:
        return a.Delete(path, header, timeoutMs, params)
    default:
        return nil, errors.New("not available method")
    }
}
```

> **注意**：方法体直接复制 SDK 对应函数（`get/post/put/delete`），只把 `client := http.Client{}` → `a.client`（共享实例）。逻辑完全一致，无行为差异。

### 2. 修改 `config/config.go`

```diff
func NewNacosConfigClient(p *NacosConfigProperties) (config_client.IConfigClient, error) {
    if p == nil || !p.Enable {
        return nil, nil
    }
    sc, err := common.BuildServerConfig(p.SCProperties)
    cc, err := common.BuildClientConfig(p.SCProperties)

-   cli, err := clients.NewConfigClient(
-       vo.NacosClientParam{ClientConfig: cc, ServerConfigs: sc},
-   )

+   nc := &nacos_client.NacosClient{}
+   nc.SetClientConfig(*cc)
+   nc.SetServerConfig(sc)
+   nc.SetHttpAgent(common.NewPooledHttpAgent())
+   return config_client.NewConfigClient(nc)
}
```

新增 import：
```go
"github.com/nacos-group/nacos-sdk-go/clients/nacos_client"
```

### 3. 修改 `naming/naming.go`

```diff
func NewNacosNamingClient(p *NacosNamingProperties) (naming_client.INamingClient, error) {
    if p == nil || !p.Enable {
        return nil, nil
    }
    sc, err := common.BuildServerConfig(p.SCProperties)
    cc, err := common.BuildClientConfig(p.SCProperties)

-   cli, err := clients.NewNamingClient(
-       vo.NacosClientParam{ClientConfig: cc, ServerConfigs: sc},
-   )

+   nc := &nacos_client.NacosClient{}
+   nc.SetClientConfig(*cc)
+   nc.SetServerConfig(sc)
+   nc.SetHttpAgent(common.NewPooledHttpAgent())
+   return naming_client.NewNamingClient(nc)
}
```

新增 import：
```go
"github.com/nacos-group/nacos-sdk-go/clients/nacos_client"
```

同时可以移除不再需要的 import：
```diff
-   "github.com/nacos-group/nacos-sdk-go/clients"
-   "github.com/nacos-group/nacos-sdk-go/vo"
```

## 改动总结

| 文件                       | 操作  | 说明                               |
| ------------------------ | --- | -------------------------------- |
| `common/pooled_agent.go` | 新增  | 共享 `http.Client` 的 IHttpAgent 实现 |
| `config/config.go`       | 修改  | 绕过 SDK 工厂，手动注入 Agent             |
| `naming/naming.go`       | 修改  | 同上                               |

## 效果

| | 原 SDK 默认 | 自定义 |
|------|---------|--------|
| `http.Client` 生命周期 | 每次请求新建、用完丢弃 | 全局共享单例 |
| Transport | `DefaultTransport`，`MaxIdleConnsPerHost=2` | 自定义，`MaxIdleConnsPerHost=50` |
| 连接复用 | 最多 2 个空闲连接，超出的关闭 | 最多 50 个空闲连接 |

## 局限性

1. **只优化了 HTTP 层面** — 没有改变 config client 的长轮询频率和 naming client 的 service 刷新频率，纯粹减少 TCP 握手次数
2. **不如 v2 的 gRPC 彻底** — v2 的 naming client 走 gRPC 后是单连接复用，HTTP 层优化只是减少握手
3. **Config client 的长轮询仍走 HTTP** — 但长轮询频率低（30s），影响有限
