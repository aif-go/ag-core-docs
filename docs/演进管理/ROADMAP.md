---
title: ag-core 演进路线图
last_updated: 2026-06-23
tags:
  - ag-core
  - roadmap
---

# 🗺️ ag-core 演进路线图

> 近期（本月）→ 中期（1-3 个月）→ 远期（3 个月后）

## 近期

| 事项 | 状态 | 优先级 | 关联 |
|------|------|--------|------|
| 模块迁移至 github.com/aif-go/ag-core | ✅ 已完成 | — | commit 565daf0 |
| Log 归档文件名改用本地时间 | ✅ 已完成 | — | 变更记录/01, commit 45d5146 |
| aglog 日志级别中间件 | ✅ 已完成 | — | commit 746c275 |
| agmetadata 并发安全修复 | ✅ 已完成 | — | commit 931c33f |
| gen-go-db conditonwhere 自包含 | ✅ 已完成 | — | commit b769cca |
| svcgen proxy CallName 修复 | ✅ 已完成 | — | commit 8aca685 |
| 文档体系整理 | ✅ 已完成 | — | 演进管理目录重组 |
| AgSarama Partitioner 枚举统一 + 新增 Random/RoundRobin | ✅ 已完成 | — | commit 55b9042 |

## 中期

| 事项 | 优先级 | 状态 | 关联提案 |
|------|--------|------|---------|
| aggo upgrade basemode 修复 | ✅ 已完成 | — | commit 0b85bc9 |
| 杂项清理（废弃模块、设计图） | ✅ 已完成 | — | commits a8c5f50, df19595 |
| protoc-gen-go-agapi 名称修复 | ✅ 已完成 | — | commit 87ea824 |
| release v0.0.1-alpha.1 发布 | ⚠️ 阻塞中 | — | go.sum 需补全 |

## 待办优化提案

| 提案 | 优先级 | 预计排期 | 链接 |
|------|--------|---------|------|
| App 生命周期钩子 | P1 | 中期 | [待办优化](待办优化/App生命周期钩子.md) |
| AgCrypto 加密模块优化 | P2 | 中期 | [待办优化](待办优化/AgCrypto加密模块.md) |
| AgNacos 大量短连接问题 | P2 | 远期 | [待办优化](待办优化/AgNacos大量短连接问题.md) |

## 阻塞项

- **release v0.0.1-alpha.1**: 5 个子模块新增了 `ag-core v0.0.1-alpha.1` 依赖但 `go.sum` 未更新，需每个子模块跑 `go mod tidy` 后重新发布标签。
