import configparser
import http.client
import json
import socket
import threading
import time

from registry.beans.instance_meta import InstanceMeta


class TCPServer(object):
    def __init__(self):
        # bind and listen端口
        self.port = None
        self.host = None
        # 创建socket工具对象
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # 设置socket重用地址
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def bind_listen(self, host, port):
        self.host = host
        self.port = port
        self.sock.bind((host, port))  # 0.0.0.0 本机的所有可用的网络接口
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
            print(f'客户端{str(client_addr)}关闭了连接')
            client_sock.close()

    def accept_receive_close(self):
        """建立与client的连接，处理请求，多线程"""
        try:
            self.sock.settimeout(3)
            client_sock, client_addr = self.sock.accept()
            print(f'与客户端{str(client_addr)}建立了连接')

            # 创建子线程处理此客户端
            t = threading.Thread(target=self.handle, args=(client_sock, client_addr))
            # 启动子线程，主线程继续循环接收另一个客户端连接的请求
            t.start()
        except socket.timeout as e:
            print(f"{e}")
        except socket.error as e:
            print(f"Error accepting connection: {e}")


class JSONRPC(object):
    def __init__(self):
        self.data = None

    def decode_data(self, req):
        """解析JSON格式序列化后的请求数据"""
        self.data = json.loads(req.decode('utf-8'))
        print(self.data)

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
        print(registry_host, " ", registry_port)  # test

    def register_to_registry(self):
        conn = http.client.HTTPConnection("localhost", 8081)
        headers = {'Content-type': 'application/json'}

        instance = InstanceMeta("json", self.host, self.port)

        # 例子，还可加各种备注
        instance.add_parameters({'ip_proto': 'ipv4'})
        instance_data = json.dumps(instance.to_dict())

        conn.request("POST", "/myRegistry/register?proto=json", instance_data, headers)
        response = conn.getresponse()
        if response.status == 200:
            response_data = json.loads(response.read().decode())
            print(f"SUCCESSFULLY REGISTER TO THE REGISTRY: \n{response_data}\n===================")
        else:
            print(f"FAIL TO REGISTER TO THE REGISTRY: \n{response.read().decode()}\n=================")

        conn.close()

    def unregister_from_registry(self):
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port)
        headers = {'Content-type': 'application/json'}

        instance = InstanceMeta("json", self.host, self.port)
        instance_data = json.dumps(instance.to_dict())

        conn.request("POST", "/myRegistry/unregister?proto=json", instance_data, headers)
        response = conn.getresponse()
        if response.status == 200:
            response_data = json.loads(response.read().decode())
            print(f"SUCCESSFULLY UNREGISTERED FROM THE REGISTRY: \n{response_data}\n===================")
        else:
            print(f"FAILED TO UNREGISTER FROM THE REGISTRY: \n{response.read().decode()}\n=================")

        conn.close()

    def register_send_heartbeat(self):
        while True:
            time.sleep(9)
            self.register_to_registry()


class RPCServer(TCPServer, JSONRPC, ServerStub, RegistryClient):
    def __init__(self):
        TCPServer.__init__(self)
        JSONRPC.__init__(self)
        ServerStub.__init__(self)
        RegistryClient.__init__(self)
        self.running = True

    def serve(self, host, port):
        # 循环监听端口
        self.bind_listen(host, port)
        print(f"SERVER {host} LISTEN {port}")

        # 向注册中心注册服务并定期发送心跳
        threading.Thread(target=self.register_send_heartbeat()).start()

        while True:
            self.accept_receive_close()

    def _process(self, msg):
        return self.call_method(msg)
