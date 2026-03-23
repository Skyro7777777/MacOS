#!/usr/bin/env python3
"""
macOS VNC Black Screen Fix for GitHub Actions
"""

import os
import sys
import subprocess
import sqlite3

class VNCFixer:
    SYSTEM_TCC = "/Library/Application Support/com.apple.TCC/TCC.db"
    USER_TCC = None
    
    def __init__(self):
        home = os.environ.get('HOME', '/Users/runner')
        self.USER_TCC = f"{home}/Library/Application Support/com.apple.TCC/TCC.db"
    
    def diagnose(self):
        print("\n" + "="*50)
        print("  VNC Black Screen Diagnostic")
        print("="*50 + "\n")
        
        print("[*] Checking Screen Recording permissions...")
        for db in [self.SYSTEM_TCC, self.USER_TCC]:
            if os.path.exists(db):
                try:
                    conn = sqlite3.connect(db)
                    cursor = conn.cursor()
                    cursor.execute("SELECT client FROM access WHERE service='kTCCServiceScreenCapture'")
                    apps = [row[0] for row in cursor.fetchall()]
                    print(f"\n  {db}:")
                    for app in apps:
                        print(f"    - {app}")
                    conn.close()
                except Exception as e:
                    print(f"  Error: {e}")
        
        if '/bin/bash' in self._get_all_screen_apps():
            print("\n[+] bash has Screen Recording - child processes can inherit!")
        
        self._check_vnc()
    
    def _get_all_screen_apps(self):
        apps = []
        for db in [self.SYSTEM_TCC, self.USER_TCC]:
            if os.path.exists(db):
                try:
                    conn = sqlite3.connect(db)
                    cursor = conn.cursor()
                    cursor.execute("SELECT client FROM access WHERE service='kTCCServiceScreenCapture'")
                    apps.extend([row[0] for row in cursor.fetchall()])
                    conn.close()
                except:
                    pass
        return list(set(apps))
    
    def _check_vnc(self):
        print("\n[*] VNC Status:")
        try:
            result = subprocess.run(['lsof', '-i', ':5900'], capture_output=True, text=True)
            print(f"  Port 5900: {'Active' if result.stdout.strip() else 'Inactive'}")
        except:
            print("  Could not check port 5900")
    
    def enable_apple_vnc(self):
        print("[*] Enabling Apple Screen Sharing...")
        try:
            subprocess.run([
                '/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart',
                '-activate', '-configure', '-access', '-on', '-restart', '-agent', '-privs', '-all'
            ], capture_output=True)
            print("[+] Done!")
        except Exception as e:
            print(f"[-] Failed: {e}")

def main():
    fixer = VNCFixer()
    if len(sys.argv) > 1:
        if sys.argv[1] == '--diagnose':
            fixer.diagnose()
        elif sys.argv[1] == '--enable-apple-vnc':
            fixer.enable_apple_vnc()
        else:
            print("Usage: python3 macos_vnc_fixer.py [--diagnose|--enable-apple-vnc]")
    else:
        fixer.diagnose()

if __name__ == "__main__":
    main()
