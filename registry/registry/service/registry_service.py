from abc import ABC, abstractmethod
from ..beans.instance_meta import InstanceMeta
from typing import List


class RegistryService(ABC):
    """
    注册中心服务接口类
    """

    @abstractmethod
    def register(self, instance: InstanceMeta) -> InstanceMeta:
        pass

    @abstractmethod
    def unregister(self, instance: InstanceMeta) -> InstanceMeta:
        """
        Unregister a service instance from the given server.

        :param instance: The instance of the service to unregister.
        :return: The unregistered InstanceMeta object.
        """
        pass

    @abstractmethod
    def find_instances_by_protocol(self, protocol : str) -> List[InstanceMeta]:
        pass

    @abstractmethod
    def handle_check_health(self):
        """
        定期检查instances的时间戳以判定服务是否还活着
        """
        pass

