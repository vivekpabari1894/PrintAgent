import time
import platform
import subprocess
import os
import ctypes
import sys
import win32event
import win32api
import winerror
import winreg as reg

# Global variables (initialized in run())
API = ""
LICENSE_KEY = ""
SERVER_ID = ""
AUTO_START = True
HEADERS = {}
STARTUP_ERROR = None
DEV_MODE = False

# Application Paths (Safe to keep at top level as they use fast os/sys)
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

config_file = os.path.join(application_path, 'agent.ini')
log_path = os.path.join(application_path, 'agent.log')

def generate_server_id(license_key, mac):
    import hashlib
    unique_str = f"{mac}-{license_key}"
    return "server-" + hashlib.md5(unique_str.encode()).hexdigest()[:8]

def set_run_at_startup(app_name, action="install"):
    if platform.system() != "Windows": return False
    registry_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, registry_key, 0, reg.KEY_ALL_ACCESS)
        if action == "install":
            app_path = sys.executable if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            final_path = app_path if app_path.startswith('"') else f'"{app_path}"'
            reg.SetValueEx(key, app_name, 0, reg.REG_SZ, final_path)
            reg.FlushKey(key)
        elif action == "remove":
            try: reg.DeleteValue(key, app_name)
            except (FileNotFoundError, OSError): pass
        reg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Failed to manage startup registry: {e}")
        return False

# Lazy-loaded Logger
class Logger(object):
    def __init__(self):
        self.terminal = sys.stdout
        try:
            self.log = open(log_path, "a", encoding='utf-8')
        except:
            self.log = None

    def write(self, message):
        if self.log:
            try:
                self.log.write(message)
                self.log.flush()
            except: pass

    def flush(self):
        if self.log: self.log.flush()

def load_logo():
    from PIL import Image
    logo_path = None
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        logo_path = os.path.join(sys._MEIPASS, 'agent_logo.png')
    else:
        logo_path = os.path.join(application_path, 'agent_logo.png')

    if logo_path and os.path.exists(logo_path):
        try: return Image.open(logo_path)
        except: pass
    return Image.new('RGB', (64, 64), (34, 113, 177))

def print_pdf(content_base64, printer_name):
    import base64
    import tempfile
    import win32print
    
    pdf_data = base64.b64decode(content_base64)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_data)
        temp_path = f.name

    try:
        if platform.system() == "Windows":
            # Attempt SumatraPDF (Premium rendering)
            sumatra_path = os.path.join(application_path, "SumatraPDF.exe")
            if os.path.exists(sumatra_path):
                # Using 'noscale' to prevent extra blank pages on 4x6 labels
                # Using 'fit' for standard reports
                subprocess.run([sumatra_path, "-print-to", printer_name, "-print-settings", "fit,noscale", temp_path], check=True)
            else:
                # Fallback to standard ShellExecute
                win32api.ShellExecute(0, "print", temp_path, f'/d:"{printer_name}"', ".", 0)
    finally:
        try: os.unlink(temp_path)
        except: pass

def print_raw(content_base64, printer_name):
    import base64
    import win32print
    
    # Strip any trailing whitespace or command delimiters that cause blank pages
    raw_data = base64.b64decode(content_base64).strip(b"\r\n\x00 ")
    
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        # RAW mode implies we send control characters directly. 
        # Redundant StartPagePrinter calls often trigger extra form-feeds on thermal printers.
        win32print.StartDocPrinter(hPrinter, 1, ("Cloud Print Job", None, "RAW"))
        try:
            win32print.WritePrinter(hPrinter, raw_data)
        finally:
            win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)

def update_status(icon, message, tooltip=None):
    # This might be called from background thread
    def _update():
        icon.menu = pystray.Menu(
            pystray.MenuItem("Server: " + SERVER_ID, lambda i, item: None, enabled=False),
            pystray.MenuItem("Status: " + message, lambda i, item: None, enabled=False),
            pystray.MenuItem("View Log", on_open_log),
            pystray.MenuItem("Edit Config", on_open_config),
            pystray.MenuItem("Exit", on_exit)
        )
        if tooltip:
            icon.title = f"Cloud Print Agent ({SERVER_ID}) - {tooltip}"
        else:
            icon.title = f"Cloud Print Agent ({SERVER_ID})"
    
    # Actually pystray doesn't need thread-safe menu updates, but good practice
    _update()

def get_printer_properties(printer_name):
    import win32print
    try:
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            # Level 2 has the DevMode structure
            info = win32print.GetPrinter(hPrinter, 2)
            dm = info['pDevMode']
            if dm:
                return {
                    "orientation": "landscape" if dm.Orientation == 2 else "portrait",
                    "paper_size": str(dm.PaperSize),
                    "copies": dm.Copies,
                    "color": "color" if dm.Color == 2 else "monochrome",
                    "duplex": "duplex" if dm.Duplex > 1 else "simplex",
                    "location": info.get('pLocation', ''),
                    "comment": info.get('pComment', '')
                }
        finally:
            win32print.ClosePrinter(hPrinter)
    except:
        pass
    return {}

def run_agent_loop(icon):
    import requests
    import win32print
    import getpass
    
    # 1. Initial Discovery
    try:
        if DEV_MODE:
            discovered_printers = [{
                "uid": "simulated-printer", 
                "name": "Simulated Label Printer", 
                "status": "online",
                "properties": {"orientation": "portrait", "color": "monochrome", "duplex": "simplex"}
            }]
        else:
            printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
            discovered_printers = []
            for p in printers:
                name = p[2]
                props = get_printer_properties(name)
                discovered_printers.append({
                    "uid": name,
                    "name": name,
                    "status": "online",
                    "properties": props
                })

        payload = {"printers": discovered_printers, "server_uid": SERVER_ID, "os_user": getpass.getuser()}
        response = requests.post(f"{API}/api/agent/printers", json=payload, headers=HEADERS, timeout=10)
        if response.status_code == 200: update_status(icon, "Online")
        else: update_status(icon, f"Error {response.status_code}")
    except Exception as e:
        update_status(icon, "Offline")

    # 2. Main Polling Loop
    while icon.visible:
        try:
            response = requests.get(f"{API}/api/agent/jobs", headers=HEADERS, timeout=10)
            if response.status_code == 200:
                update_status(icon, "Online")
                job = response.json()
                if job:
                    icon.notify(f"Printing to {job.get('printer_uid')}", "New Print Job")
                    try:
                        if job.get("format") in ["raw", "zpl"]:
                            print_raw(job["content"], job["printer_uid"])
                        else:
                            print_pdf(job["content"], job["printer_uid"])
                        requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "done"}, headers=HEADERS)
                    except Exception as e:
                        requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "error", "error": str(e)}, headers=HEADERS)
        except: pass
        time.sleep(5)

def on_open_log(icon, item):
    if os.path.exists(log_path): os.startfile(log_path)

def on_open_config(icon, item):
    if os.path.exists(config_file): os.startfile(config_file)

def on_exit(icon, item):
    icon.visible = False
    icon.stop()
    sys.exit(0)

def run():
    global API, LICENSE_KEY, SERVER_ID, HEADERS, AUTO_START, STARTUP_ERROR, DEV_MODE, pystray
    
    # 0. Single Instance Check (Instant!)
    m_name = f"Global\\OdooPrintAgent_v2" # Using V2 to isolate from old slow instances
    mutex = win32event.CreateMutex(None, False, m_name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        sys.exit(0)

    # 1. Deferred Heavy Imports
    import argparse
    import configparser
    import uuid
    import hashlib
    import getpass
    import threading
    import pystray
    
    # 2. Load Config
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        try: config.read(config_file)
        except: pass
    
    API_DEFAULT = config['General'].get('api', "http://localhost:8019") if 'General' in config else "http://localhost:8019"
    LICENSE_KEY_DEFAULT = config['General'].get('license_key', "") if 'General' in config else ""
    SERVER_ID_DEFAULT = config['General'].get('server_id', "") if 'General' in config else ""
    DEV_MODE = config['General'].getboolean('dev_mode', False) if 'General' in config else False
    AUTO_START = config['General'].getboolean('auto_start', True) if 'General' in config else True
    
    # 3. Parse Args
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default=API_DEFAULT)
    parser.add_argument('--license-key', default=LICENSE_KEY_DEFAULT)
    parser.add_argument('--server-id', default=SERVER_ID_DEFAULT)
    parser.add_argument('--dev', action='store_true', default=DEV_MODE)
    args, _ = parser.parse_known_args()
    
    API = args.api
    LICENSE_KEY = args.license_key
    DEV_MODE = args.dev
    
    # 4. Finalize Identity
    if not LICENSE_KEY:
        STARTUP_ERROR = "setup_needed"
        SERVER_ID = "NewSetup"
    else:
        mac = uuid.getnode()
        SERVER_ID = args.server_id or generate_server_id(LICENSE_KEY, mac)
        HEADERS = {"X-License-Key": LICENSE_KEY, "X-Server-ID": SERVER_ID, "X-OS-User": getpass.getuser()}

    # 5. Redirect Logs
    if not os.environ.get('AGENT_CONSOLE_DEBUG'):
        sys.stdout = Logger()
        sys.stderr = sys.stdout

    # 6. Startup Registration
    if platform.system() == "Windows":
        set_run_at_startup("OdooPrintAgent", action="install" if AUTO_START else "remove")

    # 7. Start GUI (Almost Instant)
    icon = pystray.Icon("CloudPrintAgent")
    icon.menu = pystray.Menu(
        pystray.MenuItem("Server: " + SERVER_ID, lambda i, item: None, enabled=False),
        pystray.MenuItem("Status: Initializing...", lambda i, item: None, enabled=False),
        pystray.MenuItem("View Log", on_open_log),
        pystray.MenuItem("Edit Config", on_open_config),
        pystray.MenuItem("Exit", on_exit)
    )
    icon.icon = load_logo()
    icon.title = f"Cloud Printing Agent"
    
    threading.Thread(target=run_agent_loop, args=(icon,), daemon=True).start()
    icon.run()

if __name__ == '__main__':
    run()
