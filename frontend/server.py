# server.py - Simple HTTP server for frontend
import http.server
import socketserver
import os
import webbrowser

PORT = 3000

# Get the directory where this script is located and serve it directly.
frontend_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(frontend_dir)

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # If root path, serve index.html
        if self.path == '/':
            self.path = '/index.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)
    
    def log_message(self, format, *args):
        # Optional: Suppress logging for cleaner output
        pass

Handler = CustomHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"🚀 Zeviq AI Frontend")
    print(f"📁 Serving from: {os.getcwd()}")
    print(f"🌐 http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    
    # Open browser automatically
    webbrowser.open(f'http://localhost:{PORT}')
    
    httpd.serve_forever()