---
tags:
  - ag-core
  - aggo
  - bug
  - hertz
  - client
---

# Hertz 客户端生成代码未填充查询参数

**类型**：Bug
**状态**：待修复
**优先级**：高

## 描述

`aggo proto -p hertz -m client` 生成的 Hertz 客户端代码（V2 模板 `tpl_client_v2.go`）在构建 `RequestParam` 时，只设置了 `Method`、`Path`、`PathVars`，没有将非 path/body 字段映射到 `QueryParams`。

## 影响

使用生成的类型安全 client 调用 GET 方法时，查询参数不会拼到 URL 上。

例如：
```protobuf
rpc ListStudent(ListStudentRequest) returns (ListStudentResponse) {
    option (google.api.http) = {
        get: "student/list"
        response_body: "*"
    };
};
message ListStudentRequest {
    string name = 1;     // 应为 ?name=
    int32 age = 2;       // 应为 ?age=
}
```

生成的 client 代码：
```go
reqParam := &agclient.RequestParam{
    Method: "GET",
    Path:   "student/list",
    // Bug: QueryParams 为空，查询参数丢失
}
```

## 修复方向

修改 `tool/aggen/genhertz/tpl/tpl_client_v2.go`，在生成代码时：
1. 获取 proto 方法的所有非 path、非 body 字段
2. 将这些字段映射为 `map[string]string` 填入 `RequestParam.QueryParams`
3. 注意类型转换（`int32`→`strconv.Itoa`、`int64`→`strconv.FormatInt` 等）

## 相关文档

- [ProtoIDL规范](../../代码生成/Protobuf生成流程/02-ProtoIDL规范.md#已知缺陷)
