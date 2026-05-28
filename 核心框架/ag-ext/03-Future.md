---
tags:
  - ag-core
  - ag-ext
  - future
  - async
---

# Future 异步模式

> 子包：`ag/ag_ext/future/` | package `future`

基于 `ants` 协程池的 Future/Promise 异步模式实现，提供非阻塞任务提交和结果获取。

## API

### FutureCall — 异步回调

```go
func FutureCall(f func() (interface{}, error), callback func(interface{}, error))
```

提交任务到协程池，任务完成后通过回调函数获取结果：

```go
future.FutureCall(func() (interface{}, error) {
    // 耗时操作
    return doHeavyWork()
}, func(result interface{}, err error) {
    if err != nil {
        log.Error("task failed", err)
        return
    }
    log.Info("result:", result)
})
```

### NewFutureFunc — Future 函数风格

```go
func NewFutureFunc(f func() (interface{}, error)) func() (interface{}, error)
```

提交任务后返回一个阻塞函数，调用时等待结果：

```go
future := NewFutureFunc(func() (interface{}, error) {
    return queryDatabase()
})

// 做其他事情...
doOtherWork()

// 需要结果时再阻塞等待
result, err := future()
```

### Future[T] — 泛型 Future

```go
func NewFuture[T any](task func() (T, error)) *Future[T]
func (f *Future[T]) Await(ctx context.Context) (T, error)
```

类型安全的泛型 Future，支持上下文取消：

```go
f := future.NewFuture(func() (string, error) {
    time.Sleep(time.Second)
    return "hello", nil
})

// 带超时的等待
ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
defer cancel()

result, err := f.Await(ctx)
```

## 设计要点

- **协程池**：使用 `ants` 协程池而非原生 goroutine，控制并发数量
- **Panic 保护**：所有 `Future` 自动 recover panic，转为 error 返回
- **对象池**：`Future[T]` 使用 `sync.Pool` 复用，减少 GC
- **一次性消费**：`Await` 使用 `CAS` 确保只消费一次，重复调用返回错误
- **基于 ants**：任务提交依赖 `github.com/panjf2000/ants/v2` 协程池

## 使用场景

- 并行发起多个 RPC 调用
- 异步日志/监控上报
- 批量数据处理
