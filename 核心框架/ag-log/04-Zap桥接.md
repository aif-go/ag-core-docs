---
tags:
  - ag-core
  - ag-log
  - zap
  - slogzap
---

# Zap 桥接 — logzap + slogzap

> 子包：`ag/ag_log/logzap/` + `ag/ag_log/slogzap/` | slog → zap 桥接

## 职责

提供将 Uber Zap 日志引擎作为 `slog.Handler` 使用的能力。分为两层：

| 层 | 子包 | 职责 |
|---|------|------|
| **Zap 日志引擎** | `logzap` | 基于 zap + lumberjack 的日志写入（文件轮转、控制台、JSON/Console 编码） |
| **slog 桥接** | `slogzap` | 将 `*zap.Logger` 包装为 `slog.Handler`（通过 `samber/slog-zap`） |

## logzap — Zap 日志引擎

### ZlogProperties

配置前缀：`{subpath}.{name}`（在 slogzap 场景为 `aglog.zap.logs.{name}`）

| 配置字段 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `log_level` | `string` | `"info"` | 日志级别：debug/info/warn/error |
| `log_file_name` | `string` | `""` | 日志文件路径（空 = 不写文件） |
| `max_size` | `int` | `100` | 单个日志文件最大 MB |
| `max_backups` | `int` | `0` | 最大备份数（0 = 不限） |
| `max_age` | `int` | `0` | 文件保留天数（0 = 不限） |
| `compress` | `bool` | `false` | 是否压缩归档 |
| `console` | `bool` | `false` | 是否 Console 编码（彩色） |
| `prod` | `bool` | `false` | 是否生产模式（Development=false） |
| `stdout` | `bool` | `false` | 是否同时输出到控制台 |

### NewZapLogP — 创建 Zap Logger

```go
func NewZapLogP(p *ZlogProperties) *zap.Logger
```

1. 解析日志级别（debug/info/warn/error，默认 info）
2. 构建输出目标：
   - `stdout=true` → 添加 `os.Stdout` 写入
   - `log_file_name` 非空 → 添加 `lumberjack.Logger`（文件轮转）
3. 编码器选择：
   - `console=true` → Console 编码（彩色、人类可读）
   - `console=false` → JSON 编码（标准日志格式）
4. 叠加 `zap.AddCaller()` + `zap.AddStacktrace(zap.ErrorLevel)`
5. `prod=true` 时额外使用 `zap.New(zapcore.NewTee(core), zap.Development())`

### 编码器差异

| 特性 | Console（console=true） | JSON（console=false） |
|------|------------------------|----------------------|
| 格式 | 人类可读，层级缩进 | 机器可解析 |
| 时间 | `2006-01-02 15:04:05.000000000` | Unix 时间戳（epoch） |
| 级别 | 小写彩色 | 小写纯文本 |
| 名称 Key | `Logger` | `logger` |
| 调用者 | `ShortCallerEncoder` | `ShortCallerEncoder` |

## slogzap — slog → Zap 桥接

### SlogZapProperties

```go
type SlogZapProperties struct {
    Logs map[string]logzap.ZlogProperties  // 名称 → Zap 配置
}
```

配置路径：`aglog.zap`

```yaml
aglog:
  zap:
    logs:
      zap1:           # handler 名称
        log_level: debug
        console: true
        stdout: true
      zap2:
        log_level: info
        log_file_name: "logs/app.log"
        max_size: 1024
        max_backups: 30
```

### NewSlogHandler4ZapProps

遍历 `props.Logs`，为每个配置创建 `NamedHandler`：

```go
for name, config := range props.Logs {
    zaplog := logzap.NewZapLogP(&config)
    opt := slogzap.Option{
        Level:     slog.LevelDebug,
        AddSource: true,
        Logger:    zaplog,
    }
    handler := opt.NewZapHandler()       // 创建 slog.Handler 包装
    nhandler := agslog.NewNamedHandler(name, handler)
    handlers = append(handlers, nhandler)
}
```

关键点：
- 每个 zap handler 有独立的文件/编码/级别配置
- 通过 `agslog.NewNamedHandler` 包装，支持名称路由
- 日志配置加载失败返回 `nil, nil`，**不中断应用启动**

### NewSlog4Zap（编程接口）

```go
func NewSlog4Zap(log *zap.Logger) (slog.Handler, error) {
    opt := slogzap.Option{
        Level:     slog.LevelDebug,
        Logger:    log,
        AddSource: true,
    }
    handler := opt.NewZapHandler()
    return agslog.NewNamedHandler("slog4zap", handler), nil
}
```

用于现有 `*zap.Logger` 实例的直接包装。

## 完整配置示例

### 多文件分流

```yaml
aglog:
  topHandler:
    - "zap1"
  zap:
    logs:
      zap1:
        log_level: debug
        console: true
        stdout: true
      trade_log:
        log_level: info
        log_file_name: "logs/trade.log"
        max_size: 512
        max_backups: 30
      heartbeat_log:
        log_level: info
        log_file_name: "logs/heartbeat.log"
        max_size: 256
```

### 代码使用

```go
// 获取命名 zap logger
tradeLog := agslog.GetSlogByName("trade_log")
tradeLog.Info("交易", "order_id", "12345", "amount", 100.50)

// 获取顶层 logger（zap1）
topLog := agslog.TopLogger()
topLog.Debug("系统调试信息")
```

## 注意事项

| 要点 | 说明 |
|------|------|
| 级别映射 | slog 级别 → zap 级别由 `slogzap.Option` 转换，`Level` 字段控制最小级别 |
| 调用链 | slog → slogzap zap handler → actual zap logger → lumberjack file |
| File + Console | 通过 `stdout: true` + `log_file_name` 实现同时输出 |
| 配置容错 | 绑定失败不中断应用，日志静默降级 |
| 日志轮转 | 使用 `lumberjack` 实现，配置 `max_size`/`max_backups`/`max_age`/`compress` |
