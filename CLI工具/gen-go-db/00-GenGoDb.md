---
tags:
  - ag-core
  - cli
  - gen-go-db
  - codegen
---

# GenGoDb — DAO 代码生成器

> 路径：`tool/cmd/gen-go-db/` | Excel 或 MySQL DDL → YAML → Go Model + DAO 的自动化代码生成工具

## 概述

`gen-go-db` 是一个从表结构定义自动生成 **Go ORM Model** + **DAO CRUD** 的完整代码生成器。

**输入 → 处理 → 输出：**

```
Excel 模板        YAML 定义         Go 代码
  ┌──────┐       ┌──────┐        ┌────────────┐
  │ Excel │───→  │ YAML │───→    │ repository/ │
  │ 表格  │ 解析  │ 文件  │ 生成   │   model/    │
  └──────┘       └──────┘        │   dao/      │
                                  └────────────┘
```

官方 README：`tool/cmd/gen-go-db/README.md`

## 子命令

`gen-go-db` 通过三个子命令完成代码生成流水线：

| 子命令 | 功能 | 输入 → 输出 |
|-------|------|------------|
| `gen-go-db yaml` | Excel 模板 → YAML 定义文件 | `.xlsx` → `repository/yaml/*.yaml` |
| `gen-go-db db` | YAML 定义文件 → Go 代码 | `*.yaml` → `repository/model/*.go` + `repository/dao/*.go` |
| `gen-go-db sheet` | Excel sheet 拆分工具 | 将自定义脚本拆分为独立的 sheet |

### gen-go-db yaml

解析 Excel 模板，生成 YAML 表结构定义文件。

```bash
# 基本用法
gen-go-db yaml -i ./模型模板.xlsx -o ./output

# 指定表名（只生成指定的表）
gen-go-db yaml -i ./模型模板.xlsx -o ./output -T TM_USER

# 测试模式（生成示例 YAML）
gen-go-db yaml -t
```

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--input` | `-i` | Excel 文件路径 |
| `--output` | `-o` | 输出目录（自动拼接 `repository/yaml/`） |
| `--table` | `-T` | 指定表名（逗号分隔多个表） |
| `--test` | `-t` | 测试模式，生成示例 YAML |

### gen-go-db db

从 YAML 定义文件生成 Go Model 和 DAO 代码。

```bash
# 基本用法
gen-go-db db -i ./repository/yaml -o ./output

# 指定模块名和数据库类型
gen-go-db db -i ./repository/yaml/TM_USER.yaml -o ./output -m mymodule -d mysql

# 指定表名
gen-go-db db -i ./repository/yaml -o ./output -T TM_USER
```

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--input` | `-i` | YAML 文件或目录路径 |
| `--output` | `-o` | 输出目录（自动拼接 `repository/model/` 和 `repository/dao/`） |
| `--table` | `-T` | 指定表名（逗号分隔多个表） |
| `--module` | `-m` | 模块名，默认从 `go.mod` 读取 |
| `--dbtype` | `-d` | 数据库类型：`mysql` / `db2`，不指定时生成两种 |

### gen-go-db sheet

Excel 拆分工具，将一个 sheet 中自定义规则部分拆成独立 sheet。

```bash
gen-go-db sheet -i ./模型模板.xlsx -o ./output -k "自定义脚本名字"
```

## 数据流架构

```
┌──────────────────────────────────────────────────────────────┐
│                     gen-go-db 流水线                          │
│                                                              │
│  Excel 模板                                        Go 代码    │
│  ┌──────────┐          ┌──────────┐     ┌────────────────┐  │
│  │ 表名     │          │ table_name│     │ repository/    │  │
│  │ 列定义   │─parse──→ │ columns  │─gen─→│   model/       │  │
│  │ 主键     │          │ primary..│     │   *_{Model}    │  │
│  │ 索引     │          │ indexes  │     │                │  │
│  │ 约束     │excel/   │ constrai.│     │ repository/    │  │
│  │ 自定义   │parser.go│          │     │   dao/         │  │
│  │ 脚本     │         │ self_que.│     │   *_{DAO}      │  │
│  └──────────┘  yaml/  └──────────┘     │   *_{naming}   │  │
│                gen.    model/          │   *_{constant} │  │
│                        parser.go       └────────────────┘  │
│                         ↓                                   │
│                        model/generator.go                   │
│                        dao/generator.go                     │
│                        dao/template.go                      │
│                        model/template.go                    │
└──────────────────────────────────────────────────────────────┘
```

### 模块职责

| 包 | 文件 | 职责 |
|---|------|------|
| `yaml/` | `generator.go` | Excel → YAML 转换，YAML 序列化输出 |
| `excel/` | `parser.go` | Excel 文件解析，按区域提取列/主键/索引/约束 |
| `excel/` | `parser_where.go` | WHERE 条件词法/语法分析器（Lexer + Parser） |
| `excel/` | `excel.go` | ExcelInfo/ColumnInfo 等数据模型 |
| `table/` | `table.go` | TableData/ColumnData 等渲染数据模型 |
| `model/` | `parser.go` | YAML 解析 → TableData，GORM tag 生成 |
| `model/` | `template.go` | Model 代码生成（结构体+方法+查询参数） |
| `model/` | `generator.go` | Model 生成入口，索引命中检查 |
| `dao/` | `parser.go` | YAML 文件遍历，调用 model.ParseYAML |
| `dao/` | `generator.go` | DAO 生成入口，输出 4 类文件 |
| `dao/` | `template.go` | DAO 模板代码生成（CRUD + 命名 SQL） |

## Excel 模板规范

Excel 模板按区域解析，每个 sheet 对应一张数据库表：

### 表头区

| 列 | 内容 |
|----|------|
| 第 1 行 | `表名` → `TM_USER` |

### 列定义区（标题行：`列名`）

| 列名 | 类型 | 长度 | 必填 | 默认值 | 自增 | 支持更新 | 描述 | Tag |
|------|------|------|------|--------|------|---------|------|-----|
| SEQ | int64 | | Y | | Y | N | 序列号 | |
| NAME | string | 30 | Y | | N | Y | 姓名 | |
| SEX | int | | N | 1 | N | Y | 1-男 2-女 | `///@omitempty` |
| CREATED_TIME | time | | N | | N | N | 创建时间 | `///@create` |
| LAST_MODIFIED_TIME | time | | N | | N | N | 更新时间 | `///@update` |
| JPA_VERSION | int | | Y | | N | N | JPA_VERSION | `///@javaVersion` |

**Tag 特殊标记：**

| Tag | 含义 |
|-----|------|
| `///@create` | 自动创建时间字段，GORM 标签生成 `AUTOCREATETIME` |
| `///@update` | 自动更新时间字段，GORM 标签生成 `AUTOUPDATETIME` |
| `///@javaVersion` | 乐观锁字段 |
| `///@omitempty` | 零值时忽略该字段 |

**类型映射规则（`getGoType()`）：**

| Excel 类型 | Go 类型 |
|-----------|---------|
| `int`, `int32`, `tinyint`, `smallint` | `int` |
| `int64`, `bigint` | `int64` |
| `float`, `float32`, `double`, `float64`, `decimal` | `float64` |
| `string`, `varchar`, `char`, `text` | `string` |
| `bool`, `boolean` | `bool` |
| `time`, `datetime`, `timestamp`, `date` | `time.Time` |

### 主键区（标题行：`主键`）

| 主键列 |
|--------|
| `PRIMARY_KEY` | SEQ | （可选第二主键） |

### 索引区（标题行：`索引`）

| 索引名 | 列 1 | 列 2 |
|--------|------|------|
| INDEX1_TM_USER | NAME | ADDRESS |

### 约束区（标题行：`约束`）

| 约束名 | 列 1 |
|--------|------|
| TM_USER_UNIQUE_1 | PHONE |

### 自定义脚本区（标题行：`方法名字`）

定义在 `sheetName@` 命名的附属 sheet 中。

#### 普通模式（默认）

| 方法名 | 查询字段 | 排序 | 条件 | SQL 参数 | 分页 |
|--------|---------|------|------|---------|------|
| FindByName | NAME,ADDRESS | | NAME = @Name | | Y |
| FindAll | * | SEQ DESC | | | N |

- **查询字段**：逗号分隔，`*` 表示全部字段
- **条件**：支持 AND/OR 嵌套，`@` 前缀表示参数绑定，支持 `IN`/`NOT IN`/`BETWEEN AND`
- **SQL 参数**：可选，不填时自动从条件提取

#### 动态模板模式（首行标记：`动态模版`）

| 方法名 | 查询字段 | SQL 模板 | 参数定义 | 排序 | 分页 |
|--------|---------|---------|---------|------|------|
| QueryByCondition | * | `SELECT * FROM TM_USER WHERE NAME = @Name AND AGE > @Age` | `Name,string,N;Age,int,N` | | Y |

- **SQL 模板**：写完整 SQL，`@ParamName` 为参数占位符
- **参数定义**：格式 `ParamName,Type,IsSlice[,ColName]`，分号分隔
- 未显式定义的参数会自动从列名驼峰匹配类型

## YAML 文件结构

生成示例 `repository/yaml/TM_TEST.yaml`：

```yaml
table_name: TM_TEST
columns:
  - name: SEQ
    type: int64
    not_null: true
    auto_increment: true
    support_update: false
    description: ""
  - name: NAME
    type: string
    length: "20"
    not_null: true
    support_update: true
    description: 卡号
primary_key:
  - SEQ
constraints:
  - name: TM_TEST_UNIUQE_1
    columns:
      - PHONE
indexes:
  - name: INDEX1_TM_TEST
    columns:
      - NAME
      - ADDRESS
self_query_rules:
  FindAllColsByPage:
    select_fields: "*"
    page: true
    where:
      operator: AND
      conditions:
        - expr: "ADDRESS = @Address"
```

## 输出文件结构

对于表 `TM_USER`，执行 `gen-go-db db` 后生成：

```
repository/
├── model/
│   └── tm_user_model.go          ← Model 定义
└── dao/
    ├── tm_user_dao.go             ← DAO CRUD
    ├── tm_user_constant.go        ← 常量（列名、命名 SQL 映射）
    ├── tm_user_namingsql.go       ← 命名 SQL 定义
    ├── mysql_tm_user_namingsql.go ← MySQL 特定命名 SQL
    └── db2_tm_user_namingsql.go   ← DB2 特定命名 SQL
```

### Model 文件（`tm_user_model.go`）

```go
package model

type TmUser struct {
    Seq    int64  `gorm:"column:SEQ;primaryKey;not null" json:"seq"`
    Name   string `gorm:"column:NAME;not null" json:"name"`
    Sex    int    `gorm:"column:SEX;index:INDEX1_TM_USER,priority:1" json:"sex"`
    // ...
}

// 自动生成的方法
func (t *TmUser) TableName() string             // 返回表名
func (t *TmUser) Clone() *TmUser                 // 克隆对象
func (t *TmUser) ToString() string               // 格式化输出
func (t *TmUser) ListZeroValueCols(...)           // 列出零值/非零值列
var TmUserAllowUpdateCols = []string{...}         // 可更新列列表
var TmUserIndexLeadingCols = []string{...}        // 索引前导列

// 自定义查询（如有）
type TmUserFindByNameArg struct { ... }           // 查询参数
func (a *TmUserFindByNameArg) WithName(...)       // 链式 With 方法
func (a *TmUserFindByNameArg) ConvertToMap()      // 转 map
```

### DAO 文件（`tm_user_dao.go`）

```go
package dao

import "gitlab.allinfinance.com/aifgo/ag-core/contribute/agdb/agdao"

type TmUserDao struct {
    *agdao.Dao               // 嵌入基础 DAO
}

func (d *TmUserDao) Get(ctx context.Context, entity *model.TmUser) (bool, error)
func (d *TmUserDao) Insert(ctx context.Context, entity *model.TmUser) error
func (d *TmUserDao) Update(ctx context.Context, entity *model.TmUser) error
func (d *TmUserDao) Delete(ctx context.Context, entity *model.TmUser) error
func (d *TmUserDao) BatchInsert(ctx context.Context, entities []*model.TmUser) error
func (d *TmUserDao) BatchUpdate(ctx context.Context, entities []*model.TmUser) error
```

### 常量文件（`tm_user_constant.go`）

包含列名常量、可更新列、索引前导列、命名 SQL 查询名映射、ZeroValueCols 排除空值字段映射等。

### 命名 SQL 文件

`*_namingsql.go` 和 `*_{dbtype}_namingsql.go` 包含自定义查询的命名 SQL 定义：

```go
var TmUserFindByNameNamedSql = "SELECT NAME, ADDRESS FROM TM_USER WHERE NAME = @Name"
var TmUserFindAllColsByPageNamedSql = "SELECT * FROM TM_USER"
```

## WHERE 条件解析器

`excel/parser_where.go` 实现了一个微型 **SQL WHERE 条件解析器**：

### 词法分析（Lexer）

将条件字符串切分为 token 序列，支持：

| Token | 说明 |
|-------|------|
| `Expr` | 表达式，如 `NAME = @Name` |
| `AND` | 逻辑与 |
| `OR` | 逻辑或 |
| `IN` | IN 操作符 |
| `NOT IN` | NOT IN 操作符 |
| `(` / `)` | 括号分组 |

特殊处理 `BETWEEN AND` 中的 AND 不当作逻辑操作符。

### 语法分析（Parser）

递归下降解析，生成嵌套的 `WhereClause` 树：

```
输入: "NAME = @Name AND (SEX = @Sex OR AGE > @Age)"

解析结果:
WhereClause{Operator: "AND",
  Conditions: [
    Condition{Expr: "NAME = @Name"},
    Condition{Operator: "OR",
      Conditions: [
        Condition{Expr: "SEX = @Sex"},
        Condition{Expr: "AGE > @Age"},
      ]
    }
  ]
}
```

## 索引安全检查（index guard）

`model/generator.go` 中的 `checkQueryArgsIndexes()` 在生成代码前会验证每个自定义查询的 WHERE 条件**至少命中一个索引或主键**：

1. 优先检查是否命中主键
2. 未命中主键时检查索引的**第一列**（引导列）
3. 复合主键必须包含第一个主键列
4. 未命中时返回错误，阻止生成

## 完整使用流程

```bash
# 1. 准备 Excel 模板 → 生成 YAML
gen-go-db yaml -i ./模型模板.xlsx -o ./

# 2. 从 YAML 生成 Model + DAO 代码
gen-go-db db -i ./repository/yaml -o ./
```

生成的代码位于：
- `repository/model/<table>_model.go`
- `repository/dao/<table>_dao.go`
- `repository/dao/<table>_constant.go`
- `repository/dao/<table>_namingsql.go`
- `repository/dao/<dbtype>_<table>_namingsql.go`
