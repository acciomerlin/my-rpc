import socket
import struct
import threading
from io import BytesIO


class InvalidOperation(Exception):
    def __init__(self, message=None):
        self.message = message or "Invalid Operation"


class MethodProtocol(object):
    """
    解读方法名字，放些辅助工具，考虑做成基类，让实际的方法Protocol继承这个
    """

    def __init__(self, connection):
        self.conn = connection

    def _read_all(self, size):
        """
        帮助读取二进制数据
        :param size: 欲读取的二进制数据大小
        :return: bytes 二进制数据
        """
        # 从 self.conn 中读取二进制数据，可能有两种类型：BytesIO或者socket, 要做类型判断分别处理
        # BytesIO.read(size) => truly size
        # socket.recv(size) => maybe less than size+
        if isinstance(self.conn, BytesIO):
            buff = self.conn.read(size)
            return buff
        else:
            # socket
            have = 0
            buff = b''
            while have < size:
                chunk = self.conn.recv(size)
                buff += chunk
                l = len(chunk)
                have += l

                if l == 0:
                    # 表示客户端socket关闭了连接
                    raise EOFError()
            return buff

    def get_method_name(self):
        """
        解析请求消息的方法名
        :return: str 方法名
        """
        # 读取方法名字符串长度
        buff = self._read_all(4)
        name_len = struct.unpack('!I', buff)[0]

        # 读取方法名字符
        buff = self._read_all(name_len)
        name = buff.decode()
        return name


class DivideProtocol(object):
    """
    divide过程消息协议转换工具
    """

    def args_encode(self, num1, num2=1):
        """
        将原始的调用参数转换打包成二进制消息数据
        :param num1: int
        :param num2: int
        :return: bytes 二进制消息数据
        """
        name = 'divide'

        # 处理方法的名字 字符串
        # 处理字符串长度
        buff = struct.pack('!I', 6)
        # 处理字符
        buff += name.encode()

        # 处理参数1
        # 处理序号
        buff2 = struct.pack('!B', 1)
        # 处理参数值
        buff2 += struct.pack('!i', num1)

        # 处理参数2
        if num2 != 1:
            # 处理序号
            buff2 += struct.pack('!B', 2)
            # 处理参数值
            buff2 += struct.pack('!i', num2)

        # 处理消息长度，边界确定
        args_length = len(buff2)
        buff += struct.pack('!I', args_length)

        buff += buff2
        return buff

    def _read_all(self, size):
        """
        帮助读取二进制数据
        :param size: 欲读取的二进制数据大小
        :return: bytes 二进制数据
        """
        # 从 self.conn 中读取二进制数据，可能有两种类型：BytesIO或者socket, 要做类型判断分别处理
        # BytesIO.read(size) => truly size
        # socket.recv(size) => maybe less than size+
        if isinstance(self.conn, BytesIO):
            buff = self.conn.read(size)
            return buff
        else:
            # socket
            have = 0
            buff = b''
            while have < size:
                chunk = self.conn.recv(size)
                buff += chunk
                l = len(chunk)
                have += l

                if l == 0:
                    # 表示客户端socket关闭了连接
                    raise EOFError()
            return buff

    def args_decode(self, connection):
        """
        接收调用请求消息数据并解析
        :param connection: 连接对象 socket bytesIO
        :return: dict 包含了解析之后的参数
        """
        # 参数长度映射，便于灵活处理
        param_len_map = {
            1: 4,
            2: 4
        }
        # 参数格式映射
        param_fmt_map = {
            1: '!i',
            2: '!i'
        }
        # 参数名映射
        param_name_map = {
            1: 'num1',
            2: 'num2'
        }

        # 保存用来返回的参数字典
        # args = {"num1": xxx, "num2": xxx}
        args = {}

        self.conn = connection
        # 处理方法名 稍后实现

        # 处理消息边界
        # 读取二进制数据
        buff = self._read_all(4)
        args_length = struct.unpack('!I', buff)[0]

        # 已经读取decode的字节数，用于判断是否有参数2
        have = 0

        # 处理第一个参数
        # 处理参数序号
        buff = self._read_all(1)
        have += 1
        param_seq = struct.unpack('!B', buff)[0]

        # 处理参数值
        param_len = param_len_map[param_seq]
        buff = self._read_all(param_len)
        have += param_len
        param_fmt = param_fmt_map[param_seq]
        param = struct.unpack(param_fmt, buff)[0]

        param_name = param_name_map[param_seq]
        args[param_name] = param

        if have >= args_length:
            return args

        # 处理第二个参数
        # 处理参数序号
        buff = self._read_all(1)
        have += 1
        param_seq = struct.unpack('!B', buff)[0]

        # 处理参数值
        param_len = param_len_map[param_seq]
        buff = self._read_all(param_len)
        have += param_len
        param_fmt = param_fmt_map[param_seq]
        param = struct.unpack(param_fmt, buff)[0]

        param_name = param_name_map[param_seq]
        args[param_name] = param

        return args

    def result_encode(self, result):
        """
        将原始结果数据转换为消息协议二进制数据
        :param result: 原始结果数据 float / InvalidOperation
        :return: bytes 消息协议二进制数据
        """

        # 1：正常
        if isinstance(result, float):
            # 一字节整数存返回类型，float对应字节存返回值
            buff = struct.pack('!B', 1)
            buff += struct.pack('!f', result)
            return buff
        # 2：异常
        else:
            # 一字节整数存返回类型，然后按处理字符串的流程存字符串长度+字符串本身
            buff = struct.pack('!B', 2)
            length = len(result.message)
            buff += struct.pack('!I', length)
            buff += result.message.encode()
            return buff

    def result_decode(self, connection):
        """
        将返回值二进制消息数据转回原始返回值
        :param connection: socket / BytesIO
        :return: float / InvalidOperation
        """
        self.conn = connection

        # unpack返回值类型，根据类型做不同处理
        buff = self._read_all(1)
        result_type = struct.unpack('!B', buff)[0]

        if result_type == 1:
            # 正常
            # 读取结果float数据
            buff = self._read_all(4)
            val = struct.unpack('!f', buff)[0]
            return val
        else:
            # 异常
            # 读取异常消息字符串长度
            buff = self._read_all(4)
            length = struct.unpack('!I', buff)[0]

            # 读取 length长度字符串
            buff = self._read_all(length)
            message = buff.decode()

            return InvalidOperation(message)


class Channel(object):
    """
    客户端进行服务发现的通道，与服务端进行网络连接
    ps: 创建channel != 创建连接，只有远程调用时要创建连接，传入clinetstub时才会调用get_connection方法创建连接，所以init没有创建连接
    """

    def __init__(self, host, port):
        """
        建立在TCP之上，初始化先提供要连接的服务器的主机名和端口号
        :param host: 服务器地址
        :param port: 服务器端口号
        """
        self.host = host
        self.port = port

    def get_connection(self):
        """
        获取连接对象
        :return: 与服务器通讯的socket
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, self.port))
        return sock


class Server(object):
    """
    RPC服务器
    """

    def __init__(self, host, port, handlers):
        # 创建socket工具对象
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # 设置socket重用地址
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 绑定服务器地址
        sock.bind((host, port))
        self.host = host
        self.port = port
        self.sock = sock
        self.handlers = handlers

    def serve(self):
        """
        启动服务器，创建服务器代理注册服务，提供RPC服务
        :return:
        """
        # 服务器开启监听，等待客户端连接请求
        self.sock.listen(128)
        print(f'服务器{self.host}于{self.port}开启了监听......')

        # 接收客户端连接请求
        while True:
            client_sock, client_addr = self.sock.accept()
            print(f'与客户端{str(client_addr)}建立了连接')

            # 创建服务端代理，交予与客户端的连接与要注册的服务
            stub = ServerStub(client_sock, self.handlers)
            try:
                while True:
                    stub.process()
            except EOFError:
                # 客户端关闭了连接(_read_all里面的判断）
                print(f'客户端{str(client_addr)}关闭了连接')
                client_sock.close()


class MultiThreadServer(object):
    """
    RPC服务器
    """

    def __init__(self, host, port, handlers):
        # 创建socket工具对象
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # 设置socket重用地址
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # 绑定服务器地址
        sock.bind((host, port))
        self.host = host
        self.port = port
        self.sock = sock
        self.handlers = handlers

    def serve(self):
        """
        启动服务器，创建服务器代理注册服务，提供RPC服务
        :return:
        """
        # 服务器开启监听，等待客户端连接请求
        self.sock.listen(128)
        print(f'服务器{self.host}于{self.port}开启了监听......')

        # 接收客户端连接请求
        while True:
            client_sock, client_addr = self.sock.accept()
            print(f'与客户端{str(client_addr)}建立了连接')

            # 创建子线程处理此客户端
            t = threading.Thread(target=self.handle, args=(client_sock, client_addr))
            # 启动子线程，主线程继续循环接收另一个客户端连接的请求
            t.start()

    def handle(self, client_sock, client_addr):
        """
        子线程调用方法，用来处理一个客户端的请求
        :param client_sock: 客户端连接socket
        :param client_addr: 客户端addr
        :return:
        """
        # 创建服务端代理，交予与客户端的连接与要注册的服务
        stub = ServerStub(client_sock, self.handlers)
        try:
            while True:
                stub.process()
        except EOFError:
            # 客户端关闭了连接(_read_all里面的判断）
            print(f'客户端{str(client_addr)}关闭了连接')
            client_sock.close()


class ClientStub(object):
    """
    客户端代理：帮助客户端完成 RPC 调用，客户端要远程调用时创建代理传入channel就可以近似本地调用的体感调用远程方法了
    例：
    stub = ClientStub(channel)
    stub.divide(200,100)
    stub.add()
    """

    def __init__(self, channel):
        self.channel = channel
        self.conn = self.channel.get_connection()

    def divide(self, num1, num2=1):
        # 打包调用参数
        proto = DivideProtocol()
        args = proto.args_encode(num1, num2)

        # 发送打包后的消息数据
        self.conn.sendall(args)

        # 接收服务器返回的消息数据，并进行解析
        result = proto.result_decode(self.conn)

        # 将结果 (正常float / 异常 InvalidOperation) 返回给客户端
        if isinstance(result, float):
            return result
        else:
            raise result

    # 更多服务发现
    # def add(self):
    #     pass


class ServerStub(object):
    """
    服务端代理：帮助服务端进行服务注册，辅助完成服务端的RPC
    """

    def __init__(self, connection, handlers):
        """
        :param connection: 与客户端的连接
        :param handlers: 真正被服务端本地调用的方法 （函数/过程）
        class Handlers: # Server要创建的类，用于注册服务

            @staticmethod # 使得不用创建对象直接使用类方法
            def divide():
                pass
        """
        self.conn = connection
        self.method_proto = MethodProtocol(self.conn)
        self.process_map = {
            'divide': self._process_divide,
        }
        self.handlers = handlers

    def process(self):
        """
        当服务端接收并建立了一个与客户端的连接后，处理远程调用
        :return:
        """
        # 根据接收消息解析调用方法名
        name = self.method_proto.get_method_name()

        # 根据解析的方法名调用对应的方法协议
        try:
            _process = self.process_map[name]
            _process()
        except KeyError:
            print(f"No service found for: {name}")

    def _process_divide(self):
        """
        处理除法方法调用
        :return:
        """
        # 创建用于除法方法调用参数协议数据解析的工具
        proto = DivideProtocol()
        # 解析调用参数
        # args = {"num1": xxx, "num2": xxx}
        args = proto.args_decode(self.conn)

        # 服务端调用此注册的方法
        # 并将此方法返回值打包成消息协议数据，通过连接返回客户端
        try:
            val = self.handlers.divide(**args)  # py grammar, 展开字典
        except InvalidOperation as e:
            ret_msg = proto.result_encode(e)
        else:
            ret_msg = proto.result_encode(val)

        self.conn.sendall(ret_msg)

    # def _process_add(self):
    #     pass


if __name__ == '__main__':
    proto = DivideProtocol()

    # encodeTest
    # divide(200, 100)
    # encoded_mes = proto.args_encode(200, 100)
    # divide(200)
    encoded_mes = proto.args_encode(200)
    # bytesIO模拟conn
    conn = BytesIO()
    conn.write(encoded_mes)
    conn.seek(0)  # 使读时从头读
    print(encoded_mes)

    # decodeTest
    method_proto = MethodProtocol(conn)
    name = method_proto.get_method_name()
    print(name)

    args = proto.args_decode(conn)
    print(args)
