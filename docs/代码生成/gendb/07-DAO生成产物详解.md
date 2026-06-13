---
tags:
  - ag-core
  - codegen
  - gendb
  - dao
  - model
  - reference
---

# DAO 生成产物详解

> 从 YAML 定义 `gen-go-db db` 实际生成了哪些代码？本文逐文件拆解生成的 Go 代码结构。

对于表 `STUDENT`，执行 `gen-go-db db -i ./yaml/STUDENT.yaml -o ../ -m agaidevdemo/internal` 后生成 6 个文件：

```
repository/
├── model/
│   └── student_model.go              ← Model 定义（~231 行）
└── dao/
    ├── student_dao.go                ← DAO CRUD + 命名 SQL 执行（~452 行）
    ├── student_constant.go           ← 命名 SQL 信息注册
    ├── student_namingsql.go          ← 命名 SQL 初始化入口
    ├── mysql_student_namingsql.go    ← MySQL 特定 SQL
    └── db2_student_namingsql.go      ← DB2 特定 SQL
```

---

## 1. Model 文件（`{table}_model.go`）

### 主结构体

```go
package model

type Student struct {
    Id      int64     `gorm:"column:ID;primaryKey;not null" json:"id"`
    Stuno   int64     `gorm:"column:STUNO;index:STUNO_UNIUQE_1,priority:1" json:"stuno"`
    Name    string    `gorm:"column:NAME" json:"name"`
    Age     int       `gorm:"column:AGE;index:INDEX_AGE,priority:1" json:"age"`
    Version int64     `gorm:"column:VERSION" json:"version"`
    Fct     time.Time `gorm:"column:FCT" json:"fct"`        // tag: ///@create
    Lct     time.Time `gorm:"column:LCT" json:"lct"`        // tag: ///@update
}
```

### 自动生成的成员

| 生成项 | 说明 |
|--------|------|
| `{Struct}PrimaryKey` | 单主键类型别名（如 `type StudentPrimaryKey int64`）或多主键结构体 |
| `TableName()` | 返回数据库表名 |
| `Clone()` | 深拷贝，逐字段复制 |
| `ToString()` | 格式化输出 |
| `ListZeroValueCols(filterPrimary, filterIndex, filterIsZero, filterSpecial)` | **按列类别分层检查零值**：主键列、索引列、特殊列（jpaVersion/createTime/lastUpdateTime）、普通列 |
| `{Struct}AllowUpdateCols` | 支持更新的列名列表变量 |
| `{Struct}IndexLeadingCols` | 索引前导列列表（用于运行时检查是否走了索引） |

### JSON tag 说明

生成代码中字段名使用**大驼峰**（如 `Id`、`Stuno`），JSON tag 默认与字段名相同。如需小驼峰或 snake_case，需人工调整。

### Tag 标记效果

| YAML tag | 生成效果 |
|----------|---------|
| `///@create` | GORM 标签中 **无特殊标记**（Fct 字段仅有 `column:FCT`，无 `AUTOCREATETIME`） |
| `///@update` | 同上，Lct 字段无 `AUTOUPDATETIME` |
| `///@omitempty` | **被完全忽略** |

> `///@create` 和 `///@update` 在 GORM 标签中不产生 `AUTOCREATETIME`/`AUTOUPDATETIME`——这些标记仅影响 `ListZeroValueCols` 中的 `filterSpecial` 逻辑。当前版本生成的代码中，这些标记在 GORM 层面**没有实际效果**，仅作为元信息保留。

### 自定义查询相关类型

每个 `self_query_rules` 条目生成以下类型：

#### ① 查询参数结构体（`{QueryName}Arg`）

```go
// 无分页
type StudentFindByAgeArg struct {
    FieldMask *conditonwhere.FieldMask
    Age   int     // 从 @Age 推导类型
    Stuno int64   // 从 @Stuno 推导类型
}

// 有分页
type StudentFindByAgeWithPageArg struct {
    db.Page                        // 嵌入分页参数
    FieldMask *conditonwhere.FieldMask
    Age   int
}
```

#### ② 链式 With 方法

```go
func (a *StudentFindByAgeArg) WithAge(Age int) *StudentFindByAgeArg {
    a.Age = Age
    a.FieldMask.Set("Age")       // 标记字段已被设置
    return a
}
func (a *StudentFindByAgeArg) WithStuno(Stuno int64) *StudentFindByAgeArg {
    a.Stuno = Stuno
    a.FieldMask.Set("Stuno")     // 标记字段已被设置
    return a
}
```

#### ③ ConvertToMap

```go
func (a *StudentFindByAgeArg) ConvertToMap() map[string]interface{} {
    return map[string]interface{}{
        "Age":   a.Age,
        "Stuno": a.Stuno,
    }
}
```

#### ④ 查询结果结构体（仅 `select_fields` 非 `*` 时）

```go
type StudentFindByAgeRes struct {
    Id    int64  `gorm:"column:ID" json:"id"`
    Stuno int64  `gorm:"column:STUNO" json:"stuno"`
    Name  string `gorm:"column:NAME" json:"name"`
    Age   int    `gorm:"column:AGE" json:"age"`
}
```

#### ⑤ 分页结果结构体（`page: true` 时）

```go
type StudentFindByAgeWithPagePageRes struct {
    db.PageResult                    // CurrentPage, PageSize, TotalCount, TotalPage
    ResultList []*Student            // 查询结果列表（全字段时用主结构体）
}
```

> `select_fields: "*"` 时 `ResultList` 类型为主结构体（如 `[]*Student`），否则为对应的 `Res` 结构体。

#### ⑥ WhereDataToYAMLCache + init()

在 `init()` 函数中反序列化 YAML WHERE 条件到 `ConditionMap`，供运行时动态构建查询条件：

```go
var StudentConditionMap = map[string]*conditonwhere.MaskWhereCondition{}
func init() {
    for key, whereDataYaml := range StudentWhereDataToYAMLCache {
        var newData map[interface{}]interface{}
        yaml.Unmarshal([]byte(whereDataYaml), &newData)
        StudentConditionMap[key] = conditonwhere.ParseWhereCondition(newData)
    }
}
```

---

## 2. DAO 文件（`{table}_dao.go`）

### 结构

```go
package dao

type StudentDao struct {
    *gormdb.Repository                  // 数据库连接
    info    agdao.TableInfo             // 表信息（表名）
    baseDao agdao.BaseDao               // 基础 DAO 操作
}

// 接口定义
type IStudentDao interface {
    InsertOne(ctx, entity) (int64, error)
    InsertOneIgnoreZeroValCols(ctx, entity) (int64, error)
    UpdateByPrimaryKey(ctx, entity) (int64, error)
    UpdateByPrimaryKeyIngoreZeroValCols(ctx, entity) (int64, error)
    FindByPrimaryKey(ctx, id) (*model.Student, error)
    FindByStruct(ctx, entity) ([]*model.Student, error)
    FindByCustomerRule(ctx, namingInfo, args) (any, error)
    FindByCondition(ctx, condition, orderBuilder, page) ([]*model.Student, *gormdb.PageResult, error)
    FindFirstOneByCondition(ctx, orderBuilder) (*model.Student, error)
}
```

### CRUD 方法

| 方法 | 签名 | 说明 |
|------|------|------|
| `InsertOne` | `(ctx, *model.Student) (int64, error)` | 插入完整实体 |
| `InsertOneIgnoreZeroValCols` | `(ctx, *model.Student) (int64, error)` | 自动剔除零值列后再插入 |
| `UpdateByPrimaryKey` | `(ctx, *model.Student) (int64, error)` | 按主键更新所有非零列 |
| `UpdateByPrimaryKeyIngoreZeroValCols` | `(ctx, *model.Student) (int64, error)` | 按主键更新，自动剔除零值列 |
| `FindByPrimaryKey` | `(ctx, {Struct}PrimaryKey) (*model.Student, error)` | 按主键查询 |
| `FindByStruct` | `(ctx, *model.Student) ([]*model.Student, error)` | 按实体非零值字段查询（**自动检查索引**） |

**FindByStruct 的索引检查：**
- 按优先级检查：主键 → 唯一约束 → 索引
- 至少命中一个索引或主键列才执行查询
- 未命中时返回 `errors.New("query not use any index")`

### 命名 SQL 执行

`FindByCustomerRule` 是自定义查询的统一入口，通过 `switch` 分发到具体方法：

```go
func (dao *StudentDao) FindByCustomerRule(ctx, namingInfo, args) (any, error) {
    switch namingInfo.SqlName {
    case "FindByAge":
        return dao.doFindByAge(ctx, namingInfo, args)
    case "FindByAgeWithPage":
        return dao.doFindByAgeWithPage(ctx, namingInfo, args)
    }
}
```

**每个自定义查询对应的 doXXX 方法执行流程：**

```
doFindByAge(ctx, namingInfo, args)
  │
  ├── 1. 参数类型断言：args → *model.StudentFindByAgeArg
  ├── 2. 通过 DbType + StructName + SqlName 查找 SQL
  │     如 "MYSQL_Student_FindByAge" → StudentNamingSqlMap
  ├── 3. FieldMask.BuildWhereFromConfig("FindByAge", ConditionMap)
  │     根据调用方设置的字段动态构建 WHERE
  ├── 4. ValidateLeadingCol(newwhere, IndexLeadingCols)
  │     ⚠️ 运行时检查 WHERE 是否命中索引，未命中则报错
  ├── 5. 替换 SQL 中的旧 WHERE 为新 WHERE
  ├── 6. 如果应用了分表，替换表名
  ├── 7. argsMap := queryArgs.ConvertToMap()
  ├── 8. DB(ctx).Raw(execSql, argsMap).Find(&list)
  └── 9. 返回结果
```

---

## 3. 常量文件（`{table}_constant.go`）

```go
package dao

var StudentNamingSqlMap = map[string]string{}   // 命名 SQL 映射表
var excludeStudentZeroColNames = map[string]int{} // 插入时排除的空值字段

// 每个自定义查询的 NameingSqlArgInfo
var FindByAgeNamingInfo = &db.NameingSqlArgInfo{
    SqlName:  "FindByAge",
    ReqType:  (*model.StudentFindByAgeArg)(nil),
    RespType: ([]*model.StudentFindByAgeRes)(nil),
}
```

---

## 4. 命名 SQL 初始化文件（`{table}_namingsql.go`）

```go
func InitStudentNamingSql() {
    InitStudentMYSQL()
    InitStudentDB2()
}
```

---

## 5. 数据库特定 SQL 文件（`{dbtype}_{table}_namingsql.go`）

### MySQL（`mysql_student_namingsql.go`）

```go
const MYSQL_Student_FindByAge = "SELECT ID,STUNO,NAME,AGE FROM STUDENT WHERE (AGE = @Age AND STUNO > @Stuno)"
const MYSQL_Student_FindByAgeWithPage = "SELECT * FROM STUDENT WHERE (AGE = @Age) LIMIT @Start, @End"

func InitStudentMYSQL() {
    StudentNamingSqlMap["MYSQL_Student_FindByAge"] = MYSQL_Student_FindByAge
    StudentNamingSqlMap["MYSQL_Student_FindByAgeWithPage"] = MYSQL_Student_FindByAgeWithPage
}
```

### DB2（`db2_student_namingsql.go`）

```go
const DB2_Student_FindByAgeWithPage = "SELECT * FROM (SELECT *, ROW_NUMBER() OVER(ORDER BY ID) AS RN  FROM STUDENT WHERE (AGE = @Age)) AS T WHERE RN BETWEEN @Start AND @End"

func InitStudentDB2() {
    StudentNamingSqlMap["DB2_Student_FindByAgeWithPage"] = DB2_Student_FindByAgeWithPage
}
```

### 分页 SQL 差异

| 数据库 | 分页语法 |
|--------|---------|
| MySQL | `LIMIT @Start, @End` |
| DB2 | `ROW_NUMBER() OVER(...) AS RN ... WHERE RN BETWEEN @Start AND @End` |

每个分页查询额外生成 `_Count` 查询：`SELECT COUNT(*) FROM STUDENT WHERE (AGE = @Age)`

---

## 6. 索引安全检查（Index Guard）

### 编译时检查

`model/generator.go:checkQueryArgsIndexes` 在生成代码前验证每个自定义查询的 WHERE 条件**至少命中一个索引或主键列**。未命中时阻止生成：

```bash
gen-go-db db -i ./yaml/STUDENT.yaml -o ./
# 错误：查询 FindByAddress 的请求参数没有命中任何索引或主键
```

### 运行时检查

生成的 DAO 代码在每次执行命名 SQL 时通过 `ValidateLeadingCol()` 再次验证：

```go
check := conditonwhere.ValidateLeadingCol(newwhere, model.StudentIndexLeadingCols)
if !check {
    return nil, errors.New("query not use any index")
}
```

---

## 7. 使用示例

```go
// 1. 插入
dao := NewStudentDao(repository, baseDao)
affected, err := dao.InsertOne(ctx, &model.Student{
    Name: "张三",
    Age:  18,
})

// 2. 按主键查询
student, err := dao.FindByPrimaryKey(ctx, model.StudentPrimaryKey(1))

// 3. 自定义查询（命名 SQL）
result, err := dao.FindByCustomerRule(ctx, FindByAgeNamingInfo,
    &model.StudentFindByAgeArg{}.WithAge(18).WithStuno(1001))

// 4. 条件查询（构造器模式）
condition := conditonwhere.NewWhereClauseBuilder()
condition.And("AGE = ?", 18)
list, page, err := dao.FindByCondition(ctx, condition, nil, &db.Page{PageNum: 1, PageSize: 10})
```

---

## 内部实现

| 组件 | 文件 | 职责 |
|------|------|------|
| 入口 | `dao/generator.go:GenerateDAOFromYAML` | 调度 YAML 解析 + 代码生成 |
| YAML 解析 | `dao/parser.go:YAMLParser` | 遍历 YAML 文件，调用 model.ParseYAML |
| Model 模板 | `model/template.go:GetModelTemplate` | 结构体 + 方法 + 查询参数 + ConditionMap |
| DAO 模板 | `dao/template.go` | CRUD + 接口 + 命名 SQL 调度 + 分页 |
| 索引检查 | `model/generator.go:checkQueryArgsIndexes` | 编译时验证查询命中索引 |
| 运行时索引验证 | `conditonwhere.ValidateLeadingCol` | 每次查询时验证 Where 条件命中索引 |
