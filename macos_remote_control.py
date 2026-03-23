#!/usr/bin/env python3
"""
macOS GitHub Actions Remote Control Solution
==============================================

This script provides multiple methods to control macOS GitHub Actions runners
by exploiting the pre-configured TCC (Transparency, Consent, and Control) permissions.

GitHub Actions macOS runners have the following TCC permissions pre-configured:
- /bin/bash: Screen Recording, Accessibility, Full Disk Access
- /opt/hca/hosted-compute-agent: Screen Recording, Accessibility
- /usr/local/opt/runner/provisioner/provisioner: Screen Recording, Accessibility
- /usr/bin/osascript: Screen Recording, Apple Events

Key insight: Child processes inherit TCC permissions from their parent when
spawned directly (fork/exec), NOT when launched via `open -a` command.

Author: Research-based solution for GitHub Actions macOS remote control
"""

import os
import sys
import subprocess
import sqlite3
import plistlib
import shutil
import tempfile
import time
import json
import struct
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any


class Colors:
    """Terminal colors for output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}[+] {text}{Colors.RESET}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}[-] {text}{Colors.RESET}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}[!] {text}{Colors.RESET}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.BLUE}[*] {text}{Colors.RESET}")


class TCCDatabaseManager:
    """Manage macOS TCC (Transparency, Consent, and Control) database."""
    
    SYSTEM_TCC_DB = "/Library/Application Support/com.apple.TCC/TCC.db"
    USER_TCC_DB = None  # Will be set based on home directory
    
    # TCC Service types
    SERVICES = {
        'SCREEN_CAPTURE': 'kTCCServiceScreenCapture',
        'ACCESSIBILITY': 'kTCCServiceAccessibility',
        'FULL_DISK_ACCESS': 'kTCCServiceSystemPolicyAllFiles',
        'APPLE_EVENTS': 'kTCCServiceAppleEvents',
        'MICROPHONE': 'kTCCServiceMicrophone',
        'CAMERA': 'kTCCServiceCamera',
        'POST_EVENT': 'kTCCServicePostEvent',
        'BLUETOOTH': 'kTCCServiceBluetoothAlways',
    }
    
    def __init__(self):
        home = os.environ.get('HOME', '/Users/runner')
        self.USER_TCC_DB = f"{home}/Library/Application Support/com.apple.TCC/TCC.db"
        
    def check_tcc_db_access(self) -> Tuple[bool, bool]:
        """Check if we can access TCC databases."""
        system_access = os.access(self.SYSTEM_TCC_DB, os.R_OK | os.W_OK)
        user_access = os.access(self.USER_TCC_DB, os.R_OK | os.W_OK)
        return system_access, user_access
    
    def query_permissions(self, db_path: str, service: str = None) -> List[Dict]:
        """Query TCC database for permissions."""
        if not os.path.exists(db_path):
            return []
        
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if service:
                cursor.execute(
                    "SELECT * FROM access WHERE service = ?",
                    (service,)
                )
            else:
                cursor.execute("SELECT * FROM access")
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
        except Exception as e:
            print_error(f"Failed to query TCC database: {e}")
            return []
    
    def get_screen_capture_apps(self) -> List[str]:
        """Get list of apps with Screen Recording permission."""
        apps = []
        
        for db_path in [self.SYSTEM_TCC_DB, self.USER_TCC_DB]:
            if os.path.exists(db_path):
                perms = self.query_permissions(db_path, self.SERVICES['SCREEN_CAPTURE'])
                for perm in perms:
                    client = perm.get('client', '')
                    if client:
                        apps.append(client)
        
        return apps
    
    def generate_csreq_blob(self, bundle_id: str = None, path: str = None) -> Optional[bytes]:
        """
        Generate a code requirement blob for an application.
        
        For bundle IDs: Uses the CDHash (Code Directory Hash) format
        For paths: Uses the path-based requirement
        """
        if bundle_id:
            # Generate requirement for bundle ID
            # Format: identifier "com.app.bundleid" and anchor apple generic
            req_str = f'identifier "{bundle_id}" and anchor apple generic'
            
            # Use csreq command to generate binary blob
            try:
                result = subprocess.run(
                    ['csreq', '-r', req_str, '-b', '/dev/stdout'],
                    capture_output=True
                )
                if result.returncode == 0:
                    return result.stdout
            except:
                pass
        
        return None
    
    def add_permission(self, db_path: str, service: str, client: str,
                       allowed: int = 1, auth_value: int = 2,
                       auth_reason: int = 0, csreq: bytes = None) -> bool:
        """
        Add a permission entry to TCC database.
        
        Parameters:
        - db_path: Path to TCC database
        - service: TCC service (e.g., 'kTCCServiceScreenCapture')
        - client: Bundle ID or path to the application
        - allowed: 1 = allowed, 0 = denied
        - auth_value: Authorization value (usually 2)
        - auth_reason: 0 = user, 4 = system
        - csreq: Code signature requirement blob (optional for unsigned apps)
        
        Returns True if successful, False otherwise.
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if entry already exists
            cursor.execute(
                "SELECT * FROM access WHERE service = ? AND client = ?",
                (service, client)
            )
            if cursor.fetchone():
                print_info(f"Permission already exists for {client}")
                conn.close()
                return True
            
            # Insert new permission
            current_time = int(time.time())
            
            cursor.execute("""
                INSERT INTO access (
                    service, client, client_type, auth_value, auth_reason,
                    auth_version, csreq, policy_id, indirect_object_identifier_type,
                    indirect_object_identifier, indirect_object_code_signature,
                    flags, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                service, client, 1, auth_value, auth_reason,
                1, csreq, None, 0, 'UNUSED', None, 0, current_time
            ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            print_error(f"Failed to add permission: {e}")
            return False
    
    def add_screen_capture_for_app(self, app_path: str) -> bool:
        """Add Screen Recording permission for an application."""
        success = False
        
        for db_path in [self.SYSTEM_TCC_DB, self.USER_TCC_DB]:
            if os.access(db_path, os.W_OK):
                if self.add_permission(db_path, self.SERVICES['SCREEN_CAPTURE'], app_path):
                    print_success(f"Added Screen Recording permission for {app_path} in {db_path}")
                    success = True
        
        return success


class ProcessLauncher:
    """
    Launch processes with inherited TCC permissions.
    
    Key insight: When you launch an app via `open -a AppName`, macOS LaunchServices
    handles the launch and the app becomes a child of launchd (PID 1), NOT the
    terminal that ran the command. This breaks TCC permission inheritance.
    
    To maintain TCC inheritance, we need to spawn processes directly via fork/exec.
    """
    
    @staticmethod
    def find_app_binary(app_path: str) -> Optional[str]:
        """Find the main executable binary inside an app bundle."""
        if not app_path.endswith('.app'):
            return app_path
        
        # Check Info.plist for main executable
        info_plist = os.path.join(app_path, 'Contents', 'Info.plist')
        if os.path.exists(info_plist):
            try:
                with open(info_plist, 'rb') as f:
                    plist = plistlib.load(f)
                    exe_name = plist.get('CFBundleExecutable')
                    if exe_name:
                        exe_path = os.path.join(app_path, 'Contents', 'MacOS', exe_name)
                        if os.path.exists(exe_path):
                            return exe_path
            except:
                pass
        
        # Try common locations
        for subdir in ['Contents/MacOS/', '']:
            for name in os.listdir(os.path.join(app_path, subdir)):
                full_path = os.path.join(app_path, subdir, name)
                if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                    return full_path
        
        return None
    
    @staticmethod
    def spawn_direct(binary_path: str, *args) -> subprocess.Popen:
        """
        Spawn a process directly (fork/exec) to inherit TCC permissions.
        
        This is THE KEY to inheriting TCC permissions!
        Using subprocess.Popen with the binary path directly (not `open -a`)
        means the child process inherits from the calling process.
        """
        cmd = [binary_path] + list(args)
        print_info(f"Spawning process directly: {' '.join(cmd)}")
        
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            start_new_session=False  # Important: keep in same session
        )
    
    @staticmethod
    def spawn_via_open(app_path: str, *args) -> subprocess.Popen:
        """
        Launch via `open` command (DOES NOT inherit TCC permissions).
        
        This is what typically breaks TCC inheritance.
        The app becomes a child of launchd, not the terminal.
        """
        cmd = ['open', '-a', app_path] + list(args)
        print_warning(f"Launching via 'open' (may NOT inherit TCC): {' '.join(cmd)}")
        
        return subprocess.Popen(cmd)
    
    @staticmethod
    def spawn_via_fork_exec(binary_path: str, *args, env: dict = None) -> int:
        """
        Pure Python fork/exec to spawn a process.
        
        This is the most reliable way to ensure TCC inheritance.
        """
        import ctypes
        import ctypes.util
        
        # Get libc
        libc_name = ctypes.util.find_library('c')
        libc = ctypes.CDLL(libc_name, use_errno=True)
        
        # Fork
        pid = libc.fork()
        
        if pid == 0:
            # Child process
            if env:
                os.environ.update(env)
            
            # Exec
            os.execvp(binary_path, [binary_path] + list(args))
        elif pid > 0:
            # Parent process
            return pid
        else:
            raise OSError("Fork failed")


class ScreenCaptureManager:
    """
    Screen capture utilities that work with inherited TCC permissions.
    
    Since /bin/bash has Screen Recording permission in GitHub Actions,
    we can use screencapture command directly.
    """
    
    @staticmethod
    def capture_screenshot(output_path: str = None, display: int = None,
                           window: bool = False, region: str = None) -> Optional[str]:
        """
        Capture a screenshot using the screencapture command.
        
        This works because bash has Screen Recording permission!
        """
        if output_path is None:
            output_path = f"/tmp/screenshot_{int(time.time())}.png"
        
        cmd = ['screencapture', '-x']  # -x = no sound
        
        if display is not None:
            cmd.extend(['-D', str(display)])
        
        if window:
            cmd.append('-w')  # Window mode
        
        if region:
            cmd.extend(['-R', region])
        
        cmd.append(output_path)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(output_path):
                print_success(f"Screenshot saved to: {output_path}")
                return output_path
            else:
                print_error(f"Screenshot failed: {result.stderr}")
                return None
        except Exception as e:
            print_error(f"Screenshot error: {e}")
            return None
    
    @staticmethod
    def capture_video(duration: int = 5, output_path: str = None) -> Optional[str]:
        """
        Capture a video using the screencapture command (macOS 14+).
        
        Note: This requires Screen Recording permission.
        """
        if output_path is None:
            output_path = f"/tmp/screen_recording_{int(time.time())}.mov"
        
        cmd = ['screencapture', '-v', '-V', str(duration), output_path]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(output_path):
                print_success(f"Video saved to: {output_path}")
                return output_path
            else:
                print_error(f"Video capture failed: {result.stderr}")
                return None
        except Exception as e:
            print_error(f"Video capture error: {e}")
            return None
    
    @staticmethod
    def list_windows() -> List[Dict]:
        """
        List all windows using AppleScript.
        
        This requires Accessibility permission (which bash has).
        """
        script = '''
        tell application "System Events"
            set windowList to {}
            repeat with theProcess in (every process whose visible is true)
                try
                    set processName to name of theProcess
                    repeat with theWindow in windows of theProcess
                        set windowTitle to name of theWindow
                        set end of windowList to processName & " | " & windowTitle
                    end repeat
                end try
            end repeat
            return windowList
        end tell
        '''
        
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                windows = []
                for line in result.stdout.strip().split(', '):
                    if ' | ' in line:
                        proc, title = line.split(' | ', 1)
                        windows.append({'process': proc, 'title': title})
                return windows
        except Exception as e:
            print_error(f"Failed to list windows: {e}")
        
        return []


class AppleScriptController:
    """
    AppleScript-based GUI automation.
    
    Since bash has Accessibility and Apple Events permissions,
    we can use AppleScript to control the GUI.
    """
    
    @staticmethod
    def run_script(script: str) -> Tuple[bool, str]:
        """Run an AppleScript and return success status and output."""
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def click_at(x: int, y: int) -> bool:
        """Click at specific coordinates."""
        script = f'''
        tell application "System Events"
            click at {{{x}, {y}}}
        end tell
        '''
        success, _ = AppleScriptController.run_script(script)
        return success
    
    @staticmethod
    def open_system_settings(pane: str = None) -> bool:
        """Open System Settings/Preferences to a specific pane."""
        if pane:
            script = f'''
            tell application "System Settings"
                activate
                reveal pane id "{pane}"
            end tell
            '''
        else:
            script = '''
            tell application "System Settings"
                activate
            end tell
            '''
        
        success, _ = AppleScriptController.run_script(script)
        return success
    
    @staticmethod
    def grant_screen_recording_permission(app_name: str) -> bool:
        """
        Attempt to grant Screen Recording permission via GUI automation.
        
        This opens System Settings and tries to click the checkbox.
        Requires Accessibility permission.
        """
        script = f'''
        tell application "System Settings"
            activate
            reveal pane id "com.apple.preference.security"
            delay 1
            tell application "System Events"
                tell process "System Settings"
                    -- Navigate to Screen Recording
                    click menu item "Screen Recording" of menu 1 of menu item "Privacy & Security" of menu 1 of menu bar "Window"
                    delay 1
                    -- Find and click the app checkbox
                    try
                        click checkbox "{app_name}" of table 1 of scroll area 1 of group 1 of splitter group 1 of group 2
                    end try
                end tell
            end tell
        end tell
        '''
        
        success, output = AppleScriptController.run_script(script)
        if success:
            print_success(f"Attempted to grant permission for {app_name}")
        else:
            print_warning(f"GUI automation may have failed: {output}")
        
        return success
    
    @staticmethod
    def dismiss_dialog(button: str = "Allow") -> bool:
        """Dismiss a dialog by clicking a button."""
        script = f'''
        tell application "System Events"
            try
                click button "{button}" of window 1 of process "SecurityAgent"
            end try
        end tell
        '''
        success, _ = AppleScriptController.run_script(script)
        return success


class VNCManager:
    """Manage VNC/Screen Sharing on macOS."""
    
    @staticmethod
    def enable_screen_sharing() -> bool:
        """
        Enable Screen Sharing (VNC) server.
        
        Note: Since macOS 12.1, kickstart may not work for Screen Sharing.
        Remote Management (ARD) might still work.
        """
        # Method 1: Try kickstart for Remote Management
        kickstart_cmd = '''
        /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \\
            -activate -configure -access -on -restart -agent -privs -all
        '''
        
        try:
            result = subprocess.run(kickstart_cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print_success("Remote Management enabled")
                return True
        except:
            pass
        
        # Method 2: Enable Screen Sharing service
        try:
            subprocess.run([
                'sudo', 'launchctl', 'load', '-w',
                '/System/Library/LaunchDaemons/com.apple.screensharing.plist'
            ], capture_output=True)
            print_success("Screen Sharing service enabled")
            return True
        except:
            pass
        
        print_warning("Could not enable Screen Sharing via command line")
        return False
    
    @staticmethod
    def set_vnc_password(password: str) -> bool:
        """Set VNC password for authentication."""
        # This requires root access
        script = f'''
        tell application "System Events"
            do shell script "/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart -configure -clientopts -setvnclegacy -vnclegacy yes -setvncpw -vncpw {password}" with administrator privileges
        end tell
        '''
        
        success, _ = AppleScriptController.run_script(script)
        return success
    
    @staticmethod
    def check_vnc_status() -> Dict:
        """Check VNC/Screen Sharing status."""
        status = {
            'screen_sharing': False,
            'remote_management': False,
            'port_5900': False
        }
        
        # Check Screen Sharing
        result = subprocess.run(
            ['sudo', 'launchctl', 'list'],
            capture_output=True, text=True
        )
        if 'com.apple.screensharing' in result.stdout:
            status['screen_sharing'] = True
        
        # Check Remote Management
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True, text=True
        )
        if 'ARDAgent' in result.stdout:
            status['remote_management'] = True
        
        # Check port 5900
        result = subprocess.run(
            ['lsof', '-i', ':5900'],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            status['port_5900'] = True
        
        return status


class VirtualDisplayManager:
    """
    Create virtual displays for headless macOS.
    
    Without a display attached (or virtual display), screen capture may fail
    or VNC may show a black screen.
    """
    
    @staticmethod
    def get_display_info() -> List[Dict]:
        """Get information about connected displays."""
        script = '''
        tell application "System Events"
            set displayInfo to {}
            tell process "WindowServer"
                -- Display info isn't directly accessible
            end tell
        end tell
        '''
        
        # Use system_profiler instead
        result = subprocess.run(
            ['system_profiler', 'SPDisplaysDataType'],
            capture_output=True, text=True
        )
        
        displays = []
        current_display = {}
        
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('Display Type:'):
                if current_display:
                    displays.append(current_display)
                current_display = {'type': line.split(':', 1)[1].strip()}
            elif line.startswith('Resolution:'):
                current_display['resolution'] = line.split(':', 1)[1].strip()
            elif line.startswith('Main Display:'):
                current_display['main'] = 'Yes' in line
        
        if current_display:
            displays.append(current_display)
        
        return displays
    
    @staticmethod
    def create_dummy_display(width: int = 1920, height: int = 1080) -> bool:
        """
        Create a dummy/virtual display.
        
        Note: This is typically done with third-party tools like:
        - BetterDisplay (https://github.com/waydabber/BetterDisplay)
        - displayplacer
        - HDMI dummy plugs (hardware)
        """
        print_info("Virtual display creation requires third-party tools:")
        print_info("1. BetterDisplay: brew install --cask betterdisplay")
        print_info("2. displayplacer: brew install displayplacer")
        print_info("3. Hardware: HDMI dummy plug")
        
        # Try displayplacer if available
        if shutil.which('displayplacer'):
            result = subprocess.run(
                ['displayplacer', 'list'],
                capture_output=True, text=True
            )
            print_info(f"Current displays: {result.stdout}")
        
        return False


class GitHubActionsController:
    """
    Main controller for GitHub Actions macOS runner remote control.
    """
    
    def __init__(self):
        self.tcc = TCCDatabaseManager()
        self.launcher = ProcessLauncher()
        self.screen = ScreenCaptureManager()
        self.applescript = AppleScriptController()
        self.vnc = VNCManager()
        self.display = VirtualDisplayManager()
    
    def diagnose(self):
        """Run full diagnostic of the runner's capabilities."""
        print_header("GitHub Actions macOS Runner Diagnostic")
        
        # Check TCC database access
        print_info("Checking TCC database access...")
        system_access, user_access = self.tcc.check_tcc_db_access()
        print(f"  System TCC.db: {'Writable' if system_access else 'Read-only or No access'}")
        print(f"  User TCC.db: {'Writable' if user_access else 'Read-only or No access'}")
        
        # List apps with Screen Recording permission
        print_info("\nApps with Screen Recording permission:")
        screen_apps = self.tcc.get_screen_capture_apps()
        for app in screen_apps:
            print(f"  - {app}")
        
        # Check bash permissions
        print_info("\nVerifying bash has required permissions...")
        bash_perms = self.tcc.query_permissions(
            self.tcc.SYSTEM_TCC_DB,
            TCCDatabaseManager.SERVICES['SCREEN_CAPTURE']
        )
        bash_screen = any(p.get('client') == '/bin/bash' for p in bash_perms)
        print(f"  bash Screen Recording: {'Yes' if bash_screen else 'No'}")
        
        # Check display status
        print_info("\nDisplay information:")
        displays = self.display.get_display_info()
        for i, disp in enumerate(displays):
            print(f"  Display {i+1}: {disp}")
        
        # Check VNC status
        print_info("\nVNC/Screen Sharing status:")
        vnc_status = self.vnc.check_vnc_status()
        for key, value in vnc_status.items():
            print(f"  {key}: {'Active' if value else 'Inactive'}")
        
        # Test screenshot capability
        print_info("\nTesting screenshot capability...")
        screenshot = self.screen.capture_screenshot()
        if screenshot:
            print_success(f"Screenshot works! Saved to: {screenshot}")
        else:
            print_error("Screenshot failed - may need Screen Recording permission")
    
    def setup_vnc_access(self, password: str = "github-actions"):
        """Set up VNC access for remote control."""
        print_header("Setting up VNC Access")
        
        # Enable Screen Sharing
        print_info("Enabling Screen Sharing...")
        self.vnc.enable_screen_sharing()
        
        # Set VNC password
        print_info("Setting VNC password...")
        self.vnc.set_vnc_password(password)
        
        # Check status
        status = self.vnc.check_vnc_status()
        print_info(f"VNC Status: {status}")
        
        return status
    
    def add_app_permission(self, app_path: str):
        """Add Screen Recording permission for an app via TCC database."""
        print_header(f"Adding Permission for {app_path}")
        
        # Check if we have write access
        system_access, user_access = self.tcc.check_tcc_db_access()
        
        if not system_access and not user_access:
            print_error("No write access to TCC database")
            print_info("Try running with sudo or check SIP status")
            return False
        
        # Add permission
        return self.tcc.add_screen_capture_for_app(app_path)
    
    def launch_app_with_inheritance(self, app_path: str, *args):
        """
        Launch an app in a way that inherits TCC permissions.
        
        KEY: Don't use `open -a`! Use the binary directly.
        """
        print_header(f"Launching {app_path} with TCC inheritance")
        
        # Find the actual binary
        binary = self.launcher.find_app_binary(app_path)
        if not binary:
            print_error(f"Could not find binary for {app_path}")
            return None
        
        print_info(f"Found binary: {binary}")
        
        # Launch directly
        process = self.launcher.spawn_direct(binary, *args)
        print_success(f"Launched with PID: {process.pid}")
        
        return process
    
    def automate_permission_grant(self, app_name: str):
        """
        Use AppleScript to automate granting permission via System Settings.
        
        This clicks through the GUI to add Screen Recording permission.
        """
        print_header(f"Automating Permission Grant for {app_name}")
        
        # Open System Settings to Privacy & Security
        print_info("Opening System Settings...")
        self.applescript.open_system_settings("com.apple.preference.security")
        
        time.sleep(2)
        
        # Try to navigate and click
        print_info("Attempting to grant permission via GUI...")
        self.applescript.grant_screen_recording_permission(app_name)


def create_workflow_script():
    """Create a shell script for use in GitHub Actions workflow."""
    script = '''#!/bin/bash
# GitHub Actions macOS Remote Control Setup Script
# This script sets up remote access to macOS runner

set -e

echo "========================================"
echo "macOS Runner Remote Control Setup"
echo "========================================"

# 1. Install dependencies
echo "[*] Installing dependencies..."
brew install tailscale 2>/dev/null || true

# 2. Setup Tailscale
echo "[*] Setting up Tailscale..."
if [ -n "$TAILSCALE_AUTH_KEY" ]; then
    sudo tailscale up --authkey=$TAILSCALE_AUTH_KEY --hostname=gha-macos-$(date +%s) --accept-routes
    echo "[+] Tailscale connected"
    echo "    IP: $(tailscale ip -4)"
fi

# 3. Enable Screen Sharing/VNC
echo "[*] Enabling Screen Sharing..."
sudo /System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart \\
    -activate -configure -access -on -restart -agent -privs -all 2>/dev/null || true

# 4. Create user for remote access
echo "[*] Creating remote user..."
if ! id -u remoteuser &>/dev/null; then
    sudo sysadminctl -addUser remoteuser -password "Apple@123" -admin 2>/dev/null || true
fi

# 5. Test screen capture
echo "[*] Testing screen capture..."
screencapture -x /tmp/test_screenshot.png && echo "[+] Screen capture works!" || echo "[-] Screen capture failed"

# 6. Get system info
echo ""
echo "========================================"
echo "Connection Information"
echo "========================================"
echo "Tailscale IP: $(tailscale ip -4 2>/dev/null || echo 'Not connected')"
echo "VNC Port: 5900"
echo "Username: remoteuser"
echo "Password: Apple@123"
echo ""
echo "To connect:"
echo "  1. Connect to Tailscale network"
echo "  2. Use VNC client to connect to $(tailscale ip -4 2>/dev/null || echo '<tailscale-ip>'):5900"
echo "========================================"

# Keep alive for connection
echo "[*] Runner ready. Keeping session alive..."
echo "[*] Press Ctrl+C to end session"

# Take periodic screenshots and keep display active
while true; do
    sleep 60
    screencapture -x /tmp/keepalive_$(date +%s).png 2>/dev/null || true
done
'''
    return script


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="macOS GitHub Actions Remote Control Tool"
    )
    parser.add_argument(
        'command',
        choices=['diagnose', 'setup-vnc', 'add-permission', 'launch', 'screenshot', 'workflow'],
        help='Command to execute'
    )
    parser.add_argument('--app', help='App path for permission/launch commands')
    parser.add_argument('--password', default='github-actions', help='VNC password')
    parser.add_argument('--output', help='Output file for screenshot')
    parser.add_argument('--args', nargs='*', help='Arguments for launch command')
    
    args = parser.parse_args()
    
    controller = GitHubActionsController()
    
    if args.command == 'diagnose':
        controller.diagnose()
    
    elif args.command == 'setup-vnc':
        controller.setup_vnc_access(args.password)
    
    elif args.command == 'add-permission':
        if not args.app:
            print_error("--app is required for add-permission")
            sys.exit(1)
        controller.add_app_permission(args.app)
    
    elif args.command == 'launch':
        if not args.app:
            print_error("--app is required for launch")
            sys.exit(1)
        controller.launch_app_with_inheritance(args.app, *(args.args or []))
    
    elif args.command == 'screenshot':
        output = controller.screen.capture_screenshot(args.output)
        if output:
            print_success(f"Screenshot saved: {output}")
        else:
            sys.exit(1)
    
    elif args.command == 'workflow':
        print(create_workflow_script())


if __name__ == "__main__":
    main()
