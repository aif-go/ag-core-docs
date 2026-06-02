---
tags:
  - ag-core
  - contribute
  - agdb
  - architecture
  - overview
---

# Agdb — GORM 数据库抽象层

> 路径：`contribute/agdb/` | 基于 GORM v2 的框架级数据库封装

## 概述

Agdb 是 ag-core 的数据库抽象层，在 [GORM v2](https://gorm.io) 之上提供**事务传播**、**Repository 模式**、**命名 SQL**、**动态 WHERE 构建**、**DAO 增强**能力。它不是替代 GORM，而是围绕 GORM 构建的一套框架级基础设施。

```
业务 Service
    │
    ▼
Repository ─────────────► agdb (事务传播 + TxContextAbility)
    │                             │
    │                     conditonwhere (WHERE 条件构建)
    │                             │
    ▼                             ▼
gormdb ─────────────► GORM v2 ──► 数据库 (MySQL / DB2)
    │
    └── agdao (DAO 增强: 运行时表名策略)
```

## 子模块一览

| 文档 | 内容 |
|------|------|
| [[01-事务传播]] | TransactionPropagation、TransactionManager、声明式事务中间件 |
| [[02-gormdb]] | 数据库连接、Repository、日志适配、分页 |
| [[03-命名SQL]] | 命名参数替换、模板 SQL、分页计算 |
| [[04-WHERE条件构建器]] | WhereClauseBuilder 链式 API、FieldMask 动态过滤 |
| [[05-FX集成]] | FX Module 装配与依赖注入 |
|| [[06-使用指南]] | **面向业务开发者：快速上手、配置、最佳实践** |
| [[07-生成DAO使用指南]] | **gen-go-db 生成的 DAO 接口使用详解** |

## 架构分层

| 层 | 包 | 职责 |
|---|------|------|
| **事务传播** | `agdb` | `WithTransaction`、传播行为、Context 绑定、声明式中间件 |
| **GORM 封装** | `gormdb` | Repository + 连接管理 + 日志 + 分页 + 命名 SQL |
| **DAO 增强** | `agdao` | 运行时表名策略、基础 DAO 能力 |
| **条件构建** | `conditonwhere` | 链式 WHERE 构建、FieldMask 动态过滤 |

## 文件结构

```
contribute/agdb/
├── zfx_agdb.go                     # FX 入口 (FxAgDbModule)
├── transaction.go                  # 事务传播行为核心
├── transaction_service_middleware.go # 声明式事务中间件
│
├── gormdb/
│   ├── db.go                       # 数据库连接 (NewDB / NewDB_V2)
│   ├── config.go                   # 连接配置结构体
│   ├── repository.go               # Repository + TransactionManager 实现
│   ├── page.go                     # 分页模型 + OrderBuilder
│   ├── ag_start.go                 # 启动配置绑定
│   ├── gormslog.go                 # slog 日志适配 GORM
│   ├── gormzap.go                  # zap 日志适配 GORM
│   ├── namingsql_support.go        # 命名 SQL 参数替换 + 分页计算
│   └── zfx_aicgormdb.go            # GORM 子模块 FX 注册
│
├── agdao/
│   ├── base_dao.go                 # BaseDao 接口
│   ├── dao_opts.go                 # TbInfoOpt 选项
│   ├── table_info.go               # TableInfo 结构体
│   └── zfx_dao.go                  # FX 注入 (组标签)
│
└── conditonwhere/
    ├── fieldmask.go                # FieldMask + MaskWhereCondition
    ├── build_where.go              # NhWhere 高性能正则过滤
    ├── where_clause_builder.go     # WhereClauseBuilder 链式 API (V2)
    └── where.go / condition.go     # (已废弃)
```

## 关键设计

| 概念 | 说明 |
|------|------|
| **事务传播** | 类似 Spring 的 `REQUIRED` / `SUPPORTS`，通过 context 链式传递事务对象 |
| **Context 绑定** | `TxContextAbility[T]` 泛型结构，事务以 `ctxTxKey{}` 存入 context |
| **声明式事务** | 通过 ag-service 的 tag 机制，在 service 上打 `<tag key="transaction"/>` 即可 |
| **DBOpener 注册** | 驱动可插拔，默认支持 `mysql` + `ibmdb` (DB2) |
| **分页计算** | 自动兼容 MySQL (0-indexed) 和 DB2 (1-indexed) 的物理分页差异 |
| **命名 SQL** | `@ParamName` → `?` 替换 + 结构体反射取值 + Go template 渲染 |
| **WHERE 构建** | 链式 API (`Eq`, `Gt`, `BeginGroup`, `Or`) 或 FieldMask 动态过滤 |
