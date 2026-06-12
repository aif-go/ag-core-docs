---
tags:
  - ag-core
  - agdb
  - dao
  - guide
  - gen-go-db
---

# 生成 DAO 使用指南

> 面向业务开发者：如何在业务代码中使用 gen-go-db 生成的 DAO

## 概述

gen-go-db 生成的 DAO（如 `StudentDao`）是对单表数据库操作的完整封装，业务层通过接口调用，无需手写 SQL 或操作 GORM。

每个表生成一个独立的 DAO：

```go
// 生成的接口
type IStudentDao interface {
    // 插入
    InsertOne(ctx context.Context, entity *model.Student) (int64, error)
    InsertOneIgnoreZeroValCols(ctx context.Context, entity *model.Student) (int64, error)
    
    // 更新
    UpdateByPrimaryKey(ctx context.Context, entity *model.Student) (int64, error)
    UpdateByPrimaryKeyIngoreZeroValCols(ctx context.Context, entity *model.Student) (int64, error)
    
    // 查询
    FindByPrimaryKey(ctx context.Context, id model.StudentPrimaryKey) (*model.Student, error)
    FindByStruct(ctx context.Context, entity *model.Student) ([]*model.Student, error)
    FindByCustomerRule(ctx context.Context, namingInfo *gormdb.NameingSqlArgInfo, args any) (any, error)
    FindByCondition(ctx context.Context, condition *conditonwhere.WhereClauseBuilder,
        orderBuilder *gormdb.OrderBuilder, page *gormdb.Page) ([]*model.Student, *gormdb.PageResult, error)
    FindFirstOneByCondition(ctx context.Context, condition *conditonwhere.WhereClauseBuilder,
        orderBuilder *gormdb.OrderBuilder) (*model.Student, error)
}
```

---

## 一、接口方法详解

### 1.1 插入

```go
// 全字段插入（零值字段也会写入数据库）
affected, err := dao.InsertOne(ctx, &model.Student{
    Name: "张三",
    Age:  18,
})

// 自动剔除零值列插入（主键、索引列不受影响）
affected, err := dao.InsertOneIgnoreZeroValCols(ctx, &model.Student{
    Name: "张三",
    Age:  18,
})
```

**区别：**

| 方法 | 零值字段处理 |
|------|-------------|
| `InsertOne` | 零值字段也会写入数据库 |
| `InsertOneIgnoreZeroValCols` | 自动剔除零值列，只插入有值的字段 |

### 1.2 更新

```go
// 根据主键全字段更新（零值也会写入）
affected, err := dao.UpdateByPrimaryKey(ctx, &model.Student{
    Id:   1,
    Name: "李四",
})

// 根据主键更新，自动剔除零值列
affected, err := dao.UpdateByPrimaryKeyIngoreZeroValCols(ctx, &model.Student{
    Id:   1,
    Name: "李四",
})
```

> **注意**：更新时必须传入主键值，否则返回错误 `"primary key or unique key is required"`。

### 1.3 按主键查询

```go
// 使用主键类型别名
student, err := dao.FindByPrimaryKey(ctx, model.StudentPrimaryKey(1))
// 未找到时返回 (nil, nil)，不会返回 ErrRecordNotFound
```

### 1.4 按实体查询（FindByStruct）

```go
// 根据实体中非零值的索引列/主键列查询
students, err := dao.FindByStruct(ctx, &model.Student{
    Age: 18,
})
```

`FindByStruct` 的查询逻辑：

```
1. 先检查主键 → 有值则按主键查
2. 再检查索引列 → 取第一个命中索引的列作为查询条件
3. 未命中任何索引 → 返回错误 "query not use any index"
4. 其他非零值普通列 → 附加为 AND 条件
```

> **这是编译时的索引安全检查**，确保你的查询必然走索引，避免全表扫描。

### 1.5 自定义查询（命名 SQL）

在 Excel 中定义的命名查询（如 `FindByAge`），通过 `FindByCustomerRule` 执行：

```go
// 1. 使用 Builder 模式构造参数
arg := new(model.StudentFindByAgeArg).
    WithAge(18).
    WithStuno(1001)

// 2. 通过 FindByCustomerRule 执行
result, err := dao.FindByCustomerRule(ctx, dao.FindByAgeNamingInfo, arg)
if err != nil {
    return nil, err
}
list := result.([]*model.StudentFindByAgeRes)
```

**命名 SQL 的执行流程**：

```
命名 SQL 模板
    │  FieldMask 动态构建 WHERE 条件
    ▼
WHERE 条件替换（用 FieldMask 生成的 WHERE 替换模板中的占位 WHERE）
    │  ValidateLeadingCol 检查是否命中索引
    ▼
索引校验通过 → 执行 SQL
```

#### 分页命名查询

```go
// 分页查询参数（内嵌 Page 结构体）
arg := new(model.StudentFindByAgeWithPageArg).
    WithAge(18)
arg.PageNum = 1
arg.PageSize = 20

result, err := dao.FindByCustomerRule(ctx, dao.FindByAgeWithPageNamingInfo, arg)
if err != nil {
    return nil, err
}
pageRes := result.(*model.StudentFindByAgeWithPagePageRes)
// pageRes.ResultList  — 数据列表
// pageRes.PageResult   — 分页信息（CurrentPage, PageSize, TotalCount, TotalPage）
```

### 1.6 条件构建器查询

适用于灵活多变的查询条件，无需为每个组合生成命名 SQL：

```go
import "github.com/aif-go/ag-core/contribute/agdb/conditonwhere"

// 构建条件
condition := conditonwhere.NewWhereClauseBuilder()
condition.And("AGE = ?", 18)
condition.And("NAME LIKE ?", "%张%")

// 排序
orderBuilder := gormdb.NewOrderBuilder()
orderBuilder.Asc("AGE").Desc("ID")

// 分页
page := &gormdb.Page{PageNum: 1, PageSize: 20}

// 执行查询
list, pageResult, err := dao.FindByCondition(ctx, condition, orderBuilder, page)

// 只查第一条
student, err := dao.FindFirstOneByCondition(ctx, condition, orderBuilder)
```

> **注意**：`FindByCondition` 不包含索引安全检查，请确保 WHERE 条件中的字段有数据库索引。

---

## 二、初始化与依赖注入

### 2.1 手动初始化

```go
import (
    "github.com/aif-go/ag-core/contribute/agdb/gormdb"
    "github.com/aif-go/ag-core/contribute/agdb/agdao"
    "your-project/internal/repository/dao"
)

func initDAO(db *gorm.DB) dao.IStudentDao {
    // 1. 创建 Repository
    repository := gormdb.NewRepository(db)

    // 2. 创建 BaseDao（无特殊表名策略时传入空）
    baseDao := &agdao.BaseDao{}
    // 或使用 FX 创建的 BaseDao（见 2.2）

    // 3. 创建 DAO
    return dao.NewStudentDao(repository, baseDao)
}
```

### 2.2 FX 注入（推荐）

agdb 已提供完整的 FX 模块，只需引入即可。生成的 DAO `NewStudentDao` 签名天然兼容 FX，不需要包装：

```go
// NewStudentDao 签名：func(repository *gormdb.Repository, baseDao agdao.BaseDao) IStudentDao
//                      └──── FX 自动注入 ────┘          └── FX 自动注入 ──┘
```

#### 第一步：定义 DAO 模块

在 `internal/repository/dao/` 下手动创建 `zfx_dao.go`（不会被 gen-go-db 覆盖）：

```go
// zfx_dao.go
package dao

import "go.uber.org/fx"

var FxDaoModule = fx.Module("fx_dao",
    fx.Provide(
        NewStudentDao,
        // 后续新增表只需加一行：
        // NewTeacherDao,
        // NewCourseDao,
    ),
)
```

#### 第二步：注册到内部模块

在 `internal/zfx_internal.go` 中加入 DAO 模块：

```go
// zfx_internal.go
package internal

import (
    "your-project/internal/adpgen"
    "your-project/internal/config"
    "your-project/internal/repository/dao"  // 新增
    "your-project/internal/svcgen"

    "go.uber.org/fx"
)

var FxInternalModule = fx.Module("fx-internal-module",
    config.FxAppConfigModule,
    svcgen.FxServiceWithProxyModule(),
    adpgen.FxAdapterModule(),
    dao.FxDaoModule,  // ← DAO 模块
)
```

#### 第三步：app 装配

```go
app := fx.New(
    gormdb.FxAicGromdbModule,   // *gorm.DB → Repository → TransactionManager
    agdb.FxAgDbModule,          // BaseDao + 事务中间件
    internal.FxInternalModule,   // 内部模块（含 DAO、Service、Adapter...）
    // ...
)
```

**这样做的优势：**

| 点 | 说明 |
|----|------|
| **遵循现有模式** | 和 `config.FxAppConfigModule`、`svcgen` 等放在同一层聚合 |
| **新增表不改入口** | 加表只需在 `zfx_dao.go` 加一行 `NewXxxDao` |
| **自动装配** | `NewStudentDao` 依赖的 `*Repository` 和 `BaseDao` 由 FX 自动注入 |
| **手写文件** | `zfx_dao.go` 不会被 gen-go-db 覆盖 |

**FX 模块依赖链**：

```
FxAicGromdbModule
  └─ NewAggormDbConfig ─► *Config ─► NewDB_V2 ─► *gorm.DB
       ─► NewRepository ─► *Repository（传入 DAO 构造函数）

FxAgDbModule
  └─ agdao.FxNewAgGormBaseDao ─► BaseDao（传入 DAO 构造函数）
```

### 2.3 在业务 Service 中使用

```go
type StudentServiceImpl struct {
    studentDao dao.IStudentDao  // 面向接口编程
}

// FX 自动注入 DAO
func NewStudentServiceImpl(studentDao dao.IStudentDao) *StudentServiceImpl {
    return &StudentServiceImpl{studentDao: studentDao}
}

func (s *StudentServiceImpl) GetStudent(ctx context.Context, req *student.GetStudentRequest) (*student.Student, error) {
    // 直接调用接口方法
    stu, err := s.studentDao.FindByPrimaryKey(ctx, model.StudentPrimaryKey(req.Id))
    if err != nil {
        return nil, err
    }
    if stu == nil {
        return nil, status.Errorf(codes.NotFound, "学生不存在")
    }
    return convertToPB(stu), nil
}
```

---

## 三、应用场景

### 3.1 基本 CRUD

```go
// 创建
dao.InsertOne(ctx, &model.Student{Name: "张三", Age: 18})

// 查询
stu, _ := dao.FindByPrimaryKey(ctx, 1)

// 更新
stu.Name = "李四"
dao.UpdateByPrimaryKey(ctx, stu)

// 删除（标准 DAO 不提供 Delete 方法，通过 Repository 直接操作 GORM）
// db := repository.DB(ctx)
// db.Delete(&model.Student{}, 1)
```

### 3.2 条件查询（构建器模式）

适合查询条件组合不确定的场景：

```go
// 动态构建查询条件
cond := conditonwhere.NewWhereClauseBuilder()
if req.Name != "" {
    cond.And("NAME = ?", req.Name)
}
if req.Age > 0 {
    cond.And("AGE > ?", req.Age)
}

order := gormdb.NewOrderBuilder().Desc("FCT")

list, pageResult, err := dao.FindByCondition(ctx, cond, order, &gormdb.Page{
    PageNum:  req.PageNum,
    PageSize: req.PageSize,
})
```

### 3.3 批量操作

生成的 DAO 不提供批量操作接口，遇到批量场景使用 GORM 的 `CreateInBatches` 或 `Slice`：

```go
// 批量插入
db := repository.DB(ctx)
db.CreateInBatches(students, 100)

// IN 查询
db.Where("ID IN ?", ids).Find(&list)
```

### 3.4 事务

Biz 层注入的是 **DAO 接口**，不需要手动管理事务。事务通过声明式中间件自动管理：

```go
// init() 中声明事务
svcgen.StudentServiceCreateStudentCallInfo.AddTag(agdb.TransactionTag, true)

// biz 层直接调用 DAO 方法，事务由中间件自动处理
func (b *StudentBiz) Create(ctx context.Context, req *CreateRequest) error {
    _, err := b.studentDao.InsertOne(ctx, &model.Student{Name: "张三"})
    return err
}
```

**为什么 DAO 能自动感知事务？** DAO 内部使用 `Repository.DB(ctx)` 获取数据库实例，它会自动检查 context 中是否有事务绑定。如果中间件已开启事务，`DB(ctx)` 返回事务连接；否则返回普通连接。

> **注意**：Biz 层注入的是 DAO 接口（`dao.IStudentDao`），无法调用 `repository.Transaction()`。如果确有需要手动控制事务边界的场景（批量操作、复杂事务等），请在持有 `*gormdb.Repository` 的层（如 service 层）进行操作。

### 3.5 分表策略

通过 `BaseDao` 注册表名策略，实现运行时动态修改表名：

```go
// 注册租户分表策略
fx.Provide(
    agdao.NewFxAgTbInfoOpt(func() agdao.TbInfoOpt {
        return agdao.WithTbNameStrategy(func(ctx context.Context, info *agdao.TableInfo) string {
            tenant := GetTenantFromContext(ctx)
            if tenant != "" {
                return info.TableName + "_" + tenant  // STUDENT → STUDENT_tenant01
            }
            return info.TableName
        })
    }),
)
```

所有 DAO 的查询都会自动应用这个策略，无需逐个修改。

---

## 四、注意事项

### 4.1 零值列处理

| 字段类型 | 零值 | 说明 |
|---------|------|------|
| `int` / `int64` | `0` | 插入/更新时可能被误解为空值 |
| `string` | `""` | 空字符串被视为零值 |
| `time.Time` | `time.Time{}` | 零值时间会被剔除 |

使用 `IgnoreZeroValCols` 系列方法可以避免将 Go 零值写入数据库。但需要明确一点：**如果你确实想将某个字段更新为 `0` 或 `""`，请使用非 Ignore 版本的方法**。

### 4.2 索引安全检查

DAO 内置两重索引安全机制：

1. **编译时（index guard）**：`FindByStruct` 在生成时已验证至少一个查询条件命中索引，运行时再次检查
2. **运行时（命名 SQL）**：`FindByCustomerRule` 对动态 WHERE 条件执行 `ValidateLeadingCol` 验证

如果触发错误 `"query not use any index"`，说明查询条件没有包含任何索引列的第一列。解决方法：

- 为查询字段添加数据库索引
- 或者调整查询条件，确保包含索引列

### 4.3 生成代码不可编辑

```go
// DO NOT EDIT
// DO NOT EDIT
// DO NOT EDIT
```

所有生成的代码文件（`*_dao.go`、`*_model.go`、`*_constant.go`、`*_namingsql.go`）都有只读标记。如果需要定制 DAO 行为，有以下方式：

| 方式 | 说明 |
|------|------|
| 修改 Excel 模板重新生成 | 推荐，保持代码与表结构一致 |
| 编写包装层 | 在生成的 DAO 之上封装业务逻辑 |
| 使用 BaseDao TbInfoOpt| 通过注入策略定制表名等行为 |

### 4.4 表名动态修改

`BaseDao.ApplyTbInfoOpts` 在每次 `newDB` 调用时执行，不会永久修改 DAO 的表名。如需临时改变查询目标表，可通过 `TbInfoOpt` 实现：

```go
// 生效范围：仅当前 DAO 实例的本次查询
baseDao.RegTbInfoOpt(WithTbNameStrategy(func(ctx context.Context, info *TableInfo) string {
    return info.TableName + "_archive"
}))
```

### 4.5 模型方法

生成的 Model 除了数据库映射字段外，还包含一些实用方法：

| 方法 | 用途 |
|------|------|
| `TableName()` | 返回表名 |
| `Clone()` | 深克隆对象 |
| `ToString()` | 调试输出 |
| `ListZeroValueCols(...)` | 列出零值/非零值列，用于 Insert 和 Update 的过滤 |

---

## 相关文档

| 文档 | 内容 |
|------|------|
| [[../../CLI工具/gen-go-db/00-GenGoDb\|gen-go-db CLI]] | 如何运行代码生成工具 |
| [[../../代码生成/gendb/07-DAO生成产物详解\|DAO 生成产物详解]] | 每个生成文件的代码结构详解 |
| [[../../代码生成/gendb/03a-YAML定义格式详解\|YAML 定义格式]] | 表结构 YAML 定义 |
| [[../02-gormdb\|Repository 使用]] | GORM 封装层详解 |
| [[../04-WHERE条件构建器\|条件构建器]] | 动态 WHERE 构建 |
| [[../03-命名SQL\|命名 SQL]] | 命名查询的执行机制 |
| [[agdao/00-Agdao\|Agdao 增强层]] | BaseDao 接口与表名策略 |
| [[../05-FX集成\|FX 集成]] | agdb FX 依赖注入 |
