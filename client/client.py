import configparser
import http.client
import json
import socket
import random
import threading
import time


# 示例负载均衡模块
class LoadBalance:
    @staticmethod
    def random(servers):
        s = random.choice(servers)
        print(f"负载均衡算法：random; 最终选择的服务端为：{s}\n=================")
        return s


class RegistryClient(object):
    def __init__(self):
        # 读取配置文件
        config = configparser.ConfigParser()
        config.read('config.ini')

        registry_host = config['registry']['host']
        registry_port = int(config['registry']['port'])
        self.registry_host = registry_host
        self.registry_port = registry_port
        self.servers_cache = set()
        print(f"注册中心IP ADDR: {registry_host}:{registry_port}\n=================")  # test

    def findRpcServers(self, protocol="json"):
        """
        http与注册中心通信，返回 (host, port) 的元组 list
        :return: tuple list
        """
        conn = http.client.HTTPConnection(self.registry_host, self.registry_port)
        try:
            conn.request("GET", f"/myRegistry/findAllInstances?proto={protocol}")
            response = conn.getresponse()
            if response.status == 200:
                data = response.read().decode()
                servers_raw = json.loads(data)
                print(f"成功从注册中心请求到目前可用的服务端列表：\n{servers_raw}\n=================")

                # 可以在这里加参数设置条件过滤一些server，比如要求param里必须含有一个特定字段

                # 更新本地服务列表缓存
                tmp_server_set = set()
                for ins in servers_raw:
                    tmp_server_set.add((ins['host'], ins['port']))
                origin_set = self.servers_cache.copy()
                self.servers_cache = self.servers_cache.union(tmp_server_set)
                print(f'new fetch: {tmp_server_set}')
                print(f'old cache: {origin_set}')
                self.servers_cache -= origin_set - tmp_server_set
                print(f'new cache: {self.servers_cache}')

                servers = list(self.servers_cache)
                print(f"交付给负载均衡的服务端元组列表：\n{servers}\n=================")
                return servers  # eg: return [("127.0.0.1", 9999), ("127.0.0.1", 9998)]
            else:
                # 与注册中心连接不成功，考虑使用cache
                return []
        finally:
            conn.close()


class TCPClient(object):
    def __init__(self):
        self.sock = None

    def new_socket(self):
        """创建一个新的套接字对象"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, host, port):
        """连接SERVER"""
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


class RPCClient(RegistryClient, TCPClient):
    def __init__(self):
        TCPClient.__init__(self)
        RegistryClient.__init__(self)
        self.running = True
        threading.Thread(target=self.poll_registry).start()

    def __getattr__(self, method):
        """
        访问不存在属性时被调用的方法
        为实现用户在Client端能直接调用Server端方法，利用__getattr__构建了_func方法，并将其通过setattr方法设置到RPCClient类中，使该类有Server端方法对应的映射。
        调用add方法，即调用了对应的_func方法，将数据发送至Server端并返回远程调用返回的数据
        :param method: 试图访问的不存在的属性名
        :return: _func
        """

        def _func(*args, **kwargs):
            try:
                self.connect_server_by_registry()
                print('hi _func113')
                dic = {'method_name': method, 'method_args': args, 'method_kwargs': kwargs}
                self.send(json.dumps(dic).encode('utf-8'))
                response = self.recv(1024)
                result = json.loads(response.decode('utf-8'))
                result = result["res"]
            except (json.JSONDecodeError, ConnectionError) as e:
                print(f"Error occurred: {e}")
                result = None
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                result = None
            finally:
                self.sock.close()
            return result

        setattr(self, method, _func)
        return _func

    def connect_server_by_registry(self, protocol="json"):
        """服务发现，连接SERVER"""
        try:
            # 调用rpc服务，开新sock
            self.new_socket()

            # 第一次用registry find servers,有缓存优先缓存，定期轮询以更新缓存
            if len(self.servers_cache) == 0:
                servers = self.findRpcServers(protocol)
                print("ye")
            else:
                servers = list(self.servers_cache)
            if len(servers) == 0:
                raise Exception("No servers found")
            print(f'Found servers: {servers}')

            # 负载均衡选server
            server = LoadBalance.random(servers)
            host, port = server
            print(f'Connecting to server: {host},{port}')
            self.sock.connect((host, port))
        except Exception as e:
            raise ConnectionError(f"Failed to connect to server: {e}")

    def poll_registry(self):
        """轮询注册中心，更新本地服务器列表缓存"""
        while self.running:
            self.findRpcServers()
            time.sleep(10)

    def stop(self):
        """停止客户端，关闭存在socket"""
        self.running = False
        if self.sock:
            self.close()


# test
if __name__ == '__main__':
    client = RPCClient()
    i = 0
    res = client.hi(i)
    print(res)
