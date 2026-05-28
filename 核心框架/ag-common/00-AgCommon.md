---
tags:
  - ag-core
  - ag-common
  - index
---

# AgCommon 公共工具

> 路径：`ag/ag_common/`
>
> ag-core 框架的公共工具包，提供各模块通用的基础设施。每个独立功能作为一个子包，可按需引入。

## 文件结构

```
ag/ag_common/
├── pkg.go                      ← 包声明（可放通用类型/函数）
│
├── agmetadata/                 ← 上下文元数据传播
│   └── metadata.go
│
└── ...                         ← 更多子包待扩展
```

## 子模块一览

| 子包 | 路径 | 文档 | 状态 |
|------|------|------|------|
| agmetadata | `ag/ag_common/agmetadata/` | [[01-AgMetadata\|上下文元数据]] | ✅ 已完成 |
| — | — | — | 📝 待扩展 |

---

## 待扩展

`ag_common` 的设计定位是存放各模块通用的基础设施，未来可在此目录下添加的子包示例：

| 候选子包 | 说明 |
|----------|------|
| `sliceutil` | 切片操作工具 |
| `stringutil` | 字符串处理工具 |
| `conv` | 类型转换工具 |
| `retry` | 重试机制 |

> *按需添加，避免过度抽象。*
