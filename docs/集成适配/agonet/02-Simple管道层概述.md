---
tags:
  - ag-core
  - agonet
  - simple
  - architecture
---

# Simple 管道层概述

> 路径：`simple/` | Simple 是 **agonet 的业务使用层**，解决 TCP 半包/粘包并提供链式 Handler 模型

## 为什么需要 Simple

agonet 核心层的 `EventHandler.OnTraffic(c Conn)` 每次触发时，底层 TCP 数据可能处于任意分割状态：

```
TCP 流: |---frame1--------|---frame2--------|---frame3--...|
                                            ↑
OnTraffic 触发点:     TCP 可能只送来了 frame2 的一半
```

OnTraffic 收到的数据就是 **裸 TCP 字节流**——可能一次触发只收到半帧（半包），也可能多帧挤在一起（粘包），调用者必须自己管理缓冲区、拼接帧、按协议边界拆分。

Simple 解决了这个问题。它通过 **Pipeline + Codec** 在 OnTraffic 之上构建了帧级别的处理模型：

| 问题     | raw agonet           | Simple 管道层                     |
| ------ | -------------------- | ------------------------------ |
| TCP 半包 | 调用者自行拼接              | `LengthFieldDecoder` 等编解码器自动处理 |
| TCP 粘包 | OnTraffic 收到多帧拼接数据   | 解码器逐帧拆分，每个帧触发一次 `HandleRead`   |
| 业务逻辑组织 | 全部写在 OnTraffic 中     | 多个 Handler 各司其职，可组合            |
| 异常处理   | OnClose 统一处理         | `ExceptionHandler` 链式捕获，可按需拦截  |
| 测试     | 需要 Mock 整个 EventLoop | 各 Handler 可独立单元测试              |

**正常业务场景应当使用 Simple**。纯 agonet 核心层是为需要极低层控制的场景保留的。

## 三层扩展架构

simple 包通过三层将 agonet 的扁平事件桥接到可组合的 Handler 链：

```
agonet 核心事件循环
    │
    ▼
第1层: SimpleEventHandler（桥接层）
    │  OnOpen  → 创建 Channel + Pipeline + 注入 Handler
    │  OnTraffic → FireChannelRead → Handler 链处理
    │  OnClose → FireChannelInactive
    │
    ▼
第2层: Pipeline（链式传播层）
    │  双向链表 head ⇄ ctx1 ⇄ ctx2 ⇄ ... ⇄ tail
    │  Inbound: 沿 next 正向传播
    │  Outbound: 沿 prev 反向传播
    │
    ▼
第3层: Handler（业务逻辑层）
       HandleRead / HandleWrite / HandleActive
       HandleInactive / HandleException / HandleEvent
```

## 第1层：SimpleEventHandler 桥接

### 从 EventHandler 到 Pipeline

core 定义了一个 5 方法扁平接口：

```go
// agonet/event_handler.go
type EventHandler interface {
    OnBoot(eng Engine) (action Action)
    OnShutdown(eng Engine)
    OnOpen(c Conn) (out []byte, action Action)
    OnClose(c Conn, err error) (action Action)
    OnTraffic(c Conn) (action Action)
}
```

`SimpleEventHandler` 实现它，将每个事件桥接到 Pipeline：

```go
// simple/simple_event_handler.go
type SimpleEventHandler struct {
    agonet.BuiltinEventEngine
    *eventHandlerOptions  // 持有工厂函数和 channelInitializer
}
```

### OnOpen 桥接

```
EventHandler.OnOpen(conn)
    │
    ▼
SimpleEventHandler.OnOpen(conn)
    1. pipeline = NewPipeline()                    // head ⇄ tail
    2. channel = newChannel(conn, pipeline)
    3. channelInitializer(channel)                 // ← 用户注入 Handler
       pipeline.AddLast(decoder, bizHandler)
    4. pipeline.ServeChannel(channel)
    5. pipeline.FireChannelActive()                // 触发激活事件链
    6. conn.SetContext(channelCtx)                  // Channel 存入 Conn
```

### OnTraffic 桥接

```
EventHandler.OnTraffic(conn)
    │
    ▼
SimpleEventHandler.OnTraffic(conn)
    1. channel = getChannelFromConn(conn)          // 从 context 取 Channel
    2. reader = conn.(Reader)                      // 取双缓冲读取器
    3. pipeline.FireChannelRead(reader)            // 触发读事件链
    4. 未消费数据 → conn.inboundBuffer             // 持久化下次处理
```

> `getChannelFromConn` 是内部函数；业务代码从 Conn 获取 Channel 请用公开 API `simple.ChannelFromConn(conn)`。

### OnClose 桥接

```
EventHandler.OnClose(conn, err)
    │
    ▼
SimpleEventHandler.OnClose(conn, err)
    1. channel = getChannelFromConn(conn)
    2. pipeline.FireChannelInactive(err)           // 触发关闭事件链
    3. channel.Close(err)
```

## 第2层和第3层

Pipeline 的内部结构和 Handler 类型体系在 [03-Pipeline与事件传播](03-Pipeline与事件传播.md) 中详述。

## 创建方式

```go
import (
    "github.com/aif-go/ag-core/contribute/agonet"
    "github.com/aif-go/ag-core/contribute/agonet/simple"
)

handler, _ := simple.NewSimpleEventHandlerWithOptions(
    // 1. 指定 channelInitializer——连接建立时调用
    simple.WithChannelInitializer(func(channel simple.Channel) error {
        // 2. 向 Pipeline 添加 Handler
        channel.Pipeline().AddLast(
            &simple.LengthFieldDecoder{...},   // TCP 拆包
            &MyBizHandler{},                    // 业务逻辑
        )
        return nil
    }),
)

// 3. 传给 agonet Server / Client
server, _ := agonet.NewServer(handler, config)
```

### 与直接使用 core EventHandler 的对比

| 维度 | 直接 core EventHandler | Simple 管道层 |
|------|----------------------|--------------|
| 事件模型 | 5 个扁平方法 | 链式 Handler，6 种事件类型 |
| 数据访问 | 直接操作 `Conn.Reader/Writer` | Pipeline 传播，Codec 解耦 |
| 关注点分离 | 一个结构体处理所有逻辑 | 每个 Handler 只负责一件事 |
| 可组合性 | 硬编码在 OnTraffic 中 | `AddLast(decoder, biz, encoder)` |
| TCP 粘包 | 手动处理 | `LengthFieldDecoder` 内置 |
| 异常处理 | OnClose 统一处理 | `ExceptionHandler` 链式捕获 |

## 常见陷阱

### ❌ 忘记添加编解码器

Simple 层不会自动处理 TCP 半包/粘包。不加解码器，`HandleRead` 收到的 `msg` 是 `agonet.Reader`（原始字节流），需要手动拆帧。

```go
// ✅ 总是先加解码器再加业务 Handler
ch.Pipeline().AddLast(
    simple.NewLengthFieldDecoder(binary.BigEndian, 1024*1024, 0, 4, 0, 4),
    &BizHandler{},
)
```

### ❌ 解码器顺序放反

Pipeline 是双向链表。`AddLast` 添加的顺序 = Inbound 传播顺序。解码器必须在业务 Handler **之前**：
- ✅ `AddLast(decoder, bizHandler)` — bizHandler 收到解码后的帧
- ❌ `AddLast(bizHandler, decoder)` — bizHandler 收到的是 Reader

### ❌ OnOpen 返回 `out []byte` 在 Simple 层无效

`SimpleEventHandler.OnOpen` 接管了实现，始终返回 nil。如果需要在连接建立时发送数据，在 Handler 的 `HandleActive` 中使用 `ctx.Write()`。
