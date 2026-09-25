"""画面からの入力が不正な場合にも表を返さないことを確認する。"""
import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from solver.server import Handler


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path='/', body=None, headers=None):
        c = HTTPConnection('127.0.0.1', self.server.server_port)
        c.request('POST' if body is not None else 'GET', path, body, headers or {})
        r = c.getresponse(); data = r.read(); status = r.status; c.close()
        return status, data

    def test_screen_and_cases(self):
        code, body = self.request()
        self.assertEqual(code, 200)
        self.assertIn('公休表 検証室', body.decode())
        code, body = self.request('/cases')
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(body)), 12)

    def test_other_origin_rejected(self):
        code, _ = self.request('/solve', '{}', {'Content-Type': 'application/json', 'Origin': 'https://example.com'})
        self.assertEqual(code, 403)

    def test_invalid_json_rejected(self):
        code, _ = self.request('/solve', '{', {'Content-Type': 'application/json'})
        self.assertEqual(code, 400)

    def test_invalid_conditions_never_return_table(self):
        code, body = self.request('/solve', json.dumps({'input': {'staff': []}}), {'Content-Type': 'application/json'})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['status'], 'INVALID_INPUT')
        self.assertNotIn('assignments', json.loads(body))

    def test_external_host_rejected(self):
        code, _ = self.request(headers={'Host': 'example.com'})
        self.assertEqual(code, 403)

    def test_non_json_rejected(self):
        code, _ = self.request('/solve', 'data=test', {'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(code, 415)
