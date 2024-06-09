from http.server import HTTPServer
from registry.api.my_registry_service_controller import RequestHandler


def run(server_class=HTTPServer, handler_class=RequestHandler, port=8081):
    """
    运行HTTP服务器。
    :param server_class: HTTP服务器类。
    :param handler_class: 请求处理程序类。
    :param port: 服务器监听的端口。
    """
    server_address = ('', port)  # 监听来自所有网络接口的请求
    httpd = server_class(server_address, handler_class)
    print(f'Starting httpd server on port {port}')
    httpd.serve_forever()


if __name__ == '__main__':
    run()