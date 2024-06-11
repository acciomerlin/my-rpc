import configparser
import http.client
import json
import os
import socket
import threading
import time
import argparse
from datetime import datetime


class InstanceMeta:
    def __init__(self, protocol=None, host=None, port=None):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.status = None
        self.parameters = {}

    def add_parameters(self, parameters):
        self.parameters.update(parameters)
        return self

    def to_dict(self):
        return {
            'protocol': self.protocol,
            'host': self.host,
            'port': self.port,
            'status': self.status,
            'parameters': self.parameters
        }


class Log(object):
    def __init__(self):
        if not os.path.exists('./log'):
            os.makedirs('./log')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_filename = f'./log/{timestamp}.txt'

    # 定义一个日志函数
    def info_log(self, msg):
        with open(self.log_filename, 'a') as log_file:
            log_file.write(f'[INFO]{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {msg}\n')
        print(f'[INFO]{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {msg}')

    def error_log(self, msg):
        with open(self.log_filename, 'a') as log_file:
            log_file.write(f'[ERROR]{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {msg}\n')
        print(f'[ERROR]{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {msg}')


class TCPServer(object):
    def __init__(self, host=None, port=None):
        self.port = port
        self.host = host
        self.sock = None
        self.addr_type = None
        self.set_up_socket()

    def set_up_socket(self):
        if '.' in self.host:
            self.addr_type = socket.AF_INET
        else:
            self.addr_type = socket.AF_INET6
        # 创建socket工具对象
        self.sock = socket.socket(self.addr_type, socket.SOCK_STREAM)
        # 设置socket重用地址
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def bind_listen(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)  # 参数 5 表示在拒绝连接之前，操作系统可以挂起的最大连接数（称为 "backlog"）。如果有超过 5 个连接等待处理，新连接将会被拒绝。

    def handle(self, client_sock, client_addr):
        """拿请求消息，处理请求消息，回传处理结果，与客户端长连接知道对方无情求，关闭连接"""
        try:
            while True:
                msg = client_sock.recv(1024)
                if not msg:
                    raise EOFError()
                data = self._process(msg)
                client_sock.sendall(data)
        except EOFError:
            # 客户端关闭了连接
            self.info_log(f'客户端{str(client_addr)}关闭了连接')
            client_sock.close()

    def accept_receive_close(self):
        """建立与client的连接，处理请求，多线程"""
        try:
            self.sock.settimeout(3)
            client_sock, client_addr = self.sock.accept()
            self.info_log(f'与客户端{str(client_addr)}建立了连接')

            # 创建子线程处理此客户端
            t = threading.Thread(target=self.handle, args=(client_sock, client_addr))
            # 启动子线程，主线程继续循环接收另一个客户端连接的请求
            t.start()
        except socket.timeout as e:
            self.error_log(f"{e}")
        except socket.error as e:
            self.error_log(f"Error accepting connection: {e}")


class JSONRPC(object):
    def __init__(self):
        self.data = None

    def decode_data(self, req):
        """解析JSON格式序列化后的请求数据"""
        self.data = json.loads(req.decode('utf-8'))
        self.info_log(f"来自客户端的请求数据{self.data}")

    def call_method(self, req):
        """解析JSON格式的方法请求data，调用对应方法并将执行结果返回"""
        self.decode_data(req)
        method_name = self.data['method_name']
        method_args = self.data['method_args']
        method_kwargs = self.data['method_kwargs']

        try:
            res = self.services[method_name](*method_args, **method_kwargs)  # ServerStub的存注册服务的字典
        except KeyError:
            res = f"No service found for: {method_name}"
        except TypeError as e:
            res = f"Argument error: {e}"
        except Exception as e:
            res = f"Error calling method: {e}"
        reply = {"res": res}
        return json.dumps(reply).encode('utf-8')


class ServerStub(object):
    def __init__(self):
        self.services = {}

    def register_services(self, method, name=None):
        """SERVER 服务注册，CLIENT只可调用被注册的服务"""
        if name is None:
            name = method.__name__  # 内置属性，用于获取函数或方法的名称
        self.services[name] = method
        self.info_log(f"注册方法：{name}")


class RegistryClient(object):
    def __init__(self):
        # 读取配置文件
        config = configparser.ConfigParser()
        config.read('config.ini')
        registry_host = config['registry']['host']
        registry_port = int(config['registry']['port'])
        self.registry_host = registry_host
        self.registry_port = registry_port
        self.servers_cache = []
        self.first_register = True
        self.info_log(f"读取注册中心配置：Registry IP&PORT: {registry_host}:{registry_port}")  # test

    def register_to_registry(self):
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port)
        headers = {'Content-type': 'application/json'}

        # instance = InstanceMeta("json", self.host, self.port)
        # 注册时 ip 不能 0.0.0.0
        instance = InstanceMeta("json", socket.gethostbyname(socket.gethostname()), self.port)

        # 例子，还可加各种备注
        instance.add_parameters({'ip_proto': 'ipv4'})
        instance_data = json.dumps(instance.to_dict())

        try:
            conn.request("POST", "/myRegistry/register?proto=json", instance_data, headers)
            response = conn.getresponse()
            if response.status == 200:
                response_data = json.loads(response.read().decode())
                if self.first_register:
                    self.info_log(f"SUCCESSFULLY REGISTER TO THE REGISTRY: \n{response_data}\n===================")
                    self.first_register = False
                else:
                    self.info_log(
                        f"SUCCESSFULLY SEND HEARTBEAT TO THE REGISTRY: \n{response_data}\n===================")
            else:
                if self.first_register:
                    self.error_log(f"FAIL TO REGISTER TO THE REGISTRY: \n{response.read().decode()}\n=================")
                else:
                    self.error_log(
                        f"FAIL TO SEND HEARTBEAT TO THE REGISTRY: \n{response.read().decode()}\n=================")
        except TimeoutError or ConnectionRefusedError as e:
            self.error_log(f'与注册中心建立HTTP连接时发生错误：{e}')

        conn.close()

    def unregister_from_registry(self):
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port)
        headers = {'Content-type': 'application/json'}

        instance = InstanceMeta("json", self.host, self.port)
        instance_data = json.dumps(instance.to_dict())

        try:
            conn.request("POST", "/myRegistry/unregister?proto=json", instance_data, headers)
            response = conn.getresponse()
            if response.status == 200:
                response_data = json.loads(response.read().decode())
                self.info_log(f"SUCCESSFULLY UNREGISTERED TO THE REGISTRY: \n{response_data}\n===================")
            else:
                self.error_log(f"FAIL TO UNREGISTER TO THE REGISTRY: \n{response.read().decode()}\n=================")
        except TimeoutError or ConnectionRefusedError as e:
            self.error_log(f'与注册中心建立HTTP连接时发生错误：{e}')

        conn.close()

    def register_send_heartbeat(self):
        try:
            while True:
                time.sleep(9)
                self.register_to_registry()
        except KeyboardInterrupt as e:
            self.info_log(f"Exit by Ctrl+C")
            exit(-1)
        except ConnectionError as e:
            self.error_log(f"注册中心停止了服务 : {e}")
            exit(-1)


class RPCServer(TCPServer, JSONRPC, ServerStub, RegistryClient, Log):
    def __init__(self, host, port):
        Log.__init__(self)
        TCPServer.__init__(self, host, port)
        JSONRPC.__init__(self)
        ServerStub.__init__(self)
        RegistryClient.__init__(self)
        self.running = True

    def serve(self):
        # 循环监听端口
        self.bind_listen()
        self.info_log(f"From {self.host}:{self.port} start listening...")

        # 向注册中心注册服务并定期发送心跳
        threading.Thread(target=self.register_send_heartbeat()).start()

        while True:
            self.accept_receive_close()

    def _process(self, msg):
        return self.call_method(msg)


"""要注册的函数们"""


def add(a, b, c=10):
    sum = a + b + c
    return sum


def hi(user):
    print(f"hi {user}, welcome")
    time.sleep(3)
    return f"hi {user}, welcome"


if __name__ == '__main__':
    pars = argparse.ArgumentParser(description='TCP/JSON RPC Server')
    pars.add_argument('-l', '--host', type=str, default='0.0.0.0',
                      help='服务端监听的 ip 地址，同时支持 IPv4 和 IPv6，可以为空，默认监听所有 ip 地址')
    pars.add_argument('-p', '--port', type=int, required=True,
                      help='服务端监听的端口号，不可为空')

    args = pars.parse_args()

    s = RPCServer(args.host, args.port)
    s.register_services(add)
    s.register_services(hi)
    s.serve()
