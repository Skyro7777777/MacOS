#!/usr/bin/env python3
"""
macOS Screenshot Streamer - Alternative to VNC

This script creates a simple HTTP server that streams screenshots from the macOS
runner and accepts mouse/keyboard commands. Since bash already has screen recording
permission, this works without needing additional permission dialogs.

This is a workaround for the VNC black screen issue caused by missing screen
recording permissions for VNC server processes.
"""

import subprocess
import sys
import time
import threading
import json
import base64
import io
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Tuple
import os

# Ensure required packages
def ensure_packages():
    packages = ['pyautogui', 'Pillow', 'mss']
    for package in packages:
        package_name = package.lower()
        try:
            __import__(package_name)
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '--quiet'])

ensure_packages()

import pyautogui
from PIL import Image

# Configure PyAutoGUI
pyautogui.FAILSAFE = False  # Disable failsafe for headless operation
pyautogui.PAUSE = 0.05

# Global variables
latest_screenshot: Optional[bytes] = None
screenshot_lock = threading.Lock()
connected_clients = set()


def take_screenshot() -> Optional[bytes]:
    """Take a screenshot and return as JPEG bytes."""
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            screenshot = sct.grab(monitor)
            img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
            
            # Resize for faster streaming
            max_width = 1280
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=70)
            return buffer.getvalue()
    except Exception as e:
        # Fallback to pyautogui
        try:
            img = pyautogui.screenshot()
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=70)
            return buffer.getvalue()
        except Exception as e2:
            print(f"Screenshot error: {e}, {e2}")
            return None


def screenshot_updater(interval: float = 0.5):
    """Background thread to update screenshots periodically."""
    global latest_screenshot
    while True:
        screenshot = take_screenshot()
        if screenshot:
            with screenshot_lock:
                latest_screenshot = screenshot
        time.sleep(interval)


class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for remote control."""
    
    def log_message(self, format, *args):
        """Custom log format."""
        print(f"[{self.address_string()}] {format % args}")
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/' or self.path == '/index.html':
            self.send_html_interface()
        elif self.path == '/screenshot':
            self.send_screenshot()
        elif self.path == '/screenshot.jpg':
            self.send_screenshot_jpeg()
        elif self.path == '/status':
            self.send_status()
        else:
            self.send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests for remote control."""
        if self.path == '/click':
            self.handle_click()
        elif self.path == '/type':
            self.handle_type()
        elif self.path == '/key':
            self.handle_key()
        elif self.path == '/scroll':
            self.handle_scroll()
        elif self.path == '/command':
            self.handle_command()
        else:
            self.send_error(404, "Not Found")
    
    def send_html_interface(self):
        """Send the HTML interface for remote control."""
        html = '''<!DOCTYPE html>
<html>
<head>
    <title>macOS Remote Control</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #1a1a2e;
            color: white;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 10px;
        }
        .status {
            text-align: center;
            padding: 10px;
            background: #16213e;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .screen-container {
            position: relative;
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            cursor: crosshair;
        }
        #screen {
            width: 100%;
            display: block;
        }
        .controls {
            display: flex;
            gap: 10px;
            margin-top: 20px;
            flex-wrap: wrap;
        }
        .control-group {
            background: #16213e;
            padding: 15px;
            border-radius: 8px;
            flex: 1;
            min-width: 200px;
        }
        .control-group h3 {
            margin-top: 0;
            margin-bottom: 10px;
            color: #e94560;
        }
        button {
            background: #e94560;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            margin: 2px;
            font-size: 14px;
        }
        button:hover {
            background: #ff6b6b;
        }
        button:active {
            transform: scale(0.98);
        }
        input[type="text"], input[type="password"] {
            width: calc(100% - 80px);
            padding: 10px;
            border: 1px solid #444;
            border-radius: 4px;
            background: #0f0f23;
            color: white;
            margin-right: 5px;
        }
        .info {
            font-size: 12px;
            color: #888;
            margin-top: 10px;
        }
        #clickInfo {
            position: absolute;
            background: rgba(233, 69, 96, 0.8);
            padding: 5px 10px;
            border-radius: 4px;
            pointer-events: none;
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🖥️ macOS Remote Control</h1>
        <div class="status" id="status">
            <span id="connectionStatus">Connecting...</span> | 
            FPS: <span id="fps">0</span> | 
            Resolution: <span id="resolution">-</span>
        </div>
        
        <div class="screen-container" id="screenContainer">
            <img id="screen" src="/screenshot.jpg" onclick="handleClick(event)" oncontextmenu="handleRightClick(event); return false;">
            <div id="clickInfo"></div>
        </div>
        
        <div class="controls">
            <div class="control-group">
                <h3>⌨️ Keyboard Input</h3>
                <input type="text" id="typeText" placeholder="Type text here..." onkeypress="if(event.key==='Enter')sendType()">
                <button onclick="sendType()">Send</button>
                <div class="info">Press Enter or click Send</div>
            </div>
            
            <div class="control-group">
                <h3>🔑 Special Keys</h3>
                <button onclick="sendKey('enter')">Enter</button>
                <button onclick="sendKey('escape')">Esc</button>
                <button onclick="sendKey('backspace')">Backspace</button>
                <button onclick="sendKey('tab')">Tab</button>
                <button onclick="sendKey('command')">⌘ Cmd</button>
                <button onclick="sendKey('shift')">Shift</button>
                <button onclick="sendKey('control')">Ctrl</button>
                <button onclick="sendKey('option')">Option</button>
            </div>
            
            <div class="control-group">
                <h3>🖱️ Mouse Actions</h3>
                <button onclick="sendClick('left')">Left Click</button>
                <button onclick="sendClick('right')">Right Click</button>
                <button onclick="sendClick('double')">Double Click</button>
                <button onclick="scroll('up')">Scroll Up</button>
                <button onclick="scroll('down')">Scroll Down</button>
            </div>
            
            <div class="control-group">
                <h3>🔧 Actions</h3>
                <button onclick="runCommand('screenshot')">📸 Save Screenshot</button>
                <button onclick="runCommand('allow_permissions')">✅ Allow Permissions</button>
                <button onclick="runCommand('open_terminal')">💻 Open Terminal</button>
                <button onclick="runCommand('open_settings')">⚙️ Open Settings</button>
                <button onclick="refreshScreen()">🔄 Refresh</button>
            </div>
        </div>
        
        <div class="info" style="margin-top: 20px;">
            💡 <strong>Tip:</strong> Click on the screen to click at that position. Right-click for context menu.
            The screen updates automatically every 500ms.
        </div>
    </div>
    
    <script>
        let lastFrameTime = Date.now();
        let frameCount = 0;
        
        // Auto-refresh screenshot
        function refreshScreen() {
            const img = document.getElementById('screen');
            img.src = '/screenshot.jpg?t=' + Date.now();
        }
        
        setInterval(refreshScreen, 500);
        
        // Calculate FPS
        document.getElementById('screen').onload = function() {
            frameCount++;
            const now = Date.now();
            if (now - lastFrameTime >= 1000) {
                document.getElementById('fps').textContent = frameCount;
                frameCount = 0;
                lastFrameTime = now;
            }
            
            // Update resolution
            this.naturalWidth && (document.getElementById('resolution').textContent = 
                this.naturalWidth + 'x' + this.naturalHeight);
        };
        
        // Handle click on screen
        function handleClick(event) {
            const img = document.getElementById('screen');
            const rect = img.getBoundingClientRect();
            const x = Math.round((event.clientX - rect.left) * (img.naturalWidth / rect.width));
            const y = Math.round((event.clientY - rect.top) * (img.naturalHeight / rect.height));
            
            sendClickAt(x, y, 'left');
            showClickInfo(event.clientX, event.clientY, x, y);
        }
        
        function handleRightClick(event) {
            const img = document.getElementById('screen');
            const rect = img.getBoundingClientRect();
            const x = Math.round((event.clientX - rect.left) * (img.naturalWidth / rect.width));
            const y = Math.round((event.clientY - rect.top) * (img.naturalHeight / rect.height));
            
            sendClickAt(x, y, 'right');
        }
        
        function showClickInfo(clientX, clientY, x, y) {
            const info = document.getElementById('clickInfo');
            info.style.display = 'block';
            info.style.left = clientX + 'px';
            info.style.top = clientY + 'px';
            info.textContent = `Click at (${x}, ${y})`;
            setTimeout(() => info.style.display = 'none', 1000);
        }
        
        // API calls
        async function sendClickAt(x, y, button) {
            await fetch('/click', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({x, y, button})
            });
            refreshScreen();
        }
        
        async function sendType() {
            const text = document.getElementById('typeText').value;
            if (!text) return;
            
            await fetch('/type', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text})
            });
            document.getElementById('typeText').value = '';
            refreshScreen();
        }
        
        async function sendKey(key) {
            await fetch('/key', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key})
            });
            refreshScreen();
        }
        
        async function sendClick(button) {
            await fetch('/click', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({button})
            });
            refreshScreen();
        }
        
        async function scroll(direction) {
            await fetch('/scroll', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({direction})
            });
            refreshScreen();
        }
        
        async function runCommand(cmd) {
            await fetch('/command', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({command: cmd})
            });
            refreshScreen();
        }
        
        // Update connection status
        document.getElementById('connectionStatus').textContent = '🟢 Connected';
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def send_screenshot(self):
        """Send screenshot as base64 JSON."""
        with screenshot_lock:
            if latest_screenshot:
                b64 = base64.b64encode(latest_screenshot).decode()
                response = json.dumps({'image': b64, 'timestamp': time.time()})
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(response.encode())
            else:
                self.send_error(503, "Screenshot not available")
    
    def send_screenshot_jpeg(self):
        """Send screenshot as JPEG image."""
        with screenshot_lock:
            if latest_screenshot:
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(latest_screenshot)
            else:
                self.send_error(503, "Screenshot not available")
    
    def send_status(self):
        """Send server status."""
        status = {
            'connected': len(connected_clients),
            'screenshot_available': latest_screenshot is not None,
            'screen_size': pyautogui.size()._asdict() if pyautogui.size() else None,
            'timestamp': time.time()
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())
    
    def handle_click(self):
        """Handle mouse click request."""
        try:
            content_length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(content_length))
            
            x = data.get('x')
            y = data.get('y')
            button = data.get('button', 'left')
            clicks = data.get('clicks', 1)
            
            if x is not None and y is not None:
                # Scale coordinates if needed
                screen_width, screen_height = pyautogui.size()
                # Assuming screenshot is scaled
                pyautogui.click(x, y, clicks=clicks, button=button)
                response = {'success': True, 'action': 'click', 'x': x, 'y': y, 'button': button}
            else:
                # Click at current position
                pyautogui.click(button=button)
                response = {'success': True, 'action': 'click', 'button': button}
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_type(self):
        """Handle keyboard typing request."""
        try:
            content_length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(content_length))
            
            text = data.get('text', '')
            interval = data.get('interval', 0.02)
            
            pyautogui.typewrite(text, interval=interval)
            
            response = {'success': True, 'action': 'type', 'length': len(text)}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_key(self):
        """Handle special key press request."""
        try:
            content_length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(content_length))
            
            key = data.get('key', '')
            
            pyautogui.press(key)
            
            response = {'success': True, 'action': 'key', 'key': key}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_scroll(self):
        """Handle scroll request."""
        try:
            content_length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(content_length))
            
            direction = data.get('direction', 'up')
            amount = data.get('amount', 3)
            
            if direction == 'up':
                pyautogui.scroll(amount)
            else:
                pyautogui.scroll(-amount)
            
            response = {'success': True, 'action': 'scroll', 'direction': direction}
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_command(self):
        """Handle custom command request."""
        try:
            content_length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(content_length))
            
            command = data.get('command', '')
            result = {'success': True, 'command': command}
            
            if command == 'screenshot':
                # Save screenshot to file
                screenshot = take_screenshot()
                if screenshot:
                    filename = f'/tmp/screenshot_{int(time.time())}.jpg'
                    with open(filename, 'wb') as f:
                        f.write(screenshot)
                    result['filename'] = filename
            
            elif command == 'allow_permissions':
                # Try to allow any pending permissions via AppleScript
                script = '''
                tell application "System Events"
                    try
                        click button "Allow" of window 1 of process "SecurityAgent"
                    end try
                end tell
                '''
                subprocess.run(['osascript', '-e', script], capture_output=True)
                result['message'] = 'Attempted to allow permissions'
            
            elif command == 'open_terminal':
                subprocess.run(['open', '-a', 'Terminal'])
                result['message'] = 'Opened Terminal'
            
            elif command == 'open_settings':
                # Open System Settings to Screen Recording
                if int(subprocess.run(['sw_vers', '-productVersion'], capture_output=True, text=True).stdout.split('.')[0]) >= 13:
                    subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'])
                else:
                    subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'])
                result['message'] = 'Opened Screen Recording settings'
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
            
        except Exception as e:
            self.send_error(500, str(e))


def run_server(host: str = '0.0.0.0', port: int = 8080):
    """Run the remote control server."""
    global latest_screenshot
    
    # Start screenshot updater thread
    print("Starting screenshot thread...")
    screenshot_thread = threading.Thread(target=screenshot_updater, daemon=True)
    screenshot_thread.start()
    
    # Wait for first screenshot
    for _ in range(10):
        if latest_screenshot:
            break
        time.sleep(0.5)
    
    # Start HTTP server
    server = HTTPServer((host, port), RemoteControlHandler)
    
    print(f"""
╔════════════════════════════════════════════════════════════════╗
║             macOS Remote Control Server Started                ║
╠════════════════════════════════════════════════════════════════╣
║  Local:   http://localhost:{port:<5}                               ║
║  Network: http://<your-ip>:{port:<5}                                ║
╠════════════════════════════════════════════════════════════════╣
║  Features:                                                      ║
║  • Live screenshot streaming                                    ║
║  • Mouse click control                                          ║
║  • Keyboard input                                               ║
║  • Special keys support                                         ║
║  • Permission auto-allow                                        ║
╠════════════════════════════════════════════════════════════════╣
║  Press Ctrl+C to stop                                           ║
╚════════════════════════════════════════════════════════════════╝
""")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='macOS Remote Control Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to bind to')
    
    args = parser.parse_args()
    run_server(args.host, args.port)
