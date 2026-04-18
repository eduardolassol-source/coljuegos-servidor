"""
Servidor local Coljuegos GCT-FR-052
Corre en http://localhost:8520
Abre automáticamente Chrome/browser al iniciar.
"""

import http.server
import urllib.request
import urllib.error
import ssl
import json
import os
import sys
import threading
import webbrowser
import time

PORT = 8520
API_KEY_FILE = os.path.join(os.path.dirname(__file__), 'api_key.txt')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_api_key():
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, 'r') as f:
            key = f.read().strip()
            if key and key != 'TU_API_KEY_AQUI':
                return key
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def log_message(self, format, *args):
        # Silenciar logs de archivos estáticos, solo mostrar errores y /api
        if '/api/' in (args[0] if args else ''):
            print(f"  → {args[0]}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/extraer':
            self._extraer()
        else:
            self.send_error(404)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', 'http://localhost:' + str(PORT))
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _extraer(self):
        api_key = get_api_key()
        if not api_key:
            self._json_error(503, 'API key no configurada. Edita api_key.txt')
            return

        length = int(self.headers.get('Content-Length', 0))
        if length > 20 * 1024 * 1024:  # 20MB max
            self._json_error(413, 'PDF demasiado grande')
            return

        body = self.rfile.read(length)

        try:
            payload = json.loads(body)
            pdf_b64 = payload.get('pdf_b64', '')
            if not pdf_b64:
                self._json_error(400, 'Falta pdf_b64')
                return
        except Exception:
            self._json_error(400, 'JSON inválido')
            return

        # Llamar a Claude Haiku
        anthropic_payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 600,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extrae datos de la PRIMERA PÁGINA de este Auto Comisorio de Coljuegos. "
                            "Responde SOLO con JSON, sin texto adicional ni bloques de código:\n"
                            '{"func1_nombre":"","func1_cc":"","func1_cargo":"",'
                            '"func2_nombre":"","func2_cc":"","func2_cargo":"",'
                            '"local":"nombre del local y dirección completa",'
                            '"municipio":"","departamento":"","operador":""}'
                        )
                    }
                ]
            }]
        }

        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
                'x-api-key': api_key,
            },
            data=json.dumps(anthropic_payload).encode()
        )

        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                resp = json.loads(r.read().decode())
                raw = ''.join(b['text'] for b in resp.get('content', []) if b.get('type') == 'text')
                # Extraer JSON de la respuesta
                match_start = raw.find('{')
                match_end   = raw.rfind('}') + 1
                if match_start < 0:
                    self._json_error(502, 'Respuesta IA sin JSON: ' + raw[:100])
                    return
                data = json.loads(raw[match_start:match_end])
                self._json_ok(data)

        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:200]
            self._json_error(e.code, f'API Anthropic error {e.code}: {err_body}')
        except Exception as e:
            self._json_error(502, str(e))

    def _json_ok(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code, msg):
        body = json.dumps({'error': msg}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)
        print(f"  ⚠️  {msg}")


def abrir_browser():
    time.sleep(1.2)
    webbrowser.open(f'http://localhost:{PORT}')


if __name__ == '__main__':
    api_key = get_api_key()

    print('╔══════════════════════════════════════════════════╗')
    print('║       Coljuegos GCT-FR-052 — Servidor local     ║')
    print('╚══════════════════════════════════════════════════╝')
    print()

    if not api_key:
        print('⚠️  API KEY NO CONFIGURADA')
        print('   Abre api_key.txt y reemplaza TU_API_KEY_AQUI')
        print('   con tu clave de https://console.anthropic.com')
        print()
        print('   Sin API key la extracción automática no funciona,')
        print('   pero el formulario y la generación de PDF sí.')
        print()
    else:
        print('✅ API key configurada')
        print()

    print(f'🌐 Servidor en http://localhost:{PORT}')
    print('   Abriendo el browser...')
    print('   (Ctrl+C para cerrar)')
    print()

    threading.Thread(target=abrir_browser, daemon=True).start()

    try:
        with http.server.ThreadingHTTPServer(('localhost', PORT), Handler) as srv:
            srv.serve_forever()
    except KeyboardInterrupt:
        print('\n👋 Servidor cerrado.')
