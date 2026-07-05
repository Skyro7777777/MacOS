#!/usr/bin/env python3
"""
 =============================================================================
  web_remote.py v3 — Fixed for Windows 11 desktop mouse control

  v3 fixes:
  - NO ghost clicks: mousemove ONLY updates coords, never clicks
  - Coords persist: last-clicked coords stay visible until next click
  - Click only on actual click event (not mousemove/touchmove)
  - Added coordinate input: type exact x,y to click precisely
  - Better desktop layout (no mobile touch hacks)
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
from urllib.parse import urlparse, parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
SCREENSHOT_PATH = "/tmp/apple-project/web_remote_screenshot.png"
os.makedirs("/tmp/apple-project", exist_ok=True)


def take_screenshot() -> str:
    subprocess.run(["screencapture", "-x", "-C", SCREENSHOT_PATH],
                   capture_output=True, check=True)
    with open(SCREENSHOT_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def click_at(x: int, y: int, button: str = "left") -> None:
    if button == "right":
        subprocess.run(["cliclick", f"rc:{x},{y}"], capture_output=True)
    elif button == "double":
        subprocess.run(["cliclick", f"dc:{x},{y}"], capture_output=True)
    else:
        subprocess.run(["cliclick", f"c:{x},{y}"], capture_output=True)
    time.sleep(0.5)


def type_text(text: str) -> None:
    subprocess.run(["cliclick", f"t:{text}"], capture_output=True)
    time.sleep(0.3)


def type_password_at(password: str, x: int, y: int) -> None:
    """Click at (x,y) to focus the password field, clear it, type password, press Return."""
    subprocess.run(["cliclick", f"c:{x},{y}"], capture_output=True)
    time.sleep(0.5)
    # Clear field: Cmd+A then Delete
    subprocess.run(["osascript", "-e", 'tell application "System Events" to keystroke "a" using {command down}'], capture_output=True)
    time.sleep(0.1)
    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 51'], capture_output=True)  # delete
    time.sleep(0.1)
    # Type password
    subprocess.run(["cliclick", f"t:{password}"], capture_output=True)
    time.sleep(0.3)
    # Press Return
    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 36'], capture_output=True)  # return
    time.sleep(0.5)


def press_key(key: str) -> None:
    """Press a key using osascript (reliable on macOS)."""
    # osascript key codes:
    #   return = 36, tab = 48, escape = 53, delete = 51, space = 49
    #   enter = 76, up=126, down=125, left=123, right=124
    key_codes = {
        "return": "36",
        "enter": "76",
        "tab": "48",
        "escape": "53",
        "delete": "51",   # backspace
        "space": "49",
        "up": "126",
        "down": "125",
        "left": "123",
        "right": "124",
    }
    key_combos = {
        "cmd_g": 'keystroke "g" using {command down, shift down}',
        "cmd_a": 'keystroke "a" using {command down}',
        "cmd_c": 'keystroke "c" using {command down}',
        "cmd_v": 'keystroke "v" using {command down}',
        "cmd_w": 'keystroke "w" using {command down}',
        "cmd_q": 'keystroke "q" using {command down}',
    }

    if key in key_codes:
        # Use key code (more reliable for special keys like Return, Delete)
        script = f'tell application "System Events" to key code {key_codes[key]}'
    elif key in key_combos:
        script = f'tell application "System Events" to {key_combos[key]}'
    else:
        script = f'tell application "System Events" to keystroke "{key}"'

    subprocess.run(["osascript", "-e", script], capture_output=True)
    time.sleep(0.3)


HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>macOS Web Remote</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #1a1a1a; color: #e0e0e0; font-family: Consolas, monospace; }
        .topbar { background: #2a2a2a; padding: 8px 12px; display: flex;
                  align-items: center; gap: 8px; flex-wrap: wrap; position: sticky; top: 0; z-index: 100; }
        .topbar h1 { font-size: 14px; margin-right: 10px; }
        .topbar button { background: #0a84ff; color: white; border: none;
            padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .topbar button:hover { background: #0066d6; }
        .topbar button:active { transform: scale(0.95); }
        .topbar button.rc-active { background: #d63031; }
        .topbar input[type="text"] { background: #333; border: 1px solid #555; color: #fff;
            padding: 6px 8px; border-radius: 4px; font-size: 13px; font-family: monospace; }
        .topbar input[type="number"] { background: #333; border: 1px solid #555; color: #fff;
            padding: 6px 8px; border-radius: 4px; font-size: 13px; font-family: monospace; width: 60px; }
        .topbar label { font-size: 12px; color: #aaa; }
        .screenshot-wrap { text-align: center; padding: 8px; }
        #screenshot { max-width: 100%; cursor: crosshair; border: 2px solid #444;
            border-radius: 4px; }
        #coords { position: fixed; top: 50px; right: 12px; background: rgba(0,0,0,0.9);
            color: #0f0; padding: 6px 12px; border-radius: 4px; font-size: 14px; z-index: 200; }
        #lastclick { position: fixed; top: 80px; right: 12px; background: rgba(0,0,0,0.9);
            color: #ff0; padding: 6px 12px; border-radius: 4px; font-size: 14px; z-index: 200; }
        #status { position: fixed; bottom: 12px; left: 12px; background: rgba(0,0,0,0.9);
            color: #0af; padding: 6px 12px; border-radius: 4px; font-size: 12px; z-index: 200; }
    </style>
</head>
<body>
    <div class="topbar">
        <h1>macOS Web Remote</h1>
        <button onclick="refresh()">🔄 Refresh</button>
        <label>X:</label>
        <input type="number" id="manual_x" placeholder="x" value="">
        <label>Y:</label>
        <input type="number" id="manual_y" placeholder="y" value="">
        <button onclick="manualClick()">Click XY</button>
        <button id="rc_btn" onclick="toggleRC()">R-Click OFF</button>
        <input type="text" id="text_input" placeholder="Type text..." style="width:150px"
               onkeydown="if(event.key==='Enter')doType()">
        <button onclick="doType()">Type</button>
        <button onclick="doKey('return')">⏎</button>
        <button onclick="doKey('tab')">⇥</button>
        <button onclick="doKey('escape')">Esc</button>
        <button onclick="doKey('delete')">⌫</button>
        <button onclick="doKey('cmd_g')">⌘⇧G</button>
        <button onclick="doKey('cmd_a')">⌘A</button>
        <button onclick="doKey('cmd_c')">⌘C</button>
        <button onclick="doKey('cmd_v')">⌘V</button>
        <span style="color:#555;margin:0 5px">|</span>
        <label style="color:#ff0">PW X:</label>
        <input type="number" id="pw_x" value="504" style="width:50px">
        <label style="color:#ff0">Y:</label>
        <input type="number" id="pw_y" value="467" style="width:50px">
        <button onclick="doTypePassword()" style="background:#d63031">🔐 Type Password</button>
        <span style="color:#555;margin:0 5px">|</span>
        <button onclick="openPane('screen')">Screen Rec</button>
        <button onclick="openPane('accessibility')">Accessibility</button>
        <button onclick="openPane('input')">Input Mon</button>
        <button onclick="openPane('full_disk')">Full Disk</button>
    </div>
    <div class="screenshot-wrap">
        <img id="screenshot" />
    </div>
    <div id="coords">Mouse: (0, 0)</div>
    <div id="lastclick">Last click: none</div>
    <div id="status">Loading...</div>

    <script>
        let img = document.getElementById('screenshot');
        let coordsDiv = document.getElementById('coords');
        let lastClickDiv = document.getElementById('lastclick');
        let statusDiv = document.getElementById('status');
        let rcBtn = document.getElementById('rc_btn');
        let rightClickMode = false;
        let isClicking = false;  // prevent double-clicks

        function setStatus(msg) { statusDiv.innerText = msg; }
        function setLastClick(x, y, btn) { lastClickDiv.innerText = 'Last click: (' + x + ', ' + y + ') ' + btn; }

        function refresh() {
            setStatus('Refreshing screenshot...');
            fetch('/screenshot?' + Date.now())
                .then(r => r.text())
                .then(data => {
                    img.src = 'data:image/png;base64,' + data;
                    setStatus('Ready ' + new Date().toLocaleTimeString());
                })
                .catch(e => setStatus('Error: ' + e));
        }

        function toggleRC() {
            rightClickMode = !rightClickMode;
            rcBtn.innerText = rightClickMode ? 'R-Click ON' : 'R-Click OFF';
            rcBtn.classList.toggle('rc-active', rightClickMode);
        }

        function getCoords(event) {
            const rect = img.getBoundingClientRect();
            const scaleX = img.naturalWidth / rect.width;
            const scaleY = img.naturalHeight / rect.height;
            const x = Math.round((event.clientX - rect.left) * scaleX);
            const y = Math.round((event.clientY - rect.top) * scaleY);
            return { x, y };
        }

        // CRITICAL: mousemove ONLY updates coords display, NEVER clicks
        img.addEventListener('mousemove', function(event) {
            const { x, y } = getCoords(event);
            coordsDiv.innerText = 'Mouse: (' + x + ', ' + y + ')';
        });

        // CRITICAL: click ONLY fires on actual mouse click, NOT on mousemove
        img.addEventListener('click', function(event) {
            if (isClicking) return;  // prevent double-fire
            isClicking = true;
            const { x, y } = getCoords(event);
            const btn = rightClickMode ? 'right' : 'left';
            setLastClick(x, y, btn);
            setStatus('Clicking (' + x + ', ' + y + ') ' + btn + '...');
            fetch('/click?x=' + x + '&y=' + y + '&button=' + btn)
                .then(r => r.text())
                .then(data => {
                    setStatus('Clicked OK: ' + data);
                    setTimeout(function() {
                        refresh();
                        isClicking = false;
                    }, 500);
                })
                .catch(e => {
                    setStatus('Error: ' + e);
                    isClicking = false;
                });
        });

        // Right-click via context menu event
        img.addEventListener('contextmenu', function(event) {
            event.preventDefault();
            if (isClicking) return;
            isClicking = true;
            const { x, y } = getCoords(event);
            setLastClick(x, y, 'right');
            setStatus('Right-clicking (' + x + ', ' + y + ')...');
            fetch('/click?x=' + x + '&y=' + y + '&button=right')
                .then(r => r.text())
                .then(data => {
                    setStatus('Right-clicked OK');
                    setTimeout(function() {
                        refresh();
                        isClicking = false;
                    }, 500);
                })
                .catch(e => {
                    setStatus('Error: ' + e);
                    isClicking = false;
                });
        });

        function manualClick() {
            const x = parseInt(document.getElementById('manual_x').value);
            const y = parseInt(document.getElementById('manual_y').value);
            if (isNaN(x) || isNaN(y)) { setStatus('Enter valid X,Y'); return; }
            const btn = rightClickMode ? 'right' : 'left';
            setLastClick(x, y, btn);
            setStatus('Clicking (' + x + ', ' + y + ') ' + btn + '...');
            fetch('/click?x=' + x + '&y=' + y + '&button=' + btn)
                .then(r => r.text())
                .then(data => {
                    setStatus('Clicked OK: ' + data);
                    setTimeout(refresh, 500);
                });
        }

        function doType() {
            const text = document.getElementById('text_input').value;
            if (!text) return;
            setStatus('Typing...');
            fetch('/type?text=' + encodeURIComponent(text))
                .then(r => r.text())
                .then(data => {
                    setStatus('Typed OK');
                    setTimeout(refresh, 500);
                });
        }

        function doKey(key) {
            setStatus('Key: ' + key);
            fetch('/key?key=' + key)
                .then(r => r.text())
                .then(data => {
                    setStatus('Key done');
                    setTimeout(refresh, 300);
                });
        }

        function openPane(pane) {
            setStatus('Opening ' + pane + ' settings...');
            fetch('/open_pane?pane=' + pane)
                .then(r => r.text())
                .then(data => {
                    setStatus('Opened: ' + data);
                    setTimeout(refresh, 2000);
                });
        }

        function doTypePassword() {
            const x = document.getElementById('pw_x').value;
            const y = document.getElementById('pw_y').value;
            const pw = document.getElementById('text_input').value;
            if (!pw) { setStatus('Enter password in text box first!'); return; }
            setStatus('Typing password at (' + x + ',' + y + ')...');
            fetch('/type_password?x=' + x + '&y=' + y + '&text=' + encodeURIComponent(pw))
                .then(r => r.text())
                .then(data => {
                    setStatus('Password typed + Return pressed');
                    setTimeout(refresh, 1000);
                });
        }

        // Initial load
        refresh();
    </script>
</body>
</html>"""


class RemoteHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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

        elif self.path.startswith("/type_password"):
            params = parse_qs(urlparse(self.path).query)
            x = int(params.get("x", ["504"])[0])
            y = int(params.get("y", ["467"])[0])
            text = params.get("text", [""])[0]
            type_password_at(text, x, y)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"password typed at ({x},{y})".encode())

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

        elif self.path.startswith("/open_pane"):
            params = parse_qs(urlparse(self.path).query)
            pane = params.get("pane", [""])[0]
            pane_urls = {
                "screen": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ScreenCapture",
                "accessibility": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility",
                "input": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_ListenEvent",
                "full_disk": "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_AllFiles",
            }
            url = pane_urls.get(pane, "")
            if url:
                subprocess.run(["open", url], capture_output=True)
                time.sleep(2)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"opened {pane}".encode())

        else:
            self.send_response(404)
            self.end_headers()


def main():
    print(f"    [web-remote] starting on port {PORT}", flush=True)
    try:
        subprocess.run(["screencapture", "-x", "-C", SCREENSHOT_PATH],
                       capture_output=True, check=True)
        print(f"    [web-remote] initial screenshot OK", flush=True)
    except Exception as e:
        print(f"    [web-remote][WARN] initial screenshot failed: {e}", flush=True)

    with socketserver.TCPServer(("0.0.0.0", PORT), RemoteHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
