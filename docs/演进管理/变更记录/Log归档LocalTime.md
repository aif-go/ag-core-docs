---
title: "Log 归档文件名时间改用本地时间"
status: 已实现
proposed: 2026-06-10
implemented: 2026-06-11
commit: 45d5146
tags:
  - ag-core
  - ag-log
  - zaplog
---

# Log 归档文件名时间改用本地时间

## 问题

日志文件滚动归档时（lumberjack），压缩文件名中的时间戳使用 UTC 时间，比北京时间晚 8 小时，造成归档文件名时间与实际时间不符。

## 解决方案

`ZlogProperties` 新增 `LocalTime bool` 配置项（默认 `true`），传递给 lumberjack 的 `LocalTime` 字段。

## 配置

```yaml
aglog:
  zap:
    logs:
      app:
        log_file_name: /var/log/app/app.log
        local_time: true    # 默认 true，可不配
```

如需 UTC 行为：`local_time: false`。

## 变更记录

- `logzap/zaplog.go` — `ZlogProperties.LocalTime` 新增配置项
- `logzap/zaplog.go` — `NewZapLogP` 传入 lumberjack
- 配置默认值：`true`（本地时间），而非一开始计划中的 `false`
