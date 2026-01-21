
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

# 2. Parse Arguments (Overrides Config)
parser = argparse.ArgumentParser(description='Cloud Print Agent')
parser.add_argument('--api', default=API_DEFAULT, help='Cloud API URL')
parser.add_argument('--server-id', default=SERVER_ID_DEFAULT, help='Unique Server ID')
parser.add_argument('--license-key', default=LICENSE_KEY_DEFAULT, help='SaaS License Key')
parser.add_argument('--dev', action='store_true', help='Enable Dev Mode (Simulated Printer)')

try:
    args = parser.parse_args()
except SystemExit:
    # If argparse fails (e.g. help), it exits. We catch to keep window open if needed, 
    # but usually help is fine.
    raise

if args.dev:
    DEV_MODE = True

# 3. Final Validation
if not args.license_key:
    print("="*60)
    print("ERROR: License Key is required.")
    print(f"Please create a file named 'agent.ini' in: {application_path}")
    print("Content:")
    print("[General]")
    print(f"api = {API_DEFAULT}")
    print("license_key = YOUR_LICENSE_KEY_HERE")
    print("="*60)
    input("Press Enter to exit...") # Keep window open
    sys.exit(1)



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
            
            # Using Powershell's Start-Process with 'PrintTo' verb. 
            # REQUIRES a PDF reader associated with .pdf files that supports the 'PrintTo' verb (e.g. Adobe Reader, Foxit).
            # Modern browsers (Edge/Chrome) as default PDF viewers DO NOT support this verb.
            
            cmd = f'powershell -Command "Start-Process -FilePath \'{abs_path}\' -Verb PrintTo -ArgumentList \'{printer_name_escaped}\' -PassThru -Wait"'
            
            print(f"Attempting to print {filename} to {printer_uid}...")
            try:
                subprocess.run(cmd, shell=True, check=True)
                print(f"Command sent to {printer_uid}.")
            except subprocess.CalledProcessError as e:
                print("---------------------------------------------------------------")
                print(f"ERROR: Failed to print to specific printer '{printer_uid}'.")
                print("This usually happens because the Default PDF Viewer does not support the 'PrintTo' command.")
                print("SOLUTION: Install Adobe Acrobat Reader DC and set it as the default app for .pdf files.")
                print(f"Details: {e}")
                print("---------------------------------------------------------------")
                
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

# Main Execution
if __name__ == '__main__':
    try:
        # Initial Discovery
        discovered_printers = get_printers()
        if DEV_MODE:
                discovered_printers = [
                    {
                        "os_id": "DEV_PDF",
                        "name": "Dev PDF Printer"
                    }
                ]
        if discovered_printers:
            print(f"Discovered printers: {discovered_printers}")
            try:
                response = requests.post(f"{API}/api/agent/printers", json={"printers": discovered_printers, "server_uid": SERVER_ID}, headers=HEADERS)
                if response.status_code in [401, 403]:
                    try:
                        err = response.json()
                        print(f"Auth Error: {err.get('error', 'Unknown Error')}")
                    except:
                        print(f"Auth Error: {response.text}")
                response.raise_for_status()
            except Exception as e:
                print(f"Failed to sync printers: {e}")

        while True:
            try:
                response = requests.get(f"{API}/api/agent/jobs", headers=HEADERS)
                
                if response.status_code in [401, 403]:
                     try:
                        err = response.json()
                        print(f"Auth Error: {err.get('error', 'Unknown Error')}")
                     except:
                        print(f"Auth Error: {response.text}")
                     time.sleep(10) # Wait longer on auth error
                     continue

                response.raise_for_status()
                job = response.json()
                
                if job:
                    try:
                        print_pdf(job["content"], job["printer_uid"])
                        requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "done"}, headers=HEADERS)
                    except Exception as e:
                        print(f"Printing failed: {e}")
                        requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "error", "error": str(e)}, headers=HEADERS)
            except Exception as e:
                print(f"Error polling jobs: {e}")
            time.sleep(5)

    except Exception as fatal_error:
        print("\n" + "!"*60)
        print(f"FATAL ERROR: {fatal_error}")
        print("!"*60)
        # Log to file
        try:
            with open("agent_crash.log", "w") as log:
                 log.write(str(fatal_error))
                 import traceback
                 traceback.print_exc(file=log)
        except:
            pass
        
        import traceback
        traceback.print_exc()
        print("\nApplication has crashed.")
        input("Press Enter to exit...")
        sys.exit(1)
