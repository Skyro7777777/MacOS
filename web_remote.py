#!/usr/bin/env python3
"""
 =============================================================================
  web_remote.py  —  Click-to-control web remote for macOS 15 GHA runner

  A tiny web server that lets you control the macOS desktop from your browser:
    1. Takes a screenshot via `screencapture` (inherits bash's Screen Recording TCC)
    2. Displays it in your browser
    3. You click on the screenshot → sends coordinates to the server
    4. `cliclick` clicks at those coordinates (inherits bash's Accessibility TCC)
    5. Takes a new screenshot → displays it
    6. Repeat

  No RustDesk. No VNC. No TCC permission fighting. No framebuffer black screen.
  Just screencapture + cliclick — both proven to work on the GHA macos-15 runner.

  Features:
    - Click anywhere on the screenshot → cliclick clicks at that position
    - Right-click → right-click
    - Type text in a text box → cliclick types it
    - Press Return / Tab / Escape buttons
    - Auto-refresh screenshot every 3 seconds (in addition to click-refresh)
    - Keyboard shortcuts: Cmd+Shift+G (for file picker), etc.
    - Shows the current mouse position on hover

  Usage:
    python3 web_remote.py [port]   (default port 8080)

  Then open http://<tailscale-ip>:8080 in your browser.
 =============================================================================
"""
from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import sys
import time
import base64
import io
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
SCREENSHOT_PATH = "/tmp/apple-project/web_remote_screenshot.png"
os.makedirs("/tmp/apple-project", exist_ok=True)


def take_screenshot() -> str:
    """Take a screenshot and return it as base64."""
    subprocess.run(["screencapture", "-x", "-C", SCREENSHOT_PATH],
                   capture_output=True, check=True)
    with open(SCREENSHOT_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def click_at(x: int, y: int, button: str = "left") -> None:
    """Click at (x, y) using cliclick."""
    if button == "right":
        subprocess.run(["cliclick", "rc:" f"{x},{y}"], capture_output=True)
    else:
        subprocess.run(["cliclick", f"c:{x},{y}"], capture_output=True)
    time.sleep(0.5)


def type_text(text: str) -> None:
    """Type text using cliclick."""
    subprocess.run(["cliclick", f"t:{text}"], capture_output=True)
    time.sleep(0.3)


def press_key(key: str) -> None:
    """Press a key combo using osascript."""
    key_map = {
        "return": "return",
        "tab": "tab",
        "escape": "escape",
        "space": "space",
        "delete": "delete",
        "cmd_g": '"g" using {command down, shift down}',
        "cmd_a": '"a" using {command down}',
        "cmd_c": '"c" using {command down}',
        "cmd_v": '"v" using {command down}',
        "cmd_w": '"w" using {command down}',
        "cmd_q": '"q" using {command down}',
    }
    action = key_map.get(key, key)
    subprocess.run(["osascript", "-e",
                    f'tell application "System Events" to keystroke {action}'],
                   capture_output=True)
    time.sleep(0.3)


# The HTML page — a clickable screenshot with controls
HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>macOS Web Remote</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; background: #1a1a1a; color: #e0e0e0; font-family: -apple-system, sans-serif; }
        .header { background: #2a2a2a; padding: 10px 20px; display: flex; align-items: center; gap: 15px; }
        .header h1 { font-size: 18px; margin: 0; }
        .controls { display: flex; gap: 8px; flex-wrap: wrap; }
        .controls input[type="text"] { background: #333; border: 1px solid #555; color: #fff;
            padding: 6px 10px; border-radius: 4px; width: 200px; }
        .controls button { background: #0a84ff; color: white; border: none; padding: 6px 12px;
            border-radius: 4px; cursor: pointer; font-size: 13px; }
        .controls button:hover { background: #0066d6; }
        .controls button.danger { background: #d63031; }
        .info { font-size: 12px; color: #888; margin-left: auto; }
        .screenshot-container { text-align: center; padding: 10px; }
        #screenshot { max-width: 100%; cursor: crosshair; border: 2px solid #444;
            border-radius: 4px; image-rendering: pixelated; }
        #coords { position: fixed; bottom: 10px; right: 10px; background: rgba(0,0,0,0.8);
            color: #0f0; padding: 4px 10px; border-radius: 4px; font-family: monospace; font-size: 12px; }
        .log { position: fixed; bottom: 10px; left: 10px; background: rgba(0,0,0,0.8);
            color: #ff0; padding: 4px 10px; border-radius: 4px; font-family: monospace; font-size: 12px;
            max-width: 400px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🖥️ macOS Web Remote</h1>
        <div class="controls">
            <input type="text" id="text_input" placeholder="Type text here..." onkeydown="if(event.key==='Enter')doType()">
            <button onclick="doType()">Type</button>
            <button onclick="doKey('return')">⏎ Return</button>
            <button onclick="doKey('tab')">⇥ Tab</button>
            <button onclick="doKey('escape')">Esc</button>
            <button onclick="doKey('cmd_g')">⌘⇧G</button>
            <button onclick="doKey('cmd_c')">⌘C</button>
            <button onclick="doKey('cmd_v')">⌘V</button>
            <button onclick="refresh()">🔄 Refresh</button>
        </div>
        <div class="info" id="info">Loading...</div>
    </div>
    <div class="screenshot-container">
        <img id="screenshot" onclick="handleClick(event)" oncontextmenu="handleRightClick(event); return false"
             onmousemove="handleMove(event)" />
    </div>
    <div id="coords">(0, 0)</div>
    <div class="log" id="log"></div>

    <script>
        let img = document.getElementById('screenshot');
        let info = document.getElementById('info');
        let coords = document.getElementById('coords');
        let logDiv = document.getElementById('log');

        function addLog(msg) {
            logDiv.innerText = msg;
        }

        function refresh() {
            addLog('refreshing...');
            fetch('/screenshot?' + Date.now())
                .then(r => r.text())
                .then(data => {
                    img.src = 'data:image/png;base64,' + data;
                    info.innerText = 'Updated: ' + new Date().toLocaleTimeString();
                    addLog('screenshot refreshed');
                })
                .catch(e => addLog('error: ' + e));
        }

        function getCoords(event) {
            const rect = img.getBoundingClientRect();
            const scaleX = img.naturalWidth / rect.width;
            const scaleY = img.naturalHeight / rect.height;
            const x = Math.round((event.clientX - rect.left) * scaleX);
            const y = Math.round((event.clientY - rect.top) * scaleY);
            return { x, y };
        }

        function handleClick(event) {
            const { x, y } = getCoords(event);
            addLog('click at (' + x + ',' + y + ')');
            fetch('/click?x=' + x + '&y=' + y + '&button=left')
                .then(r => r.text())
                .then(data => {
                    addLog('clicked: ' + data);
                    setTimeout(refresh, 500);
                });
        }

        function handleRightClick(event) {
            const { x, y } = getCoords(event);
            addLog('right-click at (' + x + ',' + y + ')');
            fetch('/click?x=' + x + '&y=' + y + '&button=right')
                .then(r => r.text())
                .then(data => {
                    addLog('right-clicked: ' + data);
                    setTimeout(refresh, 500);
                });
        }

        function handleMove(event) {
            const { x, y } = getCoords(event);
            coords.innerText = '(' + x + ', ' + y + ')';
        }

        function doType() {
            const text = document.getElementById('text_input').value;
            addLog('typing: ' + text.substring(0, 30) + '...');
            fetch('/type?text=' + encodeURIComponent(text))
                .then(r => r.text())
                .then(data => {
                    addLog('typed: ' + data);
                    setTimeout(refresh, 500);
                });
        }

        function doKey(key) {
            addLog('key: ' + key);
            fetch('/key?key=' + key)
                .then(r => r.text())
                .then(data => {
                    addLog('key: ' + data);
                    setTimeout(refresh, 300);
                });
        }

        // initial load
        refresh();

        // auto-refresh every 5 seconds
        setInterval(refresh, 5000);
    </script>
</body>
</html>"""


class RemoteHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default logging

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())

        elif self.path.startswith("/screenshot"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            b64 = take_screenshot()
            self.wfile.write(b64.encode())

        elif self.path.startswith("/click"):
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(self.path).query)
            x = int(params.get("x", ["0"])[0])
            y = int(params.get("y", ["0"])[0])
            button = params.get("button", ["left"])[0]
            click_at(x, y, button)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"clicked ({x},{y}) {button}".encode())

        elif self.path.startswith("/type"):
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(self.path).query)
            text = params.get("text", [""])[0]
            type_text(text)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"typed {len(text)} chars".encode())

        elif self.path.startswith("/key"):
            from urllib.parse import urlparse, parse_qs
            params = parse_qs(urlparse(self.path).query)
            key = params.get("key", [""])[0]
            press_key(key)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"key: {key}".encode())

        else:
            self.send_response(404)
            self.end_headers()


def main():
    print(f"    [web-remote] starting on port {PORT}", flush=True)
    print(f"    [web-remote] open http://<tailscale-ip>:{PORT} in your browser", flush=True)

    # Take an initial screenshot to verify screencapture works
    try:
        subprocess.run(["screencapture", "-x", "-C", SCREENSHOT_PATH],
                       capture_output=True, check=True)
        print(f"    [web-remote] initial screenshot OK ({os.path.getsize(SCREENSHOT_PATH)} bytes)", flush=True)
    except Exception as e:
        print(f"    [web-remote][WARN] initial screenshot failed: {e}", flush=True)

    with socketserver.TCPServer(("0.0.0.0", PORT), RemoteHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
