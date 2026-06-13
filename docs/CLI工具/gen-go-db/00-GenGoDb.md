---
tags:
  - ag-core
  - cli
  - gen-go-db
  - gendb
  - index
---

# gen-go-db — DAO 代码生成器

> 路径：`tool/cmd/gen-go-db/` | 从表结构定义自动生成 Go ORM Model + DAO CRUD + 命名 SQL

## 概述

`gen-go-db` 是一个 Go 命令行工具，接收 **Excel 模板**或 **YAML 定义**，输出完整的数据库访问层代码（Model、DAO、命名 SQL）。它是 ag-core 代码生成体系中数据库访问层的核心工具。

## 完整流水线

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────────────┐
│  Excel 模板  │────→│ gen-go-db yaml   │────→│ repository/yaml/*.yaml  │
│  TM_USER    │     │ Excel → YAML     │     │ 中间定义文件              │
│  .xlsx      │     │                  │     │                          │
└─────────────┘     └──────────────────┘     └──────────┬───────────────┘
                                                         │
                                                         ▼
                                              ┌──────────────────┐
                                              │ gen-go-db db     │
                                              │ YAML → Go 代码   │
                                              └──────┬───────────┘
                                                      │
                                    ┌─────────────────┼─────────────────┐
                                    ▼                 ▼                 ▼
                           ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
                           │ Model 文件    │  │ DAO 文件      │  │ 命名 SQL 文件     │
                           │ *_model.go   │  │ *_dao.go     │  │ *_namingsql.go   │
                           │ 结构体+方法   │  │ CRUD 操作    │  │ + {dbtype}_*.go  │
                           └──────────────┘  └──────────────┘  └──────────────────┘
```

## 三个子命令

| 子命令 | 功能 | 输入 → 输出 | 详解文档 |
|-------|------|------------|---------|
| **`gen-go-db yaml`** | Excel 模板 → YAML 定义 | `.xlsx` → `repository/yaml/*.yaml` | [yaml 命令详解](01-yaml命令.md) |
| **`gen-go-db db`** | YAML 定义 → Go 代码 | `*.yaml` → `repository/model/*.go` + `repository/dao/*.go` | [db 命令详解](02-db命令.md) |
| **`gen-go-db sheet`** | Excel sheet 拆分 | `.xlsx` → 拆分后的 `.xlsx` | [sheet 命令详解](03-sheet命令.md) |

## 快速上手

```bash
# 1. Excel → YAML（准备一张 Excel 模板表）
gen-go-db yaml -i ./TM_USER.xlsx -o ./

# 2. 查看生成的 YAML
cat ./repository/yaml/TM_USER.yaml

# 3. YAML → Go 代码
gen-go-db db -i ./repository/yaml/TM_USER.yaml -o ./ -m myproject

# 4. 生成的代码
#    repository/model/tm_user_model.go
#    repository/dao/tm_user_dao.go
#    repository/dao/tm_user_constant.go
#    repository/dao/tm_user_namingsql.go
#    repository/dao/mysql_tm_user_namingsql.go
#    repository/dao/db2_tm_user_namingsql.go
```

## 输出文件总览

```
repository/
├── yaml/                          ← gen-go-db yaml 输出
│   └── {TABLE_NAME}.yaml          ← YAML 中间定义
│
├── model/                         ← gen-go-db db 输出
│   └── {table}_model.go           ← Go ORM 结构体 + 方法 + 查询参数
│
└── dao/                           ← gen-go-db db 输出
    ├── {table}_dao.go             ← DAO CRUD 方法
    ├── {table}_constant.go        ← 常量定义
    ├── {table}_namingsql.go       ← 命名 SQL 定义
    ├── mysql_{table}_namingsql.go ← MySQL 特定 SQL
    └── db2_{table}_namingsql.go   ← DB2 特定 SQL
```

## 设计文档

详见 `代码生成/gendb/` 目录下的设计文档：

| 主题 | 文档 |
|------|------|
| Excel 解析架构 | [Excel 解析架构](../../代码生成/gendb/01-Excel解析架构.md) |
| WHERE 条件解析器 | [WHERE 条件解析器](../../代码生成/gendb/02-WHERE条件解析器.md) |
| YAML 生成器 | [YAML 生成器](../../代码生成/gendb/03-YAML生成器.md) |
| 表 YAML 定义格式 | [YAML 定义格式详解](../../代码生成/gendb/03a-YAML定义格式详解.md) |
| Model 代码生成引擎 | [Model 代码生成引擎](../../代码生成/gendb/04-Model代码生成引擎.md) |
| DAO 代码生成引擎 | [DAO 代码生成引擎](../../代码生成/gendb/05-DAO代码生成引擎.md) |
| 生成产物详解 | [DAO 生成产物详解](../../代码生成/gendb/07-DAO生成产物详解.md) |
| Excel 模板规范 | [Excel 模板规范](../../代码生成/gendb/08-Excel模板规范.md) |
