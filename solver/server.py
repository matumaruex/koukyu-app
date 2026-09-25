"""検証用画面をこのPCだけに配信する。本番データの変更は行わない。"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from .benchmark import cases
from .engine import solve

ROOT = Path(__file__).resolve().parent
BUSY = Lock()


class Handler(BaseHTTPRequestHandler):
    def send(self, status, value, content_type='application/json; charset=utf-8'):
        body = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        for key, val in [('Content-Type', content_type), ('Content-Length', str(len(body))), ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]:
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(body)

    def local(self):
        hosts = (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
        return self.headers.get('Host') in hosts and self.headers.get('Origin', 'http://' + hosts[0]) in ['http://' + h for h in hosts]

    def do_GET(self):
        if not self.local():
            return self.send(403, {'error': 'このPCからアクセスしてください。'})
        if self.path == '/':
            return self.send(200, (ROOT / 'lab.html').read_text(encoding='utf-8'), 'text/html; charset=utf-8')
        if self.path == '/cases':
            return self.send(200, [{'title': title, 'input': p} for title, p in cases()])
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        if not self.local():
            return self.send(403, {'error': 'このPCからアクセスしてください。'})
        if self.path != '/solve':
            return self.send(404, {'error': 'Not found'})
        if self.headers.get_content_type() != 'application/json':
            return self.send(415, {'error': 'JSON required'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2_000_000:
                return self.send(413, {'error': 'データが大きすぎるか空です。'})
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or not isinstance(payload.get('input'), dict):
                raise ValueError('入力データが必要です。')
            if not isinstance(payload['input'].get('staff'), list) or len(payload['input']['staff']) > 100:
                raise ValueError('検証画面では100人以内の職員リストを使用してください。')
            seconds = float(payload.get('seconds', 12))
            if not 0 < seconds <= 30:
                raise ValueError('計算上限は1〜30秒にしてください。')
        except (ValueError, TypeError) as exc:
            return self.send(400, {'error': str(exc)})
        if not BUSY.acquire(blocking=False):
            return self.send(429, {'error': '別の計算が実行中です。完了後に再試行してください。'})
        try:
            self.send(200, solve(payload['input'], seconds=seconds))
        finally:
            BUSY.release()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    port = parser.parse_args().port
    print(f'http://127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    main()
