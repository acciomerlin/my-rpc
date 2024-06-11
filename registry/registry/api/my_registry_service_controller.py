from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs
from ..beans.instance_meta import InstanceMeta
from ..service.impl.my_registry_service import MyRegistryService

# 初始化注册服务
register_service = MyRegistryService()


class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        """
        处理POST请求，根据URL路径执行相应的操作。
        """
        # 解析请求路径和查询参数
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)

        # 读取请求体数据
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        body = json.loads(post_data)

        # 处理注册请求
        if parsed_path.path == '/myRegistry/register':
            instance_meta = InstanceMeta.from_dict(body)
            server = instance_meta.host + ":" + str(instance_meta.port)
            self.log_message(f"====> register server: {server}, instance: {instance_meta}")
            registered_instance = register_service.register(instance_meta)
            self.respond(registered_instance.to_dict())

        # 处理注销请求
        elif parsed_path.path == '/myRegistry/unregister':
            instance_meta = InstanceMeta.from_dict(body)
            server = instance_meta.host + ":" + str(instance_meta.port)
            self.log_message(f"====> unregister server: {server}, instance: {instance_meta}")
            unregistered_instance = register_service.unregister(instance_meta)
            self.respond(unregistered_instance.to_dict())

    def do_GET(self):
        """
        处理GET请求，根据URL路径执行相应的操作。
        """
        # 解析请求路径和查询参数
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)

        # 处理查询所有实例请求
        if parsed_path.path == '/myRegistry/findAllInstances':
            protocol = query_params.get('proto', [None])[0]
            self.log_message(f"====> findAllInstances by protocol: {protocol}")
            instances = register_service.find_instances_by_protocol(protocol)
            self.respond([instance.to_dict() for instance in instances])

    def respond(self, data):
        """
        发送响应数据。
        :param data: 要发送的数据，可以是任何可以被json序列化的对象。
        """
        response = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(response)
