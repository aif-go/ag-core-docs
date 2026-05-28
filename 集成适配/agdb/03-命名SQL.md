---
tags:
  - ag-core
  - agdb
  - namingsql
  - architecture
---

# 命名 SQL

> 文件：`gormdb/namingsql_support.go`

命名 SQL 是 agdb 提供的一种**模板化 SQL**支持，类似于 MyBatis 的 `<select>` 配置。核心思路是：将 SQL 中的命名参数 `@ParamName` 替换为 `?`，再通过反射从结构体按字段名提取参数值。

设计在同一个文件中，包含：

| 函数/接口 | 用途 |
|-----------|------|
| `ReplaceNamedParamsWithIn` | 命名参数 → `?` 替换，特殊处理 `IN` |
| `GetParamsByNames` | 反射提取结构体字段值 |
| `RendSql` | Go template 渲染 SQL 模板 |
| `CalcPageStartRecord` | 多数据库兼容的分页偏移计算 |
| `NamingSqlArg` / `NamingSqlPage` | 参数 & 结果约定接口 |

---

## 1. ReplaceNamedParamsWithIn

将 SQL 中的命名参数替换为 `?`，**特别处理 `IN ( @XXX )` 为 `IN ?`**。

```go
// namingsql_support.go:26-57
func ReplaceNamedParamsWithIn(sql string) (replacedSQL string, paramNames []string)
```

**输入输出示例**：

| 输入 | 输出 | paramNames |
|------|------|------------|
| `WHERE id = @Id AND status = @Status` | `WHERE id = ? AND status = ?` | `[Id, Status]` |
| `WHERE status IN ( @StatusSlice )` | `WHERE status IN ?` | `[StatusSlice]` |
| `WHERE status NOT IN ( @Excludes )` | `WHERE status NOT IN ?` | `[Excludes]` |

**正则优化**：
- 预编译 `inRegex`（匹配 `IN ( @XXX )` 和 `NOT IN ( @XXX )`）
- 预编译 `namedParamRegex`（匹配其他 `@XXX`）
- 支持 `not` 关键字保留

> GORM 的 `?` 占位符能自动展开切片参数为 `IN (?, ?, ?)`，因此 `IN ?` 的写法是 GORM 兼容的。

---

## 2. GetParamsByNames — 结构体反射取值

```go
// namingsql_support.go:84-100
func GetParamsByNames(arg interface{}, paramNames []string) ([]interface{}, error)
```

从结构体中按字段名提取对应值，保持与 `paramNames` 相同的顺序：

```go
type QueryArg struct {
    Id     int
    Status string
    Name   string
}

sql, paramNames := ReplaceNamedParamsWithIn("WHERE id = @Id AND name = @Name")
// paramNames = ["Id", "Name"]

params, _ := GetParamsByNames(QueryArg{Id: 1, Name: "foo"}, paramNames)
// params = [1, "foo"]
```

约束：
- `arg` 必须是结构体或结构体指针
- 字段名**大小写敏感**，必须与 `@ParamName` 完全一致
- 字段不存在则返回错误

---

## 3. RendSql — Go template 渲染 SQL

```go
// namingsql_support.go:270-284
func RendSql(tmplStr string, params any) (string, error)
```

基于 `html/template` 渲染 SQL 模板，支持循环、条件等模板语法：

```go
const tmpl = `WHERE id IN ({{range $i, $v := .Ids}}{{if $i}},{{end}}@Ids{{end}}) AND status = @Status`

rawSQL, _ := RendSql(tmpl, map[string]interface{}{
    "Ids": []int{1, 2, 3},
    "Status": 1,
})
// rawSQL = "WHERE id IN (@Ids,@Ids,@Ids) AND status = @Status"
```

然后通过 `ReplaceNamedParamsWithIn` 二次处理：

```
RendSql 输出      → "WHERE id IN (@Ids,@Ids,@Ids) AND status = @Status"
                    │
                    ▼
ReplaceNamedParamsWithIn  → "WHERE id IN (?,?,?) AND status = ?"
                           paramNames = ["Ids", "Ids", "Ids", "Status"]
```

---

## 4. CalcPageStartRecord — 分页偏移量计算

```go
// namingsql_support.go:105-149
func CalcPageStartRecord(pageNum, pageSize, totalCount int64, dbType string) (
    startRecord, endRecord, totalPage int64, canQuery bool, err error,
)
```

**分页差异**：
- **MySQL**：`startRecord = (pageNum - 1) * pageSize`（0-indexed，`LIMIT offset, size`）
- **其他**（含 DB2）：`startRecord = (pageNum - 1) * pageSize + 1`（1-indexed，`BETWEEN start AND end`）

返回值：
- `startRecord`, `endRecord`：起止索引
- `totalPage`：总页数（向上取整）
- `canQuery`：是否可以执行查询
- `err`：参数校验错误

边界处理：
- `pageNum < 1` 或 `pageSize < 1` → 返回错误
- `totalCount == 0` → 无数据，`canQuery = false`
- `startRecord > totalCount` → 超过最后一页，不执行查询
- `endRecord > totalCount` → 截断为 `totalCount`

---

## 5. 接口约定

```go
// namingsql_support.go:246-261
type NamingSqlArg interface {
    ConvertToMap() map[string]interface{}
}

type NamingSqlPage interface {
    SetPageResult(PageResult)
    SetResultList(any)
}

type NameingSqlArgInfo struct {
    SqlName  string
    ReqType  interface{}
    RespType interface{}
}
```

这些接口为代码生成工具（`gen-go-db`）提供了参数/结果的契约，规约了命名 SQL 查询的参数和返回值类型。
