import http.client
import json
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from app import make_server, PLAN_REQUEST_LIMIT, REQUEST_LIMIT


class RequestSizeTests(unittest.TestCase):
    def setUp(self):
        self.store = SimpleNamespace(
            snapshot=lambda: {}, plan=Mock(return_value={'token': 'sessions'}),
            files=SimpleNamespace(plan=Mock(return_value={'token': 'files'})))
        self.server = make_server(self.store, 0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        conn = self.connection()
        try:
            conn.request('GET', '/api/state')
            self.csrf = json.loads(conn.getresponse().read())['csrf']
        finally:
            conn.close()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def connection(self):
        return http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)

    def post(self, endpoint, body=b'', **headers):
        conn = self.connection()
        try:
            conn.request('POST', endpoint, body=body, headers={
                'Content-Type': 'application/json', 'Origin': self.base,
                'X-CSRF-Token': self.csrf, **headers})
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_large_selections_reach_both_plan_services_intact(self):
        cases = [('/api/plan', self.store.plan,
                  [str(uuid.uuid4()) for _ in range(2000)], {}),
                 ('/api/files-plan', self.store.files.plan,
                  [f'.tmp/中文目录/{i:05d}-' + 'x' * 100 for i in range(1000)], {'days': 30})]
        for endpoint, service, ids, extra in cases:
            with self.subTest(endpoint=endpoint):
                body = json.dumps({'ids': ids, **extra}, ensure_ascii=False).encode('utf-8')
                self.assertGreater(len(body), REQUEST_LIMIT)
                status, result = self.post(endpoint, body)
                self.assertEqual(status, 200, result)
                if extra:
                    service.assert_called_once_with(ids, 30)
                else:
                    service.assert_called_once_with(ids)

    def test_plan_limit_boundary(self):
        for endpoint, service in [('/api/plan', self.store.plan),
                                  ('/api/files-plan', self.store.files.plan)]:
            with self.subTest(endpoint=endpoint):
                body = b'{"ids":["selected"]}'
                body += b' ' * (PLAN_REQUEST_LIMIT - len(body))
                status, result = self.post(endpoint, body)
                self.assertEqual(status, 200, result)
                service.assert_called_once()
                service.reset_mock()
                # Advertise an oversized body without sending it: reject before reading.
                status, result = self.post(endpoint, **{'Content-Length': str(PLAN_REQUEST_LIMIT + 1)})
                self.assertEqual(status, 413)
                self.assertIn(str(PLAN_REQUEST_LIMIT // 1024), result['error'])
                service.assert_not_called()

    def test_control_requests_keep_small_limit(self):
        status, result = self.post('/api/scan', **{'Content-Length': str(REQUEST_LIMIT + 1)})
        self.assertEqual(status, 413)
        self.assertIn(str(REQUEST_LIMIT // 1024), result['error'])

    def test_large_plans_still_require_csrf(self):
        for endpoint in ('/api/plan', '/api/files-plan'):
            with self.subTest(endpoint=endpoint):
                status, _ = self.post(endpoint, **{
                    'Content-Length': str(REQUEST_LIMIT + 1), 'X-CSRF-Token': 'invalid'})
                self.assertEqual(status, 403)
        self.store.plan.assert_not_called()
        self.store.files.plan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
