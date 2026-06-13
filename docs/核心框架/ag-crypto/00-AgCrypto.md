---
tags:
  - ag-core
  - ag-crypto
  - encrypt
  - decrypt
  - architecture
---

# AgCrypto — 加密模块

> 路径：`ag/ag_crypto/` | 文本加解密接口 + 默认 Base64 实现，供 ag_conf 解密配置值

## 概述

AgCrypto 提供 `ITextEncryptor` 接口和全局加密器注册机制。ag_conf 在加载配置时，通过 `GetEncrytorPrimary()` 获取当前加密器，对以 `{cipher}` 为前缀的配置值自动解密。

```
配置值 "{cipher}xxxxx"
    │
    ▼
ag_conf.CreateOrUpdateDecryptForPropertySource
    │
    ▼
ag_crypto.GetEncrytorPrimary().Decrypt("xxxxx")
    │
    ▼
明文值 → 注入 [DECRYPT]-* PropertySource
```

## 接口

```go
// ag/ag_crypto/encryptor.go:5-11
type ITextEncryptor interface {
    Name() string
    Encrypt(plaintext string) (string, error)   // 加密
    Decrypt(ciphertext string) (string, error)   // 解密
}
```

### 全局加密器

```go
var DefaultEncryptorPrimary ITextEncryptor = Base64Encryptor  // 默认

func GetEncrytorPrimary() ITextEncryptor                        // 获取
func SetEncryptorPrimary(encryptor ITextEncryptor)              // 替换
```

默认使用 `Base64Encryptor`，通过 `SetEncryptorPrimary` 可替换为自定义实现（如 AES、SM4）。

## 内置实现：Base64Encryptor

```go
// ag/ag_crypto/base64_encryptor.go:7-9
type Base64Encrypt struct{}
var Base64Encryptor = &Base64Encrypt{}

func (enc *Base64Encrypt) Name() string { return "Base64" }
func (enc *Base64Encrypt) Encrypt(plaintext string) (string, error) {
    return base64.StdEncoding.EncodeToString([]byte(plaintext)), nil
}
func (enc *Base64Encrypt) Decrypt(ciphertext string) (string, error) {
    bytearr, err := base64.StdEncoding.DecodeString(ciphertext)
    return string(bytearr), err
}
```

## 自定义加密器

实现 `ITextEncryptor` 接口，在应用启动时注册：

```go
import "github.com/aif-go/ag-core/ag/ag_crypto"

type SM4Encryptor struct{}

func (e *SM4Encryptor) Name() string                             { return "SM4" }
func (e *SM4Encryptor) Encrypt(plaintext string) (string, error) { /* SM4 加密 */ }
func (e *SM4Encryptor) Decrypt(ciphertext string) (string, error) { /* SM4 解密 */ }

func init() {
    ag_crypto.SetEncryptorPrimary(&SM4Encryptor{})
}
```

注册后，所有配置中的 `{cipher}...` 值都会使用新加密器解密。

## 与 ag_conf 的协作

解密流程在 `ag_conf/decrypt.go` 中：

1. 遍历 PropertySource 的所有 key-value
2. 值以 `{cipher}` 开头 → 去掉前缀，调用 `GetEncrytorPrimary().Decrypt()`
3. 明文值写入新的 `[DECRYPT]-*` PropertySource
4. 通过 `AddBefore` 插入到原始源之前，优先级略高

```go
// ag_conf/decrypt.go:78-91
for key, value := range source {
    ciphertext, ok := value.(string)
    if ok && strings.HasPrefix(ciphertext, ConstEncryptKeyWords) {
        ciphertext = ciphertext[len(ConstEncryptKeyWords):]   // 去掉 {cipher} 前缀
        plaintext, err := encryptor.Decrypt(ciphertext)
        decryptSource[key] = plaintext
    }
}
```

## 文件结构

```
ag/ag_crypto/
├── encryptor.go           # ITextEncryptor 接口 + 全局加密器 get/set
└── base64_encryptor.go    # 默认 Base64 实现
```
