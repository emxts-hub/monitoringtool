import os
import sys
import urllib.request

# ------------------- Hidden PyInstaller Dependencies -------------------
# These imports force PyInstaller to bundle these libraries inside the .exe!
import asyncio
import json
import os
import re
import socket
import threading
import time
import winsound
from datetime import datetime

# ------------------- GitHub Configuration -------------------
GITHUB_USER = "matxmata13-sketch"
REPO_NAME = "AppToolAS400"
FILE_PATH = "main.py"
BRANCH = "main"

GITHUB_TOKEN = "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" 

RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/{BRANCH}/{FILE_PATH}"

def fetch_and_run():
    print("🌐 Connecting to secure GitHub repository...")
    try:
        req = urllib.request.Request(RAW_URL)
        if GITHUB_TOKEN and GITHUB_TOKEN != "YOUR_NEW_GITHUB_TOKEN_HERE":
            req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
        req.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(req) as response:
            code_bytes = response.read()
            script_code = code_bytes.decode('utf-8')

        print("🚀 Executing LPAR Monitoring Script...\n")
        
        script_globals = {"__name__": "__main__"}
        exec(script_code, script_globals)

    except Exception as e:
        print(f"❌ Execution failed: {e}")
        print("💡 Please ensure that your VPN is connected and your GitHub token is valid. If you continue to experience issues, contact the developer.")
        input("\nPress Enter to exit...")

if __name__ == "__main__":
    fetch_and_run()