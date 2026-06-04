---
tags:
  - ag-core
  - contribute
  - agnacos
  - nacos
  - architecture
  - overview
---

# AgNacos — Nacos 集成

> 路径：`contribute/agnacos/` | 阿里 Nacos 双向集成：配置中心 + 服务发现与注册

## 概述

AgNacos 在官方 `nacos-sdk-go` 之上提供两层封装，对应 Nacos 的两大核心能力：

```
agnacos/
├── config/          ← 远程配置中心：拉取 DataID → PropertySource → ag_conf 配置链
├── naming/          ← 服务发现与注册：创建 INamingClient → 供 agkitex / aghertz 消费
│
└── common/          ← 共享：SCProperties 配置模型 + Server/Client Config 构建器
```

- **配置中心**（`config/`）：将 Nacos 上的远程配置（yaml/properties/json）拉取为 `NacosPropertySource`，注入到 `ag_conf` 的 PropertySources 链中，支持自动刷新
- **服务发现与注册**（`naming/`）：创建 Nacos Naming Client，供 agkitex / aghertz 的 Resolver 和 Registry 使用

两个子功能共用同一套 `SCProperties` 连接模型，避免重复配置 Nacos 地址、命名空间、认证信息。

## 文件结构

```
agnacos/
├── common/                          ← 共享层
│   ├── serverclient_properties.go   # SCProperties 结构 + BuildServerConfig / BuildClientConfig
│   └── util.go                      # ParseIPPort 解析器
│
├── config/                          ← 配置中心
│   ├── nacos_properties.go          # NacosConfigProperties + DataIDInfo
│   ├── config.go                    # NewNacosConfigClient
│   ├── ag_conf_nacos.go             # EnableNacosRemoteConfig → PropertySource 注入
│   └── nacos_watcher.go             # NacosConfigWatcher 自动刷新
│
├── naming/                          ← 服务发现与注册
│   ├── nacos_properties.go          # NacosNamingProperties
│   └── naming.go                    # NewNacosNamingClient
│
├── testdata/
│   └── nacos_properties_test.go
│
└── zfx_conf_nacos.go                # FX 模块组装
```

## 配置前缀

| 子功能 | 配置前缀 | 示例 |
|--------|---------|------|
| 配置中心 | `nacos.config` | `nacos.config.enable`, `nacos.config.dataids[0].dataid` |
| 服务发现与注册 | `nacos.naming` | `nacos.naming.enable`, `nacos.naming.serveraddr` |

二者共用 Nacos 连接信息（SCProperties），位于各自的 prefix 之下：

```yaml
nacos:
  config:
    enable: true
    serveraddr: 192.168.1.1:8848,192.168.1.2:8848
    namespace: aic-dev
    username: nacos
    password: nacos
    dataids:
      - dataid: app-config.yaml
        group: DEFAULT_GROUP
        type: yaml
        autorefresh: true
      - dataid: db-config.yaml
        group: DEFAULT_GROUP
        type: yaml
        autorefresh: true
  naming:
    enable: true
    serveraddr: 192.168.1.1:8848
    namespace: aic-dev
```

## 子模块一览

| 文档 | 内容 |
|------|------|
| [[01-远程配置中心]] | DataID 加载、PropertySource 注入、配置变更监听 |
| [[02-服务发现与注册]] | NamingClient 创建、消费方一览（agkitex / aghertz） |
| [[03-使用指南]] | 配置、FX 模块注册、验证、FAQ |
