---
tags:
  - ag-core
  - agdb
  - agdao
  - architecture
---

# Agdao — DAO 增强层

> 路径：`contribute/agdb/agdao/` | 基础 DAO 能力

## 概述

Agdao 提供了**运行时表名策略**的基础设施，允许在 DAO 层面动态修改查询的表名（如按租户分表、按环境分表）。

## 文件结构

```
agdao/
├── base_dao.go     # BaseDao 接口 + baseDao 实现
├── dao_opts.go     # TbInfoOpt 选项函数
├── table_info.go   # TableInfo 结构体
└── zfx_dao.go      # FX 注入（组标签）
```

## BaseDao 接口

```go
// base_dao.go:6-8
type BaseDao interface {
    ApplyTbInfoOpts(ctx context.Context, info *TableInfo)
}
```

实现 `baseDao` 通过 `TbInfoOpt` 列表进行表信息修改：

```go
// base_dao.go:14-18
func (dao *baseDao) ApplyTbInfoOpts(ctx context.Context, info *TableInfo) {
    for _, opt := range dao.tbInfoOpts {
        opt(ctx, info)
    }
}

func (dao *baseDao) RegTbInfoOpt(opts ...TbInfoOpt) {
    dao.tbInfoOpts = append(dao.tbInfoOpts, opts...)
}
```

## TableInfo

```go
// table_info.go:3-5
type TableInfo struct {
    TableName string  // 运行时动态确定的表名
}
```

## TbInfoOpt

```go
// dao_opts.go:5
type TbInfoOpt func(ctx context.Context, info *TableInfo)
```

内置 `WithTbNameStrategy` 用于自定义表名策略：

```go
// dao_opts.go:7-12
func WithTbNameStrategy(strategy func(ctx context.Context, info *TableInfo) string) TbInfoOpt {
    return func(ctx context.Context, info *TableInfo) {
        info.TableName = strategy(ctx, info)
    }
}
```

## FX 集成

通过 FX 组标签 `"fx_ag_gorm_tbinfo_opt"` 实现多路注入：

```go
// zfx_dao.go:20-24
func FxNewAgGormBaseDao(in FxInBaseDao) (BaseDao, error) {
    bdao := &baseDao{}
    bdao.RegTbInfoOpt(in.TbInfoOpts...)  // 注册所有表信息选项
    return bdao, nil
}
```

其他模块注册表名策略：
```go
fx.Provide(
    NewFxAgTbInfoOpt(func() TbInfoOpt {
        return WithTbNameStrategy(func(ctx context.Context, info *TableInfo) string {
            tenant := GetTenantFromContext(ctx)
            if tenant != "" {
                return info.TableName + "_" + tenant
            }
            return info.TableName
        })
    }),
)
```

该模块隶属于 agdb FX 模块的一部分，见 [[../05-FX集成]]。
