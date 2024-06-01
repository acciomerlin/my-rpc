from time import sleep

from services import Channel, ClientStub, InvalidOperation

# 创建与服务器连接的通道
channel = Channel('127.0.0.1', 8000)

# 创建客户端代理，使用RPC服务的工具
stub = ClientStub(channel)

# 使用RPC服务，进行远程服务调用
# for i in range(5):
while True:
    sleep(2)
    try:
        val = stub.divide(100, 10)
        val2 = stub.add(100,100)
    except InvalidOperation as e:
        print(e.message)
    else:
        print(val)