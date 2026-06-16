---
tags:
  - ag-core
  - index
  - MOC
---

# 📚 ag-core 文档索引

> 企业级 Go 微服务框架 + 代码生成平台
> 源码：`http://github.com/aif-go/ag-core`

---

## 🏗️ [项目概览](01-项目概览.md)

- 项目定位、技术栈、目录结构

## 🧱 [核心框架 — ag/](核心框架/00-核心框架.md)

| 模块                                             | 说明                   |                                  |
| ---------------------------------------------- | -------------------- | -------------------------------- |
| [App 应用启动器](核心框架/ag-app/00-AgApp.md)            | 统一入口、生命周期管理          |                                  |
| [AgConf 配置管理](核心框架/ag-conf/00-AgConf-概览.md)     | 多属性源、占位符解析、绑定、热更新、解密 |                                  |
| [AgServer 服务端抽象](核心框架/ag-server/00-AgServer.md) | Gin/Hertz/Kitex 统一抽象 |                                  |
| [AgService 调用链框架](核心框架/ag-service/00-AgService.md) | Endpoint 中间件 + CallInfo 上下文 (3篇) |                                  |
| [AgCrypto 加密模块](核心框架/ag-crypto/00-AgCrypto.md)  | 加解密工具                |                                  |
| [AgCommon 公共工具](核心框架/ag-common/00-AgCommon.md)  | 通用工具函数               |                                  |
| [AgExt 扩展机制](核心框架/ag-ext/00-AgExt.md)           | 可插拔扩展点               |                                  |

## 🔌 [集成适配 — contribute/](集成适配/00-集成适配.md)

| 模块 | 说明 |
|------|------|
| [agdb (GORM)](集成适配/agdb/00-Agdb.md) | 数据库 ORM 层 |
| [agdao DAO 层](集成适配/agdb/agdao/00-Agdao.md) | 基础 CRUD 抽象 |
| [aghertz (Hertz)](集成适配/aghertz/00-AgHertz.md) | 字节跳动 Hertz 框架适配 ✅ |
| [agkitex (Kitex)](集成适配/agkitex/00-AgKitex.md) | 字节跳动 Kitex RPC 适配 ✅ |
| [agredis (Redis)](集成适配/agredis/00-AgRedis.md) | Redis 客户端封装 ✅ |
| [agsarama (Sarama/Kafka)](集成适配/agsarama/00-Agsarama.md) | Kafka 消息队列 ✅ |
| [agnacos (Nacos)](集成适配/agnacos/00-AgNacos.md) | Nacos 集成 ✅ (2篇) |
| [agonet 网络层](集成适配/agonet/00-Agonet.md) | 网络通信抽象 ✅ (7篇) |

## 🛠️ [CLI 工具 — tool/cmd/](CLI工具/00-CLI工具.md)

| 工具 | 说明 |
|------|------|
| [aggo](CLI工具/aggo/00-Aggo.md) | 主 CLI：proto 生成、protoc 一键调用 |
| [gen-go-db](CLI工具/gen-go-db/00-GenGoDb.md) | Excel → 完整 CRUD + DAO 生成 |
| [protoc 插件族](CLI工具/protoc插件族/00-Protoc插件族.md) | 6 个 protoc 插件 |

## ⚡ [代码生成流程](代码生成/00-代码生成.md)

| 流程                                                | 说明                      |
| ------------------------------------------------- | ----------------------- |
| [Excel → YAML](代码生成/Excel到YAML流程/00-Excel到YAML.md) | 从 Excel 模板解析表结构         |
| [YAML → DAO](代码生成/YAML到DAO代码/00-YAML到DAO.md)       | 生成 Go ORM 模型 + CRUD     |
| [Protobuf 生成](代码生成/Protobuf生成流程/00-Protobuf生成.md)  | proto → API/服务端/客户端代码 ✅ |

## 📐 [演进管理 — 技术评估 / 待办优化 / 变更记录](演进管理/00-概述与流程.md)

框架演进相关的技术评估、待办优化提案、已完成变更归档。

| 维度 | 内容 |
|------|------|
| 🗺️ [演进路线图 (ROADMAP)](演进管理/ROADMAP.md) | 近期/中期/远期优先级排期 |
| 🔭 [待办优化](演进管理/待办优化/App生命周期钩子.md) | 待解决的问题提案 |
| ✅ [变更记录](演进管理/变更记录/Log归档LocalTime.md) | 已实现的变更归档 |

## 🧪 [开发指南](开发指南/00-开发指南.md)

- 环境搭建、如何扩展新模块、最佳实践

---

> 📝 **文档状态：逐步建设中**
> - [x] 项目结构分析
> - [x] 各模块详细文档（ag-conf ✅ ag-log ✅ ag-app ✅ agdb ✅ agdao ✅ ag-ext ✅ ag-common ✅）
> - [x] 代码生成流程图
> - [ ] 架构决策记录

---

📐 **文档组织规范**：参见 [文档组织规范](../文档组织规范.md)
