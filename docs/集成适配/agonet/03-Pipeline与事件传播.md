---
tags:
  - ag-core
  - agonet
  - simple
  - pipeline
  - handler
  - propagation
  - architecture
---

# Pipeline 与事件传播

> 路径：`simple/pipeline.go` + `context.go` + `handler.go` | 双向链表 + 类型路由 + 6 种事件

## Pipeline 数据结构

```go
// pipeline.go:26-31
// import "gitlab.allinfinance.com/aifgo/ag-core/contribute/agonet/simple"

type pipeline struct {
    head    *handlerContext  // 头节点（headHandler）
    tail    *handlerContext  // 尾节点（tailHandler）
    channel Channel
    size    int
}
```

Pipeline 是一个**双向链表**，每个节点是 `handlerContext`：

```
head ⇄ ctx1 ⇄ ctx2 ⇄ ... ⇄ ctxN ⇄ tail
```

初始状态（无业务 Handler 时）：`head ⇄ tail`

---

## handlerContext — 预缓存类型断言

```go
// context.go:14-27
type handlerContext struct {
    pipeline Pipeline
    prev     *handlerContext
    next     *handlerContext
    handler  Handler

    // 预缓存：创建时一次类型断言，传播时直接查字段
    cast2Inbound   InboundHandler
    cast2Outbound  OutboundHandler
    cast2Exception ExceptionHandler
    cast2Active    ActiveHandler
    cast2Inactive  InactiveHandler
    cast2Event     EventHandler
}
```

```go
// context.go:29-45
func newHandlerContext(p Pipeline, handler Handler, prev, next *handlerContext) *handlerContext {
    hc := &handlerContext{pipeline: p, handler: handler, prev: prev, next: next}
    // 一次断言，永久使用
    hc.cast2Inbound,   _ = handler.(InboundHandler)
    hc.cast2Outbound,  _ = handler.(OutboundHandler)
    hc.cast2Exception, _ = handler.(ExceptionHandler)
    hc.cast2Active,    _ = handler.(ActiveHandler)
    hc.cast2Inactive,  _ = handler.(InactiveHandler)
    hc.cast2Event,     _ = handler.(EventHandler)
    return hc
}
```

**为什么预缓存**：避免每次事件传播时对 Handler 做动态类型断言（`handler.(InboundHandler)`），在 Handler 数量多时减少反射开销。

---

## 事件传播机制

所有 FireXxx 方法共享同一个模式：**从当前节点开始遍历链表，找到第一个实现了对应接口的 Handler**。

### FireRead（入站-读）— next 正向

```go
// context.go:131-144
func (hc *handlerContext) FireRead(message any) {
    var next = hc
    for {
        if next = next.nextContext(); nil == next { break }
        if handler := next.cast2Inbound; nil != handler {
            handler.HandleRead(next, message)  // 命中第一个 InboundHandler
            break
        }
    }
}
```

### FireWrite（出站-写）— prev 反向

```go
// context.go:147-160
func (hc *handlerContext) FireWrite(message any) {
    var prev = hc
    for {
        if prev = prev.prevContext(); nil == prev { break }
        if handler := prev.cast2Outbound; nil != handler {
            handler.HandleWrite(prev, message)
            break
        }
    }
}
```

### FireActive（连接激活）— next 正向

```go
// context.go:99-112
func (hc *handlerContext) FireActive() {
    var next = hc
    for {
        if next = next.nextContext(); nil == next { break }
        if handler := next.cast2Active; nil != handler {
            handler.HandleActive(next)
            break
        }
    }
}
```

### FireInactive（连接关闭）— next 正向

```go
// context.go:115-128
func (hc *handlerContext) FireInactive(err error) {
    var next = hc
    for {
        if next = next.nextContext(); nil == next { break }
        if handler := next.cast2Inactive; nil != handler {
            handler.HandleInactive(next, err)
            break
        }
    }
}
```

### FireExceptionCaught（异常捕获）— next 正向

```go
// context.go:163-176
func (hc *handlerContext) FireExceptionCaught(ex error) {
    var next = hc
    for {
        if next = next.nextContext(); nil == next { break }
        if handler := next.cast2Exception; nil != handler {
            handler.HandleException(next, ex)
            break
        }
    }
}
```

### FireEvent（自定义事件）— next 正向

```go
// context.go:179-193
func (hc *handlerContext) FireEvent(event any) {
    var next = hc
    for {
        if next = next.nextContext(); nil == next { break }
        if handler := next.cast2Event; nil != handler {
            handler.HandleEvent(next, event)
            break
        }
    }
}
```

### 事件传播方向总结

| 事件 | Fire 方法 | 方向 | 查找字段 | Handler 方法 |
|------|-----------|------|---------|-------------|
| 读 | `FireRead` | next (正向) | `cast2Inbound` | `HandleRead(ctx, msg)` |
| 写 | `FireWrite` | prev (反向) | `cast2Outbound` | `HandleWrite(ctx, msg)` |
| 激活 | `FireActive` | next (正向) | `cast2Active` | `HandleActive(ctx)` |
| 关闭 | `FireInactive` | next (正向) | `cast2Inactive` | `HandleInactive(ctx, err)` |
| 异常 | `FireExceptionCaught` | next (正向) | `cast2Exception` | `HandleException(ctx, ex)` |
| 事件 | `FireEvent` | next (正向) | `cast2Event` | `HandleEvent(ctx, event)` |

### Handler 手动传播

Handler 通过收到的 context 手动调用 FireXxx 来继续传播。这是**链式处理的核心**：

```go
// 解码器处理完后继续传播
func (h *DecoderHandler) HandleRead(ctx InboundContext, msg any) {
    decoded := decode(msg)
    ctx.FireRead(decoded)  // → 下一个 InboundHandler
}

// 编码器处理完后继续传播
func (h *EncoderHandler) HandleWrite(ctx OutboundContext, msg any) {
    encoded := encode(msg)
    ctx.FireWrite(encoded) // → 上一个 OutboundHandler
}
```

如果 Handler **不调用** FireXxx，传播就在此终止（拦截模式）。

---

## Handler 类型体系

### 分层 context 接口

```go
// apis.go:112-158
HandlerContext (base)
  ├── Channel() Channel
  ├── Handler() Handler
  ├── Write(message any)     // 写出站（从当前位置向前找 OutboundHandler）
  └── Trigger(event any)     // 触发自定义事件

ActiveContext     → FireActive()
InactiveContext   → FireInactive(err)
InboundContext    → FireRead(msg)
OutboundContext   → FireWrite(msg)
ExceptionContext  → FireExceptionCaught(err)
EventContext      → FireEvent(event)
```

`handlerContext` 结构体实现了全部 6 个 context 接口。

### Handler 接口类型

```go
// apis.go:53-110
Handler                       // 空接口——标记所有 Handler

ActiveHandler     → HandleActive(ctx ActiveContext)
InactiveHandler   → HandleInactive(ctx InactiveContext, ex error)
InboundHandler    → HandleRead(ctx InboundContext, message any)
OutboundHandler   → HandleWrite(ctx OutboundContext, message any)
ExceptionHandler  → HandleException(ctx ExceptionContext, ex error)
EventHandler      → HandleEvent(ctx EventContext, event any)

// 复合类型
DuplexHandler  → InboundHandler + OutboundHandler
CodecHandler   → DuplexHandler + Name()
DecoderHandler → InboundHandler + Name()
EncoderHandler → OutboundHandler + Name()
```

### 函数式 Handler

```go
// handler.go:14-20
type ActiveHandlerFunc   func(ctx ActiveContext)
type InactiveHandlerFunc func(ctx InactiveContext, ex error)
type EventHandlerFunc    func(ctx EventContext, event any)
type ExceptionHandlerFunc func(ctx ExceptionContext, ex error)
```

用于简单场景，不必定义结构体：

```go
pipeline.AddLast(ActiveHandlerFunc(func(ctx ActiveContext) {
    slog.Info("连接建立", "remote", ctx.Channel().RemoteAddr())
}))
```

---

## headHandler — 出站终端

```go
// handler.go:23-32
func (headHandler) HandleWrite(ctx OutboundContext, message any) {
    ch := ctx.Channel()
    switch m := message.(type) {
    case []byte:
        ch.Write1(m)  // → channel.Write1 → conn.Write → TCP 发送
    }
}
```

**head 是 Outbound 事件的终点**。当 Write 沿 prev 反向查找 OutboundHandler 传播到 head 时，它将 `[]byte` 写入底层连接。非 `[]byte` 类型会 panic —— 确保出站数据最终被编码为字节。

## tailHandler — 异常兜底

```go
// handler.go:34-40
func (tailHandler) HandleException(ctx ExceptionContext, ex error) {
    slog.Error("exception", "err", ex)
    ctx.Channel().Close(ex)
}
```

**tail 是 Exception 事件的终点**。如果没有业务 `ExceptionHandler` 捕获异常，传播最终到达 tail，它会关闭连接。其他事件传播到 tail 时为空操作（FireActive/Read/Inactive 到 tail 就结束）。

---

## Pipeline 操作

```go
// 末尾追加
pipeline.AddLast(handler1, handler2)

// 头部插入
pipeline.AddFirst(handler1)

// 添加时的类型校验
// checkHandler 确保 handler 至少实现一种 Handler 接口:
// InboundHandler / OutboundHandler / ActiveHandler /
// InactiveHandler / ExceptionHandler / EventHandler
// 否则 panic
```

---

## 完整传播示例

```
连接建立:
    FireActive
    → head → 找 cast2Active → LoggingActiveHandler
      → HandleActive → ctx.FireActive() (继续传播)
        → tail → 没有 ActiveHandler → 结束

数据到达:
    FireRead(reader)
    → head → 找 cast2Inbound → LengthFieldDecoder
      → HandleRead → 解码 → ctx.FireRead(frame)
        → 找下一个 cast2Inbound → BizHandler
          → HandleRead → 处理 → ctx.Write(response)
            → Write → 找 prev.cast2Outbound → Encoder
              → HandleWrite → 编码 → ctx.FireWrite(encoded)
                → 找上一个 cast2Outbound → headHandler
                  → HandleWrite → ch.Write1(data) → TCP

异常:
    FireExceptionCaught(err)
    → head → 找 cast2Exception → RecoveryHandler
      → HandleException → 处理 → 不继续传播
    （如果没有 ExceptionHandler → tail 关闭连接）

连接关闭:
    FireInactive(err)
    → head → 找 cast2Inactive → CleanupHandler
      → HandleInactive → ctx.FireInactive(err)
        → tail → 没有 InactiveHandler → 结束
```

---

## 常见陷阱

### ❌ 不要调用 `ctx.Next()` 或 `ctx.ChannelHandlerContext`

这些是旧版 API，**当前版本不存在**。正确传播方式：
- Inbound 继续传播：`ctx.FireRead(message)`
- Outbound 继续传播：`ctx.FireWrite(message)`
- Handler 方法**无返回值**

```go
// ❌ 旧版写法（已废弃）
func (h *Handler) ChannelRead(ctx simple.ChannelHandlerContext, msg any) error {
    return ctx.Next()
}

// ✅ 当前 API
func (h *Handler) HandleRead(ctx simple.InboundContext, msg any) {
    ctx.FireRead(msg) // 传播到下一个 InboundHandler
}
```

### ❌ headHandler 只接受 `[]byte`

`headHandler.HandleWrite` 对非 `[]byte` 类型会 **panic**。确保出站编码器输出 `[]byte`：

```go
// ❌ 不经过编码器直接 Write
ctx.Write(someStruct)  // → headHandler → panic: unsupported type

// ✅ 经过编码器转成 []byte
ctx.FireWrite(encode(someStruct))  // → Encoder → headHandler → Write1([]byte)
```

### ❌ tailHandler 会关闭连接

如果 Pipeline 中没有任何 `ExceptionHandler` 捕获异常，`FireExceptionCaught` 最终到达 `tailHandler`，它会**直接关闭连接**。建议在业务 Handler 链末尾添加 Recovery Handler。
