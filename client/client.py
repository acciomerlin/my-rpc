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


# 示例负载均衡模块
class LoadBalance:
    @staticmethod
    def random(servers):
        s = random.choice(servers)
        return s


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


class RegistryClient:
    def __init__(self, logger):
        self.logger = logger
        # 读取配置文件
        config = configparser.ConfigParser()
        try:
            config.read('config.ini')
        except Exception as e:
            self.logger.error(f"Error occurred in reading registry config:{e}")
            exit(-1)

        registry_host = config['registry']['host']
        registry_port = int(config['registry']['port'])
        self.registry_host = registry_host
        self.registry_port = registry_port
        self.servers_cache = set()
        self.logger.info(f"成功从配置文件读取到注册中心ip地址: {registry_host}:{registry_port}"
                         f"\n=========================================================================================")  # test

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
                # print(f"成功从注册中心请求到目前可用的服务端列表：\n{servers_raw}\n=================")

                # 可以在这里加参数设置条件过滤一些server，比如要求param里必须含有一个特定字段

                # 更新本地服务列表缓存
                tmp_server_set = set()
                for ins in servers_raw:
                    tmp_server_set.add((ins['host'], ins['port']))
                origin_set = self.servers_cache.copy()
                self.servers_cache = self.servers_cache.union(tmp_server_set)
                # print(f'新获取到的服务端列表: {tmp_server_set}')
                # print(f'本地旧的服务端列表缓存: {origin_set}')
                self.servers_cache -= origin_set - tmp_server_set
                # print(f'更新后的本地服务端缓存: {self.servers_cache}')

                servers = list(self.servers_cache)
                # print(f"交付给负载均衡的服务端元组列表：\n{servers}\n=================")
                return servers  # eg: return [("127.0.0.1", 9999), ("127.0.0.1", 9998)]
            else:
                # 与注册中心连接不成功，考虑使用cache
                return []
        except (TimeoutError, ConnectionRefusedError) as e:
            self.logger.error(f'与注册中心通信时发生错误：{e}，停止与注册中心通信，')
            return []
        finally:
            conn.close()


class TCPClient:
    def __init__(self, host=None, port=None):
        self.sock = None
        self.host = host
        self.port = port

    def new_socket(self):
        """创建一个新的套接字对象"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self, host=None, port=None):
        """连接SERVER"""
        if host is None and port is None:
            # 没传入，是 connect_by_args，已指定self.host, self.port
            self.sock.connect((self.host, self.port))
        else:
            # 传入，是 connect_by_registry
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


class RPCClient(TCPClient):
    def __init__(self, host=None, port=None):
        self.logger = Logger()
        TCPClient.__init__(self, host, port)
        self.running = True
        if host is not None and port is not None:
            self.mode = 0  # no registry
        else:
            self.mode = 1  # with registry
            self.registry_client = RegistryClient(self.logger)
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
                if self.mode == 0:
                    self.connect_server_by_args()
                else:
                    self.connect_server_by_registry()
                dic = {'method_name': method, 'method_args': args, 'method_kwargs': kwargs}
                self.send(json.dumps(dic).encode('utf-8'))
                response = self.recv(1024)
                result = json.loads(response.decode('utf-8'))
                result = result["res"]
                self.logger.info(f"Call method: {method} args:{args} kwargs:{kwargs} | result: {result}")
            except (json.JSONDecodeError, ConnectionError) as e:
                self.logger.error(f"Error occurred when calling method {method}: {e}")
                result = None
            finally:
                self.close()
            return result

        setattr(self, method, _func)
        return _func

    def connect_server_by_args(self):
        """服务发现，连接SERVER"""
        try:
            # 调用rpc服务，开新sock
            self.new_socket()
            host, port = self.host, self.port
            self.connect(host, port)
            self.logger.info(f'Connected to server: {host},{port}')
        except Exception as e:
            raise ConnectionError(f"Failed to connect to server in connect_server_by_args: {e}")

    def connect_server_by_registry(self, protocol="json"):
        """服务发现，连接SERVER"""
        # 调用rpc服务，开新sock
        self.new_socket()
        # 第一次用registry find servers,有缓存优先缓存，定期轮询以更新缓存
        if len(self.registry_client.servers_cache) == 0:
            servers = self.registry_client.findRpcServers(protocol)
        else:
            servers = list(self.registry_client.servers_cache)
        if len(servers) == 0:
            raise ConnectionError(f"No available servers")
        # else:
        #     self.logger.info(f'Found servers: {servers}')

        # 负载均衡选server
        server = LoadBalance.random(servers)
        # self.logger.info(f"选择的负载均衡算法：random; 最终选择的服务端为：{server}")
        host, port = server
        try:
            self.connect(host, port)
            self.logger.info(f'Connected to server: {host},{port}')
        except Exception:
            if server in self.registry_client.servers_cache:
                self.registry_client.servers_cache.remove(server)
            raise ConnectionError(f"Failed to connect to rpc server")

    def poll_registry(self):
        """轮询注册中心，更新本地服务器列表缓存"""
        while self.running:
            self.registry_client.findRpcServers()
            time.sleep(3)

    def stop(self):
        """停止客户端，关闭存在socket"""
        self.running = False
        if self.sock:
            self.close()


# test
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='TCP/JSON RPC Client')
    parser.add_argument('-i', '--host', type=str, help='客户端需要发送的服务端 ip 地址，同时支持 IPv4 和 IPv6，不得为空')
    parser.add_argument('-p', '--port', type=int, help='客户端需要发送的服务端端口，不得为空')
    parser.add_argument('-m', '--mode', type=str, default='registry', choices=['registry', 'server'],
                        help='客户端模式，默认为server，registry模式不需要指定host和port')

    args = parser.parse_args()

    if args.mode == 'server' and (not args.host or not args.port):
        parser.error("在server模式下，必须指定host和port参数")

    client = RPCClient(host=args.host, port=args.port)
    try:
        for i in range(1, 20):
            client.hi(i)
    except KeyboardInterrupt:
        client.logger.info(f"Main thread received KeyboardInterrupt, stopping...")
    finally:
        client.stop()
        exit(0)
