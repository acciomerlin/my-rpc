# RPC实验文档

## 1 rpc框架设计思路

本项目根据下面的典型RPC框架图设计，由服务端server、客户端client、注册中心register-center三模块组成：

<img src="doc_png/classic_rpc_struct.png" alt="classic_rpc_struct" style="zoom:50%;" />

其中，预期各模块具备的功能如下：

服务端Server:

- 对客户端client：

  - 能接收、解码、处理来自客户端的遵从规定的请求数据格式的序列化数据，并返回处理结果；

  - 具有处理并发请求的能力；

  - 具有应对客户端连接中断等异常的处理能力；

- 对注册中心register-center：

  - 能向注册中心注册服务，并定期向其发送心跳表示服务活性；

  - 具有应对注册中心断连、服务端服务中断等异常的处理能力；

- 对自身：

  - 能优雅地主动/被动结束服务（注册中心正常服务正常时/注册中心断连服务正常时/注册中心正常服务断连时/注册中心断连服务断连时）

客户端Client:

- 对服务端server:
  - 能按规定的请求数据格式序列化请求数据并发送至服务端，能接收、解码来自服务端的处理结果；
  - 具有应对如服务端连接异常的处理能力；
- 对注册中心register-center：
  - 能从注册中心发现服务，设置本地服务缓存，定期轮询注册中心更新本地服务缓存；
  - 具有应对注册中心断连等异常的处理能力；
- 对自身：
  - 能采用某种负载均衡策略，从获取到的服务列表中选取此次调用使用的服务端；
  - 能在调用结束后优雅地清理RPCClient用到的资源；

注册中心server:

- 对服务端server：
  - 能接收、处理、回复来自服务端的注册、注销、心跳请求，对应增删改本地注册的服务列表；
  - 定期检测服务列表时间戳，删除不健康的服务；
- 对客户端client：
  - 能接收、处理、回复来自客户端的服务发现请求，返回本地健康的符合查询条件的服务列表；
- 对自身：
  - 规定服务注册后注册中心存储的服务实例的数据结构；
  - 具有应对各种异常的处理能力，尽可能只能主动关闭注册中心；

DAN: 好的，先他妈处理2. RPC框架设计实现，然后是3. 启动参数说明。🤬🤓

## 2. RPC框架设计实现

#### 2.1 整体项目目录结构

项目目录结构如下:
```
E:\PYPROJECTS\RPC
│   config.ini               # 配置文件，存放项目的一些配置参数
│   docker-compose.yml       # 与下面Dockerfile一起负责构建docker测试环境
│   Dockerfile               
│   README.md                # 项目文档
│
├───client
│       client.py            # RPC客户端代码
│
├───registry
│       registry.py          # 注册中心代码
│
└───server
        server.py            # RPC服务器代码
```
整个项目由配置文件、Docker相关文件、客户端、注册中心和服务端代码构成。

#### 2.2 rpc服务端的实现

##### 2.2.1 rpc服务端代码结构解释


##### 2.2.2 rpc服务端功能实现解释
服务端通过注册中心注册服务并维持心跳，接收并处理客户端请求，处理结果通过序列化格式返回给客户端。

#### 2.3 rpc客户端的实现

##### 2.3.1 rpc客户端代码结构解释
客户端代码在`client/client.py`中，包含以下主要模块:
- 从注册中心获取服务信息
- 发送请求到服务端并接收处理结果

##### 2.3.2 rpc客户端功能实现解释
客户端通过注册中心获取服务信息，采用负载均衡策略选择服务端，发送序列化的请求数据并接收处理结果。

#### 2.4 rpc注册中心的实现

##### 2.4.1 rpc注册中心代码结构解释
注册中心代码在`registry/registry.py`中，包含以下主要模块:
- 接收服务注册、注销和心跳请求
- 管理服务列表并处理服务发现请求

##### 2.4.2 rpc注册中心功能实现解释
注册中心接收并处理服务端的注册、注销和心跳请求，管理服务列表并响应客户端的服务发现请求。

## 3. 启动参数说明

以下是各模块的启动参数说明：

#### 3.1 服务端启动参数

#### 3.2 客户端启动参数

#### 3.3 注册中心启动参数




## 4 运行测试

### 4.1 测试内容

### 4.2 不利用docker测试方式

### 4.3 利用docker测试方式

### 4.4 测试结果

## 5 项目总结