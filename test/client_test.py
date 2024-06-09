import threading
import time

import rpc_consumer as rpc

c = rpc.RPCClient()
c.connect_server_by_registry()
c.stop()
c.connect_server_by_registry()

# def test(i):
#     c = rpc.RPCClient()
#     # 加了注册中心后， connect, loadbalance 都放RPCClient中实现, 用户只需c,hi()获取res就好
#     # c.connect('127.0.0.1', 9999)
#     c.connect_server_by_registry()
#     t0 = threading.Thread(target=c.poll_registry)
#     t0.start()
#     res = c.hi(i)
#     print(f"res: {res}")
#     c.close()
#     return
#
#
# threads=[]
#
# # for i in range(10):
# #     # 创建子线程处理此客户端
# #     t = threading.Thread(target=test, args=(i,))
# #     threads.append(t)
# #     # 启动子线程，主线程继续循环接收另一个客户端连接的请求
# #     t.start()
# #
# # for t in threads:
# #     t.join()
#
# test("accio")
