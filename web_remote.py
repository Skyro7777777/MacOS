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
    """Type password into the macOS SecurityAgent password prompt.

    The prompt has TWO fields: username (auto-focused, shows 'Anka') and
    password (empty). We need to:
    1. Press Tab to move focus from username to password field
    2. Type the password
    3. Press Return to submit

    We do NOT click at (x,y) or use Cmd+A — that would select/clear the
    USERNAME field and type the password there. Tab is the reliable way
    to move to the password field on macOS.
    """
    # 1. Press Tab to move from username field to password field
    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 48'], capture_output=True)  # tab
    time.sleep(0.3)
    # 2. Type the password into the now-focused password field
    subprocess.run(["cliclick", f"t:{password}"], capture_output=True)
    time.sleep(0.3)
    # 3. Press Return to submit
    subprocess.run(["osascript", "-e", 'tell application "System Events" to key code 36'], capture_output=True)  # return
    time.sleep(1.0)
    # 4. ALSO click "Modify Settings" via AX (Return alone may not submit
    #    on macOS SecurityAgent — the button needs to be clicked)
    subprocess.run(["osascript", "-e",
        '''tell application "System Events"
    repeat with procName in {"SecurityAgent", "CoreServicesUIAgent"}
        set procList to (every process whose name is procName)
        if (count of procList) > 0 then
            set theProc to item 1 of procList
            repeat with w in (windows of theProc)
                try
                    repeat with b in (every button of w)
                        try
                            set bName to name of b as text
                            if bName is "Modify Settings" or bName is "OK" or bName is "Continue" then
                                click b
                                return
                            end if
                        end try
                    end repeat
                end try
            end repeat
        end if
    end repeat
end tell'''], capture_output=True)
    time.sleep(1.0)


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
        "delete": "51",   # backspace (delete left)
        "forwarddelete": "117",  # forward delete (delete right)
        "home": "115",
        "end": "119",
        "pageup": "116",
        "pagedown": "121",
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
    <meta charset="UTF-8">
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
        .screenshot-wrap { text-align: center; padding: 8px; position: relative; display: inline-block; }
        #screenshot { max-width: 100%; cursor: crosshair; border: 2px solid #444;
            border-radius: 4px; display: block; margin: 0 auto; }
        #crosshair { position: absolute; pointer-events: none; width: 20px; height: 20px;
            border: 2px solid #ff0000; border-radius: 50%; transform: translate(-50%, -50%);
            display: none; z-index: 50; }
        #crosshair::before { content: ''; position: absolute; top: 50%; left: -10px; right: -10px;
            height: 2px; background: #ff0000; transform: translateY(-50%); }
        #crosshair::after { content: ''; position: absolute; left: 50%; top: -10px; bottom: -10px;
            width: 2px; background: #ff0000; transform: translateX(-50%); }
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
        <button onclick="refresh()">Refresh</button>
        <label>X:</label>
        <input type="number" id="manual_x" placeholder="x" value="">
        <label>Y:</label>
        <input type="number" id="manual_y" placeholder="y" value="">
        <button onclick="manualClick()">Click XY</button>
        <button id="rc_btn" onclick="toggleRC()">R-Click OFF</button>
        <input type="text" id="text_input" placeholder="Type text..." style="width:150px"
               onkeydown="if(event.key==='Enter')doType()">
        <button onclick="doType()">Type</button>
        <button onclick="doKey('return')">Enter</button>
        <button onclick="doKey('tab')">Tab</button>
        <button onclick="doKey('escape')">Esc</button>
        <button onclick="doKey('delete')">BkSp</button>
        <button onclick="doKey('forwarddelete')">Del</button>
        <button onclick="doKey('cmd_g')">Cmd+Shift+G</button>
        <button onclick="doKey('cmd_a')">Cmd+A</button>
        <button onclick="doKey('cmd_c')">Cmd+C</button>
        <button onclick="doKey('cmd_v')">Cmd+V</button>
        <span style="color:#555;margin:0 5px">|</span>
        <label style="color:#ff0">PW X:</label>
        <input type="number" id="pw_x" value="504" style="width:50px">
        <label style="color:#ff0">Y:</label>
        <input type="number" id="pw_y" value="467" style="width:50px">
        <button onclick="doTypePassword()" style="background:#d63031">Type Password</button>
        <span style="color:#555;margin:0 5px">|</span>
        <button onclick="openPane('screen')">Screen Recording</button>
        <button onclick="openPane('accessibility')">Accessibility</button>
        <button onclick="openPane('input')">Input Mon</button>
        <button onclick="openPane('full_disk')">Full Disk</button>
    </div>
    <div class="screenshot-wrap">
        <img id="screenshot" />
        <div id="crosshair"></div>
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
        let crosshair = document.getElementById('crosshair');

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
            // CRITICAL: use offsetX/offsetY if available (more accurate on Windows)
            // fallback to clientX/Y calculation
            let x, y;
            if (event.offsetX !== undefined && event.offsetX !== 0) {
                // offsetX/offsetY are relative to the element, already in the right scale
                // but we need to scale from display size to natural size
                const scaleX = img.naturalWidth / rect.width;
                const scaleY = img.naturalHeight / rect.height;
                x = Math.round(event.offsetX * scaleX);
                y = Math.round(event.offsetY * scaleY);
            } else {
                const scaleX = img.naturalWidth / rect.width;
                const scaleY = img.naturalHeight / rect.height;
                x = Math.round((event.clientX - rect.left) * scaleX);
                y = Math.round((event.clientY - rect.top) * scaleY);
            }
            // Clamp to valid range
            x = Math.max(0, Math.min(x, img.naturalWidth - 1));
            y = Math.max(0, Math.min(y, img.naturalHeight - 1));
            return { x, y };
        }

        // CRITICAL: mousemove ONLY updates coords display + crosshair, NEVER clicks
        img.addEventListener('mousemove', function(event) {
            const { x, y } = getCoords(event);
            coordsDiv.innerText = 'Mouse: (' + x + ', ' + y + ')';
            // Move crosshair to mouse position (relative to the screenshot-wrap div)
            const rect = img.getBoundingClientRect();
            const wrapRect = img.parentElement.getBoundingClientRect();
            crosshair.style.display = 'block';
            crosshair.style.left = (event.clientX - wrapRect.left) + 'px';
            crosshair.style.top = (event.clientY - wrapRect.top) + 'px';
        });

        // Hide crosshair when mouse leaves the screenshot
        img.addEventListener('mouseleave', function() {
            crosshair.style.display = 'none';
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
