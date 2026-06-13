---
tags:
  - ag-core
  - future
  - ag-log
  - optimization
  - bug
---

# AgLog 优化 — 日志归档文件名时间改用本地时间

> 记录日期：2026-06-10 | 状态：待修复

## 问题

日志文件滚动归档时（lumberjack），压缩文件名中的时间戳使用 UTC 时间，比北京时间晚 8 小时，造成归档文件名时间与实际时间不符。

## 根因分析

### 时间戳生成链路

```
slogzap.NewSlogHandler4ZapProps → logzap.NewZapLogP → lumberjack.Logger
```

### 核心代码位置

**1. `zaplog.go:60-66`** — 创建 lumberjack 时未设置 `LocalTime`：

```go
hook := lumberjack.Logger{
    Filename:   lp,
    MaxSize:    p.MaxSize,
    MaxBackups: p.MaxBackUps,
    MaxAge:     p.MaxAge,
    Compress:   p.Compress,
    // ❌ LocalTime 未设置，Go bool 零值为 false → 使用 UTC
}
```

**2. `ZlogProperties` 结构体**（`zaplog.go:15-25`）没有 `LocalTime` 配置项，外部无法配置。

### lumberjack 行为

`lumberjack.go:101-104`：
> LocalTime determines if the time used for formatting the timestamps in backup files is the computer's local time. **The default is to use UTC time.**

`lumberjack.go:247-259` `backupName` 函数：
```go
t := currentTime()
if !local {
    t = t.UTC()   // local=false 时强制转 UTC
}
timestamp := t.Format("2006-01-02T15-04-05.000")
```

### 时间格式

归档文件名格式：`<name>-2006-01-02T15-04-05.000.ext`（若启用压缩则为 `.gz`）

## 影响范围

- 所有使用 ag-log 文件输出 + 日志滚动（MaxSize > 0）的场景
- 覆盖 `slogzap` 和 `logzap` 两条路径

## 修复方案

### 1. `ZlogProperties` 添加配置项（`zaplog.go:15-25`）

```go
type ZlogProperties struct {
    // ...
    LocalTime  bool   `value:"${local_time:false}"`  // 新增：是否使用本地时间
}
```

### 2. `NewZapLogP` 传入 `LocalTime`（`zaplog.go:60-66`）

```go
hook := lumberjack.Logger{
    // ...
    LocalTime:  p.LocalTime,  // 新增
}
```

### 3. 配置变更

用户配置中添加 `local_time: true`：

```yaml
aglog:
  zap:
    logs:
      app:
        log_file_name: /var/log/app/app.log
        local_time: true  # 新增
```

## 注意

- lumberjack 不支持独立归档目录，归档文件始终存放在 `log_file_name` 所在目录
- `LocalTime` 默认 `false` 保持向后兼容，需显式开启
