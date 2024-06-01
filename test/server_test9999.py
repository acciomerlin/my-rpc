import time

import rpc_provider as rpc


def add(a, b, c=10):
    sum = a + b + c
    return sum


def hi(user):
    print(f"hi {user}, welcome")
    time.sleep(3)
    return f"hi {user}, welcome"


s = rpc.RPCServer()
s.register_services(add)
s.register_services(hi)
s.serve('127.0.0.1', 9999)
