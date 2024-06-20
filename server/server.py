import argparse
import configparser
import http.client
import inspect
import json
import math
import os
import socket
import threading
import time
from datetime import datetime


class InstanceMeta:
    """服务实例注册与发现使用的数据结构"""

    def __init__(self, protocol=None, host=None, port=None):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.status = None
        self.parameters = {}

    @staticmethod
    def from_dict(data):
        instance = InstanceMeta(
            protocol=data.get('protocol'),
            host=data.get('host'),
            port=data.get('port'),
        )
        instance.status = data.get('status')
        instance.parameters = data.get('parameters', {})
        return instance

    def to_dict(self):
        return {
            'protocol': self.protocol,
            'host': self.host,
            'port': self.port,
            'status': self.status,
            'parameters': self.parameters
        }

    def get_parameters(self):
        return self.parameters

    def add_parameters(self, parameters):
        self.parameters.update(parameters)
        return self

    def get_status(self):
        return self.status

    def set_status(self, status):
        self.status = status

    def __eq__(self, other):
        if not isinstance(other, InstanceMeta):
            return False
        return self.protocol == other.protocol and self.host == other.host and self.port == other.port

    def __hash__(self):
        return hash((self.protocol, self.host, self.port))

    def __str__(self):
        return (f"InstanceMeta(protocol={self.protocol}, host={self.host}, port={self.port}, "
                f"status={self.status}, parameters={self.parameters})")


class Logger:
    def __init__(self, save_log=False):
        self.save = save_log
        if self.save:
            if not os.path.exists('./log'):
                os.makedirs('./log')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.log_filename = f'./log/{timestamp}.txt'

    def log(self, level, msg):
        if self.save:
            with open(self.log_filename, 'a') as log_file:
                log_file.write(f'[{level}]{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {msg}\n')
        print(f'[{level}]{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} - {msg}')

    def info(self, msg):
        self.log('INFO', msg)

    def error(self, msg):
        self.log('ERROR', msg)


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

        try:
            # 解码并解析请求数据
            req_data = json.loads(req.decode('utf-8'))
            self.logger.info(f"来自客户端{str(client_addr)}的请求数据{req_data}")

            # 从请求数据中提取方法名、方法参数和方法关键字参数
            method_name = req_data['method_name']
            method_args = req_data['method_args']
            method_kwargs = req_data['method_kwargs']

            # 响应服务发现
            if method_name == 'all_your_methods':
                # 返回所有注册的方法名和参数格式
                res = []
                for method_name, method in self.services.items():
                    # 获取方法的签名
                    sig = inspect.signature(method)
                    params = sig.parameters
                    # 构造方法信息字典，包括方法名、必需参数和可选参数
                    method_info = {
                        "method_name": method_name,
                        "method_args": [param.name for param in params.values() if param.default == param.empty],
                        "method_kwargs": {param.name: param.default for param in params.values() if
                                          param.default != param.empty}
                    }
                    res.append(method_info)
            else:
                # 响应服务调用
                res = self.services[method_name](*method_args, **method_kwargs)
        except KeyError:
            # 方法名不存在的情况
            res = f"No service found for: {method_name}"
        except TypeError as e:
            # 方法参数错误的情况
            res = f"Argument error: {e}"
        except Exception as e:
            # 其他调用错误的情况
            res = f"Error calling method: {e}"

        # 构造响应消息，记录日志并返回序列化后的响应消息
        reply_raw = {"res": res}
        reply = json.dumps(reply_raw).encode('utf-8')
        self.logger.info(f"给客户端{str(client_addr)}的回复{reply}")
        return reply


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
        self.logger = logger
        config = configparser.ConfigParser()
        try:
            config.read('docket_test_config.ini')  # docker
            # config.read('../config.ini')  # local
            registry_host = config['registry']['host']
            registry_port = int(config['registry']['port'])
        except Exception as e:
            self.logger.error(f"Error occurred in reading registry config:{e}")
            exit(-1)

        self.registry_host = registry_host
        self.registry_port = registry_port
        self.first_register = True
        self.strong_stop_event = None
        self.weak_stop_event = threading.Event()
        self.logger.info(f"成功从配置文件读取到注册中心ip地址: {registry_host}:{registry_port}"
                         f"\n=========================================================================================")

    def register_to_registry(self, host, port):
        """
        通过发送HTTP POST请求，向注册中心注册服务，得到注册请求的结果
        也是服务向注册中心发送心跳的方式，通过成员变量 self.first_register 判断是注册请求还是心跳发送请求
        :param host: 注册服务的IP地址
        :param port: 注册服务的端口
        """
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port, timeout=10)
        headers = {'Content-type': 'application/json'}

        if host == '0.0.0.0':
            instance = InstanceMeta("json", socket.gethostbyname(socket.gethostname()), port)
        else:
            instance = InstanceMeta("json", host, port)

        instance.add_parameters({'mode': 'development'})  # 加额外控制信息例子
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
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port, timeout=10)
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
        self.strong_stop_event = stop_e
        while not self.strong_stop_event.is_set() or not self.weak_stop_event.is_set():
            try:
                self.register_to_registry(host, port)
                time.sleep(5)
            except Exception as e:
                self.logger.error(f'与注册中心通信时发生错误，停止与注册中心联系：{e}')
                self.weak_stop_event.set()


class TCPServer:
    def __init__(self, host, port, logger, stop_event):
        self.port = port
        self.host = host
        self.logger = logger
        self.sock = None
        self.addr_type = None
        self.stop_event = stop_event
        self.set_up_socket()

    def set_up_socket(self):
        if '.' in self.host:
            self.addr_type = socket.AF_INET
        else:
            self.addr_type = socket.AF_INET6
        self.sock = socket.socket(self.addr_type, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)

    def send_tcp_server_stop_signal(self):
        """
        本地创建一个tcp client socket给server socket连一次关一次表示停止信号，
        解决accept不设timeout就无限期阻塞的问题
        """
        # 检查地址类型并设置地址
        if self.addr_type == socket.AF_INET6:
            host = '::1'  # IPv6 localhost
        else:
            host = '127.0.0.1'  # IPv4 localhost

        h_socket = socket.socket(self.addr_type, socket.SOCK_STREAM)
        try:
            h_socket.connect((host, self.port))
            h_socket.close()
            self.logger.info("Successfully sent stop signal to TCP server.")
        except Exception as e:
            e_name = e.__class__.__name__
            e_msg = str(e)
            self.logger.error(
                f"Received Exception: {e_name}, Message: {e_msg}, when trying send tcp stop signal")
        finally:
            h_socket.close()

    def loop_detect_stop_signal(self):
        while True:
            time.sleep(0.1)  # 让线程不至于占满CPU
            if self.stop_event.is_set():
                self.send_tcp_server_stop_signal()
                break

    def rpc_client_handler(self, client_sock, client_addr):
        """rpc server处理每个client请求的handler，由继承的RPCServer实现"""
        pass

    def loop_accept_client(self):
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


class RPCServer(TCPServer):
    def __init__(self, host, port):
        self.logger = Logger()  # 运行日志创建
        self.stub = ServerStub(self.logger)
        self.registry_client = RegistryClient(self.logger)
        # 线程管理.....
        self.stop_event = threading.Event()
        super().__init__(host, port, self.logger, self.stop_event)
        self.loop_detect_stop_signal_thread = threading.Thread(target=self.loop_detect_stop_signal)
        self.tcp_serve_thread = threading.Thread(target=self.loop_accept_client)
        self.register_and_send_hb_thread = threading.Thread(target=self.registry_client.register_send_heartbeat,
                                                            args=(self.host, self.port, self.stop_event))

    def rpc_client_handler(self, client_sock, client_addr):
        try:
            while not self.stop_event.is_set():
                msg = client_sock.recv(1024)
                if not msg:
                    raise EOFError()
                response_data = self.stub.call_method(msg, client_addr)
                client_sock.sendall(response_data)
        except EOFError:
            self.logger.info(f'info on handle: 客户端{str(client_addr)}关闭了连接')
        except Exception as e:
            self.logger.error(f'except on handle: 客户端{str(client_addr)}异常地关闭了连接, {e}')
        finally:
            client_sock.close()

    def serve(self):
        self.logger.info(f"From {self.host}:{self.port} start listening...")
        self.loop_detect_stop_signal_thread.start()
        self.tcp_serve_thread.start()
        self.register_and_send_hb_thread.start()
        try:
            while True:
                time.sleep(100)
        except KeyboardInterrupt:
            self.logger.info("Received KeyboardInterrupt, stopping...")
            self.registry_client.unregister_from_registry(self.host, self.port)
            self.stop_event.set()
        except Exception as e:
            self.logger.info(f"Unexpected exception: {e} occurred, stopping...")
            self.registry_client.unregister_from_registry(self.host, self.port)
            self.stop_event.set()
        finally:
            self.logger.info("Waiting for other threads to join...")
            self.register_and_send_hb_thread.join(3)
            self.loop_detect_stop_signal_thread.join(3)
            self.tcp_serve_thread.join()
            self.logger.info("Server service stopped.")
            exit(0)


"""要注册的函数们"""


def add(a, b, c=10):
    return a + b + c


def subtract(a, b):
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    if b == 0:
        return "Division by zero error!"
    return a / b


def area_of_circle(radius):
    return math.pi * radius ** 2


def square(number):
    return number ** 2


def to_uppercase(string):
    return string.upper()


def reverse_string(string):
    # string[::-1] 是Python中的切片操作，表示从头到尾以步长-1反向取值，即反转字符串。
    return string[::-1]


def hi(user):
    return f"hi {user}, welcome"


def hello(name):
    return f"Hello, {name}!"


if __name__ == '__main__':
    pars = argparse.ArgumentParser(description='RPC Server based on TCP + JSON')

    pars.add_argument('-l', '--host', type=str, default='0.0.0.0',
                      help='服务端监听的 ip 地址，同时支持 IPv4 和 IPv6，可以为空，默认监听所有 ip 地址')
    pars.add_argument('-p', '--port', type=int, required=True,
                      help='服务端监听的端口号，不可为空')

    args = pars.parse_args()

    server = RPCServer(args.host, args.port)
    server.stub.register_services(add)
    server.stub.register_services(hi)
    server.serve()
