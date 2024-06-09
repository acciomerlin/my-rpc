from urllib.parse import urlparse


class InstanceMeta:
    def __init__(self, protocol=None, host=None, port=None):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.status = None
        self.parameters = {}

    # def to_path(self):
    #     return f"{self.host}_{self.port}_{self.context}"
    #
    def to_url(self):
        return f"{self.protocol}://{self.host}:{self.port}"

    def add_parameters(self, parameters):
        self.parameters.update(parameters)
        return self

    # @staticmethod
    # def from_url(url):
    #     parsed_url = urlparse(url)
    #     context = parsed_url.path.lstrip('/')
    #     return InstanceMeta(parsed_url.scheme, parsed_url.hostname, parsed_url.port, context)

    @staticmethod
    def from_dict(data):
        instance = InstanceMeta(
            protocol=data.get('protocol'),
            host=data.get('host'),
            port=data.get('port'),
        )
        instance.status = data.get('status')
        instance.parameters = data.get('parameters', {})
        return instance

    def to_dict(self):
        return {
            'protocol': self.protocol,
            'host': self.host,
            'port': self.port,
            'status': self.status,
            'parameters': self.parameters
        }

    def get_protocol(self):
        return self.protocol

    def set_protocol(self, schema):
        self.protocol = schema

    def get_host(self):
        return self.host

    def set_host(self, host):
        self.host = host

    def get_port(self):
        return self.port

    def set_port(self, port):
        self.port = port

    def get_status(self):
        return self.status

    def set_status(self, status):
        self.status = status

    def get_parameters(self):
        return self.parameters

    def set_parameters(self, parameters):
        self.parameters = parameters

    def __eq__(self, other):
        if not isinstance(other, InstanceMeta):
            return False
        return (self.protocol == other.protocol and
                self.host == other.host and
                self.port == other.port)

    def __hash__(self):
        return hash((self.protocol, self.host, self.port))

    def __str__(self):
        return (f"InstanceMeta(protocol={self.protocol}, host={self.host}, port={self.port}, "
                f"status={self.status}, parameters={self.parameters})")


# test
if __name__ == '__main__':
    instance = InstanceMeta("json", "127.0.0.1", 8080)
    # print(instance.to_path())
    # print(instance.to_url())
    print(instance.add_parameters({"key": "value"}))
    print(instance.add_parameters({"name":"accio"}))
