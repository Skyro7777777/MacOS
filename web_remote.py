#!/usr/bin/env python3
"""
 =============================================================================
  web_remote.py  —  Click-to-control web remote for macOS 15 GHA runner

  v2: Fixed mobile issues:
  - Removed auto-refresh (was causing ghost clicks)
  - Added explicit Right-Click toggle button
  - Coordinates always visible
  - Better mobile touch support
  - Manual refresh only (button + after click)
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
from pathlib import Path
from urllib.parse import urlparse, parse_qs

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
        subprocess.run(["cliclick", f"rc:{x},{y}"], capture_output=True)
    elif button == "double":
        subprocess.run(["cliclick", f"dc:{x},{y}"], capture_output=True)
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


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>macOS Web Remote</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <style>
        * { box-sizing: border-box; }
        body { margin: 0; background: #1a1a1a; color: #e0e0e0;
               font-family: -apple-system, sans-serif; -webkit-user-select: none; user-select: none; }
        .header { background: #2a2a2a; padding: 8px 12px; position: sticky; top: 0; z-index: 100; }
        .header h1 { font-size: 16px; margin: 0 0 8px 0; }
        .controls { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
        .controls button { background: #0a84ff; color: white; border: none;
            padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 14px;
            min-height: 36px; min-width: 44px; }
        .controls button:active { background: #0066d6; transform: scale(0.95); }
        .controls button.toggle { background: #555; }
        .controls button.toggle.active { background: #d63031; }
        .controls button.green { background: #00b894; }
        .controls input[type="text"] { background: #333; border: 1px solid #555; color: #fff;
            padding: 8px 10px; border-radius: 6px; font-size: 14px; flex: 1; min-width: 120px; }
        .screenshot-container { text-align: center; padding: 5px; }
        #screenshot { max-width: 100%; cursor: crosshair; border: 2px solid #444;
            border-radius: 4px; display: block; margin: 0 auto; }
        #coords { position: fixed; top: 5px; right: 5px; background: rgba(0,0,0,0.9);
            color: #0f0; padding: 6px 12px; border-radius: 6px; font-family: monospace;
            font-size: 14px; z-index: 200; }
        #log { position: fixed; bottom: 5px; left: 5px; right: 5px; background: rgba(0,0,0,0.9);
            color: #ff0; padding: 6px 12px; border-radius: 6px; font-family: monospace;
            font-size: 12px; z-index: 200; text-align: center; }
        .tip { font-size: 11px; color: #888; margin-top: 6px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🖥️ macOS Web Remote</h1>
        <div class="controls">
            <button class="green" onclick="refresh()">🔄</button>
            <input type="text" id="text_input" placeholder="Type text..." onkeydown="if(event.key==='Enter')doType()">
            <button onclick="doType()">Type</button>
            <button onclick="doKey('return')">⏎</button>
            <button onclick="doKey('tab')">⇥</button>
            <button onclick="doKey('escape')">Esc</button>
            <button onclick="doKey('delete')">⌫</button>
            <button onclick="doKey('cmd_g')">⌘⇧G</button>
            <button onclick="doKey('cmd_v')">⌘V</button>
            <button class="toggle" id="rc_toggle" onclick="toggleRC()">R-Click</button>
        </div>
        <div class="tip">Tap screenshot to click. Toggle R-Click for right-click. 🔄 to refresh.</div>
    </div>
    <div class="screenshot-container">
        <img id="screenshot" />
    </div>
    <div id="coords">(0, 0)</div>
    <div id="log">Loading...</div>

    <script>
        let img = document.getElementById('screenshot');
        let coords = document.getElementById('coords');
        let logDiv = document.getElementById('log');
        let rcToggle = document.getElementById('rc_toggle');
        let rightClickMode = false;

        function addLog(msg) {
            logDiv.innerText = msg;
        }

        function refresh() {
            addLog('Refreshing...');
            fetch('/screenshot?' + Date.now())
                .then(r => r.text())
                .then(data => {
                    img.src = 'data:image/png;base64,' + data;
                    addLog('Ready ' + new Date().toLocaleTimeString());
                })
                .catch(e => addLog('Error: ' + e));
        }

        function toggleRC() {
            rightClickMode = !rightClickMode;
            if (rightClickMode) {
                rcToggle.classList.add('active');
                addLog('Right-click mode ON');
            } else {
                rcToggle.classList.remove('active');
                addLog('Right-click mode OFF');
            }
        }

        function getCoords(event) {
            const rect = img.getBoundingClientRect();
            const scaleX = img.naturalWidth / rect.width;
            const scaleY = img.naturalHeight / rect.height;
            let clientX, clientY;
            if (event.touches && event.touches.length > 0) {
                clientX = event.touches[0].clientX;
                clientY = event.touches[0].clientY;
            } else if (event.changedTouches && event.changedTouches.length > 0) {
                clientX = event.changedTouches[0].clientX;
                clientY = event.changedTouches[0].clientY;
            } else {
                clientX = event.clientX;
                clientY = event.clientY;
            }
            const x = Math.round((clientX - rect.left) * scaleX);
            const y = Math.round((clientY - rect.top) * scaleY);
            return { x, y };
        }

        function doClick(event) {
            event.preventDefault();
            const { x, y } = getCoords(event);
            const btn = rightClickMode ? 'right' : 'left';
            addLog('Click (' + x + ',' + y + ') ' + btn);
            fetch('/click?x=' + x + '&y=' + y + '&button=' + btn)
                .then(r => r.text())
                .then(data => {
                    addLog('Done: ' + data);
                    setTimeout(refresh, 600);
                })
                .catch(e => addLog('Error: ' + e));
        }

        // Handle both touch and mouse
        img.addEventListener('click', doClick);
        img.addEventListener('touchend', doClick);

        img.addEventListener('mousemove', function(event) {
            const { x, y } = getCoords(event);
            coords.innerText = '(' + x + ', ' + y + ')';
        });

        // Also show coords on touch
        img.addEventListener('touchmove', function(event) {
            event.preventDefault();
            const { x, y } = getCoords(event);
            coords.innerText = '(' + x + ', ' + y + ')';
        }, { passive: false });

        function doType() {
            const text = document.getElementById('text_input').value;
            if (!text) return;
            addLog('Typing: ' + text.substring(0, 20) + '...');
            fetch('/type?text=' + encodeURIComponent(text))
                .then(r => r.text())
                .then(data => {
                    addLog('Typed OK');
                    setTimeout(refresh, 500);
                });
        }

        function doKey(key) {
            addLog('Key: ' + key);
            fetch('/key?key=' + key)
                .then(r => r.text())
                .then(data => {
                    addLog('Key done');
                    setTimeout(refresh, 300);
                });
        }

        // Initial load
        refresh();
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
            params = parse_qs(urlparse(self.path).query)
            x = int(params.get("x", ["0"])[0])
            y = int(params.get("y", ["0"])[0])
            button = params.get("button", ["left"])[0]
            click_at(x, y, button)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"({x},{y}) {button}".encode())

        elif self.path.startswith("/type"):
            params = parse_qs(urlparse(self.path).query)
            text = params.get("text", [""])[0]
            type_text(text)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"typed {len(text)} chars".encode())

        elif self.path.startswith("/key"):
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

    # Take an initial screenshot
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
