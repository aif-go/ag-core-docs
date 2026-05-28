---
tags:
  - ag-core
  - contribute
  - agonet
  - network
  - eventloop
  - architecture
  - overview
---

# Agonet — 事件循环网络框架

> 路径：`contribute/agonet/` + `simple/` + `pkg/` | 自研 Netty 风格事件循环网络库

## 概述

A gonet 是 ag-core 自研的高性能网络框架，基于 Gnet 衍生发展而来，采用 **EventLoop + Reactor** 模型，支持 TCP（含 TLS/TLCP）和 Unix Socket。不 支持 UDP（`listener.go` 中 udp 相关代码已被注释）。

它分为三层：

- **核心层**（`agonet` 包）：事件循环引擎 + Server/Client + Conn 接口 + TLS/TLCP
- **Simple 应用层**（`simple` 包）：Netty 风格 Channel–Pipeline–Handler 管道链 + 编解码器
- **基础设施**（`pkg` 包）：弹性环形缓冲区池、字节切片池、Goroutine 池、环形缓冲区、错误定义

```
Application Code (EventHandler / Handler Chain)
    │
Simple Layer ─── Channel ─── Pipeline ─── Handler (双向链表)
    │                              │
    │                  Codec (LengthField, Simple)
    │
Core Layer ─── EventHandler (OnBoot/OnOpen/OnTraffic/OnClose)
    │
Engine ─── EventLoop[0..N] (goroutine + chan any)
    │           │
    │      goroutine.WorkerPool (ants, 256K)
    │
Listener ─── TCP / TLS / TLCP / Unix Socket
```

---

## 内存管理体系

agonet 包含多层的内存复用策略，贯穿整个数据路径：

| 层级 | 技术 | 用途 |
|------|------|------|
| **字节切片池** | `byteslice.Pool` — 32 个 `sync.Pool`（2^0~2^32） | 临时字节切片分配，`Next()`/`Peek()` 用 |
| **ByteBuffer 池** | `valyala/bytebufferpool` | 连接临时入站缓冲区（`conn.buffer`） |
| **环形缓冲区池** | `ringbuffer.Pool` — 自适应大小（P99 校准） | 持久化入站缓冲区（`conn.inboundBuffer`） |
| **Goroutine 池** | `ants.Pool` — 256K 容量，非阻塞 | 数据读取 goroutine、异步任务提交 |
| **弹性环形缓冲区** | `elastic.RingBuffer` — 懒初始化包装 | 自动管理环形缓冲区生命周期 |

详见 [[06-内存管理与对象池]]。

## 文件结构

```
agonet/                          ← 核心层
├── agonet.go                   # Action 类型 + parseProtoAddr
├── typs.go                     # Conn/EventLoop/Reader/Writer 核心接口
├── engine.go                   # Engine + engine（事件循环引擎）
├── event_loop.go               # eventloop（单 goroutine 事件处理循环）
├── connection.go               # conn（双缓冲 + Reader/Writer 实现）
├── server.go                   # Server 接口 + 创建
├── client.go                   # Client 接口 + Dial/Enroll
├── config.go                   # ServerConfig/ClientConfig/OptionsConfig
├── config_tls.go               # SecurityConfig/TLSConfig/TLCPConfig
├── options.go                  # Options/Option + KeepAlive
├── options_tls.go              # TLS/TLCP Option 构建
├── load_balancer.go            # roundRobin / leastConnections
├── listener.go                 # 监听器（TCP/Unix，UDP 注释）
├── event_handler.go            # EventHandler 接口
├── ag_stater.go                # 启动辅助
└── zfx_agonet.go               # FX Module

simple/                          ← 应用层（Netty 管道）
├── apis.go                     # Channel/Pipeline/Handler 接口定义
├── channel.go                  # channel 实现
├── pipeline.go                 # Pipeline（双向链表，head→tail）
├── context.go                  # ChannelHandlerContext（链传播核心）
├── handler.go                  # Handler 接口 + 具体 Handler 类型
├── simple_handler.go           # SimpleHandler 基类
├── simple_event_handler.go     # SimpleEventHandler（EventHandler → Pipeline 桥接）
├── promise.go                  # Promise 异步结果
├── codec.go                    # Codec 接口
├── codec_simple_codec.go       # SimpleCodec
├── codec_length_field_decoder.go     # LengthField 解码器
├── codec_length_field_str_decoder.go # LengthField 字符串解码器
├── codec_length_field_encoder.go     # LengthField 编码器
├── codec_length_field_str_encoder.go # LengthField 字符串编码器
├── short_client.go             # 短连接客户端（Promise 模式）
├── options.go                  # Simple 层选项
├── exception.go                # 异常处理
├── sorter.go                   # 排序辅助
├── handler_idle.go             # Idle Handler
├── client.go                   # Simple 客户端封装
└── zfx_agonet_simple.go        # FX Module

pkg/                             ← 基础设施
├── buffer/ring/                # ring.Buffer（环形缓冲区原始实现）
├── buffer/elastic/             # elastic.RingBuffer（懒初始化包装）
├── pool/ringbuffer/            # ringbuffer.Pool（GC 友好 + 自适应校准）
├── pool/byteslice/             # byteslice.Pool（32 级幂等切片区）
├── pool/goroutline/            # ants goroutine 池
├── math/                       # 数学工具
└── aerrors/                    # 错误定义（ErrEngineShutdown 等）
```

## 子模块一览

| 文档 | 内容 |
|------|------|
| [[01-核心事件循环框架]] | Engine、EventLoop、Conn 双缓冲、Server |
| [[02-Simple管道层概述]] | 为什么需要Simple、三层桥接架构、与raw EventHandler对比 |
| [[03-Pipeline与事件传播]] | 双向链表、handlerContext、6 种事件传播 |
| [[04-客户端]] | 长连接(Simple优先)、短连接(SimpleShortClient)、纯Client作旁注 |
| [[05-安全配置-TLS与TLCP]] | TLS/TLCP 双栈、证书加载 |
| [[07-使用指南]] | 快速开始、配置示例、最佳实践 |
| [[06-内存管理与对象池]] | 字节切片池、环形缓冲区池、goroutine 池 |
