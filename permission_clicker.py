#!/usr/bin/env python3
"""
macOS Permission Dialog Auto-Clicker

This script automatically detects and clicks "Allow" on macOS permission dialogs.
Since bash already has screen recording permission on GitHub Actions macOS runners,
this script inherits that permission and can capture the screen to detect dialogs.

Key insight: bash, hosted-compute-agent, and provisioner already have screen recording
permissions on GitHub Actions macOS runners. This script runs from bash and inherits
those permissions, allowing it to:
1. Capture screenshots to detect permission dialogs
2. Use PyAutoGUI to click "Allow" automatically
"""

import subprocess
import sys
import time
import threading
from typing import Optional, Tuple
import os

# Try to import required modules, install if not available
def ensure_packages():
    """Ensure required packages are installed."""
    packages = ['pyautogui', 'Pillow', 'mss', 'opencv-python']
    for package in packages:
        package_name = package.replace('-', '_') if package != 'opencv-python' else 'cv2'
        try:
            __import__(package_name)
        except ImportError:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '--quiet'])

ensure_packages()

import pyautogui
from PIL import Image
import cv2
import numpy as np

# Configure PyAutoGUI for safety
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

class PermissionDialogClicker:
    """Automatically detects and clicks Allow on macOS permission dialogs."""
    
    def __init__(self, check_interval: float = 0.5):
        self.check_interval = check_interval
        self.running = False
        self.click_count = 0
        
        # Known button texts for permission dialogs
        self.allow_buttons = [
            "Allow",
            "OK",
            "Open System Settings",
            "Open System Preferences",
        ]
        
        # Permission dialog window titles (for detection)
        self.dialog_indicators = [
            "would like to",
            "is requesting",
            "permission",
            "Screen Recording",
            "Accessibility",
            "Microphone",
            "Camera",
        ]
    
    def take_screenshot(self) -> Optional[Image.Image]:
        """Take a screenshot. Uses bash's inherited screen recording permission."""
        try:
            # Try using mss first (faster)
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # All monitors
                screenshot = sct.grab(monitor)
                return Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
        except Exception as e:
            # Fallback to pyautogui
            try:
                return pyautogui.screenshot()
            except Exception as e2:
                print(f"Screenshot failed: {e}, {e2}")
                return None
    
    def find_allow_button(self, screenshot: Image.Image) -> Optional[Tuple[int, int]]:
        """
        Find the "Allow" button on screen using multiple methods.
        Returns the center coordinates of the button if found.
        """
        # Method 1: Use macOS accessibility via AppleScript
        try:
            result = self._find_button_applescript()
            if result:
                return result
        except Exception as e:
            pass
        
        # Method 2: Image template matching
        # The "Allow" button in macOS permission dialogs is typically blue/white
        try:
            result = self._find_button_color(screenshot)
            if result:
                return result
        except Exception as e:
            pass
        
        # Method 3: OCR-based detection (if available)
        try:
            result = self._find_button_ocr(screenshot)
            if result:
                return result
        except Exception as e:
            pass
        
        return None
    
    def _find_button_applescript(self) -> Optional[Tuple[int, int]]:
        """Use AppleScript to find and interact with permission dialogs."""
        script = '''
        tell application "System Events"
            try
                set frontmostProcess to first process whose frontmost is true
                set windowList to windows of frontmostProcess
                
                repeat with theWindow in windowList
                    try
                        set windowTitle to name of theWindow
                        if windowTitle contains "would like to" or windowTitle contains "is requesting" then
                            -- Found a permission dialog
                            set buttonList to buttons of theWindow
                            repeat with theButton in buttonList
                                set buttonTitle to name of theButton
                                if buttonTitle is "Allow" or buttonTitle is "OK" then
                                    click theButton
                                    return "clicked"
                                end if
                            end repeat
                        end if
                    end try
                end repeat
            end try
        end tell
        return "not found"
        '''
        
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=5
            )
            if 'clicked' in result.stdout:
                self.click_count += 1
                print(f"✓ Clicked Allow button via AppleScript (total: {self.click_count})")
                return True
        except Exception as e:
            pass
        
        return None
    
    def _find_button_color(self, screenshot: Image.Image) -> Optional[Tuple[int, int]]:
        """Find Allow button by detecting button-like UI elements."""
        # Convert to numpy array
        img_array = np.array(screenshot)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # Look for blue button (macOS "Allow" button color)
        # Blue button: BGR approximately (0, 122, 255) or similar
        lower_blue = np.array([200, 100, 0])
        upper_blue = np.array([255, 180, 100])
        mask = cv2.inRange(img_bgr, lower_blue, upper_blue)
        
        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            # Button should have reasonable size
            if 40 < w < 200 and 20 < h < 60:
                # Check if it's in a likely position (right side of screen, typical for dialogs)
                center_x = x + w // 2
                center_y = y + h // 2
                screen_width = screenshot.width
                
                # Permission dialogs usually have Allow button on the right
                if center_x > screen_width * 0.5:
                    return (center_x, center_y)
        
        return None
    
    def _find_button_ocr(self, screenshot: Image.Image) -> Optional[Tuple[int, int]]:
        """Find Allow button using OCR (if pytesseract is available)."""
        try:
            import pytesseract
            
            # Get OCR data with bounding boxes
            data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
            
            for i, text in enumerate(data['text']):
                if text.strip().lower() in ['allow', 'ok']:
                    x = data['left'][i] + data['width'][i] // 2
                    y = data['top'][i] + data['height'][i] // 2
                    return (x, y)
        except ImportError:
            pass
        
        return None
    
    def click_at(self, x: int, y: int):
        """Click at the specified coordinates."""
        pyautogui.click(x, y)
        self.click_count += 1
        print(f"✓ Clicked at ({x}, {y}) (total clicks: {self.click_count})")
    
    def check_and_click(self) -> bool:
        """Check for permission dialogs and click Allow if found."""
        # First try AppleScript method (most reliable for system dialogs)
        if self._find_button_applescript():
            return True
        
        # Then try visual detection
        screenshot = self.take_screenshot()
        if screenshot is None:
            print("Warning: Could not take screenshot")
            return False
        
        button_pos = self.find_allow_button(screenshot)
        if button_pos:
            self.click_at(button_pos[0], button_pos[1])
            return True
        
        return False
    
    def start_monitoring(self, duration: float = 300):
        """Start monitoring for permission dialogs for the specified duration."""
        print(f"Starting permission dialog monitor for {duration} seconds...")
        self.running = True
        start_time = time.time()
        
        while self.running and (time.time() - start_time) < duration:
            self.check_and_click()
            time.sleep(self.check_interval)
        
        print(f"Monitoring stopped. Total Allow clicks: {self.click_count}")
    
    def stop_monitoring(self):
        """Stop monitoring for permission dialogs."""
        self.running = False


class BackgroundPermissionMonitor:
    """Run permission monitoring in a background thread."""
    
    def __init__(self):
        self.clicker = PermissionDialogClicker()
        self.thread = None
    
    def start(self, duration: float = 300):
        """Start monitoring in background."""
        self.thread = threading.Thread(target=self.clicker.start_monitoring, args=(duration,))
        self.thread.daemon = True
        self.thread.start()
        print("Background permission monitor started")
    
    def stop(self):
        """Stop the background monitor."""
        self.clicker.stop_monitoring()
        if self.thread:
            self.thread.join(timeout=2)


def grant_screen_recording_to_app(app_path: str) -> bool:
    """
    Attempt to grant screen recording permission to an application.
    
    This works by:
    1. Launching the app to trigger the permission request
    2. Auto-clicking "Allow" on the dialog
    """
    print(f"Attempting to grant screen recording permission to: {app_path}")
    
    # Start the permission monitor in background
    monitor = BackgroundPermissionMonitor()
    monitor.start(duration=60)
    
    # Launch the app
    try:
        subprocess.run(['open', app_path], check=True)
        print(f"Launched {app_path}")
        
        # Wait for permission dialog
        time.sleep(3)
        
        # Try to trigger screen recording permission
        # For VNC, we can use kickstart
        if 'VNC' in app_path or 'Screen' in app_path or 'Remote' in app_path:
            trigger_vnc_permission()
        
        # Give time for the monitor to click
        time.sleep(5)
        
    except Exception as e:
        print(f"Error launching app: {e}")
    
    monitor.stop()
    return True


def trigger_vnc_permission():
    """Trigger VNC/Screen Recording permission by enabling Remote Management."""
    print("Triggering VNC permission...")
    
    # Enable Remote Management (requires admin, but we're running as admin user)
    kickstart_cmd = [
        '/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart',
        '-activate',
        '-configure',
        '-access', '-on',
        '-privs', '-all',
        '-restart', '-agent'
    ]
    
    try:
        result = subprocess.run(kickstart_cmd, capture_output=True, text=True, timeout=30)
        print(f"Kickstart output: {result.stdout}")
        if result.returncode != 0:
            print(f"Kickstart error: {result.stderr}")
    except Exception as e:
        print(f"Kickstart failed: {e}")


def setup_vnc_with_password(password: str = "Apple@123"):
    """Set up VNC with a specific password."""
    print("Setting up VNC with password...")
    
    # Start permission monitor
    monitor = BackgroundPermissionMonitor()
    monitor.start(duration=120)
    
    # Enable Remote Management
    kickstart_cmd = [
        '/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart',
        '-activate',
        '-configure',
        '-access', '-on',
        '-privs', '-all',
        '-restart', '-agent',
        '-clientopts',
        f'-setvnclegacy', '-vnclegacy', 'yes',
        f'-setvncpw', '-vncpw', password
    ]
    
    try:
        result = subprocess.run(kickstart_cmd, capture_output=True, text=True, timeout=60)
        print(f"VNC setup output: {result.stdout}")
        if result.returncode != 0:
            print(f"VNC setup error: {result.stderr}")
    except Exception as e:
        print(f"VNC setup failed: {e}")
    
    time.sleep(5)
    monitor.stop()
    print("VNC setup complete")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='macOS Permission Dialog Auto-Clicker')
    parser.add_argument('--monitor', '-m', type=float, default=60,
                        help='Duration to monitor for dialogs (seconds)')
    parser.add_argument('--setup-vnc', action='store_true',
                        help='Set up VNC with auto-permission granting')
    parser.add_argument('--password', default='Apple@123',
                        help='VNC password (default: Apple@123)')
    parser.add_argument('--grant-app', type=str,
                        help='Grant screen recording permission to an app')
    
    args = parser.parse_args()
    
    if args.setup_vnc:
        setup_vnc_with_password(args.password)
    elif args.grant_app:
        grant_screen_recording_to_app(args.grant_app)
    else:
        # Just run the monitor
        clicker = PermissionDialogClicker()
        clicker.start_monitoring(args.monitor)


if __name__ == '__main__':
    main()
