
import time
import base64
import requests

import platform
import subprocess
import os

import argparse
import sys

import configparser

# Default Configuration
API_DEFAULT = "http://localhost:8019" # Updated to your port 8019
SERVER_ID_DEFAULT = ""
LICENSE_KEY_DEFAULT = ""

import hashlib
import uuid

# 1. Load Config File (if exists)
config = configparser.ConfigParser()

# robustly find agent.ini in the same folder as the exe/script
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

config_file = os.path.join(application_path, 'agent.ini')

if os.path.exists(config_file):
    try:
        config.read(config_file)
    except Exception as e:
        print(f"Error reading config: {e}")

# Get defaults from config if available
DEV_MODE = False
if 'General' in config:
    API_DEFAULT = config['General'].get('api', API_DEFAULT)
    SERVER_ID_DEFAULT = config['General'].get('server_id', SERVER_ID_DEFAULT)
    LICENSE_KEY_DEFAULT = config['General'].get('license_key', LICENSE_KEY_DEFAULT)
    DEV_MODE = config['General'].getboolean('dev_mode', False)

# ... imports ...


# 2. Parse Arguments (Overrides Config)
# function to parse args safely without exiting
def parse_args_safe():
    parser = argparse.ArgumentParser(description='Cloud Print Agent')
    parser.add_argument('--api', default=API_DEFAULT, help='Cloud API URL')
    parser.add_argument('--server-id', default=SERVER_ID_DEFAULT, help='Unique Server ID')
    parser.add_argument('--license-key', default=LICENSE_KEY_DEFAULT, help='SaaS License Key')
    parser.add_argument('--dev', action='store_true', help='Enable Dev Mode (Simulated Printer)')
    
    # In GUI mode, sys.argv might have weird stuff or nothing. 
    # If called from bootloader/noconsole, standard parsing is fine.
    try:
        args, unknown = parser.parse_known_args()
        return args
    except:
        return argparse.Namespace(api=API_DEFAULT, server_id=SERVER_ID_DEFAULT, license_key=LICENSE_KEY_DEFAULT, dev=False)

# Global variables will be set in run()
API = API_DEFAULT
LICENSE_KEY = LICENSE_KEY_DEFAULT
SERVER_ID = SERVER_ID_DEFAULT
HEADERS = {}
STARTUP_ERROR = None

# Validation Logic moved to run()
args = parse_args_safe()
if args.dev:
    DEV_MODE = True
if args.api:
    API = args.api
if args.server_id:
    SERVER_ID = args.server_id # Temporary, will be finalized in run()
if args.license_key:
    LICENSE_KEY = args.license_key

def generate_server_id(license_key):
    # ... existing logic ...
    mac = uuid.getnode()
    unique_str = f"{mac}-{license_key}"
    return "server-" + hashlib.md5(unique_str.encode()).hexdigest()[:8]

if not LICENSE_KEY:
    STARTUP_ERROR = "License Key Missing. Checks agent.ini"
else:
    SERVER_ID = args.server_id or generate_server_id(LICENSE_KEY)
    HEADERS = {"X-License-Key": LICENSE_KEY, "X-Server-ID": SERVER_ID}



def generate_server_id(license_key):
    # Combine MAC address and License Key to ensure uniqueness per machine per license
    mac = uuid.getnode()
    unique_str = f"{mac}-{license_key}"
    return "server-" + hashlib.md5(unique_str.encode()).hexdigest()[:8]

API = args.api
LICENSE_KEY = args.license_key
SERVER_ID = args.server_id or generate_server_id(LICENSE_KEY)
HEADERS = {"X-License-Key": LICENSE_KEY, "X-Server-ID": SERVER_ID}

print("="*60)
print(f"   CLOUD PRINT AGENT STARTED")
print(f"   SERVER ID: {SERVER_ID}")
print("-" * 60)
print("   ACTION REQUIRED:")
print("   1. Go to your Odoo -> Cloud Printing -> Print Servers")
print(f"   2. Create a new server with Identifier: {SERVER_ID}")
print("   3. Click 'Sync Printers'")
print("="*60)

def get_printers():
    printers = []
    system = platform.system()
    try:
        if system == "Darwin" or system == "Linux":
            # lpstat -a output format: "printer_name accepting requests since..."
            output = subprocess.check_output(["lpstat", "-a"]).decode("utf-8")
            for line in output.splitlines():
                if line.strip():
                    printers.append(line.split(' ')[0])
        elif system == "Windows":
             # Basic Powershell command to list printers
            cmd = 'powershell "Get-Printer | Select-Object Name"'
            output = subprocess.check_output(cmd, shell=True).decode("utf-8")
            lines = output.splitlines()
            # Skip header and empty lines
            for line in lines[2:]:
                if line.strip():
                     printers.append(line.strip())
    except Exception as e:
        print(f"Error discovering printers: {e}")
    return printers

def print_pdf(content, printer_uid):
    filename = f"job_{int(time.time())}.pdf"
    with open(filename, "wb") as f:
        f.write(base64.b64decode(content))
    print(f"Saved job to {filename}")

    if printer_uid == "DEV_PDF":
        print(f"Simulating print to {printer_uid}")
        # Keep file for manual inspection
        return

    try:
        system = platform.system()
        if system == "Darwin" or system == "Linux":
            # lp -d printer_name filename
            subprocess.run(["lp", "-d", printer_uid, filename], check=True)
            print(f"Sent {filename} to printer {printer_uid}")
        elif system == "Windows":
            # os imported globally now
            abs_path = os.path.abspath(filename)
            printer_name_escaped = printer_uid.replace('"', '`"')
            
            # 1. OPTION A: SumatraPDF (Recommended & Bundled)
            # Check for bundled SumatraPDF in PyInstaller temp folder (_MEIPASS)
            sumatra_path = None
            
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                # Bundled in single-file EXE
                bundled_path = os.path.join(sys._MEIPASS, 'SumatraPDF.exe')
                if os.path.exists(bundled_path):
                     sumatra_path = bundled_path
            
            # If not bundled, check local folder (for dev/testing)
            if not sumatra_path:
                if getattr(sys, 'frozen', False):
                    app_dir = os.path.dirname(sys.executable)
                else:
                    app_dir = os.path.dirname(os.path.abspath(__file__))
                local_path = os.path.join(app_dir, 'SumatraPDF.exe')
                if os.path.exists(local_path):
                    sumatra_path = local_path
            
            if sumatra_path and os.path.exists(sumatra_path):
                print(f"Printing via SumatraPDF...")
                # Sumatra command: SumatraPDF.exe -print-to "Printer Name" -exit-on-print "file.pdf"
                # -silent prevents the window from showing up
                cmd = [sumatra_path, '-print-to', printer_uid, '-exit-on-print', '-silent', abs_path]
                subprocess.run(cmd, check=True)
                print("Sent to printer via SumatraPDF.")
                return # Success
            
            # 2. OPTION B: PowerShell (Fallback)
            # Using Powershell's Start-Process with 'PrintTo' verb. 
            # REQUIRES a PDF reader associated with .pdf files that supports the 'PrintTo' verb (e.g. Adobe Reader, Foxit).
            
            print("SumatraPDF.exe not found. Falling back to System Default PDF Viewer...")
            
            cmd = f'powershell -Command "Start-Process -FilePath \'{abs_path}\' -Verb PrintTo -ArgumentList \'{printer_name_escaped}\' -PassThru -Wait"'
            
            print(f"Attempting to print {filename} to {printer_uid}...")
            try:
                subprocess.run(cmd, shell=True, check=True)
                print(f"Command sent to {printer_uid}.")
            except subprocess.CalledProcessError as e:
                print("---------------------------------------------------------------")
                print(f"ERROR: Failed to print to specific printer '{printer_uid}'.")
                print("---------------------------------------------------------------")
                print("POSSIBLE FIXES:")
                print("1. (Recommended) Download 'SumatraPDF.exe' and place it in this folder.")
                print("   The agent will automatically use it for reliable printing.")
                print("2. Install Adobe Acrobat Reader DC and set it as default.")
                print("---------------------------------------------------------------")
                print(f"Details: {e}")
                
                # Fallback: Try printing to Default Printer
                print("Attempting fallback: Printing to System Default Printer...")
                try:
                    fallback_cmd = f'powershell -Command "Start-Process -FilePath \'{abs_path}\' -Verb Print -PassThru -Wait"'
                    subprocess.run(fallback_cmd, shell=True, check=True)
                    print("Fallback successful: Sent to Default Printer.")
                except Exception as ex:
                    print(f"Fallback failed: {ex}")
    except Exception as e:
        print(f"Failed to print to {printer_uid}: {e}")
    finally:
        # Cleanup temp file
        if os.path.exists(filename):
            try:
                os.remove(filename)
                print(f"Cleaned up temp file: {filename}")
            except Exception as rm_err:
                print(f"Warning: Failed to delete temp file {filename}: {rm_err}")

import threading
from PIL import Image, ImageDraw
import pystray
import webbrowser

# ... config ...

# Redirect print to log file since we have no console
class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        self.log = open("agent.log", "a", encoding='utf-8')

    def write(self, message):
        # self.terminal.write(message) # Uncomment if debugging with console
        try:
            self.log.write(message)
            self.log.flush()
        except:
            pass

    def flush(self):
        #self.terminal.flush()
        self.log.flush()

# Apply logger if not in dev (console) mode, or just always for safety in GUI mode
if not os.environ.get('AGENT_CONSOLE_DEBUG'):
    sys.stdout = Logger()
    sys.stderr = sys.stdout

def create_image():
    # Generate a simple icon programmatically (64x64 blue box with a P)
    width = 64
    height = 64
    color1 = "blue"
    color2 = "white"
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=color2)
    return image

def run_agent_loop(icon):
    if STARTUP_ERROR:
        print(f"Startup Error: {STARTUP_ERROR}")
        icon.title = "Agent Error: Missing Config"
        icon.notify(STARTUP_ERROR, "Configuration Error")
        return

    print(f"Agent Loop Started. Server ID: {SERVER_ID}")
    
    # Initial Discovery
    try:
        discovered_printers = get_printers()
        if DEV_MODE:
            discovered_printers.append({"os_id": "DEV_PDF", "name": "Dev PDF Printer"})
            
        if discovered_printers:
            print(f"Discovered: {len(discovered_printers)} printers.")
            try:
                response = requests.post(f"{API}/api/agent/printers", json={"printers": discovered_printers, "server_uid": SERVER_ID}, headers=HEADERS)
                if response.status_code in [401, 403]:
                    print(f"AUTH ERROR during sync: {response.text}")
                    icon.notify("Authentication Failed. Check agent.ini", "Cloud Print Error")
                response.raise_for_status()
            except Exception as e:
                print(f"Sync Failed: {e}")
    except Exception as e:
        print(f"Startup Failed: {e}")

    # Main Loop
    while True:
        if not icon.visible:
            break # Stop if icon hidden (exit)
            
        try:
            response = requests.get(f"{API}/api/agent/jobs", headers=HEADERS)
            
            if response.status_code in [401, 403]:
                 print("Auth Error polling jobs.")
                 time.sleep(10)
                 continue

            response.raise_for_status()
            job = response.json()
            
            if job:
                print(f"Received Job: {job.get('job_id')}")
                icon.notify(f"Printing to {job.get('printer_uid')}", "New Print Job")
                try:
                    print_pdf(job["content"], job["printer_uid"])
                    requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "done"}, headers=HEADERS)
                except Exception as e:
                    print(f"Printing failed: {e}")
                    requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "error", "error": str(e)}, headers=HEADERS)
        except Exception as e:
            # print(f"Polling error: {e}") # Too spammy if offline
            pass
            
        time.sleep(5)

def on_open_log(icon, item):
    if os.path.exists("agent.log"):
        os.startfile("agent.log")

def on_open_config(icon, item):
    if os.path.exists("agent.ini"):
        os.startfile("agent.ini")
    else:
        # Create default
        with open("agent.ini", "w") as f:
            f.write(f"[General]\napi={API_DEFAULT}\nlicense_key=\n")
        os.startfile("agent.ini")

def on_exit(icon, item):
    icon.visible = False
    icon.stop()
    sys.exit(0)

# ... (previous code) ...

# Main Execution wrapper for Cython
def run():
    # GUI Mode Main Entry
    icon = pystray.Icon("CloudPrintAgent")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Server: " + SERVER_ID, lambda i, item: None, enabled=False),
        pystray.MenuItem("View Log", on_open_log),
        pystray.MenuItem("Edit Config", on_open_config),
        pystray.MenuItem("Exit", on_exit)
    )
    icon.icon = create_image()
    icon.title = f"Cloud Print Agent ({SERVER_ID})"
    
    # Start Agent Thread
    t = threading.Thread(target=run_agent_loop, args=(icon,), daemon=True)
    t.start()
    
    # Run UI (Blocking)
    try:
        icon.run()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    run()
