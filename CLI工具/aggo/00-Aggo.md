---
tags:
  - ag-core
  - cli
  - aggo
  - proto
---

# Aggo 主 CLI

> 路径：`tool/cmd/aggo/` | 代码生成的统一入口 CLI

`aggo` 是 ag-core 代码生成系统的**主命令**，封装了 proto 生成、项目创建、升级等核心操作。

## 子命令

| 命令 | 说明 |
|------|------|
| `aggo proto` | **核心命令**：protoc 包装器，从 `.proto` 生成全套微服务代码 |
| `aggo new` | 从模板创建新项目 |
| `aggo upgrade` | 升级 ag-core 框架依赖 |

## aggo proto 快速总结

`aggo proto` 是一个 `protoc` 包装命令，负责调度 7 个 protoc 插件完成代码生成。

```bash
aggo proto -p <plugins> -m <model> -e <proto-path> <idl-file-or-dir>
```

调用流程：
```
aggo proto
  ├── initProtos()     → 查找 proto 文件（递归目录）
  ├── initPlugins()    → 解析 -p 参数
  ├── initModels()     → 解析 -m 参数
  ├── initExtPlugins() → 解析 -P 参数（透传）
  ├── selectPlugins()  → 按 -p + -m 筛选 → 生成 protoc flags
  └── protoc <flags> <protos>
```

### 7 个插件一览

| 插件 | protoc 插件 | 输出内容 | model 注册 |
|------|------------|---------|:----------:|
| `go` | `protoc-gen-go` | `api/*.pb.go`（基础类型） | `base` |
| `api` | `protoc-gen-go-agapi` | `api/*_interface.go`（服务接口描述） | `base` |
| `server` | `protoc-gen-go-agserver` | `internal/adpgen/`（服务端适配器） | `base` |
| `service` | `protoc-gen-go-agservice` | `internal/service/` + `internal/svcgen/` | `server` |
| `kitex` | `protoc-gen-go-agkitex` | `internal/adpgen/kitex/`（Kitex RPC） | `server` + `client` |
| `hertz` | `protoc-gen-go-aghertz` | `internal/adpgen/hertz/`（Hertz HTTP） | `server` + `client` |
| `openapi` | `protoc-gen-openapi` | `openapi.yaml` | `base` |

### -m 参数的作用范围

`-m` 的过滤逻辑（`selectPlugins()`）：

```go
if modelAll || m == ModelBase || lo.Contains(models, m) {
    pgs = append(pgs, mps[m]...)
}
```

因为 `m == ModelBase` 条件，注册为 `"base"` 的插件**不受 `-m` 控制**，始终生成。

| 有效 | 条件 | 生成的插件 |
|:----:|------|-----------|
| ✅ | `-m server` | `service` + `kitex/server` + `hertz/server` |
| ✅ | `-m client` | `kitex/client` + `hertz/client` |
| ❌ | 任意值 | `go` / `api` / `server` / `openapi` — 始终生成 |

### 快速示例

```bash
# 一步生成全部（默认 -p all -m all）
aggo proto -e ./idl/api ./idl/api/student/student.proto

# 只生成服务端代码
aggo proto -p all -m server -e ./idl/api ./idl/api/student/student.proto

# 只生成特定插件
aggo proto -p go,api,server -e ./idl/api ./idl/api/student/student.proto
```

> 详细文档见：[[../../代码生成/Protobuf生成流程/00-Protobuf生成|Protobuf 生成流程]]
