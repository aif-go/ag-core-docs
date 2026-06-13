## 1. 创建项目
`aggo new  -r http://github.com/aif-go/ag-layout-demo.git -b base agaidevdemo`
使用项目模版创建项目：agaidevdemo

## 2. 定义api接口
`idl/api/student/student.proto`
- 要了解grpc 和 http 定义规则
## 3. 生成代码
### - 生成接口代码
- `aggo proto -p go -m server -e ./idl/api  ./idl/api/student/student.proto`
	生成`api/student/student.pb.go` 接口请求
- `aggo proto -p api -m server -e ./idl/api  ./idl/api/student/student.proto`
	生成`api/student/agserver_student_interface.go` 接口描述

### - 生成服务端代码
#### server基础
- `aggo proto -p server -m server -e ./idl/api  ./idl/api/student/student.proto`
	生成：
	- `internal/adpgen/zfx_adapter.go` 
	- `internal/adpgen/adpinit/zfx_adapter_init.go`
#### kitex服务端adp代码
- `aggo proto -p kitex -m server -e ./idl/api  ./idl/api/student/student.proto`
	生成：
	- `internal/adpgen/kitex/studentservice/agkitex_studentservice_server.go`
	- `internal/adpgen/kitex/studentservice/agkitex_studentservice_fx.go`
	- `internal/adpgen/adpinit/zfx_agkitex_student_studentservice_adpinit.go`
#### hertz服务端adp代码
- `aggo proto -p hertz -m server -e ./idl/api  ./idl/api/student/student.proto`
	生成：
	- `internal/adpgen/hertz/studentservice/aghertz_studentservice_server.go`
	- `internal/adpgen/hertz/studentservice/aghertz_studentservice_fx.go`
	- `internal/adpgen/adpinit/zfx_aghertz_student_studentservice_adpinit.go`
#### 服务端service代码
- `aggo proto -p service -m server -e ./idl/api  ./idl/api/student/student.proto`
	生成：
	- `internal/svcgen/zfx_service.go`
	- `internal/svcgen/zfx_agservice_proxy_student.go`
	- `internal/svcgen/agservice_studentservice_proxy.go`
	- `internal/service/agservice_studentservice.go`此为模板代码，不会被重新覆盖，业务逻辑以该文件为入口进行开发

### - 生成客户端代码
> 需要调用其他为微服务时，要用对方的proto接口定义生成相关client
#### hertz客户端代码
- `aggo proto -p hertz -m client -e ./idl/api  ./idl/api/student/student.proto`
	生成：
	- `internal/adpgen/hertz/studentservice/aghertz_studentservice_client.go`
#### kitex客户端代码
- `aggo proto -p kitex -m client -e ./idl/api  ./idl/api/student/student.proto`
	生成：
	- `internal/adpgen/kitex/studentservice/agkitex_studentservice.go`
	- `internal/adpgen/kitex/studentservice/agkitex_studentservice_client.go`
	- `internal/adpgen/kitex/studentservice/agkitex_studentservice_agclient.go`

## 4. 实现业务逻辑
- `internal/service/agservice_studentservice.go`为入口，开展业务逻辑实现
- 编写微服务调用等
- 数据库访问等

## 5. 构建运行
``` bash
cd cmd/server
go build
./server

# http访问测试：
curl localhost:9997/student/get
```

## 附录样板代码目录结构
```
agaidevdemo
├── api
│   └── student
│       ├── agserver_student_interface.go
│       └── student.pb.go
├── cmd
│   └── server
│       ├── app.yml
│       ├── main.go
│       └── server
├── go.mod
├── go.sum
├── idl
│   └── api
│       └── student
│           └── student.proto
├── internal
│   ├── adpgen
│   │   ├── adpinit
│   │   │   ├── zfx_adapter_init.go
│   │   │   ├── zfx_aghertz_student_studentservice_adpinit.go
│   │   │   └── zfx_agkitex_student_studentservice_adpinit.go
│   │   ├── hertz
│   │   │   └── studentservice
│   │   │       ├── aghertz_studentservice_client.go
│   │   │       ├── aghertz_studentservice_fx.go
│   │   │       └── aghertz_studentservice_server.go
│   │   ├── kitex
│   │   │   └── studentservice
│   │   │       ├── agkitex_studentservice_agclient.go
│   │   │       ├── agkitex_studentservice_client.go
│   │   │       ├── agkitex_studentservice_fx.go
│   │   │       ├── agkitex_studentservice.go
│   │   │       └── agkitex_studentservice_server.go
│   │   └── zfx_adapter.go
│   ├── init.go
│   ├── repository
│   │   └── idl
│   │       └── student.xlsx
│   ├── service
│   │   └── agservice_studentservice.go
│   ├── svcgen
│   │   ├── agservice_studentservice_proxy.go
│   │   ├── zfx_agservice_proxy_student.go
│   │   └── zfx_service.go
│   └── zfx_internal.go
└── third_party
	...proto相关依赖
```