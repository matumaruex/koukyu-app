"""公開版と同じ画面・APIをローカルで確認する。"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from api.schedule import handler

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


class AppHandler(handler):
    def do_GET(self):
        path = self.path.split('?')[0]
        files = {'/': ('index.html', 'text/html'), '/mobile.js': ('mobile.js', 'text/javascript'), '/mobile.css': ('mobile.css', 'text/css'), '/example.json': ('example.json', 'application/json')}
        if path == '/api/schedule':
            return super().do_GET()
        if path not in files:
            return self.reply(404, {'error': 'Not found'})
        name, mime = files[path]
        body = (PUBLIC / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/api/schedule':
            return self.reply(404, {'error': 'Not found'})
        super().do_POST()


if __name__ == '__main__':
    print('http://127.0.0.1:8766/', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8766), AppHandler).serve_forever()
