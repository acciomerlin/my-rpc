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
        """
        成员变量解释
        self.registry_host : string 配置文件中读入的注册中心的 IP
        self.registry_port : int 配置文件中读入的注册中心的端口号
        self.servers_cache = set() 本地缓存的服务端列表
        :param logger: 运行日志
        """
        self.logger = logger
        # 读取配置文件
        config = configparser.ConfigParser()
        try:
            # config.read('docket_test_config.ini')  # docker
            config.read('../config.ini')  # local
            registry_host = config['registry']['host']
            registry_port = int(config['registry']['port'])
        except Exception as e:
            self.logger.error(f"Error occurred in reading registry config:{e}")
            exit(-1)

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
            self.logger.error(f'与注册中心通信时发生错误：{e}，获取最新服务端信息失败，使用本地缓存的服务端列表')
            return []
        finally:
            conn.close()


class TCPClient:
    def __init__(self, host=None, port=None):
        self.sock = None
        self.host = host
        self.port = port

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
        """
        初始化作用：
        根据是否提供 RPCServer host和port判断是否使用注册中心
        如果使用注册中心，启动一个线程定期轮询注册中心。
        """
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
        访问不存在属性时被调用的方法，动态创建一个代理函数_func，用于处理该方法调用,从而实现RPC远程调用；

        为实现用户在Client端能直接调用Server端方法，利用__getattr__构建了_func方法，并将其通过setattr方法设置到RPCClient类中，使该类有Server端方法对应的映射。
        如 RPCClient调用add方法，即调用了对应的_func方法，将数据发送至Server端并返回远程调用返回的数据
        :param method: 试图访问的不存在的属性名
        :return: _func: 远程调用method后返回调用结果的函数
        """

        def _func(*args, **kwargs):
            """
            代理函数，用于调用Server端的方法；
            连接服务器，发送方法调用请求，并处理响应

            :param args: 远程调用位置参数
            :param kwargs: 远程调用关键字参数
            :return: 远程调用的结果
            """
            try:
                # 根据模式选择连接服务器的方式
                if self.mode == 0:
                    self.connect_server_by_args()
                else:
                    self.connect_server_by_registry()

                # 构建方法调用的请求数据
                dic = {'method_name': method, 'method_args': args, 'method_kwargs': kwargs}

                # 发送请求数据到服务器
                self.send(json.dumps(dic).encode('utf-8'))

                # 接收并解析服务器的响应数据
                response = self.recv(1024)
                result = json.loads(response.decode('utf-8'))
                result = result["res"]

                # 记录方法调用信息和结果
                self.logger.info(f"Call method: {method} args:{args} kwargs:{kwargs} | result: {result}")
            except (json.JSONDecodeError, ConnectionError) as e:
                # 处理JSON解析错误或连接错误，并记录错误日志
                self.logger.error(f"Error occurred when calling method {method}: {e}")
                result = None
            finally:
                # 关闭连接
                self.close()

            return result

        # 将动态生成的方法绑定到当前实例上
        setattr(self, method, _func)
        return _func

    def connect_server_by_args(self):
        try:
            host, port = self.host, self.port
            # 调用rpc服务，根据host ip地址类型开新sock
            if '.' in host:
                addr_type = socket.AF_INET
            else:
                addr_type = socket.AF_INET6
            self.sock = socket.socket(addr_type, socket.SOCK_STREAM)
            self.connect(host, port)
            self.logger.info(f'Connected to server: {host},{port}')
        except Exception as e:
            raise ConnectionError(f"Failed to connect to server in connect_server_by_args: {e}")

    def connect_server_by_registry(self, protocol="json"):
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

        # 调用rpc服务，根据host ip地址类型开新sock
        if '.' in host:
            addr_type = socket.AF_INET
        else:
            addr_type = socket.AF_INET6
        self.sock = socket.socket(addr_type, socket.SOCK_STREAM)

        try:
            self.connect(host, port)
            self.logger.info(f'Connected to server: {host},{port}')
        except Exception as e:
            if server in self.registry_client.servers_cache:
                self.registry_client.servers_cache.remove(server)
            raise ConnectionError(f"Failed to connect to rpc server, {e}")

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
                        help='客户端运行模式，默认值为 server，可选值为 registry (通过注册中心发现服务)和 server(直接与服务端相连)。在 registry 模式下，无需指定 '
                             'host 和 port 参数')

    args = parser.parse_args()

    if args.mode == 'server' and (not args.host or not args.port):
        parser.error("在server模式下，必须指定host和port参数")

    client = RPCClient(host=args.host, port=args.port)
    try:
        for i in range(1, 20):
            time.sleep(3)
            client.all_your_methods(i)
    except KeyboardInterrupt:
        client.logger.info(f"Main thread received KeyboardInterrupt, stopping...")
    finally:
        client.stop()
        exit(0)
