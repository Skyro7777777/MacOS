#!/usr/bin/env python3
"""
macOS VNC Black Screen Fix for GitHub Actions
==============================================

This script addresses the common issue of VNC showing a black screen when
connecting to macOS GitHub Actions runners.

ROOT CAUSE ANALYSIS:
====================
1. VNC apps (RustDesk, AnyDesk, RealVNC, etc.) need Screen Recording permission
   to capture screen content on macOS 10.15+
   
2. These apps are NOT pre-approved in GitHub Actions TCC database

3. When you launch them via `open -a` or Homebrew, they become children of
   launchd (PID 1), NOT bash, so they DON'T inherit bash's TCC permissions

4. The black screen = VNC connected but has no permission to read screen pixels

SOLUTIONS:
==========
1. Use Apple's built-in Screen Sharing (screensharingd) - may have better luck
2. Launch VNC apps as direct children of bash (not via `open`)
3. Inject TCC database entries (requires write access)
4. Use a wrapper script that inherits bash's permissions

This script implements all approaches.
"""

import os
import sys
import subprocess
import sqlite3
import time
import shutil
from pathlib import Path
from typing import Optional, List, Tuple


class VNCFixer:
    """Fix VNC black screen issues on macOS."""
    
    SYSTEM_TCC = "/Library/Application Support/com.apple.TCC/TCC.db"
    USER_TCC = None
    
    def __init__(self):
        home = os.environ.get('HOME', '/Users/runner')
        self.USER_TCC = f"{home}/Library/Application Support/com.apple.TCC/TCC.db"
    
    def print_status(self, msg: str, status: str = "info"):
        """Print colored status message."""
        colors = {
            "info": "\033[94m[*]",
            "success": "\033[92m[+]",
            "error": "\033[91m[-]",
            "warning": "\033[93m[!]",
            "reset": "\033[0m"
        }
        print(f"{colors.get(status, colors['info'])} {msg}{colors['reset']}")
    
    def check_tcc_access(self) -> Tuple[bool, bool]:
        """Check if we can modify TCC databases."""
        system_writable = os.access(self.SYSTEM_TCC, os.W_OK)
        user_writable = os.access(self.USER_TCC, os.W_OK)
        return system_writable, user_writable
    
    def list_screen_recording_apps(self) -> List[str]:
        """List all apps with Screen Recording permission."""
        apps = []
        
        for db_path in [self.SYSTEM_TCC, self.USER_TCC]:
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT client FROM access WHERE service='kTCCServiceScreenCapture'"
                    )
                    for row in cursor.fetchall():
                        apps.append(row[0])
                    conn.close()
                except Exception as e:
                    self.print_status(f"Error reading {db_path}: {e}", "warning")
        
        return list(set(apps))
    
    def check_app_in_tcc(self, app_identifier: str) -> bool:
        """Check if an app has Screen Recording permission."""
        apps = self.list_screen_recording_apps()
        return app_identifier in apps
    
    def add_app_to_tcc(self, app_path: str, bundle_id: str = None) -> bool:
        """
        Add an app to Screen Recording permissions.
        
        Args:
            app_path: Path to the app binary
            bundle_id: Bundle ID (for signed apps)
        
        Returns:
            True if successful, False otherwise
        """
        system_writable, user_writable = self.check_tcc_access()
        
        if not system_writable and not user_writable:
            self.print_status("No write access to TCC databases!", "error")
            self.print_status("This usually means:", "info")
            self.print_status("  1. SIP (System Integrity Protection) is enabled", "info")
            self.print_status("  2. Full Disk Access not granted", "info")
            return False
        
        # Generate csreq blob for signed apps
        csreq_blob = None
        if bundle_id:
            try:
                result = subprocess.run(
                    ['csreq', '-r', f'identifier "{bundle_id}"', '-b', '/dev/stdout'],
                    capture_output=True
                )
                if result.returncode == 0:
                    csreq_blob = result.stdout
            except:
                pass
        
        # Insert into database(s)
        success = False
        current_time = int(time.time())
        
        for db_path, writable in [(self.SYSTEM_TCC, system_writable), 
                                   (self.USER_TCC, user_writable)]:
            if not writable:
                continue
            
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Check if exists
                cursor.execute(
                    "SELECT * FROM access WHERE service='kTCCServiceScreenCapture' AND client=?",
                    (app_path,)
                )
                if cursor.fetchone():
                    self.print_status(f"Already in {db_path}: {app_path}", "info")
                    conn.close()
                    success = True
                    continue
                
                # Insert new entry
                cursor.execute("""
                    INSERT INTO access (
                        service, client, client_type, auth_value, auth_reason,
                        auth_version, csreq, policy_id, indirect_object_identifier_type,
                        indirect_object_identifier, indirect_object_code_signature,
                        flags, last_modified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    'kTCCServiceScreenCapture',
                    app_path,
                    1,  # client_type: 1 = path, 0 = bundle_id
                    2,  # auth_value: allowed
                    4 if db_path == self.SYSTEM_TCC else 0,  # auth_reason: system/user
                    1,  # auth_version
                    csreq_blob,
                    None,
                    0,
                    'UNUSED',
                    None,
                    0,
                    current_time
                ))
                
                conn.commit()
                conn.close()
                self.print_status(f"Added to {db_path}: {app_path}", "success")
                success = True
                
            except Exception as e:
                self.print_status(f"Failed to add to {db_path}: {e}", "error")
        
        return success
    
    def enable_apple_screen_sharing(self) -> bool:
        """
        Enable Apple's built-in Screen Sharing.
        
        This is often the best option because:
        1. It's a system component with better permission handling
        2. It may inherit system-level permissions
        """
        self.print_status("Enabling Apple Screen Sharing...", "info")
        
        # Method 1: kickstart for Remote Management (includes VNC)
        kickstart_cmd = [
            '/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart',
            '-activate',
            '-configure',
            '-access', '-on',
            '-restart', '-agent',
            '-privs', '-all',
            '-clientopts', '-setvnclegacy', '-vnclegacy', 'yes'
        ]
        
        try:
            result = subprocess.run(kickstart_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.print_status("Remote Management enabled successfully", "success")
                return True
            else:
                self.print_status(f"kickstart output: {result.stderr}", "warning")
        except Exception as e:
            self.print_status(f"kickstart failed: {e}", "warning")
        
        # Method 2: Enable Screen Sharing service
        try:
            subprocess.run([
                'sudo', 'launchctl', 'load', '-w',
                '/System/Library/LaunchDaemons/com.apple.screensharing.plist'
            ], capture_output=True)
            self.print_status("Screen Sharing service enabled", "success")
            return True
        except:
            pass
        
        self.print_status("Could not enable Screen Sharing", "error")
        return False
    
    def check_vnc_status(self) -> dict:
        """Check VNC/Screen Sharing status."""
        status = {
            'port_5900': False,
            'ard_agent': False,
            'screen_sharing_service': False
        }
        
        # Check if port 5900 is open
        try:
            result = subprocess.run(['lsof', '-i', ':5900'], capture_output=True, text=True)
            status['port_5900'] = bool(result.stdout.strip())
        except:
            pass
        
        # Check ARDAgent
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            status['ard_agent'] = 'ARDAgent' in result.stdout
        except:
            pass
        
        # Check Screen Sharing service
        try:
            result = subprocess.run(['sudo', 'launchctl', 'list'], capture_output=True, text=True)
            status['screen_sharing_service'] = 'com.apple.screensharing' in result.stdout
        except:
            pass
        
        return status
    
    def launch_vnc_inherited(self, vnc_app: str, password: str = None) -> Optional[subprocess.Popen]:
        """
        Launch a VNC app in a way that inherits TCC permissions.
        
        KEY: Launch the binary directly, not via `open -a`!
        
        When you run `open -a AnyDesk`, macOS LaunchServices handles the launch,
        making it a child of launchd (PID 1), breaking TCC inheritance.
        
        By launching the binary directly, the app becomes a child of the
        calling process (bash), inheriting bash's Screen Recording permission!
        """
        self.print_status(f"Launching {vnc_app} with TCC inheritance...", "info")
        
        # Find the actual binary
        binary_path = None
        
        if vnc_app.endswith('.app'):
            # App bundle - find executable inside
            info_plist = os.path.join(vnc_app, 'Contents', 'Info.plist')
            if os.path.exists(info_plist):
                # Use plutil to read CFBundleExecutable
                try:
                    result = subprocess.run(
                        ['plutil', '-extract', 'CFBundleExecutable', 'raw', info_plist],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        exe_name = result.stdout.strip()
                        binary_path = os.path.join(vnc_app, 'Contents', 'MacOS', exe_name)
                except:
                    pass
        else:
            binary_path = vnc_app
        
        if not binary_path or not os.path.exists(binary_path):
            self.print_status(f"Could not find binary for: {vnc_app}", "error")
            return None
        
        self.print_status(f"Found binary: {binary_path}", "info")
        
        # Launch directly (NOT via `open`)
        # This maintains TCC inheritance!
        try:
            process = subprocess.Popen(
                [binary_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                # Don't start new session - keep parent relationship
                start_new_session=False
            )
            self.print_status(f"Launched with PID: {process.pid}", "success")
            self.print_status("This process SHOULD inherit bash's Screen Recording permission!", "success")
            return process
        except Exception as e:
            self.print_status(f"Failed to launch: {e}", "error")
            return None
    
    def create_vnc_wrapper_script(self, output_path: str = None) -> str:
        """
        Create a wrapper script that inherits TCC permissions.
        
        The idea: bash has Screen Recording permission.
        If we run a script from bash, the script inherits permission.
        The script can then do screen capture operations.
        """
        if output_path is None:
            output_path = "/tmp/vnc_wrapper.sh"
        
        script = '''#!/bin/bash
# VNC Wrapper Script with TCC Permission Inheritance
# ==================================================
# This script inherits Screen Recording permission from bash!
# Run this script directly (not via `open`) to maintain inheritance.

VNC_APP="${1:-/Applications/AnyDesk.app}"

# Find the binary
if [[ "$VNC_APP" == *.app ]]; then
    EXE_NAME=$(plutil -extract CFBundleExecutable raw "$VNC_APP/Contents/Info.plist" 2>/dev/null)
    BINARY="$VNC_APP/Contents/MacOS/$EXE_NAME"
else
    BINARY="$VNC_APP"
fi

if [[ ! -x "$BINARY" ]]; then
    echo "Error: Cannot find executable at $BINARY"
    exit 1
fi

echo "[*] Launching $BINARY with TCC inheritance..."
echo "[*] Parent PID: $PPID"
echo "[*] This process should inherit Screen Recording permission from bash!"

# Launch directly - NOT via `open -a`
exec "$BINARY" "$@"
'''
        
        with open(output_path, 'w') as f:
            f.write(script)
        
        os.chmod(output_path, 0o755)
        self.print_status(f"Wrapper script created: {output_path}", "success")
        return output_path
    
    def diagnose(self):
        """Run full diagnostic."""
        self.print_status("\n" + "="*50, "info")
        self.print_status("VNC Black Screen Diagnostic", "info")
        self.print_status("="*50, "info")
        
        # TCC access
        system_w, user_w = self.check_tcc_access()
        self.print_status(f"\nTCC Database Access:", "info")
        self.print_status(f"  System TCC.db: {'Writable' if system_w else 'Read-only'}", 
                         "success" if system_w else "warning")
        self.print_status(f"  User TCC.db: {'Writable' if user_w else 'Read-only'}",
                         "success" if user_w else "warning")
        
        # Current permissions
        self.print_status(f"\nApps with Screen Recording permission:", "info")
        apps = self.list_screen_recording_apps()
        for app in apps:
            self.print_status(f"  - {app}", "info")
        
        # Check bash specifically
        if '/bin/bash' in apps:
            self.print_status("\n✓ bash HAS Screen Recording permission!", "success")
            self.print_status("  Child processes can inherit this!", "success")
        else:
            self.print_status("\n✗ bash does NOT have Screen Recording permission", "error")
        
        # VNC status
        self.print_status(f"\nVNC Status:", "info")
        status = self.check_vnc_status()
        for key, value in status.items():
            self.print_status(f"  {key}: {'Active' if value else 'Inactive'}",
                            "success" if value else "warning")
        
        # Recommendations
        self.print_status("\n" + "="*50, "info")
        self.print_status("RECOMMENDATIONS:", "info")
        self.print_status("="*50, "info")
        
        if '/bin/bash' in apps:
            self.print_status("1. Use bash to launch VNC apps directly:", "info")
            self.print_status("   /path/to/VNC.app/Contents/MacOS/VNC", "info")
            self.print_status("   (NOT: open -a VNC)", "warning")
        
        if system_w or user_w:
            self.print_status("2. Add VNC app to TCC database:", "info")
            self.print_status("   python3 vnc_fixer.py --add /path/to/vnc", "info")
        
        self.print_status("3. Use Apple's built-in Screen Sharing:", "info")
        self.print_status("   python3 vnc_fixer.py --enable-apple-vnc", "info")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix VNC black screen on macOS GitHub Actions")
    parser.add_argument('--diagnose', action='store_true', help='Run diagnostic')
    parser.add_argument('--add', metavar='APP_PATH', help='Add app to Screen Recording permissions')
    parser.add_argument('--bundle-id', help='Bundle ID for signed apps')
    parser.add_argument('--enable-apple-vnc', action='store_true', help='Enable Apple Screen Sharing')
    parser.add_argument('--launch', metavar='APP_PATH', help='Launch app with TCC inheritance')
    parser.add_argument('--create-wrapper', action='store_true', help='Create VNC wrapper script')
    
    args = parser.parse_args()
    
    fixer = VNCFixer()
    
    if args.diagnose or len(sys.argv) == 1:
        fixer.diagnose()
    
    if args.add:
        fixer.add_app_to_tcc(args.add, args.bundle_id)
    
    if args.enable_apple_vnc:
        fixer.enable_apple_screen_sharing()
        status = fixer.check_vnc_status()
        print(f"\nVNC Status: {status}")
    
    if args.launch:
        fixer.launch_vnc_inherited(args.launch)
    
    if args.create_wrapper:
        fixer.create_vnc_wrapper_script()


if __name__ == "__main__":
    main()
