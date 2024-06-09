import random
import threading
import unittest
import json
import http.client
from time import sleep

from registry.beans.instance_meta import InstanceMeta
from app import run


class Test(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        print("UnitTest Begin...")
        # 启动服务器
        self.server_thread = threading.Thread(target=run, kwargs={'port':8081}, daemon=True)
        self.server_thread.start()
        sleep(1)

    @classmethod
    def tearDownClass(self):
        # 关闭服务器
        print("UnitTest End...")

    def setUp(self):
        print("Begin a test case...")

    # Run after each test case execution
    def tearDown(self):
        print("End a test case...")

    def test_1_register(self):
        conn = http.client.HTTPConnection("localhost", 8081)
        headers = {'Content-type': 'application/json'}

        for i in range(20):
            random_ctx = random.randint(1, 10)
            instance = InstanceMeta("json", "127.0.0.1", 9999 + random_ctx)
            instance.add_parameters({'alive-time': 100, 'ip_proto': 'ipv4'})
            instance_data = json.dumps(instance.to_dict())

            conn.request("POST", "/myRegistry/register?proto=json", instance_data, headers)
            response = conn.getresponse()

            self.assertEqual(response.status, 200)
            response_data = json.loads(response.read().decode())
            print(response_data)
            self.assertEqual(response_data['host'], "127.0.0.1")
        conn.close()

    def test_2_unregister(self):
        conn = http.client.HTTPConnection("localhost", 8081)
        headers = {'Content-type': 'application/json'}

        random_ctx = random.randint(1,10)
        instance = InstanceMeta("json", "127.0.0.1", 9999+random_ctx)
        instance_data = json.dumps(instance.to_dict())

        conn.request("POST", "/myRegistry/unregister?server=test_server", instance_data, headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response_data = json.loads(response.read().decode())
        print(response_data)
        self.assertEqual(response_data['host'], "127.0.0.1")
        conn.close()

    def test_3_find_instances_by_proto(self):
        conn = http.client.HTTPConnection("localhost", 8081)
        conn.request("GET", "/myRegistry/findAllInstances?proto=json")
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response_data = json.loads(response.read().decode())
        print(response_data)
        self.assertIsInstance(response_data, list)
        conn.close()

    # def test_renews(self):
    #     conn = http.client.HTTPConnection("localhost", 8081)
    #     headers = {'Content-type': 'application/json'}
    #
    #     instance = InstanceMeta("http", "localhost", 8080, "context")
    #     instance_data = json.dumps(instance.to_dict())
    #
    #     conn.request("POST", "/myRegistry/renews?servers=test_server", instance_data, headers)
    #     response = conn.getresponse()
    #     self.assertEqual(response.status, 200)
    #     response_data = json.loads(response.read().decode())
    #     print(response_data)
    #     self.assertIsInstance(response_data, int)
    #     conn.close()
    #
    # def test_version(self):
    #     conn = http.client.HTTPConnection("localhost", 8081)
    #     conn.request("GET", "/myRegistry/version?server=test_server")
    #     response = conn.getresponse()
    #     self.assertEqual(response.status, 200)
    #     response_data = json.loads(response.read().decode())
    #     print(response_data)
    #     self.assertIsInstance(response_data, int)
    #     conn.close()

    # def test_versions(self):
    #     conn = http.client.HTTPConnection("localhost", 8081)
    #     conn.request("GET", "/myRegistry/versions?servers=test_server")
    #     response = conn.getresponse()
    #     self.assertEqual(response.status, 200)
    #     response_data = json.loads(response.read().decode())
    #     self.assertIsInstance(response_data, dict)
    #     conn.close()


if __name__ == '__main__':
    unittest.main()
