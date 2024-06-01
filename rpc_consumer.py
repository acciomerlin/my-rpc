import configparser
import http.client
import json
import socket
from typing import Type


# 示例负载均衡模块
class LoadBalance:
    @staticmethod
    def random(servers):
        import random
        return random.choice(servers)


class RegistryClient(object):
    def __init__(self):
        # 读取配置文件
        config = configparser.ConfigParser()
        config.read('config.ini')

        registry_host = config['registry']['host']
        registry_port = int(config['registry']['port'])
        self.registry_host = registry_host
        self.registry_port = registry_port
        print(registry_host, " ", registry_port) # test

    # gpt生成的参考
    def get_servers(self, service_name):
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port)
        conn.request("GET", f"/services/{service_name}")
        response = conn.getresponse()
        if response.status_code == 200:
            data = response.read()
            servers = json.loads(data)
            return servers
        else:
            return []

    def findRpcServers(self):
        """
        http与注册中心通信，返回 (host, port) 的元组 list
        :return: tuple list
        """
        # 返回可用服务器的列表，这里假设返回的是包含(host, port)元组的列表
        return [("127.0.0.1", 9999), ("127.0.0.1", 9998)]


class TCPClient(object):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, host, port):
        """连接SERVER"""
        self.sock.connect((host, port))

    def connect_with_registry(self):
        """连接SERVER"""
        servers = self.findRpcServers()
        server = LoadBalance.random(servers)
        host, port = server
        self.sock.connect((host, port))

    def send(self, data):
        """发送数据到SERVER"""
        self.sock.send(data)

    def recv(self, length):
        """接收SERVER回传的数据"""
        return self.sock.recv(length)

    def close(self):
        """关闭连接"""
        self.sock.close()


class ClientStub(object):
    def __getattr__(self, method):
        """
        访问不存在属性时被调用的方法
        为实现用户在Client端能直接调用Server端方法，利用__getattr__构建了_func方法，并将其通过setattr方法设置到RPCClient类中，使该类有Server端方法对应的映射。
        调用add方法，即调用了对应的_func方法，将数据发送至Server端并返回远程调用返回的数据
        :param method: 试图访问的不存在的属性名
        :return: _func
        """

        def _func(*args, **kwargs):
            dic = {'method_name': method, 'method_args': args, 'method_kwargs': kwargs}
            self.send(json.dumps(dic).encode('utf-8'))
            data = self.recv(1024)
            data = json.loads(data.decode('utf-8'))
            data = data["res"]
            return data

        setattr(self, method, _func)
        return _func


class RPCClient(RegistryClient, TCPClient, ClientStub):
    def __init__(self):
        TCPClient.__init__(self)
        RegistryClient.__init__(self)


# test
if __name__ == '__main__':
    client = RPCClient()
