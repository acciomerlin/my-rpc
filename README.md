# RPC实验文档

## 一、rpc框架设计思路

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

## 二、RPC框架设计实现

### 2.1 整体项目目录结构

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

### 2.2 rpc服务端的实现

server.py用到的库：
```python
import argparse
import configparser
import http.client
import json
import math
import os
import socket
import threading
import time
from datetime import datetime
```
server.py代码结构：

<img src="doc_png/server.png" alt="server" style="zoom: 67%;" />

其中：

- **InstanceMeta**: 与注册中心通信，注册与保活服务时约定的服务实例数据结构，传输自身使用的序列化协议(如json)、监听的ip与端口、注册状态与一携带额外信息的字典parameters，InstanceMeta初始化方法与打包服务实例数据的to_dic方法展示如下：

```python
class InstanceMeta:
    def __init__(self, protocol=None, host=None, port=None):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.status = None
        self.parameters = {}

    def to_dict(self):
        return {
            'protocol': self.protocol,
            'host': self.host,
            'port': self.port,
            'status': self.status,
            'parameters': self.parameters
        }
```

- **Logger**: 用于输出与存储日志信息，默认不存储仅输出，分为info与error两个级别，代码解释：：

```python
class Logger:
    def __init__(self, save_log=False):
        self.save = save_log
		# ...
```

- **ServerStub**: 作为服务端代理，负责处理服务端方法的注册与对注册方法的调用请求，代码解释：：

```python
class ServerStub:
    def __init__(self, logger):
        self.services = {}
        self.logger = logger

    def register_services(self, method, name=None):
        """
        处理方法注册，把注册的方法以方法名为键，函数为值（python中的函数是第一类对象（first-class
        objects），可以像其他对象一样被传递、赋值、存储在如列表、字典等数据结构中）的方式存于成员变量services中
        :param method: function 要注册的方法
        :param name: string 要注册方法的名称，为空则默认为注册方法函数名
        """
        if name is None:
            name = method.__name__
        self.services[name] = method
        self.logger.info(f"注册方法：{name}")

    def call_method(self, req, client_addr):
        """
        处理方法的调用，解析请求，从 services 中寻找请求的注册方法，返回调用成功或失败的回复消息
        :param req: 以json格式序列化后的请求方法调用消息
        :param client_addr: 调用方的 ip 地址，运行日志记录需要
        :return: reply: 序列化后的调用结果信息（调用成功/调用不存在方法/调用方法参数错误/其余方法处理时发生错误）
        """
        req_data = json.loads(req.decode('utf-8'))
        self.logger.info(f"来自客户端{str(client_addr)}的请求数据{req_data}")
        method_name = req_data['method_name']
        method_args = req_data['method_args']
        method_kwargs = req_data['method_kwargs']
        try:
            res = self.services[method_name](*method_args, **method_kwargs)
        except KeyError:
            res = f"No service found for: {method_name}"
        except TypeError as e:
            res = f"Argument error: {e}"
        except Exception as e:
            res = f"Error calling method: {e}"
        reply_raw = {"res": res}
        reply = json.dumps(reply_raw).encode('utf-8')
        self.logger.info(f"给客户端{str(client_addr)}的回复{reply}")
        return reply
```

- **RegistryClient**: 负责注册中心相关的功能，向注册中心注册、注销服务，并能定期向其发送心跳保持服务活性，代码解释：：

```python
class RegistryClient:
    def __init__(self, logger):
        """
        初始化成员信息
        self.registry_host : string 配置文件中读入的注册中心的 IP
        self.registry_port : int 配置文件中读入的注册中心的端口号
        self.first_register : bool 区分服务端发送的是注册服务请求还是心跳请求
        self.strong_stop_event : threading.Event() RPCServer不再监听/主线程出现问题时被set的event，用于停止给注册中心发心跳的线程，由外界传入此 event
        self.weak_stop_event : threading.Event() 与注册中心通信出现异常，不该再与注册中心通信是被set的event，用于停止给注册中心发心跳的线程，内部设置
        :param logger: 运行日志
        """

    def register_to_registry(self, host, port):
        """
        通过发送HTTP POST请求，向注册中心注册服务，得到注册请求的结果
        也是服务向注册中心发送心跳的方式，通过成员变量 self.first_register 判断是注册请求还是心跳发送请求
        
        :param host: 注册服务的IP地址
        :param port: 注册服务的端口
        """
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port)
        headers = {'Content-type': 'application/json'}

        if host == '0.0.0.0':
            instance = InstanceMeta("json", socket.gethostbyname(socket.gethostname()), port)
        else:
            instance = InstanceMeta("json", host, port)

        instance.add_parameters({'ip_proto': 'ipv4'})
        instance_data = json.dumps(instance.to_dict())

        conn.request("POST", "/myRegistry/register?proto=json", instance_data, headers)
        response = conn.getresponse()
        if response.status == 200:
            response_data = json.loads(response.read().decode())
            if self.first_register:
                self.logger.info(f"SUCCESSFULLY REGISTER TO REGISTRY: {response_data}")
                self.first_register = False
            else:
                self.logger.info(f"SEND ❤ TO REGISTRY")
        else:
            if self.first_register:
                self.logger.error(f"FAIL TO REGISTER TO REGISTRY: {response.read().decode()}")
            else:
                self.logger.error(f"FAIL TO SEND ❤ TO REGISTRY")

        conn.close()

    def unregister_from_registry(self, host, port):
        """
        通过发送HTTP POST请求，向注册中心注销服务，得到注销请求的结果
        
        :param host: 注册服务的IP地址
        :param port: 注册服务的端口
        """
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port)
        headers = {'Content-type': 'application/json'}

        if host == '0.0.0.0':
            instance = InstanceMeta("json", socket.gethostbyname(socket.gethostname()), port)
        else:
            instance = InstanceMeta("json", host, port)
        instance_data = json.dumps(instance.to_dict())

        try:
            conn.request("POST", "/myRegistry/unregister?proto=json", instance_data, headers)
            response = conn.getresponse()
            if response.status == 200:
                response_data = json.loads(response.read().decode())
                self.logger.info(f"SUCCESSFULLY UNREGISTERED TO REGISTRY: \n{response_data}")
            else:
                self.logger.error(
                    f"FAIL TO UNREGISTER TO REGISTRY: {response.read().decode()}")
        except (TimeoutError, ConnectionRefusedError) as e:
            self.logger.error(f'与注册中心通信时发生错误：{e}，停止与注册中心联系')

        conn.close()

    def register_send_heartbeat(self, host, port, stop_e):
        """
        注册服务并定期发送心跳到注册中心，直到接收到停止信号。

        :param host: 注册服务的IP地址
        :param port: 注册服务的端口
        :param stop_e: 赋值 self.strong_stop_event 停止事件，用于控制心跳发送的停止
        """
        self.strong_stop_event = stop_e
        while not self.strong_stop_event.is_set() and not self.weak_stop_event.is_set():
            try:
                self.register_to_registry(host, port)
                time.sleep(9)
            except (TimeoutError, ConnectionRefusedError) as e:
                self.logger.error(f'与注册中心通信时发生错误，停止与注册中心联系：{e}')
                self.weak_stop_event.set()
                
```

- **TCPServer**: 负责TCP连接相关功能，监听、并发处理客户端请求，并能够在收到停止信号时优雅关闭，代码解释：

```python
# TCPServer: 负责处理TCP连接，监听客户端请求，并能够在收到停止信号时优雅关闭
class TCPServer:
    def __init__(self, host, port, logger, stop_event):
        self.port = port # 服务器监听的IP地址
        self.host = host # 服务器监听的端口
        self.logger = logger # 运行日志
        self.sock = None #服务器的Socket对象，用于监听和接受客户端连接
        self.addr_type = None # 服务器监听的IP地址类型，支持IPV4/IPV6
        self.stop_event = stop_event # 停止事件，用于控制TCPServer的停止
        self.set_up_socket() # 初始化 self.sock

    def set_up_socket(self):
        """
        设置服务器的Socket，根据host确定使用IPv4还是IPv6
        并配置Socket选项，绑定地址和端口，设置Socket为监听模式，指定连接请求的最大等待队列长度
        """
        if '.' in self.host:
            self.addr_type = socket.AF_INET
        else:
            self.addr_type = socket.AF_INET6
        self.sock = socket.socket(self.addr_type, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(10)

    def send_tcp_server_stop_signal(self):
        """
        发送TCP服务器停止信号
        通过本地创建一个TCP客户端连接到服务器并马上关闭以触发服务器的accept方法
        解决accept不设timeout会无限期阻塞，无法进入下一次循环导致无法接收到停止信号的问题
        """
        h_socket = socket.socket(self.addr_type, socket.SOCK_STREAM)
        try:
            h_socket.connect(('localhost', self.port))
            h_socket.close()
        except Exception as e:
            e_name = e.__class__.__name__
            self.logger.info(f"Received Exception {e_name}, stopping...")

    def loop_detect_stop_signal(self):
        """
        循环检测停止事件，如果检测到停止事件被设置，则发送服务器停止信号
        """
        while True:
            time.sleep(0.1)  # 让线程不至于占满CPU
            if self.stop_event.is_set():
                self.send_tcp_server_stop_signal()
                break

    def rpc_client_handler(self, client_sock, client_addr):
        """
        处理每个客户端请求的handler，需要由继承的RPCServer实现具体处理逻辑
        
        :param client_sock: 客户端的Socket
        :param client_addr: 客户端的地址
        """
        pass

    def loop_accept_client(self):
        """
        循环接受客户端连接，并为每个连接创建一个新的线程来处理请求以支持并发请求
        """
        while not self.stop_event.is_set():
            try:
                client_sock, client_addr = self.sock.accept()
            except socket.timeout as e:
                if not self.stop_event.is_set():
                    self.logger.error(f"accept client {e}")
                continue
            except socket.error as e:
                if not self.stop_event.is_set():
                    self.logger.error(f"Error accepting connection: {e}")
                continue
            if not self.stop_event.is_set():
                self.logger.info(f'与客户端{str(client_addr)}建立了连接')
            t = threading.Thread(target=self.rpc_client_handler, args=(client_sock, client_addr))
            t.start()
        self.sock.close()  # 然后关闭自身socket

```

- **RPCServer**: 继承自**TCPServer**，并结合**Logger**、**ServerStub**和**RegistryClient**实现了完整的RPC服务功能，代码解释：

```python
class RPCServer(TCPServer):
    def __init__(self, host, port):
        self.logger = Logger()
        self.stub = ServerStub(self.logger)  # 设置服务端代理，负责处理服务端方法的注册与调用请求
        self.registry_client = RegistryClient(self.logger)  # 设置注册中心客户端，负责与注册中心通信，注册和保活服务
        self.stop_event = threading.Event()  # 停止事件，用于控制RPCServer的停止
        super().__init__(host, port, self.logger, self.stop_event) # 初始化父类TCPServer，传入要监听的ip与端口号
        # 创建三个线程，分别用于处理停止信号、接受TCP连接和向注册中心注册与发送心跳。
        self.loop_detect_stop_signal_thread = threading.Thread(target=self.loop_detect_stop_signal)
        self.tcp_serve_thread = threading.Thread(target=self.loop_accept_client)
        self.register_and_send_hb_thread = threading.Thread(target=self.registry_client.register_send_heartbeat,
                                                            args=(self.host, self.port, self.stop_event))

    def rpc_client_handler(self, client_sock, client_addr):
        """
        实现父类的处理每个客户端请求的handler
        处理每个客户端的RPC请求，接收消息后调用注册的方法，并返回结果
        :param client_sock: 客户端的Socket
        :param client_addr: 客户端的地址
        """
        try:
            while not self.stop_event.is_set():
                msg = client_sock.recv(1024)
                if not msg:
                    raise EOFError()
                response_data = self.stub.call_method(msg, client_addr)
                client_sock.sendall(response_data)
        except EOFError:
            self.logger.info(f'info on handle: 客户端{str(client_addr)}关闭了连接')
        except ConnectionResetError:
            self.logger.error(f'except on handle: 客户端{str(client_addr)}异常地关闭了连接')
        finally:
            client_sock.close()

    def serve(self):
        """
        启动RPC服务器，开始监听并处理客户端连接，
        启动检测停止信号、处理TCP连接和注册中心心跳的线程。
        """
        self.logger.info(f"From {self.host}:{self.port} start listening...")
        self.loop_detect_stop_signal_thread.start()
        self.tcp_serve_thread.start()
        self.register_and_send_hb_thread.start()
        try:
            while True:
                time.sleep(100)
        except KeyboardInterrupt:
            self.stop_event.set()
            self.registry_client.unregister_from_registry(self.host, self.port)
            self.logger.info("Received KeyboardInterrupt, stopping...")
        finally:
            self.logger.info("Server service stopped.")
            exit(0)
```

- 结构中剩余的10个函数为测试服务端功能时编写的注册的方法:

```python
"""要注册的函数们"""
def add(a, b, c=10):
    return a + b + c
"""......略"""
```

### 2.3 rpc客户端的实现

client.py用到的库：
```python
import argparse
import configparser
import http.client
import json
import os
import socket
import random
import threading
import time
from datetime import datetime
```
server.py代码结构：

<img src="doc_png/server.png" alt="server" style="zoom: 67%;" />

其中：

### 2.4 rpc注册中心的实现

server.py用到的库：
```python
import argparse
import configparser
import http.client
import json
import math
import os
import socket
import threading
import time
from datetime import datetime
```
server.py代码结构：

<img src="doc_png/server.png" alt="server" style="zoom: 67%;" />

其中：

## 三、功能实现解释

### 3.1 消息格式定义，消息序列化和反序列化

消息的格式，以及其序列化和反序列化方式可以自行定义，具体可以**参考之**

**前我们处理 tcp 粘包的过程**，另外消息的序列化和反序列化方式也可以使用其

他主流的序列化方式，如 json、xml 和 protobuf 等方式。

### 3.2 服务注册

RPC 服务端启动时需要注册其能支持的函数。我们要求服务端**至少能同时支**

**持注册 10 个以上的函数**。

如果你的设计中包括 “服务注册中心”，请通过它进行服务的注册。

### 3.3 服务发现

RPC 服务器需要为客户端提供接口，这样客户端才能知道服务端是否支持其

希望调用的服务。

如果你的设计中包括 “服务注册中心”，请通过它进行服务的发现。

### 3.4 服务调用

在 RPC 客户端发现服务后，根据你所设置的 RPC 协议正确地调用远程服

务。服务调用的输入和输出的数据格式即在 3.1 你定义的格式。

### 3.5 服务注册中心

可以支持多个服务端把自己的服务注册到服务注册中心，客户端向服务注册

中心询问服务端的地址并调用。

### 3.6 支持并发

服务端需要具有并发处理客户端请求的能力。

比如，假设客户端 A 发来请求，然后服务端处理客户端 A 的请求，这时客

户端 B 也发来了请求，要求服务端也能同时处理客户端 B 的请求，不能出现服

务端处理完客户端 A 的请求才能处理客户端 B 的请求的情况，导致客户端 B需要等待。具体地，可以利用多线程或者多进程的方式，参考我们之前的编程作

业！

另外，**我们要求，服务端至少可以支持并发处理 10 个客户端的请求**。

### 3.7 异常处理及超时处理

RPC 框架需要具备进行异常处理以及超时处理的能力。其中，超时处理包括

但不限于以下几个方面。

**（1）客户端处理异常/超时的地方：**

 与服务端建立连接时产生的异常/超时

 发送请求到服务端，写数据时出现的异常/超时

 等待服务端处理时，等待处理导致的异常/超时（比如服务端已挂死，

迟迟不响应）

 从服务端接收响应时，读数据导致的异常/超时

**（2）服务端处理异常/超时的地方：**

 读取客户端请求数据时，读数据导致的异常/超时

 发送响应数据时，写数据导致的异常/超时

 调用映射服务的方法时，处理数据导致的异常/超时

### **3.8 负载均衡（可选，加分项）**

为了减少服务端的负载，服务端肯定不能只有一个，客户端可以通过服务注

册中心选择服务器。因此，负载均衡功能就是把每个请求平均负载到每个服务器

上，充分利用每个服务器的资源。

注：考虑成本原因，不同的服务器可以使用多个虚拟机或 docker 镜像，但

不能是单机多线程或多进程

## 四、运行教程

以下是各模块的启动参数说明：

 服务端启动参数

客户端启动参数

注册中心启动参数



## 五、运行测试

### 4.1 测试内容与配置

### 4.2 测试结果

## 六、项目总结