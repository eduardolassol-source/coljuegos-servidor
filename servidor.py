import http.server, urllib.request, urllib.error, ssl, json, os, threading, webbrowser, time

PORT = int(os.environ.get('PORT', 8520))

def get_api_key():
    # Primero buscar en variable de entorno (Render)
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if key: return key
    # Fallback: archivo local (PC)
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_key.txt')
    if os.path.exists(f):
        key = open(f).read().strip()
        if key and key != 'TU_API_KEY_AQUI': return key
    return None

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=os.path.dirname(os.path.abspath(__file__)), **kw)
    def log_message(self, fmt, *args): pass  # silenciar logs

    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()

    def do_GET(self):
        if self.path == '/ping':
            self._ok({'status': 'ok'})
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == '/api/extraer': self._extraer()
        else: self.send_error(404)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _extraer(self):
        api_key = get_api_key()
        if not api_key:
            return self._err(503, 'API key no configurada (env: ANTHROPIC_API_KEY)')
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            b64 = body.get('pdf_b64', '')
            if not b64: return self._err(400, 'Falta pdf_b64')
        except Exception as e:
            return self._err(400, str(e))

        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 600,
            "messages": [{"role": "user", "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                {"type": "text", "text": 'Extrae datos de la PRIMERA PÁGINA. SOLO JSON sin texto extra:\n{"func1_nombre":"","func1_cc":"","func1_cargo":"","func2_nombre":"","func2_cc":"","func2_cargo":"","local":"","municipio":"","departamento":"","operador":""}'}
            ]}]
        }
        ctx = ssl.create_default_context()
        req = urllib.request.Request('https://api.anthropic.com/v1/messages', method='POST',
            headers={'Content-Type':'application/json','anthropic-version':'2023-06-01','x-api-key':api_key},
            data=json.dumps(payload).encode())
        try:
            with urllib.request.urlopen(req, timeout=45, context=ctx) as r:
                resp = json.loads(r.read())
                raw = ''.join(b['text'] for b in resp.get('content',[]) if b.get('type')=='text')
                s, e = raw.find('{'), raw.rfind('}')+1
                if s < 0: return self._err(502, 'Sin JSON en respuesta')
                self._ok(json.loads(raw[s:e]))
        except urllib.error.HTTPError as e:
            self._err(e.code, 'Anthropic: ' + e.read().decode()[:200])
        except Exception as e:
            self._err(502, str(e))

    def _ok(self, data):
        b = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(b)))
        self._cors(); self.end_headers(); self.wfile.write(b)

    def _err(self, code, msg):
        b = json.dumps({'error': msg}).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(b)))
        self._cors(); self.end_headers(); self.wfile.write(b)

if __name__ == '__main__':
    local = not os.environ.get('PORT')
    host  = 'localhost' if local else '0.0.0.0'
    key   = get_api_key()
    print(f"Coljuegos servidor en http://{host}:{PORT}")
    print(f"API key: {'✅ configurada' if key else '❌ FALTA (agrega ANTHROPIC_API_KEY en Render)'}")
    if local:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(f'http://localhost:{PORT}')), daemon=True).start()
    with http.server.ThreadingHTTPServer((host, PORT), Handler) as srv:
        srv.serve_forever()
