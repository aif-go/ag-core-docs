---
tags:
  - ag-core
  - ag-app
  - architecture
  - overview
---

# AgApp — 应用启动框架

> 模块：`ag/ag_app/` | 应用容器 + 服务生命周期管理

## 概述

AgApp 是 ag-core 的应用启动框架，负责**组装服务、管理生命周期、响应信号**。它提供两种运行模式：

| 模式 | 入口 | 场景 |
|------|------|------|
| **手动模式** | `ag_app.NewApp(...)` + `app.Run()` | 简单的独立应用 |
| **FX 模式** | `fxs.FxAppMode` | DI 驱动的微服务应用 |

## 文件结构

```
ag/
├── ag_app/
│   └── app.go                 # App 定义：NewApp、Run、Start、Stop
│
├── ag_server/
│   ├── server.go              # Server 接口定义
│   ├── http/
│   │   └── http.go            # Gin HTTP Server 实现
│   └── hello/
│       └── hello.go           # Hello HTTP Server 实现（示例/调试）
│
└── ../../fxs/                  # FX Module 层
    ├── zfx_app.go             # FxAppMode — 主 Module
    ├── zfx_conf.go            # FxAgConfModule — 配置加载
    ├── zfx_log.go             # FxAgSlogMode / FxAgSlogZapMode（已弃用）
    ├── zfx_server_http.go     # FxHttpServerBaseModule — Gin HTTP Server
    └── zfx_hello.go           # FxHelloServerMode — Hello Server
```

## 架构分层

```
┌─────────────────────────────────────────────┐
│               fxs (FX Module)                │
│  FxAppMode + FxAgConfModule + FxHttpServer* │
├─────────────────────────────────────────────┤
│              ag_app (App 容器)                │
│  NewApp → Start/Stop/Run                    │
├─────────────────────────────────────────────┤
│            ag_server (Server 接口)            │
│  Server{Start, Stop}                        │
├──────────────────┬──────────────────────────┤
│  http.Server     │  hello.Server            │
│  (Gin引擎)       │  (标准 net/http)          │
└──────────────────┴──────────────────────────┘
```

## 子模块一览

| 文件 | 内容 |
|------|------|
| [01-核心App](01-核心App.md) | App 结构、生命周期、Option 模式 |
| [02-Server接口](02-Server接口.md) | Server 接口定义 + Gin HTTP 实现 + Hello 实现 |
| [03-FX集成](03-FX集成.md) | FX Module 装配与依赖注入 |
| [04-使用指南](04-使用指南.md) | **面向业务开发者：快速上手、配置、最佳实践** |

## 关键设计

| 概念 | 说明 |
|------|------|
| **Server 接口** | `Start(ctx) error` + `Stop(ctx) error`，仅两个方法 |
| **Option 模式** | `NewApp(opts...)` + `WithServer/WithName/WithLogger` |
| **goroutine 启动** | 每个 Server 在自己的 goroutine 中 Start |
| **信号驱动** | `Run()` 监听 SIGINT/SIGTERM 触发 Stop |
| **FX 生命周期** | `FxApp` 将 App.Start/Stop 挂到 fx.Lifecycle Hook |
| **context 分离** | `Start()` 从 `context.Background()` 创建独立生命周期 ctx |

## 🔭 未来优化方向

App 当前只有 Start/Stop 两个阶段，实际应用需要更细粒度的生命周期管理：

```
当前：Start → stop
需求：init → start → ready → stop → cleanup
```

- **init**：DB 连接、证书加载、配置校验
- **ready**：服务注册、健康检查
- **cleanup**：日志 flush、连接池关闭、服务反注册

详细讨论见 [App 生命周期钩子优化](../../架构决策/未来优化/01-App生命周期钩子.md)。
