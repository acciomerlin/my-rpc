from abc import ABC, abstractmethod
from registry.beans.instance_meta import InstanceMeta
from typing import List, Dict


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

    # @abstractmethod
    # def version(self, server: str) -> int:
    #     """
    #     Get the current version of the given server.
    #
    #     :param server: The server name to get the version of.
    #     :return: The version number of the server.
    #     """
    #     pass
    #
    # @abstractmethod
    # def versions(self, *servers: str) -> Dict[str, int]:
    #     """
    #     Get the versions of multiple servers.
    #
    #     :param servers: The names of the servers to get the versions of.
    #     :return: A dictionary mapping server names to their version numbers.
    #     """
    #     pass
    #
    # @abstractmethod
    # def renew(self, instance: InstanceMeta, *servers: str) -> int:
    #     """
    #     Renew the timestamp for the given instance on the specified servers.
    #
    #     :param instance: The instance of the service to renew.
    #     :param servers: The names of the servers where the instance should be renewed.
    #     :return: The new timestamp after renewal.
    #     """
    #     pass
