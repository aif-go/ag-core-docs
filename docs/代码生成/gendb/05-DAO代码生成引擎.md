---
tags:
  - ag-core
  - codegen
  - gendb
  - dao
  - template
  - architecture
---

# DAO 代码生成引擎

> 文件：`tool/cmd/gen-go-db/dao/` (`parser.go` + `generator.go` + `template.go`) | YAML 定义 → Go DAO CRUD + 命名 SQL

## 概述

DAO 代码生成引擎从 YAML 定义文件生成完整的数据库访问层代码，包括基础 CRUD（增删改查）、批量操作、命名 SQL 查询以及多数据库类型（MySQL/DB2）特化 SQL。

## 职责链

```
YAML 文件/目录
  │
  ▼
dao/parser.go: YAMLParser()
  │  遍历 YAML 文件 → 复用 model.ParseYAML()
  │  → []*table.TableData
  ▼
dao/generator.go: GenerateDAO()
  │  每张表输出 4 类文件
  │
  ├── generateDaoFile()
  │     → *_dao.go（CRUD 方法）
  ├── generateConstantFile()
  │     → *_constant.go（列名常量、命名 SQL 映射）
  ├── generateNamingSqlFile()
  │     → *_namingsql.go（通用命名 SQL）
  └── generateDBTypeNamingSqlFile()
        → {mysql|db2}_*_namingsql.go（数据库特化 SQL）
```

## 一、文件遍历（dao/parser.go）

```go
// dao/parser.go:13-45
func YAMLParser(yamlPath string) ([]*table.TableData, error)
```

- 输入可以是**单个 `.yaml` 文件**或**目录**（递归遍历）
- 每个 YAML 文件调用 `model.ParseYAML(file, "")` 解析为 `TableData`
- 返回 `[]*table.TableData` 切片

## 二、DAO 生成入口（dao/generator.go）

### GenerateDAOFromYAML

```go
// dao/generator.go:15-88
func GenerateDAOFromYAML(inputFile, outputDir, tableName, moduleName, dbType string) error
```

输出目录结构：

```
{outputDir}/
├── repository/model/       ← Model 文件（调用 model.GenerateModel）
│   └── {table}_model.go
└── repository/dao/         ← DAO 文件
    ├── {table}_dao.go
    ├── {table}_constant.go
    ├── {table}_namingsql.go
    ├── mysql_{table}_namingsql.go
    └── db2_{table}_namingsql.go
```

### 模块名自动发现

```go
// dao/generator.go:91-113
func getModuleName() string
// 从当前目录 go.mod 读取 module 声明
```

### GenerateDAO

```go
// dao/generator.go:116-164
func GenerateDAO(tableData *table.TableData, outputPath, moduleName, dbType string) error
```

- **总是生成**：`_dao.go` + `_constant.go`
- **有条件生成**：`_namingsql.go` + `{dbtype}_namingsql.go`（有自定义查询时）
- **dbType 处理**：空值 → 同时生成 mysql 和 db2；指定值 → 只生成指定类型

## 三、DAO 模板（dao/template.go）

`template.go` 约 1128 行，是 gen-go-db 中最大的模板文件。

### 3.1 CRUD 方法（_dao.go）

默认生成的 DAO 方法：

```go
type TmUserDao struct {
    *agdao.Dao               // 嵌入 agdao.Dao 基础能力
}

func (d *TmUserDao) Get(ctx, entity)          // 主键查询 (bool, error)
func (d *TmUserDao) Insert(ctx, entity)       // 插入
func (d *TmUserDao) Update(ctx, entity)       // 更新
func (d *TmUserDao) Delete(ctx, entity)       // 删除
func (d *TmUserDao) BatchInsert(ctx, entities) // 批量插入
func (d *TmUserDao) BatchUpdate(ctx, entities) // 批量更新
```

**Get 方法实现逻辑**（`template.go`）：

1. 使用 `ListZeroValueCols(false, false, false, true)` 列出非零值列
2. 使用 `conditonwhere.MaskWhereCondition` 构建 WHERE 条件
3. 调用 `agdao.Dao.Get`

**Update 方法实现逻辑**：

1. 使用 `AllowUpdateCols` 限制可更新列
2. 使用主键作为 WHERE 条件
3. 调用 `agdao.Dao.Update`

### 3.2 常量文件（_constant.go）

由 `generateConstantFile()` 生成，包含：

- 列名常量切片
- 可更新列切片
- 索引前导列切片
- 命名 SQL 查询名到 SQL 的映射
- ZeroValueCols 排除空值字段映射

### 3.3 命名 SQL 文件（_namingsql.go）

由 `generateNamingSqlFile()` 生成，每个自定义查询生成：

```go
// 查询参数结构体
type TmUserFindByNameParam struct {
    Name string
}

// 命名 SQL 定义
const TmUserFindByNameNamedSql = `
    SELECT NAME, ADDRESS
    FROM TM_USER
    WHERE NAME = @Name
`
```

### 3.4 数据库特化 SQL（{dbtype}_namingsql.go）

由 `generateDBTypeNamingSqlFile()` 生成，处理数据库间 SQL 语法差异：

| 数据库 | 生成内容 | 差异点 |
|--------|---------|--------|
| MySQL | `mysql_{table}_namingsql.go` | 标准 SQL，分页用 `LIMIT` |
| DB2 | `db2_{table}_namingsql.go` | DB2 方言，分页用 `FETCH FIRST ROWS ONLY` |

### 3.5 SQL 模板生成函数

`dao/template.go` 中的关键辅助函数：

| 函数 | 用途 |
|------|------|
| `generatePrimaryKeyWhere()` | 生成主键查询条件（`PK1 = ? AND PK2 = ?`） |
| `generateSelectSQL()` | 生成 SELECT 语句 |
| `generateInsertSQL()` | 生成 INSERT 语句 |
| `generateUpdateSQL()` | 生成 UPDATE 语句 |
| `generateDeleteSQL()` | 生成 DELETE 语句 |
| `generateNamedSQL()` | 为每个自定义查询生成命名 SQL |
| `generateDBTypeNamedSQL()` | 生成数据库特化命名 SQL |
| `generateZeroValueCheck()` | 生成零值判断表达式 |

### 3.6 零值判断

```go
// template.go:12-35
func generateZeroValueCheck(columns []table.ColumnData) string
```

根据列类型生成不同的零值检查：

| Go 类型 | 零值判断 |
|---------|---------|
| `string` | `entity.Field == ""` |
| `time.Time` | `entity.Field.IsZero()` |
| 数值类型 | `entity.Field == 0` |

## 四、DB 类型扩散

当 `dbType` 参数为空时，`GenerateDAO()` 会遍历 `["MYSQL", "DB2"]` 分别生成 SQL：

```go
// dao/generator.go:148-154
dbTypes := []string{"MYSQL", "DB2"}
for _, dbType := range dbTypes {
    dbTypeFileName := fmt.Sprintf("%s_%s_namingsql.go",
        strings.ToLower(dbType), strings.ToLower(tableData.TableName))
    generateDBTypeNamingSqlFile(tableData, dbTypePath, dbType)
}
```
