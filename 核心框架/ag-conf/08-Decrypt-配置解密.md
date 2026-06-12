---
tags:
  - ag-core
  - ag-conf
  - security
  - decrypt
---

# 配置解密

> 对应文件：`decrypt.go`

## 概述

敏感配置（如数据库密码、API 密钥）可以加密存储，AgConf 在加载时自动检测并解密。

## 加密格式

```yaml
# 配置文件中的加密值
database:
  password: "{cipher}QzAxMjM0NTY3ODkwMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="
  username: "{cipher}YWRtaW4="

redis:
  password: "{cipher}cmVkaXNwYXNz"
```

`{cipher}` 前缀标记该值需要解密。

## 解密流程

有三层解密，分别在配置加载的不同阶段执行：

### 1. DecryptSystemConfig（系统配置解密）

```go
// 在 NewStandardEnvironment() 中立即执行
// 遍历 [SYS] 开头的属性源
// 解密后插入头部 [DECRYPT]-SystemEnvAndProp
```

### 2. DecryptLocalConfig（本地配置解密）

```go
// 在 LoadLocalConfig() 中执行
// 遍历 [LOCAL] 开头的属性源
// 解密后插入头部 [DECRYPT]-[LOCAL]
```

### 3. DecryptConfigSource / DecryptOtherConfig（其他源解密）

```go
// 用于 Nacos 等远程配置源更新时的解密
// 新增解密源放在原源前面，保证解密值优先
```

## 解密顺序与优先级

```
高优先级
  │
  ├── [DECRYPT]-SystemEnvAndProp    ← 系统配置解密结果
  ├── [DECRYPT]-[LOCAL]             ← 本地配置解密结果
  ├── [DECRYPT]-NacosDataId         ← Nacos 配置解密结果
  │
低优先级（原始加密值作为 fallback）
```

解密后的属性源**插入在原始加密源之前**，所以：

- `GetProperty("db.password")` 返回**解密后的明文**
- 如果解密失败，原始的 `{cipher}...` 值被后面的源覆盖（安全）

## 解密器

使用 `ag_crypto.GetEncrytorPrimary()` 获取主加密器进行解密：

```go
import "github.com/aif-go/ag-core/ag/ag_crypto"

// 当前实现：Base64 解码
// 后续可替换为 AES/RSA 等真实加密
plaintext, err := ag_crypto.GetEncrytorPrimary().Decrypt(ciphertext)
```

## 常量

```go
const ConstEncryptKeyWords = "{cipher}"

var (
    SourceKeyDecryptSystem = "[DECRYPT]-SystemEnvAndProp"
    SourceKeyDecryptLocal  = "[DECRYPT]-[LOCAL]"
)
```
