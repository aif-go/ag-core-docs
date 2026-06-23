---
tags:
  - ag-core
  - future
  - agdb
  - gormdb
  - optimization
  - connection-pool
---

# Agdb 优化 — 数据库连接池心跳保活

> 记录日期：2026-06-18 | 状态：待解决

## 问题

生产环境中，数据库连接在长时间闲置后被 MySQL 服务端主动断开（默认 `wait_timeout=28800`，8 小时）。下次查询时从连接池取到已断开的连接，导致查询失败。

## 根因：连接池无心跳保活机制

### 当前连接池配置（`NewDB_V2`）

```go
// contribute/agdb/gormdb/db.go:56-119
func NewDB_V2(cfg *Config, l logger.Interface) (*gorm.DB, error) {
    // ...
    if cfg.Pool.ConnMaxLifetime > 0 {
        sqlDB.SetConnMaxLifetime(time.Duration(cfg.Pool.ConnMaxLifetime) * time.Second)
    }
    if cfg.Pool.ConnMaxIdleTime > 0 {
        sqlDB.SetConnMaxIdleTime(time.Duration(cfg.Pool.ConnMaxIdleTime) * time.Second)
    }
    // 只有启动时的一次性 Ping
    if err := sqlDB.Ping(); err != nil {
        return nil, fmt.Errorf("db ping failed: %w", err)
    }
    return db, nil
}
```

### 三个缺陷

| 缺陷 | 说明 |
|------|------|
| **`ConnMaxLifetime` 默认 0** | `NewDefaultConfig()` 中 `ConnMaxLifetime=0`（无限制），若 app.yml 也漏配，连接永不回收 |
| **无定期心跳** | 只有启动时的一次 `Ping()`，没有后台定期保活。MySQL 的 `wait_timeout` 到期后仍在空闲池中的连接变成"僵尸连接" |
| **`ConnMaxIdleTime` 有副作用** | 可配置但会关空闲连接，导致首笔查询需新建连接，增加 5-15ms 延迟 |

### 问题链路

```
业务长时间无请求
    ↓
连接池中的空闲连接无人使用
    ↓
MySQL 8 小时后主动断开（wait_timeout=28800）
    ↓
新请求到达，连接池取出已断开的"僵尸连接"
    ↓
查询失败（"MySQL has gone away" / "connection closed"）
```

## 分析：三个维度的权衡

### 「首笔延迟」vs「防断连」vs「资源占用」

| 方案 | 首笔延迟 | 防断连 | 空闲连接 |
|------|---------|--------|---------|
| 仅 `ConnMaxLifetime: 3600` | 0ms ✅ | ✅（1h < 8h）| 保留 |
| 仅 `ConnMaxIdleTime: 600` | 5-15ms ⚠️ | ✅（间接）| 归零 |
| 两个都不配（当前默认） | 0ms ✅ | ❌ | 保留 |
| **心跳保活** | **0ms ✅** | **✅** | **保留** |

### 推荐方案：后台心跳保活

核心思路：不需要回收连接，而是用 `Ping()` 定期向空闲池中的连接发 `SELECT 1`，保持 MySQL 侧的活跃状态，让 `wait_timeout` 永不触发。

```
时间线：
  t=0      创建连接，用完归还空闲池
  t=30min  后台心跳 Ping → 取空闲连接 → SELECT 1 → 归还
            ↓ MySQL wait_timeout 计时器被重置
  t=60min  同上，连接持续保活
  ...
  t=∞      首笔请求 → 复用空闲连接 → 0ms 额外延迟 ✅
```

### 与现有方案的关系

| 参数 | 还配不配？ |
|------|-----------|
| `ConnMaxLifetime` | **不配**（有心跳保活就不需要，避免过期重建导致首笔变慢） |
| `ConnMaxIdleTime` | **不配**（不需要关空闲连接） |
| `HeartbeatInterval` | **新增**（30 分钟 Ping 一次，远小于 MySQL 的 8h） |

## 修复方向

### 改动范围

| 文件 | 改动 |
|------|------|
| `contribute/agdb/gormdb/config.go` | `PoolConfig` 新增 `HeartbeatInterval` 字段（秒，0=不开启） |
| `contribute/agdb/gormdb/db.go` | `NewDB_V2` 中 `HeartbeatInterval > 0` 时启动后台 goroutine 定期 Ping |

### 代码示意

```go
// config.go
type PoolConfig struct {
    MaxIdleConns      int
    MaxOpenConns      int
    ConnMaxLifetime   int    // 秒，0=不限制
    ConnMaxIdleTime   int    // 秒，0=不限制
    HeartbeatInterval int    // 秒，0=不开启后台心跳
}

// db.go — NewDB_V2 末尾
if cfg.Pool.HeartbeatInterval > 0 {
    go func() {
        ticker := time.NewTicker(
            time.Duration(cfg.Pool.HeartbeatInterval) * time.Second)
        defer ticker.Stop()
        for range ticker.C {
            if err := sqlDB.Ping(); err != nil {
                slog.Warn("db keepalive ping failed", "error", err)
            }
        }
    }()
}
```

### 推荐配置

```yaml
data:
  db:
    pool:
      maxIdleConns: 5
      maxOpenConns: 100
      heartbeatInterval: 1800   # 30分钟心跳，防 MySQL wait_timeout
      # connMaxLifetime: 不配   # 由心跳取代
      # connMaxIdleTime: 不配   # 不关空闲连接
```

### 注意事项

- **心跳间隔 ≈ 30 分钟**（`wait_timeout=8h` 的 1/16，安全裕度充足）
- **`sqlDB.Ping()` 是并发安全的** — 取空闲连接、发 Ping、归还，不会阻塞业务查询
- **心跳失败不影响业务** — 只打 warn 日志，等待下次心跳
- **连接本来存活时 Ping 几乎零开销** — 服务端 `SELECT 1` 微秒级返回

### 关联文档

实现后需同步更新：

- [ ] `docs/集成适配/agdb/02-gormdb.md` — 新增 `HeartbeatInterval` 字段说明
- [ ] `docs/集成适配/agdb/06-使用指南.md` — 配置示例中增加心跳节
