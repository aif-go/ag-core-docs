---
tags:
  - ag-core
  - ag-ext
  - index
---

# AgExt 扩展工具

> 路径：`ag/ag_ext/`

AgExt 是 ag-core 的扩展工具包，提供框架各模块依赖的通用基础设施——并发安全容器、配置展开、Future 异步模式、IP 工具等。

## 文件结构

```
ag/ag_ext/
├── util.go                    ← 配置展开（GetFlattenedMap）
├── copy_on_write.go           ← 并发安全容器（CopyOnWriteSlice/Map）
│
├── future/                    ← Future 异步模式
│   ├── future_func.go
│   └── future_stuct.go
│
├── ip/                        ← IP 工具
│   ├── ip.go
│   └── ip_range.go
│
└── ...                        ← 更多子包待扩展
```

## 子模块一览

| 子包 | 路径 | 文档 | 说明 | 状态 |
|------|------|------|------|------|
| — | `ag_ext/` | [[01-GetFlattenedMap\|配置展开]] | YAML/JSON 嵌套结构展开为扁平 map | ✅ |
| — | `ag_ext/` | [[02-CopyOnWrite\|并发安全容器]] | 泛型 CopyOnWriteSlice/Map + AtomicValue | ✅ |
| future | `ag_ext/future/` | [[03-Future\|Future 异步模式]] | 基于 ants 协程池的 Future/Promise | ✅ |
| ip | `ag_ext/ip/` | [[04-IP工具\|IP 工具]] | 端口检查、IP 范围匹配、主机探测 | ✅ |

---

## 依赖关系

| 调用方 | 使用 | 用途 |
|--------|------|------|
| ag_conf | `GetFlattenedMap` | 配置文件加载时展开嵌套 YAML |
| ag_conf | `CopyOnWriteSlice[IPropertySource]` | MutablePropertySources 底层列表 |
| 框架各模块 | `ip.GetAvailablePort` | 服务启动时端口检测 |
| 框架各模块 | `future.FutureCall` | 异步任务执行 |

---

## 待扩展

`ag_ext` 可扩展的子包方向：

| 候选子包 | 说明 |
|----------|------|
| `rate` | 限流器 |
| `circuit` | 熔断器 |
| `retry` | 重试机制 |
