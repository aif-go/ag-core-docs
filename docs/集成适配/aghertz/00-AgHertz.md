---
tags:
  - ag-core
  - contribute
  - aghertz
  - hertz
  - architecture
  - overview
---

# AgHertz — Hertz HTTP 框架适配

> 路径：`contribute/aghertz/` | 基于字节跳动 CloudWeGo [Hertz](https://github.com/cloudwego/hertz) 的框架级 HTTP 封装

## 概述

AgHertz 是 ag-core 对 Hertz HTTP 框架的适配层，提供**服务端**和**客户端**两套封装，集成 Nacos 服务注册与发现、元数据透传、序列化器扩展、基于优先级的中间件排序等能力，通过 FX 模块装配接入 ag-app 生命周期。

```
业务 Service / Protobuf 生成的代码
    │
    ├── Server ──── AgHertzServer ──── ag_server.Server
    │                   │
    │             ServerConfigurator
    │             (路由 + 中间件 + 选项)
    │                   │
    │             *server.Hertz
    │                   │
    │              Nacos Registry
    │
    └── Client ──── HertzBaseClient
                        │
                  *client.Client
                   ( + 优先中间件 )
                        │
                   Nacos Resolver
```

## 子模块一览

| 文档 | 内容 |
|------|------|
| [01-服务端](01-服务端.md) | AgHertzServer、ConfigSuite、ServerOption、路由、中间件 |
| [02-客户端](02-客户端.md) | HertzClient、ClientSuite、优先级中间件、选项构建 |
| [03-服务注册与发现](03-服务注册与发现.md) | Nacos 服务注册 + 服务发现 |
| [04-基础客户端与序列化](04-基础客户端与序列化.md) | HertzBaseClient、Serializer、DoRequest |
| [05-FX集成](05-FX集成.md) | FX Module 装配与依赖注入 |
| [06-使用指南](06-使用指南.md) | **面向业务开发者：快速上手、配置、最佳实践** |

## 架构分层

| 层 | 包 | 职责 |
|---|------|------|
| **Server 封装** | `server/` | AgHertzServer、Hertz 创建、配置构建、路由注册 |
| **Server Option 体系** | `server/` | ConfigSuite（原生 Option）、ServerOption（增强能力） |
| **Server 配置器** | `server/` | ServerConfigurator（路由+中间件+选项聚合初始化） |
| **服务注册** | `server/registry/` | Nacos Registry |
| **Client 封装** | `client/` | HertzClient 创建、ClientSuite、中间件排序 |
| **服务发现** | `client/discovery/` | Nacos Resolver |
| **基础客户端** | `aghertzclient/` | HertzBaseClient、序列化器、DoRequest |
| **元数据透传** | `metadata/` | 服务端/客户端 agmetadata 头信息中间件 |

## 文件结构

```
contribute/aghertz/
├── server/
│   ├── hertz.go                     # NewHertzServer + 配置构建
│   ├── ag_server.go                 # AgHertzServer（ag_server.Server 实现）
│   ├── config.go                    # HertzServerProperties + 配置绑定
│   ├── config_options_def.go        # ConfigSuite / SimpleSuite
│   ├── server_options.go            # ServerOption / ServerSuite
│   ├── server_options_suites.go     # WithPprof / WithH2C
│   ├── server_manager.go            # ServerConfigurator
│   ├── route.go                     # Route 定义
│   ├── consts/consts.go             # 常量
│   ├── zfx_server_hertz.go          # FX Module
│   └── registry/
│       ├── zfx_registy.go           # FX 聚合
│       └── nacos/
│           ├── registy.go           # Nacos Registry
│           └── zfx_nacos.go         # FX Module
│
├── client/
│   ├── client.go                    # NewHertzClient
│   ├── config.go                    # HertzClientProperties
│   ├── options.go                   # ClientSuite
│   ├── middleware.go                # 优先级中间件排序
│   ├── zfx_client_hertz.go          # FX Module
│   └── discovery/
│       ├── discovery.go             # 占位
│       ├── zfx_discovery.go         # FX 聚合
│       └── nacos/
│           ├── discovery_nacos.go   # Nacos Resolver
│           └── zfx_nacos.go         # FX Module
│
├── aghertzclient/
│   ├── aghertz_base_client.go       # HertzBaseClient
│   └── serializer.go                # Serializer 接口 + JSON/Protobuf
│
└── metadata/
    └── aghertz_metadata.go          # 元数据透传中间件
```

## 关键设计

| 概念 | 说明 |
|------|------|
| **双 Option 体系** | `ConfigSuite`（Hertz 原生 `config.Option` 聚合） + `ServerSuite`（增强能力如 pprof/H2C） |
| **ServerConfigurator** | 聚合路由、中间件、选项，统一初始化 Hertz 服务 |
| **ag_server.Server 接口** | AgHertzServer 实现 Start/Stop，通过 `group:"ag_servers"` 被 ag-app 自动发现 |
| **优先级中间件** | `PrioritizedClientMiddleware` 带排序的客户端中间件，保证执行顺序 |
| **序列化器扩展** | 可注册自定义 `Serializer`，内置 JSON（sonic）和 Protobuf |
| **元数据透传** | 服务端解析 Header → context，客户端将 context → Header，实现 RPC 链路透传 |
