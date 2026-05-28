---
tags:
  - ag-core
  - ag-conf
  - config
  - index
---

# AgConf 配置管理模块

> 路径：`ag/ag_conf/`

AgConf 是 ag-core 的配置管理模块，**深度借鉴了 Spring Framework 的配置体系**，提供统一的属性源管理、占位符解析、配置绑定和热更新能力。

## 核心能力

| 功能        | 说明                             |
| --------- | ------------------------------ |
| **多属性源**  | 系统环境变量、命令行参数、本地配置文件、Nacos 远程配置 |
| **占位符解析** | 支持 `${key:default}` 语法，可递归嵌套   |
| **配置绑定**  | 自动将扁平化配置映射到 Go 结构体             |
| **配置解密**  | 支持 `{cipher}` 前缀的加密值自动解密       |
| **热更新**   | 配置变更时自动通知绑定对象，支持 Nacos 配置监听    |

## 文档目录

| 文档                                                    | 说明                                   |
| ----------------------------------------------------- | ------------------------------------ |
| [[01-架构概览\|架构概览]]                                     | 整体架构、类层次、数据流                         |
| [[02-PropertySource-属性源\|PropertySource 属性源]]         | 属性源体系、优先级、集合操作                       |
| [[03-PropertyResolver-属性解析器\|PropertyResolver 属性解析器]] | 属性解析链路、占位符递归解析                       |
| [[04-Environment-环境抽象\|Environment 环境抽象]]             | 环境接口、属性源 + 解析器的组合                    |
| [[05-ConfigLoading-配置加载\|配置加载]]                       | 本地 YAML/JSON/Properties 文件加载         |
| [[06-Bind-配置绑定\|配置绑定]]                                | Struct 反射绑定、`value`/`required` 标签    |
| [[07-ConfigWatch-配置热更新\|配置热更新]]                       | Watcher 机制、变更通知、自动刷新                 |
| [[08-Decrypt-配置解密\|配置解密]]                             | `{cipher}` 前缀加密值自动解密                 |
| [[09-与Spring对比\|与 Spring 对比]]                         | AgConf vs Spring PropertySource 体系对比 |
| [[10-使用指南\|📖 使用指南]]                                  | 面向业务开发者的纯实用教程                        |

## 模块文件

```
ag/ag_conf/
├── api_*.go                    ← 接口定义层
│   ├── api_resolver.go         ─ IPropertyResolver, IEnvironment
│   ├── api_source.go           ─ IPropertySource
│   └── api_sources.go          ─ IPropertySources
│
├── resolver_*.go               ← 解析器实现层
│   ├── resolver_abstract_enviroment.go           ─ AbstractEnvironment
│   ├── resolver_abstract_property_resolver.go    ─ AbstractPropertyResolver
│   ├── resolver_property_sources_property_resolver.go  ─ PropertySourcesPropertyResolver
│   └── resolver_standardEnvironment.go           ─ StandardEnvironment
│
├── source_*.go                 ← 属性源实现层
│   ├── source_property_source.go                 ─ MapPropertySource / PropertiesPropertySource
│   └── sources_mutable_property_sources.go       ─ MutablePropertySources
│
├── property_placeholder_helper.go   ← 占位符解析引擎
├── local.go                         ← 本地配置文件加载
├── bind.go                          ← 配置绑定到结构体
├── decrypt.go                       ← 配置值解密
├── watch.go                         ← Watcher 管理器
├── watcher_refresh.go               ← 配置热刷新
├── consts.go                        ← 常量定义
└── util.go                          ← 工具函数
```

> 📝 建议按顺序阅读 01→09，了解完整设计脉络
