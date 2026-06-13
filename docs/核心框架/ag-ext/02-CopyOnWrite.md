---
tags:
  - ag-core
  - ag-ext
  - concurrent
  - copy-on-write
---

# 并发安全容器 — CopyOnWrite

> 文件：`ag/ag_ext/copy_on_write.go`

## 概览

提供泛型化的并发安全容器，采用 **Copy-on-Write（写时复制）** 策略，读多写少场景下性能优异。

## 类型一览

| 类型 | 说明 | 底层 |
|------|------|------|
| `AtomicValue[T]` | 泛型原子值封装 | `atomic.Value` |
| `CopyOnWriteMap[K, V]` | 写时复制 Map | `AtomicValue[map[K]V]` + `RWMutex` |
| `CopyOnWriteSlice[T]` | 写时复制 Slice | `AtomicValue[[]T]` + `RWMutex` |

## AtomicValue[T]

Go 1.18+ `atomic.Value` 的泛型封装：

```go
var av AtomicValue[string]
av.Store("hello")
val := av.Load()  // "hello"
```

## CopyOnWriteMap[K, V]

```go
m := CopyOnWriteMap[string, string]{}

m.Put("key", "value")  // 写：复制后替换
v, ok := m.Get("key")  // 读：无锁
all := m.AsMap()       // 读：返回快照
```

**写操作**（Put）：复制整个 map → 修改副本 → 原子替换。读操作不受影响。

## CopyOnWriteSlice[T]

**主要使用者：** `ag_conf.MutablePropertySources` 的属性源列表。

```go
s := NewCopyOnWriteSlice[IPropertySource]()

s.Add(source)              // 追加到末尾
s.AddIndex(0, source)      // 插入到指定位置
s.Value()                  // 读取快照
s.IndexOf(target)          // 查找索引
s.Delete(target)           // 删除指定元素
s.DeleteIndex(0)           // 删除指定索引
s.Set(0, newSource)        // 替换指定索引
s.Len()                    // 长度
```

**边界处理：**
- `AddIndex` 索引 < 0 视为 0，> 长度视为末尾
- `DeleteIndex` 索引越界时静默跳过
- `Set` 索引越界时静默跳过

## 设计要点

- **读多写少优化**：读操作使用 `RLock`，允许多 goroutine 并发
- **写操作用锁**：`Lock` 保证写互斥，复制后 `Store` 原子替换
- **遍历安全**：遍历期间写入不会导致 panic（遍历的是旧快照）
- **泛型约束**：`CopyOnWriteSlice` 要求 `T comparable`
