---
tags:
  - ag-core
  - contribute
  - agkitex
  - kitex
  - architecture
  - overview
---

# AgKitex — Kitex RPC 框架适配

> 路径：`contribute/agkitex/` | 基于字节跳动 CloudWeGo [Kitex](https://github.com/cloudwego/kitex) RPC 框架的框架级封装

## 概述

AgKitex 是 ag-core 对 Kitex RPC 框架的适配层，提供**服务端**和**客户端**两套封装，集成 Nacos 服务注册与发现、自定义 Resolver（兼容 Spring gRPC 注册协议）、HTTP2 元数据透传、优先级中间件排序等能力，通过 FX 模块装配接入 ag-app 生命周期。

```
Protobuf 定义的 RPC Service
    │
    ├── Server ──── AgKitexServer ──── ag_server.Server
    │                   │
    │            KitexServerSuiteBuilder
    │          (配置 + 中间件 + 注册器)
    │                   │
    │            server.Server (Kitex)
    │                   │
    │              Nacos Registry
    │
    └── Client ──── KitexSuiteBuilder
                        │
                  client.Suite (Kitex)
                        │
                  AgNacosResolver (Spring gRPC 兼容)
```

## 子模块一览

| 文档 | 内容 |
|------|------|
| [01-服务端](01-服务端.md) | AgKitexServer、KitexServerSuiteBuilder、优先级中间件 |
| [02-客户端](02-客户端.md) | KitexSuiteBuilder、双模式 Resolver |
| [03-服务注册与发现](03-服务注册与发现.md) | Nacos Registry + AgNacosResolver（Spring gRPC 兼容） |
| [04-元数据透传](04-元数据透传.md) | HTTP2 StreamingMetaHandler |
| [05-FX集成](05-FX集成.md) | FX Module 装配与依赖注入 |
| [06-使用指南](06-使用指南.md) | **面向业务开发者：快速上手、配置、最佳实践** |
| [07-流式传输](07-流式传输.md) | protobuf stream 方法实现、客户端调用、配置与限制 |

## 架构分层

| 层 | 包 | 职责 |
|---|------|------|
| **Server 封装** | `server/` | KitexServerSuiteBuilder、AgKitexServer、服务注册 |
| **Server 中间件** | `server/` | 优先级中间件排序（Highest→Lowest） |
| **服务注册** | `server/registry/` | Nacos Registry |
| **Client 封装** | `client/` | KitexSuiteBuilder、双模式 Resolver |
| **Client 中间件** | `client/` | 优先级中间件排序 |
| **自定义 Resolver** | `client/` | AgNacosResolver（Spring gRPC 兼容） |
| **元数据透传** | `metadata/` | HTTP2 StreamingMetaHandler 双向透传 |

## 文件结构

```
contribute/agkitex/
├── server/
│   ├── server.go                  # KitexServerSuiteBuilder + AgKitexServer
│   ├── config.go                  # KitexServerProperties
│   ├── middleware.go              # PrioritizedServerMiddleware
│   ├── service_registry.go        # AgKitexServiceRegistry + Holder
│   ├── zfx_kitex_server.go        # FX Module
│   └── registry/
│       ├── zfx_registy.go         # FX 聚合
│       └── nacos/
│           ├── registry.go        # Nacos Registry
│           └── zfx_nacos.go       # FX Module
│
├── client/
│   ├── client.go                  # KitexSuiteBuilder
│   ├── config.go                  # KitexClientConfig
│   ├── middleware.go              # PrioritizedClientMiddleware
│   ├── resolver.go                # BuildKitexResolver（双模式）
│   ├── ag_nacos_resolver.go       # AgNacosResolver（Spring gRPC 兼容）
│   └── zfx_kitex_client.go        # FX Module
│
└── metadata/
    └── http2.go                   # StreamingMetaHandler 双向透传
```

## 关键设计

| 概念 | 说明 |
|------|------|
| **Suite 模式** | 使用 Kitex 原生 `server.WithSuite` / `client.WithSuite` 聚合所有选项 |
| **SuiteBuilder** | `KitexServerSuiteBuilder` / `KitexSuiteBuilder` 统一组装配置、中间件、注册器 |
| **服务注册 Holder** | `AgKitexServiceRegistryHolder` 聚合多个 `AgKitexServiceRegistry`，统一注册 |
| **AgNacosResolver** | 自定义 Resolver，解析 Spring gRPC 注册的 `gRPC_port` metadata |
| **双模式 Resolver** | 客户端支持 `agnacos`（自定义）和 `nacos`（官方）两种解析器 |
| **优先级中间件** | 服务端 + 客户端均支持 `PrioritizedMiddleware` 排序 |
| **HTTP2 元数据透传** | 通过 Kitex `StreamingMetaHandler` 实现 context → HTTP2 header 双向透传 |
