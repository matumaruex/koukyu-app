"""Vercel上の計算窓口。入力データを保存せず、その場で計算・検査する。"""
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from solver.service import dispatch


class handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(200, {'version': '3.0', 'ready': True})

    def do_POST(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        if origin and urlparse(origin).netloc != host:
            return self.reply(403, {'error': 'アプリから操作してください。'})
        if self.headers.get_content_type() != 'application/json':
            return self.reply(415, {'error': '入力形式を確認してください。'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 400_000:
                return self.reply(413, {'error': 'データが大きすぎるか空です。'})
            payload = json.loads(self.rfile.read(size))
            result = dispatch(payload)
        except (ValueError, TypeError):
            return self.reply(400, {'error': '入力データを読み取れませんでした。'})
        except Exception:
            # 職員情報を含む例外の詳細はレスポンスやログに出さない。
            return self.reply(500, {'error': '計算を完了できませんでした。保存済みの表は残っています。'})
        self.reply(200, result)

    def log_message(self, fmt, *args):
        pass
