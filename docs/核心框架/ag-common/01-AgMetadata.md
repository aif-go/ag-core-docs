---
tags:
  - ag-core
  - ag-common
  - agmetadata
  - metadata
---

# AgMetadata 上下文元数据

> 子包：`ag/ag_common/agmetadata/` | package `agmetadata`

基于 `context.Context` 的键值对元数据传播系统，用于在微服务调用链中传递上下文信息（如 trace ID、用户信息等）。

---

## 数据结构

```go
// MD 元数据键值对
type MD map[string]string
```

## 创建元数据

```go
// 从 map 创建
md := agmetadata.New(map[string]string{
    "trace_id": "abc123",
    "user_id":  "u_001",
})

// 从键值对列表创建（必须成对出现）
md, err := agmetadata.Pairs("trace_id", "abc123", "user_id", "u_001")
```

## 元数据操作

```go
md := agmetadata.New(map[string]string{})

md.Set("key", "value")   // 设置值（空值不会被设置）
val := md.Get("key")     // 获取值
n := md.Len()            // 条目数
cpy := md.Copy()         // 深拷贝
```

## 上下文传播

```go
// 将元数据写入上下文
ctx := agmetadata.AppendMdToContext(ctx, md)

// 从上下文提取元数据
extracted := agmetadata.GetMdFromContext(ctx)

// 从上下文获取指定 key 的值
val, ok := agmetadata.GetValueFromContext(ctx, "trace_id")

// 遍历上下文中的元数据
agmetadata.HandlerMdFromContext(ctx, func(k, v string) {
    println(k, v)
})
```

## 解析与注册机制

支持通过注册的 key 列表，自动解析上游传入的元数据：

```go
// 注册需要解析的 key
agmetadata.RegMdKey("trace_id")
agmetadata.RegMdKey("x-request-id")

// 获取所有已注册的 key
keys := agmetadata.GetMdKeys()  // ["trace_id", "x-request-id"]

// 使用 ParseFunc 从请求中提取并注入上下文
parseFn := func(key string) ([]string, bool) {
    return []string{req.Header.Get(key)}, true
}
ctx, err := agmetadata.ParseMdToContext(ctx, parseFn)
```

## 设计要点

- 全局 key 注册中心使用 `sync.RWMutex` 保护并发访问
- key 列表缓存通过 `atomic.Value` 实现无锁读取
- `keysCache` 在 key 新增时惰性刷新

## 典型使用场景

```go
// 服务 A：发送请求时携带元数据
md := agmetadata.Pairs("trace_id", generateTraceID())
ctx := agmetadata.AppendMdToContext(ctx, md)

// 服务 B：接收请求时解析元数据
traceID, ok := agmetadata.GetValueFromContext(ctx, "trace_id")
```

## 调用方

| 调用方 | 用途 |
|--------|------|
| 框架各模块 | 在服务之间传递上下文元数据 |
| RPC 中间件 | 从请求中提取元数据注入 Context |
| 日志模块 | 从 Context 中提取 trace ID 等用于日志关联 |
