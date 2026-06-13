---
tags:
  - ag-core
  - codegen
  - gendb
  - index
  - architecture
---

# GenGoDb 代码生成引擎

> 路径：`tool/cmd/gen-go-db/` | Excel 表结构定义 → YAML → Go Model + DAO + 命名 SQL 的自动化代码生成引擎

## 概述

GenGoDb 是 ag-core 代码生成体系中的**数据库访问层（DAO）生成器**。它从 Excel 模板或 MySQL DDL 解析表结构定义，生成完整的 Go 数据库访问代码（ORM Model、DAO CRUD、条件查询、命名 SQL）。

## 架构分层

```
┌──────────────────────────────────────────────────────────────────┐
│                        gen-go-db CLI                            │
│               cobra 命令调度（main.go）                           │
│     yaml 子命令           db 子命令        sheet 子命令           │
└──────────┬────────────────────┬────────────────────┬────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌──────────────────┐  ┌──────────────────────┐  ┌──────────────┐
│  Excel → YAML    │  │   YAML → Go 代码      │  │ Sheet 拆分   │
│                  │  │                      │  │              │
│  yaml/generator  │  │  model/parser.go     │  │ other/       │
│  excel/parser    │  │  → TableData         │  │ split_excel  │
│  excel/parser_   │  │  model/template.go   │  │              │
│    where         │  │  → _model.go         │  └──────────────┘
│  excel/excel.go  │  │  dao/template.go     │
│  (数据模型)       │  │  → _dao.go           │
│                  │  │  → _constant.go      │
│                  │  │  → _namingsql.go     │
└──────────────────┘  └──────────────────────┘
```

## 文件结构

```
tool/cmd/gen-go-db/
├── main.go                  ← CLI 入口，cobra 子命令注册（yaml/db/sheet）
│
├── excel/                   ← Excel 解析层
│   ├── excel.go             ← 数据模型：ExcelInfo, ColumnInfo, ConstraintInfo
│   ├── parser.go            ← Excel 文件解析器：按区域提取结构信息
│   └── parser_where.go      ← WHERE 条件词法/语法分析器（Lexer + Parser）
│
├── yaml/                    ← YAML 生成层
│   └── generator.go         ← ExcelInfo → YAML 序列化，保持字段顺序
│
├── table/                   ← 共享数据模型
│   └── table.go             ← TableData, ColumnData, QueryData 等渲染模型
│
├── model/                   ← Model 代码生成层
│   ├── parser.go            ← YAML → TableData 解析，GORM tag 生成
│   ├── template.go          ← Model 模板生成（结构体+方法+查询参数）
│   └── generator.go         ← 生成入口 + 索引命中检查（index guard）
│
├── dao/                     ← DAO 代码生成层
│   ├── parser.go            ← YAML 文件遍历，复用 model.ParseYAML
│   ├── generator.go         ← DAO 生成入口，输出 4 类文件
│   └── template.go          ← DAO 模板（CRUD + 命名 SQL + 数据库特化 SQL）
│
├── utils/                   ← 工具函数
│   ├── constant.go          ← CUSTOM_RULE_SUFFIX 等常量
│   └── strings.go           ← ToCamelCase, ParseCommaSeparatedList
│
└── other/                   ← 辅助工具
    └── split_excel.go       ← Excel sheet 拆分工具
```

## 数据流

```
Excel 模板
  │
  ▼
excel/parser.go: ParseExcel()
  │  按区域提取：表名 → 列定义 → 主键 → 索引 → 约束 → 自定义脚本
  │  返回：map[string]*excel.ExcelInfo
  ▼
yaml/generator.go: GenerateYAML()
  │  ExcelInfo → yaml.MapSlice → yaml.Marshal → *.yaml 文件
  ▼
repository/yaml/*.yaml        ← 中间产物
  │
  ▼
model/parser.go: ParseYAML()
  │  YAML → TableData（含类型映射、GORM tag 生成、索引/约束处理）
  ▼
model/generator.go: GenerateModel()
  │  → repository/model/*_model.go
  │  索引安全检查（checkQueryArgsIndexes）
  ▼
dao/generator.go: GenerateDAO()
  ├── → repository/dao/*_dao.go          CRUD 方法
  ├── → repository/dao/*_constant.go     常量定义
  ├── → repository/dao/*_namingsql.go    命名 SQL 定义
  └── → repository/dao/{dbtype}_*.go     数据库特定 SQL
```

## 文档目录

| # | 文档 | 说明 | 面向读者 |
|---|------|------|---------|
| 01 | [Excel 解析架构](01-Excel解析架构.md) | Excel 模板的区域识别、数据模型、自定义脚本解析 | 维护者 |
| 02 | [WHERE 条件解析器](02-WHERE条件解析器.md) | 词法分析器 + 语法分析器设计，递归下降解析 | 维护者 |
| 03 | [表 YAML 定义格式详解](03a-YAML定义格式详解.md) | YAML 中间格式的完整字段说明、where 条件树、动态模板结构 | 维护者 · 业务开发者 |
| 04 | [Model 代码生成引擎](04-Model代码生成引擎.md) | YAML → Go Model 的完整流水线，GORM tag，index guard | 维护者 |
| 05 | [DAO 代码生成引擎](05-DAO代码生成引擎.md) | DAO CRUD + 命名 SQL + 数据库特化代码生成 | 维护者 |
| 06 | [使用指南](06-使用指南.md) | 从 Excel 模板到运行代码的完整操作流程 | 业务开发者 |

## 关键设计

| 设计 | 说明 | 文件 |
|------|------|------|
| **区域解析器** | Excel 按 `表名/列名/主键/约束/索引/方法名字` 标记行切换解析模式 | `excel/parser.go` |
| **条件解析器** | 自实现的 SQL WHERE 词法/语法分析器，支持 AND/OR 嵌套 | `excel/parser_where.go` |
| **MapSlice 序列化** | 使用 `yaml.MapSlice` 而非 `map[string]interface{}` 保证 YAML 字段顺序 | `yaml/generator.go` |
| **模板字符串拼接** | 不使用 Go text/template，用逐行字符串拼接生成代码 | `model/template.go`, `dao/template.go` |
| **index guard** | 生成前检查自定义查询的 WHERE 条件是否命中索引/主键 | `model/generator.go:29-94` |
| **动态 SQL 模板** | 支持在 Excel 中编写完整 SQL 模板，参数自动提取 | `excel/parser.go:processDynamicTemplate` |
