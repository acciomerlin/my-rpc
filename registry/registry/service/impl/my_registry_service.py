from datetime import datetime
import threading
from collections import defaultdict
import time
from typing import List
from ...beans.instance_meta import InstanceMeta
from ..registry_service import RegistryService


class MyRegistryService(RegistryService):
    def __init__(self):
        self.proto2instances = defaultdict(list)  # 访问不存在键时不会抛keyerror, 会返回默认值，list表示默认值设置为空列表
        self.versions = {}
        self.version_counter = 0
        self.ins2timestamp = defaultdict(int)
        threading.Thread(target=self.loop_check_health).start()

    def register(self, ins: InstanceMeta) -> InstanceMeta:
        proto = ins.protocol
        if ins in self.proto2instances[proto]:
            print(f"==> already exists instance: {ins}")
            ins.set_status(True)
            # 更新时间戳
            old_time = self.ins2timestamp[ins]
            print(f"该实例上一次注册的时间：{datetime.fromtimestamp(old_time).strftime('%Y-%m-%d %H:%M:%S')}")
            self.ins2timestamp[ins] = int(time.time())
            new_time = self.ins2timestamp[ins]
            print(f"该实例本次时间戳更新的时间：{datetime.fromtimestamp(new_time).strftime('%Y-%m-%d %H:%M:%S')}")
            return ins
        print(f"==> register instance: {ins}")
        ins.set_status(True)  # 实例状态置为已注册
        self.proto2instances[proto].append(ins)
        self.ins2timestamp[ins] = int(time.time())
        return ins

    def unregister(self, ins: InstanceMeta) -> InstanceMeta:
        proto = ins.protocol
        if ins not in self.proto2instances[proto]:
            print(f"==> not exists instance: {ins}")
            ins.set_status(False)
            return ins
        print(f"==> unregister instance: {ins}")
        self.proto2instances[proto].remove(ins)
        del self.ins2timestamp[ins]
        ins.set_status(False)

        return ins

    def find_instances_by_protocol(self, protocol="json") -> List[InstanceMeta]:
        return self.proto2instances[protocol]

    def handle_check_health(self):
        """定期检查instances的时间戳以判定服务是否还活着线程的target函数"""
        cur_time = int(time.time())
        threshold = 10  # s
        if not self.ins2timestamp:
            print(f'instance list is empty')
        else:
            for ins, timestamp in list(self.ins2timestamp.items()):
                if cur_time - timestamp > threshold:
                    print(
                        f"!!!Instance {ins} is unhealthy, last seen at {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}")
                    self.unregister(ins)
                else:
                    print(
                        f"Instance {ins} is healthy, last seen at {datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')}")

    def loop_check_health(self):
        """定期检查services活性"""
        while True:
            time.sleep(5)
            print("=======================health checking====================")
            self.handle_check_health()


# 示例用法
if __name__ == "__main__":
    service = MyRegistryService()
    instance = InstanceMeta("json", "localhost", 8080)
    service.register(instance)
    instance = InstanceMeta("json", "localhost", 8081)
    service.register(instance)
    instances = service.find_instances_by_protocol("json")
    for i in instances:
        print(i)
    service.unregister(instance)
    instances = service.find_instances_by_protocol("json")
    for i in instances:
        print(i)
