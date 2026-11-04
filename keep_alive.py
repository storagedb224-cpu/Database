from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import os

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is ALIVE and RUNNING!")

def run_server():
    # रेंडर अपने आप PORT देता है, नहीं तो 8080 इस्तेमाल करेगा
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
