"""公開版と同じ画面・APIをローカルで確認する。"""
from http.server import ThreadingHTTPServer
from pathlib import Path
from api.schedule import handler

PUBLIC = Path(__file__).resolve().parents[1] / 'public'


class AppHandler(handler):
    def do_GET(self):
        path = self.path.split('?')[0]
        files = {'/': ('index.html', 'text/html'), '/mobile.js': ('mobile.js', 'text/javascript'), '/roster-storage.js': ('roster-storage.js', 'text/javascript'), '/creation-workflow.js': ('creation-workflow.js', 'text/javascript'), '/mobile.css': ('mobile.css', 'text/css'), '/example.json': ('example.json', 'application/json')}
        for script in ('overtime-preference.js', 'consecutive-rest.js', 'overtime-cycles.js', 'auto-holiday-policy.js', 'auto-creation-workflow.js', 'auto-roster-ui.js'):
            files['/' + script] = (script, 'text/javascript')
        # 3.48：象形文字だけを切り出した書体（公開版と同じく public/fonts から配る）。
        files['/fonts/egypt-glyphs.woff2'] = ('fonts/egypt-glyphs.woff2', 'font/woff2')
        if path == '/api/schedule':
            return super().do_GET()
        if path not in files:
            return self.reply(404, {'error': 'Not found'})
        name, mime = files[path]
        body = (PUBLIC / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mime if mime.startswith('font/') else mime + '; charset=utf-8')
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

