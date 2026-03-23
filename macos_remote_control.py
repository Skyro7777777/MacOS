#!/usr/bin/env python3
"""
macOS GitHub Actions Remote Control Solution
==============================================
"""

import os
import sys
import subprocess
import sqlite3
import time

class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_success(text): print(f"{Colors.GREEN}[+] {text}{Colors.RESET}")
def print_error(text): print(f"{Colors.RED}[-] {text}{Colors.RESET}")
def print_warning(text): print(f"{Colors.YELLOW}[!] {text}{Colors.RESET}")
def print_info(text): print(f"{Colors.BLUE}[*] {text}{Colors.RESET}")

class TCCDatabaseManager:
    SYSTEM_TCC_DB = "/Library/Application Support/com.apple.TCC/TCC.db"
    USER_TCC_DB = None
    
    def __init__(self):
        home = os.environ.get('HOME', '/Users/runner')
        self.USER_TCC_DB = f"{home}/Library/Application Support/com.apple.TCC/TCC.db"
    
    def check_tcc_db_access(self):
        system_access = os.access(self.SYSTEM_TCC_DB, os.R_OK | os.W_OK)
        user_access = os.access(self.USER_TCC_DB, os.R_OK | os.W_OK)
        return system_access, user_access
    
    def get_screen_capture_apps(self):
        apps = []
        for db_path in [self.SYSTEM_TCC_DB, self.USER_TCC_DB]:
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT client FROM access WHERE service='kTCCServiceScreenCapture'")
                    for row in cursor.fetchall():
                        apps.append(row[0])
                    conn.close()
                except Exception as e:
                    print_warning(f"Error reading {db_path}: {e}")
        return list(set(apps))

class VNCManager:
    @staticmethod
    def enable_screen_sharing():
        try:
            subprocess.run([
                '/System/Library/CoreServices/RemoteManagement/ARDAgent.app/Contents/Resources/kickstart',
                '-activate', '-configure', '-access', '-on', '-restart', '-agent', '-privs', '-all'
            ], capture_output=True)
            print_success("Remote Management enabled")
            return True
        except Exception as e:
            print_error(f"Failed: {e}")
            return False
    
    @staticmethod
    def check_vnc_status():
        try:
            result = subprocess.run(['lsof', '-i', ':5900'], capture_output=True, text=True)
            return bool(result.stdout.strip())
        except:
            return False

class GitHubActionsController:
    def __init__(self):
        self.tcc = TCCDatabaseManager()
        self.vnc = VNCManager()
    
    def diagnose(self):
        print("\n" + "="*50)
        print("  TCC Permission Diagnostic")
        print("="*50 + "\n")
        
        system_w, user_w = self.tcc.check_tcc_db_access()
        print_info(f"System TCC.db: {'Writable' if system_w else 'Read-only'}")
        print_info(f"User TCC.db: {'Writable' if user_w else 'Read-only'}")
        
        print_info("\nApps with Screen Recording permission:")
        apps = self.tcc.get_screen_capture_apps()
        for app in apps:
            print(f"  - {app}")
        
        if '/bin/bash' in apps:
            print_success("\nbash HAS Screen Recording permission!")
        
        print_info(f"\nVNC Status: {'Active' if self.vnc.check_vnc_status() else 'Inactive'}")
        
        print_info("\nTesting screen capture...")
        try:
            subprocess.run(['screencapture', '-x', '/tmp/test.png'], capture_output=True)
            if os.path.exists('/tmp/test.png'):
                print_success("Screenshot works!")
            else:
                print_error("Screenshot failed")
        except Exception as e:
            print_error(f"Screenshot error: {e}")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'diagnose':
        controller = GitHubActionsController()
        controller.diagnose()
    else:
        print("Usage: python3 macos_remote_control.py diagnose")

if __name__ == "__main__":
    main()
