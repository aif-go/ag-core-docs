---
tags:
  - ag-core
  - ag-app
  - server
  - http
---

# Server 接口与实现

> 接口：`ag/ag_server/server.go` | 实现：`ag/ag_server/http/` + `hello/`

## Server 接口

```go
type Server interface {
    Start(context.Context) error
    Stop(context.Context) error
}
```

**极简接口** — 任何实现了 `Start` + `Stop` 的类型都可以作为 ag-app 的服务。

| 方法 | 语义 |
|------|------|
| `Start(ctx)` | 启动服务，**阻塞直到服务结束或出错** |
| `Stop(ctx)` | 优雅关闭服务 |

> `Start()` 是阻塞的！App 在 goroutine 中调用 `srv.Start()`，所以 `Start` 必须在内部启动监听后阻塞（如 `http.ListenAndServe`）。

## HTTP Server（Gin 引擎）

> 源码：`ag/ag_server/http/http.go`

生产环境中推荐使用的 HTTP 服务实现，基于 Gin 框架。

### 结构

```go
type Server struct {
    *gin.Engine                    // 嵌入 Gin 引擎，可直接注册路由
    httpSrv *http.Server
    host    string
    port    int
    logger  *slog.Logger
}
```

### 创建

```go
func NewServer(engine *gin.Engine, logger *slog.Logger, opts ...Option) *Server
```

Options：

| Option | 作用 |
|--------|------|
| `WithServerHost(host string)` | 设置监听地址 |
| `WithServerPort(port int)` | 设置监听端口 |

### 便捷工厂 — NewHttpGinServer

```go
func NewHttpGinServer(
    logger *slog.Logger,
    conf ag_conf.IConfigurableEnvironment,
) *Server
```

从配置中读取 HTTP 地址：

```yaml
http:
  host: 0.0.0.0
  port: 8080
```

```go
s := http.NewHttpGinServer(logger, env)
// s 可直接添加路由
s.GET("/api/health", healthHandler)
```

### Start / Stop

```go
func (s *Server) Start(ctx context.Context) error {
    s.logger.Info("gin server start", "host", "http://"+s.host+":"+s.port)
    s.httpSrv = &http.Server{
        Addr:    fmt.Sprintf("%s:%d", s.host, s.port),
        Handler: s,                    // s 嵌入了 gin.Engine
    }
    // 阻塞：ListenAndServe 会一直运行直到出错或关闭
    return s.httpSrv.ListenAndServe()
}

func (s *Server) Stop(ctx context.Context) error {
    s.logger.Info("Shutting down server...")
    ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
    defer cancel()
    return s.httpSrv.Shutdown(ctx)     // 优雅关闭，最多等待 5 秒
}
```

## Hello Server（示例/调试）

> 源码：`ag/ag_server/hello/hello.go`

简单的标准库 HTTP Server，用于快速验证功能。

```go
func NewHelloServer(logger *slog.Logger) *Server
```

- 固定监听 `0.0.0.0:8888`
- 根路径返回 "Hello, World!"
- 打印请求 Header 和 Body
- 启动了就自动阻塞在 `ListenAndServe`

## 实现 Server 接口

要添加自定义 Server，只需实现两个方法：

```go
type MyServer struct {
    // ...
}

func (s *MyServer) Start(ctx context.Context) error {
    // 启动逻辑（阻塞）
    return nil
}

func (s *MyServer) Stop(ctx context.Context) error {
    // 关闭逻辑
    return nil
}
```

然后通过 `WithServer` 注入 App：

```go
app, _ := ag_app.NewApp(
    ag_app.WithServer(myServer),
)
```

## 注意事项

| 要点 | 说明 |
|------|------|
| **Start 必须阻塞** | `Start()` 应像 `ListenAndServe` 一样阻塞调用方 goroutine |
| **Stop 由 ctx 控制超时** | HTTP Server 的 Stop 从 `context.Background()` 创建带超时的独立 ctx |
| **路由注册时机** | `NewServer` 后即可注册路由，`Start()` 前完成 |
| **Gin 实例可复用** | `NewServer` 不限制 `gin.Engine` 的创建方式，可使用自定义配置 |
