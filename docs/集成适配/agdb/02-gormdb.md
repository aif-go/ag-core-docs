---
tags:
  - ag-core
  - agdb
  - gormdb
  - gorm
  - architecture
---

# gormdb — GORM 数据库核心实现

> 路径：`contribute/agdb/gormdb/`

gormdb 是 agdb 的核心实现子包，封装了 GORM v2 的**连接管理**、**Repository 模式**、**日志适配**、**分页模型**和**命名 SQL 支持**。

## 文件结构

```
gormdb/
├── db.go                 # 数据库连接：NewDB / NewDB_V2 / DBOpener 注册
├── config.go             # Config 配置结构体
├── repository.go         # Repository：事务管理器 + 上下文感知 DB
├── page.go               # 分页模型 + OrderBuilder
├── ag_start.go           # Config 绑定 + logger 构建
├── gormslog.go           # slog → GORM logger 适配
├── gormzap.go            # zap → GORM logger 适配
├── namingsql_support.go  # 命名 SQL 参数替换 + 分页计算
└── zfx_aicgormdb.go      # FX Module 注册
```

---

## 1. 数据库连接 (`db.go`)

两个版本的连接函数：

### NewDB（旧版）

```go
// db.go:16-54
func NewDB(env ag_conf.IConfigurableEnvironment, l logger.Interface) (*gorm.DB, error)
```

- 通过 `IConfigurableEnvironment` 读取 `data.db.user.driver` 和 `data.db.user.dsn`
- 支持 `mysql` 和 `ibmdb` 驱动
- 硬编码连接池：MaxIdleConns=10, MaxOpenConns=100, ConnMaxLifetime=1h
- 默认开启 `db.Debug()`

### NewDB_V2（新版）

```go
// db.go:56-119
func NewDB_V2(cfg *Config, l logger.Interface) (*gorm.DB, error)
```

- 通过 `*Config` 结构体配置
- 完整的参数校验（driver/dsn 非空检查）
- 通过 `GetDBOpener` 获取驱动
- 可配置连接池：MaxIdleConns、MaxOpenConns、ConnMaxLifetime、ConnMaxIdleTime（带合法校验）
- **Ping 测试**：连接后执行 `sqlDB.Ping()` 验证数据库真实可用

### DBOpener 驱动注册机制

```go
// db.go:132-151
type DBOpener func(dsn string) gorm.Dialector

func RegisterDBOpener(driver string, opener DBOpener) error  // 注册（判重）
func GetDBOpener(driver string) DBOpener                     // 获取
```

默认注册：
```go
func init() {
    RegisterDBOpener("ibmdb", gormibmdb.Open)  // DB2
    RegisterDBOpener("mysql", mysql.Open)       // MySQL
}
```

驱动注册是 **并发安全** 的（`sync.RWMutex`），支持扩展自定义驱动。

> ⚠️ 仅 `NewDB_V2` 使用 registry 机制。旧版 `NewDB` 使用 hardcoded switch，**不支持**扩展驱动。

### 扩展自定义驱动

以 SQLite 为例，在项目 `init()` 或 `main()` 启动阶段注册：

```go
import (
    "github.com/aif-go/ag-core/contribute/agdb/gormdb"
    "gorm.io/driver/sqlite"
)

func init() {
    _ = gormdb.RegisterDBOpener("sqlite", sqlite.Open)
}
```

然后在 YAML 中使用：

```yaml
data:
  db:
    user:
      driver: sqlite
      dsn: test.db     # 文件路径，或 ":memory:" 纯内存模式
```

任何实现了 `gorm.Dialector` 接口的 GORM 驱动均可通过此方式注册。

---

## 2. 配置 (`config.go`)

```go
// config.go:9-30
type Config struct {
    User   UserConfig     // Driver + DSN
    Pool   PoolConfig     // MaxIdleConns, MaxOpenConns, ConnMaxLifetime(秒), ConnMaxIdleTime(秒)
    Logger LoggerConfig   // Name("agdb"), Debug
}

func NewDefaultConfig() *Config {
    numP := runtime.GOMAXPROCS(0)
    return &Config{
        Logger: LoggerConfig{Name: "agdb", Debug: false},
        Pool:   PoolConfig{MaxIdleConns: numP, MaxOpenConns: numP},
    }
}
```

配置前缀：`data.db`。启动时通过 `ag_start.go` 绑定到结构体。

---

## 3. Repository (`repository.go`)

Repository 是 agdb 的核心数据结构，集成了**事务管理 + 上下文感知 DB 获取**。

### 结构定义

```go
// repository.go:12-16
type Repository struct {
    agdb.TxContextAbility[*gorm.DB]  // 嵌入泛型事务上下文能力
    db     *gorm.DB                  // 原始 GORM DB（无事务）
    DbType string                    // 数据库类型：DB2 / MYSQL
}
```

### 构造函数

```go
// repository.go:18-37
func NewRepository(db *gorm.DB) *Repository {
    rep := &Repository{db: db}
    rep.DbType = strings.ToUpper(db.Dialector.Name())
    switch rep.DbType {
    case "GO_IBM_DB":
        rep.DbType = "DB2"  // 统一命名为 DB2
    }
    return rep
}
```

### TransactionManager 实现

```go
// repository.go:39-42
func NewTransactionManager(repository *Repository) agdb.TransactionManager {
    return repository
}
```

将 `*Repository` 转型为 `agdb.TransactionManager` 接口。

### 核心方法

**DB(ctx)** — 上下文感知的 DB 获取：
```go
// repository.go:44-52
func (r *Repository) DB(ctx context.Context) *gorm.DB {
    v := r.GetTxFromCtx(ctx)     // 优先取 context 中的事务 DB
    if v != nil {
        return v
    }
    return r.db.WithContext(ctx) // 无事务则返回普通 DB
}
```

**Transaction(ctx, fn)** — 开启事务：
```go
// repository.go:55-61
func (r *Repository) Transaction(ctx context.Context, fn func(ctx context.Context) error) error {
    return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
        ctx = r.BindTxToCtx(ctx, tx)  // 将 tx 绑定到 context
        return fn(ctx)
    })
}
```

**TransactionWithTP(ctx, tp, fn)** — 支持传播行为的事务：
```go
// repository.go:63-65
func (r *Repository) TransactionWithTP(ctx context.Context, tp agdb.TransactionPropagation, fn func(ctx context.Context) error) error {
    return agdb.WithTransaction(ctx, r, tp, fn)
}
```

---

## 4. 日志适配

两个 GORM `logger.Interface` 实现，二选一：

### GormSlogLogger (`gormslog.go`)

基于 Go 1.21 `log/slog` 标准库：

```go
// gormslog.go:15-21
type GormSlogLogger struct {
    SlogLogger                *slog.Logger
    SlowThreshold             time.Duration    // 默认 100ms
    IgnoreRecordNotFoundError bool             // 默认 true
    ParameterizedQueries      bool
    LogLevel                  logger.LogLevel  // 默认 Warn
}

func NewSLogGormLog(slogLogger *slog.Logger) logger.Interface
```

Trace 日志的三级输出：
- **Error**（SQL 执行出错）→ `slog.LevelError`，输出 error、耗时、行数、SQL
- **Warn**（慢查询 > SlowThreshold）→ `slog.LevelWarn`，输出 `SLOW SQL` 标记
- **Info**（正常日志）→ `slog.LevelDebug`，输出耗时、行数、SQL

### Zap 版 Logger (`gormzap.go`)

基于 `go.uber.org/zap`：

```go
// gormzap.go:20-27
type Logger struct {
    ZapLogger                 *zap.Logger
    SlowThreshold             time.Duration  // 默认 100ms
    Colorful                  bool
    IgnoreRecordNotFoundError bool
    ParameterizedQueries      bool
    LogLevel                  gormlog.LogLevel
}
```

支持从 context 中提取 zap.Logger（通过 `ctxLoggerKey = "zapLogger"`），实现**上下文日志**。

**调用链追溯**：通过 `runtime.Caller()` 向上查找调用栈，定位到实际业务代码的文件位置，跳过 GORM 内部帧。

---

## 5. 启动配置 (`ag_start.go`)

```go
// ag_start.go:10-34
func NewAggormDbConfig(binder ag_conf.IBinder) (*Config, error) {
    cfg := NewDefaultConfig()
    err := binder.Bind(cfg, DBConfigPrefix)   // "data.db" 前缀绑定
    return cfg, err
}

func FindGormLoggerFromAgslog(conf *Config) logger.Interface {
    slogLogger := agslog.GetSlogByName(conf.Logger.Name)  // 默认 "agdb"
    log := NewSLogGormLog(slogLogger)
    if conf.Logger.Debug {
        log = log.LogMode(logger.Info)  // 调试模式
    }
    return log
}
```

---

## 6. 分页模型 (`page.go`)

```go
// page.go:6-17
type Page struct {
    PageSize int64
    PageNum  int64
}

type PageResult struct {
    CurrentPage int64
    TotalCount  int64
    TotalPage   int64
    PageSize    int64
}
```

### OrderBuilder — ORDER BY 链式构建器

```go
// page.go:46-115
func NewOrderBuilder() *OrderBuilder
    .Asc("col1")      // 升序
    .Desc("col2")     // 降序
    .Order("col3", DESC) // 自定义
    .Build()          // → "col1 ASC, col2 DESC, col3 DESC"
```

支持 `Asc`、`Desc`、`Order`、`Orders`（批量）、`Build`、`BuildWithoutKeyword`、`Clear` 等链式方法。

---

## 7. 命名 SQL 支持 (`namingsql_support.go`)

详见 [03-命名SQL](03-命名SQL.md)。

---

## FX 依赖

gormdb 子模块通过 `FxAicGromdbModule` 注册（[05-FX集成](05-FX集成.md)）：

```go
fx.Provide(
    NewAggormDbConfig,        // *Config
    NewDB_V2,                 // *gorm.DB
    NewRepository,            // *Repository
    NewTransactionManager,    // agdb.TransactionManager
    FindGormLoggerFromAgslog, // logger.Interface
)
```
