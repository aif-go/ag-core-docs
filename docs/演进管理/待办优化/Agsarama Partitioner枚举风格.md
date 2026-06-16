---
tags:
  - ag-core
  - agsarama
  - future
  - optimization
  - discussion
---

# AgSarama Partitioner 枚举风格 — `Manual` 大小写不一致

> 讨论日期：2026-06-16 | 状态：待讨论

## 问题

`PartitionerType` 枚举中 `Manual` 的值首字母大写，而其他所有枚举均采用全小写风格，导致两处问题：

|| 问题 | 影响 |
|---|------|------|
| 1 | **命名风格不统一** — `hash` 全小写 vs `Manual` 首字母大写 | YAML 中 `partitioner: Manual` 显得突兀，开发者直觉写 `manual` |
| 2 | **静默降级** — `manual`（全小写）不匹配，通过 `default` 分支仅 warn 后返回零值 | Sarama 默认分区器是 `hash`，即写了 `manual` 实际用的是 `hash`，无声丢失语义 |

## 现状分析

### 枚举定义

```go
// config.go:261-266
type PartitionerType string

const (
    PartitionerTypeHash   PartitionerType = "hash"
    PartitionerTypeManual PartitionerType = "Manual"   // ← 首字母大写
)
```

### 默认行为的对比

| 枚举 | 值 | 大小写 |
|------|-----|--------|
| `hash` (默认) | `"hash"` | 全小写 ✅ |
| `Manual` | `"Manual"` | 首字母大写 ❌ |
| `none`, `gzip`, `snappy`, `lz4`, `zstd` | 全小写 | ✅ |
| `plain`, `scram-sha-256`, `oauth` 等 | 全小写 | ✅ |

### 静默降级逻辑

```go
// config.go:268-279
func (p PartitionerType) ToSarama() (sarama.PartitionerConstructor, error) {
    switch p {
    case PartitionerTypeHash:
        return sarama.NewHashPartitioner, nil
    case PartitionerTypeManual:
        return sarama.NewManualPartitioner, nil
    default:
        // ⚠️ 只有 warn，不报错
        slog.Warn(fmt.Sprintf("invalid partitioner type: %s, will ignore and use default by sarama", p))
        return nil, nil  // ← 返回 nil，sarama 使用默认值（hash）
    }
}
```

**场景**：开发者 YAML 中写 `partitioner: manual`（常识性的全小写）→ 匹配 `default` 分支 → 只打一行 warn（容易被忽略）→ 实际分区器是 hash → 消息分区行为与预期不一致。

## 优化方案

### 方案 A：统一为全小写 + 兼容旧值（推荐）

```go
// 1. 常量值改为全小写
const (
    PartitionerTypeHash   PartitionerType = "hash"
    PartitionerTypeManual PartitionerType = "manual"   // ← 改为全小写
)

// 2. 增加大小写不敏感匹配（兼容存量配置）
func (p PartitionerType) ToSarama() (sarama.PartitionerConstructor, error) {
    switch strings.ToLower(string(p)) {    // ← 大小写归一化
    case "hash":
        return sarama.NewHashPartitioner, nil
    case "manual":
        return sarama.NewManualPartitioner, nil
    default:
        return nil, fmt.Errorf("agsarama: invalid partitioner type: %q (valid: hash, manual)", p)
        //    ↑ 改为 error 而非静默降级
    }
}
```

#### 优点

- 枚举风格统一
- 存量 YAML 中写 `Manual`（大写）依然可用（大小写不敏感匹配）
- 新配置写 `manual`（小写）也能正确工作
- 无效值不再无声降级，用户第一时间知道写错了

#### 缺点

- 改常量值 = 修改包公共 API，理论上 `PartitionerTypeManual == "Manual"` 的 caller 会受影响（但该场景极少）

### 方案 B：仅加大小写不敏感 + error 反馈

不改常量值，只改 `ToSarama()` 逻辑：

```go
func (p PartitionerType) ToSarama() (sarama.PartitionerConstructor, error) {
    switch {
    case strings.EqualFold(string(p), "hash"):
        return sarama.NewHashPartitioner, nil
    case strings.EqualFold(string(p), "Manual"):
        return sarama.NewManualPartitioner, nil
    default:
        // 至少改为 error，不再静默
        return nil, fmt.Errorf("agsarama: invalid partitioner type: %q (valid: hash, manual)", p)
    }
}
```

#### 优点
- 不改常量，API 零影响
- 修复了最核心的两个问题：大小写敏感 + 静默降级

#### 缺点
- 「存量配置中写 `Manual`」仍然风格不统一，但功能正确

### 方案 C：加 `PartitionerTypeAny` + 大小写不敏感（最保守）

```go
// 新增一个别名常量用于兼容
const (
    PartitionerTypeHash        PartitionerType = "hash"
    PartitionerTypeManual      PartitionerType = "Manual"    // 保持原值
    PartitionerTypeManualLower PartitionerType = "manual"    // 新加别名
)
```

函数中两个 case 分支。不推荐，因为别名引入冗余。

## 方案对比

| 维度 | 方案 A（重命名+不敏感） | 方案 B（仅不敏感+error） | 方案 C（别名） |
|------|-----------------------|------------------------|---------------|
| 统一枚举风格 | ✅ `manual` 全小写 | ❌ `Manual` 仍突兀 | ❌ 两个别名更乱 |
| 兼容存量 | ✅ `Manual` 仍可用 | ✅ `Manual` 仍可用 | ✅ |
| 静默降级 | ✅ 改为 error | ✅ 改为 error | ❌ 仍通过 warn 降级 |
| 改动范围 | 常量 + 函数 | 仅函数 | 常量 + 函数 |
| 推荐度 | ⭐ 推荐 | ⭐ 最小改动可选 | ❌ 不推荐 |

## 初步结论

**倾向方案 A**，理由：

1. 枚举风格统一是长期收益：全小写的枚举在 YAML 配置中自然一致
2. 大小写不敏感匹配彻底消除陷阱：无论用户写 `Manual`、`manual`、`MANUAL` 都能正确工作
3. 改 error 而非静默降级：无效值尽早失败（fail fast），避免生产事故
4. 仅改 `config.go` 中的几个 case + 一行常量值，不影响其他包

## 待讨论

- 是否需要同步更新文档中 `Manual` 的写法为 `manual`？
- `PartitionerTypeManual` 这个 Go 常量名是否需要改成 `PartitionerTypeManual = "manual"`（值变但名不变，不影响 Go 代码引用）？
- 存量配置中写 `Manual` 的需不需要做迁移通知或兼容期？
