---
tags:
  - ag-core
  - proto
  - idl
  - specification
---

# Proto IDL 定义规范

> 面向业务开发者：编写 `.proto` 定义文件的规范与最佳实践

---

## 文件结构

### 目录位置

```
idl/api/<service-name>/<service-name>.proto
```

示例：`idl/api/student/student.proto`

### 基本模板

```protobuf
syntax = "proto3";                          // 必须 proto3

package student;                            // 包名

option go_package = "myproject/api/student";  // Go 包路径（含模块名）

import "google/api/annotations.proto";       // HTTP 注解依赖

// Service 定义
service StudentService {
    rpc GetStudent(GetStudentReq) returns (GetStudentResp) {
        option (google.api.http) = {
            get: "student/get"
            response_body: "*"
        };
    };
}

// 请求消息
message GetStudentReq {
    int64 id = 1;
}

// 响应消息
message GetStudentResp {
    int64 id = 1;
    string name = 2;
    int32 age = 3;
}
```

---

## `google.api.http` 用法全解

### 基本 HTTP 方法

| Proto 写法 | HTTP 方法 | 说明 |
|-----------|----------|------|
| `get: "path"` | GET | 查询 |
| `post: "path"` | POST | 创建/提交 |
| `put: "path"` | PUT | 全量更新 |
| `delete: "path"` | DELETE | 删除 |
| `patch: "path"` | PATCH | 部分更新 |

### 路径参数（`:Name`）

```protobuf
rpc DeleteStudent(DeleteStudentReq) returns (DeleteStudentResp) {
    option (google.api.http) = {
        delete: "student/:Id"
    };
};

// 请求消息中必须有 Id 字段
message DeleteStudentReq {
    int64 id = 1;      // proto id → Go Id → 路径 :Id
}
```

**命名规则**：路径变量 `:Name` 必须与 proto 字段的 **Go 导出名**一致。

| proto 字段 | Go 导出名 | 路径变量 |
|-----------|----------|---------|
| `id` | `Id` | `:Id` |
| `student_id` | `StudentId` | `:StudentId` |
| `stuno` | `Stuno` | `:Stuno` |

### 请求体（`body`）

```protobuf
rpc CreateStudent(CreateStudentReq) returns (CreateStudentResp) {
    option (google.api.http) = {
        post: "student/create"
        body: "*"              // 整个请求消息作为 JSON body
    };
};

// 部分字段作为 body
rpc UpdateStudent(UpdateStudentReq) returns (UpdateStudentResp) {
    option (google.api.http) = {
        put: "student/:Id"
        body: "student"        // 只取 student 字段作为 body
    };
};

message UpdateStudentReq {
    int64 id = 1;              // 路径参数（不在 body 中）
    Student student = 2;       // body 字段
}
```

### 响应体（`response_body`）

```protobuf
rpc GetStudent(GetStudentReq) returns (GetStudentResp) {
    option (google.api.http) = {
        get: "student/get"
        response_body: "*"      // 返回整个响应消息
    };
};
```

> 不加 `response_body` 时返回完整响应消息，加 `response_body: "*"` 时返回消息内容。

### 多路由规则（`additional_bindings`）

```protobuf
rpc GetStudent(GetStudentReq) returns (Student) {
    option (google.api.http) = {
        get: "student/get/:Stuno"
        response_body: "*"
        additional_bindings: [
            {
                get: "student/get"      // 同时支持无路径参数模式
                response_body: "*"
            }
        ]
    };
};
```

---

## 查询参数：`?a=xx&b=xx`

### 原理

在 `google.api.http` 中，**请求消息中既不是路径参数、也不是 body 的字段，自动成为查询参数**。

```protobuf
message ListStudentRequest {
    string name = 1;         // 查询参数 ?name=
    int32 age = 2;           // 查询参数 ?age=
    int32 pageNum = 3;       // 查询参数 ?pageNum=
    int32 pageSize = 4;      // 查询参数 ?pageSize=
}

service StudentService {
    rpc ListStudent(ListStudentRequest) returns (ListStudentResponse) {
        option (google.api.http) = {
            get: "student/list"            // 没有 body，没有 :param
            response_body: "*"
        };
    };
}
```

**实际 HTTP 请求**：
```
GET /student/list?name=张三&age=20&pageNum=1&pageSize=20
```

### 路径参数 + 查询参数混用

```protobuf
message FindByAgeRequest {
    int32 age = 1;           // 路径参数 :Age
    string stuno = 2;        // 路径参数 :Stuno
    int32 pageNum = 3;       // 查询参数 ?pageNum=
}

rpc FindByAge(FindByAgeRequest) returns (FindByAgeResponse) {
    option (google.api.http) = {
        get: "student/findByAge/:Age/:Stuno"   // age 和 stuno 是路径参数
        response_body: "*"
    };
};
```

**请求 URL**：`GET /student/findByAge/20/S001?pageNum=1`

### 服务端绑定机制

生成的 Handler 中：

| 条件 | 绑定方式 | 绑定的字段 |
|------|---------|-----------|
| 无 `body` | `BindQuery(&in)` | 所有非 path 字段 |
| 有 `body` | `BindByContentType(&in.Body)` | body 字段 |
| 有路径参数 | `BindPath(&in)` | 路径参数对应字段 |

### 注意事项

- proto 定义中**不需要写 `?` 符号或 URL 编码**，框架自动处理
- 查询参数字段的类型支持：`int32`、`int64`、`string`、`bool`、`float`、`double`
- `repeated` 字段作为查询参数时，多个值用 `&key=val1&key=val2` 传递

---

## 路径规则

### 路径格式

| 格式 | 示例 | 说明 |
|------|------|------|
| 静态路径 | `"student/list"` | 固定路径 |
| 带路径参数 | `"student/get/:Id"` | `:Name` 会被替换为实际值 |
| 多级路径 | `"api/v1/student/list"` | 支持任意层级 |
| 多路径参数 | `"student/:Id/class/:ClassId"` | 多个参数用 `/` 分隔 |

### 路径前缀规范

- HTTP 路径**不需要以 `/` 开头**，如 `"student/get"` 而非 `"/student/get"`
- 路径中不要包含查询字符串（`?key=val`），查询参数通过 proto 消息字段自动绑定

---

## 命名规范

| 元素 | 规范 | 示例 |
|------|------|------|
| Service 名 | PascalCase | `StudentService` |
| RPC 方法名 | PascalCase | `GetStudent` |
| Message 名 | PascalCase + Req/Resp 后缀 | `GetStudentReq` |
| 字段名 | snake_case | `student_id` |
| 文件名 | snake_case | `student_service.proto` |
| go_package | 完整模块路径 | `myproject/api/student` |

---

## 数据类型映射

| Proto 类型 | Go 类型 | 说明 |
|-----------|---------|------|
| `int32` | `int32` | 32 位整数 |
| `int64` | `int64` | 64 位整数（ID、时间戳） |
| `string` | `string` | 文本 |
| `bool` | `bool` | 布尔值 |
| `float` | `float32` | 32 位浮点 |
| `double` | `float64` | 64 位浮点 |
| `bytes` | `[]byte` | 二进制数据 |
| `repeated T` | `[]T` | 列表 |
| `map<K,V>` | `map[K]V` | 映射 |
| `google.protobuf.Timestamp` | `timestamppb.Timestamp` | 时间戳 |
| `google.protobuf.Struct` | `structpb.Struct` | 动态 JSON |

---

## 流式方法

```protobuf
// 服务端流：请求单次，响应流式推送
rpc ListStudents(ListStudentsReq) returns (stream ListStudentsResp);

// 客户端流：请求流式，响应单次
rpc BatchCreate(stream CreateReq) returns (CreateResp);

// 双向流：双方均为流式
rpc Chat(stream ChatReq) returns (stream ChatResp);
```

> 流式方法**不支持** HTTP 注解（`option (google.api.http)`），仅通过 gRPC 协议使用。

---

## RESTful 风格参考

| 操作 | Proto RPC | HTTP |
|------|----------|------|
| 创建 | `CreateXxx` | `POST /xxx` + `body: "*"` |
| 查询（单条） | `GetXxx` | `GET /xxx/:Id` |
| 查询（列表） | `ListXxx` | `GET /xxx/list` + 查询参数 |
| 更新 | `UpdateXxx` | `PUT /xxx/:Id` + `body: "*"` |
| 部分更新 | `PatchXxx` | `PATCH /xxx/:Id` + `body: "*"` |
| 删除 | `DeleteXxx` | `DELETE /xxx/:Id` |

---

## 已知缺陷

### Bug：生成的 Hertz 客户端未填充查询参数

**状态**：待修复 | **影响范围**：aggo 生成的 V2 Hertz 客户端（`tpl_client_v2.go`）

**描述**：生成的客户端代码构建 `RequestParam` 时，只设置了 `Method`、`Path`、`PathVars`，**没有将非 path/body 字段映射到 `QueryParams`**：

```go
// 生成的 client code — QueryParams 为空
reqParam := &agclient.RequestParam{
    Method: "GET",
    Path:   "student/list",
    // Bug: 没有填充 QueryParams，查询参数丢失
}
rerr := c.DoRequest(ctx, reqParam, nil, &resp, opts...)
```

**后果**：使用生成的类型安全 client 调用 GET 方法时，请求消息中的查询参数字段不会拼到 URL 上。

**临时规避**：退回到 `HertzBaseClient.DoRequest` 手动传入 `QueryParams`：

```go
err := cli.DoRequest(ctx, &agclient.RequestParam{
    Method: "GET",
    Path:   "student/list",
    QueryParams: map[string]string{
        "name":     req.GetName(),
        "pageNum":  fmt.Sprintf("%d", req.GetPageNum()),
    },
}, nil, &resp)
```

**修复方向**：修改 `tool/aggen/genhertz/tpl/tpl_client_v2.go` 模板，在生成代码时自动将非 path/body 字段填入 `RequestParam.QueryParams`。
