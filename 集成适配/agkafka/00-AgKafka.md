---
tags:
  - ag-core
  - contribute
  - agkafka
  - agsarama
  - kafka
  - architecture
  - overview
---

# AgKafka — Kafka 消息队列

> 路径：`contribute/agsarama/` | 基于 [IBM Sarama](https://github.com/IBM/sarama) 的 Kafka 客户端封装

## 概述

AgKafka（包名 `agsarama`）是 ag-core 对 Kafka 消息队列的**配置封装层**，基于 Sarama 库。核心职责是提供一套**YAML友好的配置结构体**，将 Sarama 庞大的配置体系通过 `Config` 结构体暴露，并自动转换为 `sarama.Config`。

```
YAML 配置
    │
    ▼
agsarama.Config ──► ToSaramaConfig()
    │                       │
    ├── Admin               ├── sarama.Config.Admin
    ├── Net (SASL)          ├── sarama.Config.Net
    ├── Metadata            ├── sarama.Config.Metadata
    ├── Producer            ├── sarama.Config.Producer
    └── Consumer            └── sarama.Config.Consumer
    │
    ▼
sarama.Client ──► 生产者 / 消费者 / Admin 客户端
```

## 文件列表

| 文件 | 职责 |
|------|------|
| `config.go` | Config 结构体 + 类型枚举 + ToSaramaConfig 转换 + 默认值 |
| `config_options.go` | ConfigOption + ExtendSaramaConfigWithOptions |
| `ag_starter.go` | 入口函数：NewAgsaramaConfig / NewClientWithAgConfig |
| `zfx_agsarama.go` | FX Module |

## 设计要点

| 概念 | 说明 |
|------|------|
| **单位统一** | 所有时间字段单位统一为**毫秒**（ms），便于 YAML 配置 |
| **枚举映射** | `RequiredAcks`、`CompressionCodec`、`SASLMechanism`、`IsolationLevel`、`PartitionerType` 等字符串枚举 → Sarama 枚举转换 |
| **配置前缀** | `agsarama` |
| **ConfigOption** | 提供 `fx.ResultTags("group:\"agsarama\"")` 扩展 sarama.Config |
| **封装层次** | 仅为配置层封装，不提供高级的生产者/消费者抽象 |

## 子模块一览

| 文档 | 内容 |
|------|------|
| [[01-配置]] | Config 结构体、类型枚举、ToSaramaConfig 转换 |
| [[02-FX集成]] | FX Module 装配 |
| [[03-使用指南]] | **面向业务开发者：快速上手、配置、生产者/消费者、Consumer 生命周期集成、Multi-Handler 路由（routes 映射 + 集中校验）、最佳实践** |
