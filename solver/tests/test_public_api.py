"""公開する窓口が不正入力や未検査の表を通さないことを確認する。"""
import json
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from solver.app_server import AppHandler
from solver.benchmark import cases
from solver.service import dispatch


class PublicApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), AppHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, body=None, headers=None):
        c = HTTPConnection('127.0.0.1', self.server.server_port)
        c.request('GET' if body is None else 'POST', path, body, headers or {})
        r = c.getresponse()
        status, content = r.status, r.read()
        c.close()
        return status, content

    def test_health_and_no_private_data(self):
        status, body = self.request('/api/schedule')
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['ready'])
        self.assertEqual(self.request('/user_data.json')[0], 404)

    def test_cross_origin_and_invalid_json(self):
        self.assertEqual(self.request('/api/schedule', '{}', {'Origin': 'https://example.com', 'Content-Type': 'application/json'})[0], 403)
        self.assertEqual(self.request('/api/schedule', '{', {'Content-Type': 'application/json'})[0], 400)

    def test_time_limit_cannot_be_removed(self):
        raw = next(cases())[1]
        for seconds in (0, 61, True, '60'):
            self.assertEqual(dispatch({'input': raw, 'seconds': seconds})['status'], 'INVALID_INPUT')

    def test_empty_table_cannot_pass_validation(self):
        result = dispatch({'action': 'validate', 'input': next(cases())[1], 'assignments': {}})
        self.assertEqual(result['status'], 'INVALID')
        self.assertTrue(result['validationErrors'])
