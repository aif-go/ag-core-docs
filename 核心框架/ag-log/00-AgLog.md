---
tags:
  - ag-core
  - ag-log
  - architecture
  - overview
---

# AgLog — 结构化日志框架

> 模块：`ag/ag_log/` | 基于 Go `log/slog` 标准库

## 概述

AgLog 是 ag-core 的结构化日志框架，在 Go 1.21 的 `log/slog` 标准库之上构建了一套**多层次、可组合、可热替换**的日志管道。核心设计思路是**通过 `slog.Handler` 包装链实现关注点分离**，每个层次只负责一件事。

```
应用代码 → slog.Logger → NamedHandler → Middlewares → Fanout/Failover → AsyncHandler → ZapHandler/TextHandler → 文件/控制台
```

## 文件结构

```
ag_log/
├── pkg.go                          # 包声明
├── zfx_aglog.go                    # 顶层 FX Module（合并所有子包）
│
├── agslog/                         # ◀ 核心层
│   ├── agslog.go                   #   全局 TopLogger、Builder 单例
│   ├── slog_common.go              #   类型定义（SlogAttrFromContext, HandlerInitFunc）
│   ├── slog_context.go             #   Context 中 handler 名称传递
│   ├── slog_handler.go             #   NamedHandler + HandlerFactory
│   ├── slog_handler_replaceable.go #   ReplaceableHandler（热替换）
│   ├── slog_wrap_config.go         #   Builder（构造器）~490行
│   ├── agslog_test.go              #   单元测试 + 基准测试
│   └── zfx_agslog.go               #   FX Provide（agslog 模块）
│
├── fanout/                         # ◀ 扇出层
│   ├── slog_fanout.go              #   按名称路由到多个 handler
│   └── zfx_aglog_fanout.go         #   FX Provide
│
├── async/                          # ◀ 异步层
│   ├── ag_async.go                 #   HandlerFactory 构建
│   ├── async_config.go             #   配置定义
│   ├── async_handler.go            #   AsyncHandler 包装
│   ├── async_worker_group.go       #   工作池 + 队列 + 三种满策略
│   ├── async_handler_bench_test.go #   基准测试（关键性能指标）
│   └── zfx_async_log.go            #   FX Provide
│
├── logzap/                         # ◀ Zap 日志后端（legacy）
│   └── zaplog.go                   #   ZlogProperties + NewZapLogP
│
├── slogzap/                        # ◀ slog → Zap 桥接层
│   ├── slog_zap.go                 #   SlogZapProperties + handler 构建
│   └── zfx_slogzap.go              #   FX Provide
│
└── test/                           # ◀ 集成测试
    ├── agslog_test.go
    ├── agslog_fx_test.go
    ├── agslog_fxbyconf_test.go
    ├── agslog_async_fxconf_test.go
    ├── slog_multi_test.go
    ├── slog_zap_test.go
    ├── slog4zap_test.go
    ├── agslog_formatter_test.go
    ├── agslog.yaml                 # 集成测试配置文件
    ├── agslog_async.yaml           # 异步日志配置文件
    └── test.yaml                   # 传统日志配置文件
```

## 架构分层

| 层 | 子包 | 职责 | 依赖 |
|---|------|------|------|
| **应用接口** | `agslog` | 全局 `TopLogger()`、`GetSlogByName()`、Builder 构造 | 无 |
| **Handler 命名** | `agslog` | `NamedHandler`：每个 handler 实例有唯一名称 | 无 |
| **Handler 热替换** | `agslog` | `ReplaceableHandler`：运行时原子替换 handler | 无 |
| **Handler 工厂** | `agslog` | `HandlerFactory`：延迟初始化 + 循环依赖检测 | 无 |
| **中间件管道** | 第三方 | `slogmulti.Pipe`：日志预处理/过滤/增强 | `samber/slog-multi` |
| **扇出路由** | `fanout` | 一条日志同时分发到多个 handler | `slog-multi` |
| **异步处理** | `async` | Worker 池 + 队列 + 三种满策略 | 无 |
| **Zap 桥接** | `slogzap` | 将 Uber Zap 包装为 `slog.Handler` | `samber/slog-zap` |
| **Zap 后端** | `logzap` | Zap 日志引擎 + 轮转归档 | `uber-go/zap`, `lumberjack` |

## 子模块一览

| 文件 | 内容 |
|------|------|
| [[01-核心agslog]] | Builder、NamedHandler、HandlerFactory、ReplaceableHandler |
| [[02-扇出fanout]] | 按名称路由到多个 handler |
| [[03-异步日志async]] | Worker 池、队列、满策略、基准测试 |
| [[04-Zap桥接]] | logzap + slogzap 桥接 |
| [[05-FX集成]] | FX Module 组装与配置绑定 |
| [[06-使用指南]] | **面向业务开发者：快速上手、配置、最佳实践** |

## 设计要点

1. **基于 slog 标准库**：不重复造轮子，在 `slog.Handler` 接口上进行装饰器式的包装链
2. **命名驱动**：每个 handler 实例有唯一名称，通过名称引用和组合
3. **懒加载**：HandlerFactory 按需创建 handler，避免启动时全部初始化
4. **可替换**：ReplaceableHandler 支持运行时无缝切换 handler 实例
5. **组合式**：Fanout（广播）、Middleware（管道处理）、Failover（故障转移）通过 samber/slog-multi 实现
6. **异步隔离**：AsyncHandler 将同步 handler 包装为异步 worker 池，不影响业务 goroutine

## 调用方

| 调用者 | 用途 |
|--------|------|
| 应用业务代码 | 通过 `agslog.GetSlog()` 或 `agslog.TopLogger()` 获取 logger 实例 |
| 框架组件 | 通过 `GetSlogByName("模块名")` 获取模块专属 logger |
| FX 应用初始化 | `FxAglogMode` 自动装配完整日志管道 |

## 配置示例

```yaml
aglog:
  isDefault: false
  topHandler: ["zap1"]          # 顶层 handler 列表（fanout）
  fanout:
    logs:
      f1: ["zap1", "zap2"]      # 复合 handler：同时写入两个 zap
      f3: ["f2"]                 # 嵌套 fanout
  async:
    groups:
      logg1:
        worker: 2
        queue: 1000
        fullStrategy: drop_new
    logs:
      asynclog1:
        group: logg1
        log: zap1               # 异步包装 zap1
  zap:
    logs:
      zap1:
        log_level: debug
        console: true
        stdout: true
      zap2:
        log_level: info
        # log_file_name: "logs/app.log"
        # max_size: 1024
        # max_backups: 30
        # max_age: 7
        # compress: true
```
