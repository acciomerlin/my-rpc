import argparse
import configparser
import http.client
import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import random


# 示例负载均衡模块
class LoadBalance:
    @staticmethod
    def random(servers):
        return random.choice(servers)


class Logger:
    def __init__(self, save_log=False):
        self.save = save_log
        if self.save:
            if not os.path.exists('./log'):
                os.makedirs('./log')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.log_filename = f'./log/{timestamp}.txt'

    def log(self, level, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 包含毫秒的时间格式
        if self.save:
            with open(self.log_filename, 'a') as log_file:
                log_file.write(f'[{level}]{timestamp} - {msg}\n')
        print(f'[{level}]{timestamp} - {msg}')

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
            config.read('docket_test_config.ini')  # docker
            # config.read('../config.ini')  # local
            self.registry_host = config['registry']['host']
            self.registry_port = int(config['registry']['port'])
        except Exception as e:
            self.logger.error(f"Error occurred in reading registry config:{e}")
            exit(-1)

        self.servers_cache = set()
        self.logger.info(f"成功从配置文件读取到注册中心ip地址: {self.registry_host}:{self.registry_port}"
                         f"\n=========================================================================================")

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
                tmp_server_set = set()
                for ins in servers_raw:
                    tmp_server_set.add((ins['host'], ins['port']))
                origin_set = self.servers_cache.copy()
                self.servers_cache = self.servers_cache.union(tmp_server_set)
                self.servers_cache -= origin_set - tmp_server_set
                servers = list(self.servers_cache)
                return servers  # eg: return [("127.0.0.1", 9999), ("127.0.0.1", 9998)]
            else:
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
            self.sock.connect((self.host, self.port))
        else:
            self.sock.connect((host, port))

    def send(self, data):
        """发送数据到SERVER"""
        self.sock.sendall(data)

    def recv(self, length):
        """接收SERVER回传的数据"""
        return self.sock.recv(length)

    def close(self):
        """关闭连接"""
        self.sock.close()


class RPCClient:
    def __init__(self, host=None, port=None):
        """
        初始化作用：
        根据是否提供 RPCServer host和port判断是否使用注册中心
        如果使用注册中心，启动一个线程定期轮询注册中心。
        """
        self.logger = Logger()
        self.host = host
        self.port = port
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
        """
        def _func(*args, **kwargs):
            """
            代理函数，用于调用Server端的方法；
            """
            try:
                tcp_client = TCPClient(self.host, self.port)
                if self.mode == 0:
                    if '.' in self.host:
                        addr_type = socket.AF_INET
                    else:
                        addr_type = socket.AF_INET6
                    tcp_client.sock = socket.socket(addr_type, socket.SOCK_STREAM)
                    tcp_client.sock.settimeout(10)
                    tcp_client.connect()
                else:
                    self.connect_server_by_registry(tcp_client)

                dic = {'method_name': method, 'method_args': args, 'method_kwargs': kwargs}
                tcp_client.send(json.dumps(dic).encode('utf-8'))
                response = tcp_client.recv(1024)
                result = json.loads(response.decode('utf-8'))["res"]

                tcp_client.close()
                self.logger.info(f"Call method: {method} args:{args} kwargs:{kwargs} | result: {result} ｜ server: {self.host}:{self.port}")
            except Exception as e:
                self.logger.error(f"Error occurred when calling method {method}: {e}")
                result = None

            return result

        setattr(self, method, _func)
        return _func

    def connect_server_by_registry(self, tcp_client, protocol="json"):
        """
        通过注册中心连接服务端模式下连接服务端, 此模式下轮询注册中心线程开启，
        优先使用本地服务端缓存，为空则调用registry_client的findRpcServers，若结果仍为空则抛出无可用服务端异常
        并在此处使用负载均衡类的负载均衡算法选出最终连接的服务端，进行连接
        :param tcp_client: TCPClient 与选出的server建立连接的tcp客户端
        :param protocol: 客户端使用的消息数据格式
        """
        if len(self.registry_client.servers_cache) == 0:
            servers = self.registry_client.findRpcServers(protocol)
        else:
            servers = list(self.registry_client.servers_cache)
        if len(servers) == 0:
            raise Exception(f"No available servers")

        server = LoadBalance.random(servers)
        host, port = server
        self.host, self.port = host, port # just for print log

        if '.' in host:
            addr_type = socket.AF_INET
        else:
            addr_type = socket.AF_INET6
        tcp_client.sock = socket.socket(addr_type, socket.SOCK_STREAM)
        tcp_client.sock.settimeout(10)

        try:
            tcp_client.connect(host, port)
        except Exception as e:
            if server in self.registry_client.servers_cache:
                self.registry_client.servers_cache.remove(server)
            raise Exception(f"Failed to connect to rpc server, {e}")

    def poll_registry(self):
        while self.running:
            self.registry_client.findRpcServers()
            time.sleep(3)

    def stop(self):
        self.running = False


def test_sync_calls(client):
    client.logger.info('同步调用测试开始')
    for i in range(3):
        time.sleep(1)
        client.hi(i)
    client.logger.info('同步调用测试完成\n')


def test_async_calls(client):
    def call_method(index):
        client.hi(index)

    client.logger.info('异步调用测试开始')
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(call_method, i) for i in range(30)]
        for future in futures:
            future.result()
    client.logger.info('异步调用测试完成\n')


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
        # 同步调用测试
        test_sync_calls(client)

        # 异步调用测试
        test_async_calls(client)

    except KeyboardInterrupt:
        client.logger.info(f"Main thread received KeyboardInterrupt, stopping...")
    finally:
        client.stop()
        exit(0)
