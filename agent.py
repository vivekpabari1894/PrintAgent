import time
import platform
import subprocess
import os
import ctypes
import sys
import hashlib
import base64
import tempfile
import argparse
import configparser
import uuid
import getpass
import threading
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler

# Windows Specific Imports
import win32event
import win32api
import winerror
import winreg as reg
import win32print

# Third Party
import requests
import pystray
from PIL import Image
import shutil

# Global variables (initialized in run())
API = ""
LICENSE_KEY = ""
SERVER_ID = ""
AUTO_START = True
HEADERS = {}
AGENT_VERSION = "1.0.7"
STARTUP_ERROR = None
DEV_MODE = False
DC_PAPERS       = 2
DC_PAPERSIZE    = 3
DC_PAPERNAMES   = 16
DC_BINNAMES     = 12
DC_BINS         = 6
DC_COLORDEVICE  = 32
# Application Paths (Safe placeholders)
application_path = ""
config_file = ""
log_path = ""

def init_paths():
    global application_path, config_file, log_path
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(application_path, 'agent.ini')
    log_path = os.path.join(application_path, 'agent.log')

def generate_server_id(license_key, mac):
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
        logger.info(f"Failed to manage startup registry: {e}")
        return False

# Proper Logging Setup
logger = logging.getLogger("PrintAgent")
logger.setLevel(logging.INFO)

class StdoutToLogger(object):
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
    def write(self, message):
        if message.rstrip():
            self.logger.log(self.level, message.rstrip())
    def flush(self):
        pass

def setup_logging():
    global log_path
    if not log_path: return
    
    # Standardized format with fixed-width columns for better alignment
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s')
    
    # Rotation: Daily at midnight, keep 7 days
    handler = TimedRotatingFileHandler(log_path, when='midnight', interval=1, backupCount=7, encoding='utf-8')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    # Also log to console if not redirected
    # console_handler = logging.StreamHandler(sys.stdout)
    # console_handler.setFormatter(formatter)
    # logger.addHandler(console_handler) 

    # Redirect stdout/stderr so logger.info() calls go to log file
    sys.stdout = StdoutToLogger(logger, logging.INFO)
    sys.stderr = StdoutToLogger(logger, logging.ERROR)

def load_logo():
    logo_path = None
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        logo_path = os.path.join(sys._MEIPASS, 'agent_logo.png')
    else:
        logo_path = os.path.join(application_path, 'agent_logo.png')

    if logo_path and os.path.exists(logo_path):
        try: return Image.open(logo_path)
        except: pass
    return Image.new('RGB', (64, 64), (34, 113, 177))

def print_pdf(content_base64, printer_name, orientation='portrait', color_mode=None, duplex_mode=None, paper_size=None, bin_name=None):
    pdf_data = base64.b64decode(content_base64)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_data)
        temp_path = f.name

    try:
        logger.info(f"Starting print job for printer: {printer_name}")
        if platform.system() == "Windows":
            # Smart Discovery for SumatraPDF
            sumatra_path = None
            search_locations = []
            
            # 1. Check if bundled inside PyInstaller EXE (_MEIPASS)
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                search_locations.append(os.path.join(sys._MEIPASS, "SumatraPDF.exe"))
                
            # 2. Check locally next to the EXE
            search_locations.append(os.path.join(application_path, "SumatraPDF.exe"))
            
            # 3. Check System PATH
            sys_exe = shutil.which("SumatraPDF.exe")
            if sys_exe: search_locations.append(sys_exe)
            
            # 4. Common Program Files
            search_locations.extend([
                r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
                r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe"
            ])

            for p in search_locations:
                if p and os.path.exists(p):
                    sumatra_path = p
                    break

            if sumatra_path:
                # Build settings string based on orientation and other preferences
                settings_list = ["fit", "noscale", orientation]
                if color_mode: settings_list.append(color_mode)
                if duplex_mode: 
                    sd_duplex = "duplexlong" if duplex_mode == "duplex" else "simplex"
                    settings_list.append(sd_duplex)
                if paper_size: settings_list.append(f"paper={paper_size}")
                if bin_name: settings_list.append(f"bin={bin_name}")
                
                settings = ",".join(settings_list)
                logger.info(f"Executing SumatraPDF ({sumatra_path}): -print-to \"{printer_name}\" -print-settings \"{settings}\"")
                subprocess.run([sumatra_path, "-print-to", printer_name, "-print-settings", settings, temp_path], check=True)
                logger.info("Job successfully sent to SumatraPDF")
            else:
                logger.warning("SumatraPDF not found in bundle, local dir or PATH. Falling back to ShellExecute (Simple Printing).")
                win32api.ShellExecute(0, "print", temp_path, f'/d:"{printer_name}"', ".", 0)
                logger.info("Job sent via ShellExecute")
    except Exception as e:
        logger.error(f"ERROR in print_pdf: {e}")
        raise e
    finally:
        try: os.unlink(temp_path)
        except: pass

def print_raw(content_base64, printer_name):
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
            icon.title = f"Cloud Print Agent v{AGENT_VERSION} ({SERVER_ID}) - {tooltip}"
        else:
            icon.title = f"Cloud Print Agent v{AGENT_VERSION} ({SERVER_ID})"
    
    # Actually pystray doesn't need thread-safe menu updates, but good practice
    _update()

def get_printer_properties(printer_name):
    try:
        logger.info(f"Scanning capabilities for printer: {printer_name}")
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            # 1. Get Basic Info & Current Defaults
            info = win32print.GetPrinter(hPrinter, 2)
            dm = info['pDevMode']

            # Map Windows spooler status bitmask to a human-readable status
            raw_status = info.get('Status', 0)
            if raw_status & 0x00000080:       # PRINTER_STATUS_OFFLINE
                hw_status = 'offline'
            elif raw_status & 0x00000002:      # PRINTER_STATUS_ERROR
                hw_status = 'error'
            elif raw_status & 0x00000008:      # PRINTER_STATUS_PAPER_JAM
                hw_status = 'error'
            elif raw_status & 0x00000010:      # PRINTER_STATUS_PAPER_OUT
                hw_status = 'error'
            elif raw_status & 0x00100000:      # PRINTER_STATUS_USER_INTERVENTION
                hw_status = 'error'
            elif raw_status & 0x00000001:      # PRINTER_STATUS_PAUSED
                hw_status = 'paused'
            elif raw_status & 0x00000400:      # PRINTER_STATUS_PRINTING
                hw_status = 'printing'
            elif raw_status == 0:
                hw_status = 'online'
            else:
                hw_status = 'online'
            logger.info(f"  - Windows Status Bitmask: {raw_status} -> {hw_status}")

            res = {
                "orientation": "portrait",
                "paper_size": "unknown",
                "copies": 1,
                "color": "monochrome",
                "duplex": "simplex",
                "location": info.get('pLocation', ''),
                "comment": info.get('pComment', ''),
                "has_color": False,
                "supported_papers": [],
                "supported_bins": [],
                "hw_status": hw_status
            }
            if dm:
                res.update({
                    "orientation": "landscape" if dm.Orientation == 2 else "portrait",
                    "paper_size": str(dm.PaperSize),
                    "copies": dm.Copies,
                    "color": "color" if dm.Color == 2 else "monochrome",
                    "duplex": "duplex" if dm.Duplex > 1 else "simplex",
                })
            
            logger.info(f"  - Defaults: {res['orientation']}, {res['color']}, {res['duplex']}")

            # 2. Scan Device Capabilities (The "Menu" of options)
            # DC_COLORDEVICE returns 1 if hardware supports color
            try:
                result = win32print.DeviceCapabilities(printer_name, "", DC_COLORDEVICE)
                res["has_color"] = result > 0
            except Exception as e:
                # Label printers (Zebra, DYMO) don't support this call — expected
                res["has_color"] = False
                if "too small" not in str(e).lower():
                    logger.warning(f"  - Failed to scan color support: {e}")

            # DC_PAPERNAMES returns a list of supported paper names
            try:
                papers = win32print.DeviceCapabilities(printer_name, "", DC_PAPERNAMES)
                if papers:
                    # Clean up strings (they are often null-padded)
                    res["supported_papers"] = [p.strip("\x00") for p in papers if p.strip("\x00")]
                logger.info(f"  - Found {len(res['supported_papers'])} Paper Sizes: {', '.join(res['supported_papers'][:3])}...")
            except Exception as e:
                logger.warning(f"  - Failed to scan paper sizes: {e}")

            # DC_BINNAMES returns a list of supported input bins
            try:
                bins = win32print.DeviceCapabilities(printer_name, "", DC_BINNAMES)
                if bins:
                    res["supported_bins"] = [b.strip("\x00") for b in bins if b.strip("\x00")]
                logger.info(f"  - Found {len(res['supported_bins'])} Input Trays: {', '.join(res['supported_bins'])}")
            except Exception as e:
                logger.warning(f"  - Failed to scan input trays: {e}")

            return res

        finally:
            win32print.ClosePrinter(hPrinter)
    except Exception as e:
        logger.error(f"ERROR scanning properties for {printer_name}: {e}")
    return {}

import traceback

def get_all_presets(printer_name):
    """Get ALL available presets/paper sizes/bins for a printer"""
    presets = []
    try:
        logger.info(f"  - Debug: Beginning preset scan for {printer_name}")
        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            # Get paper names + sizes + bins
            # Using try/except for each capability as some drivers fail on certain queries
            paper_names = paper_sizes = paper_dims = bin_names = bin_ids = []
            
            try: paper_names = win32print.DeviceCapabilities(printer_name, "", DC_PAPERNAMES)
            except: logger.warning(f"    - Driver failed to provide paper names")
            
            try: paper_sizes = win32print.DeviceCapabilities(printer_name, "", DC_PAPERS)
            except: pass
            
            try: paper_dims = win32print.DeviceCapabilities(printer_name, "", DC_PAPERSIZE)
            except: pass
            
            try: bin_names = win32print.DeviceCapabilities(printer_name, "", DC_BINNAMES)
            except: logger.warning(f"    - Driver failed to provide bin names")
            
            try: bin_ids = win32print.DeviceCapabilities(printer_name, "", DC_BINS)
            except: pass

            # Build paper presets
            if paper_names:
                p_names_cnt = len(paper_names) if paper_names else 0
                p_sizes_cnt = len(paper_sizes) if paper_sizes else 0
                p_dims_cnt = len(paper_dims) if paper_dims else 0
                
                for i in range(p_names_cnt):
                    try:
                        name = paper_names[i]
                        clean_name = name.strip("\x00").strip()
                        if not clean_name:
                            continue
                            
                        # Safely get size code and dimensions
                        code = paper_sizes[i] if i < p_sizes_cnt else 0
                        width_mm = round(paper_dims[i][0] / 10, 1) if (i < p_dims_cnt and paper_dims[i]) else 0
                        height_mm = round(paper_dims[i][1] / 10, 1) if (i < p_dims_cnt and paper_dims[i]) else 0
                        
                        presets.append({
                            "printer_name" : printer_name,
                            "preset_type"  : "paper",
                            "name"         : clean_name,
                            "code"         : code,
                            "width_mm"     : width_mm,
                            "height_mm"    : height_mm,
                            "bin_name"     : None,
                            "bin_id"       : None,
                        })
                    except: continue

            # Build bin/tray presets
            if bin_names:
                b_names_cnt = len(bin_names) if bin_names else 0
                b_ids_cnt = len(bin_ids) if bin_ids else 0
                
                for i in range(b_names_cnt):
                    try:
                        name = bin_names[i]
                        clean_name = name.strip("\x00").strip()
                        if not clean_name:
                            continue
                            
                        # Safely get bin ID
                        code = bin_ids[i] if i < b_ids_cnt else 0
                        
                        presets.append({
                            "printer_name" : printer_name,
                            "preset_type"  : "bin",
                            "name"         : clean_name,
                            "code"         : code,
                            "width_mm"     : None,
                            "height_mm"    : None,
                            "bin_name"     : clean_name,
                            "bin_id"       : code,
                        })
                    except: continue

            logger.info(f"  - Collected {len(presets)} presets for {printer_name}")
        finally:
            win32print.ClosePrinter(hPrinter)

    except Exception as e:
        logger.error(f"ERROR collecting presets for {printer_name}: {e}")
        logger.error(traceback.format_exc())

    return presets

def upload_logs(line_count=100):
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.splitlines()
                
                # Fetch specified number of lines, or 0 for full log
                target_lines = lines if line_count == 0 else lines[-abs(line_count):]
                
                header = f"--- REMOTE LOG DUMP (Server: {SERVER_ID}, Version: {AGENT_VERSION}) ---\n"
                header += f"--- Range: {'Full Log' if line_count == 0 else f'Last {len(target_lines)} lines'} ---\n\n"
                
                summary = header + "\n".join(target_lines)
                requests.post(f"{API}/api/agent/upload_logs", json={"logs": summary}, headers=HEADERS, timeout=60)
    except Exception as e:
        logger.error(f"Failed to upload logs: {e}")


def sync_printers(icon=None):
    try:
        logger.info(f"Starting printer discovery (Server: {SERVER_ID}, API: {API})...")
        if DEV_MODE:
            logger.info("Running in Simulation mode")
            discovered_printers = [{
                "uid": "simulated-printer", 
                "name": "Simulated Label Printer", 
                "status": "online",
                "properties": {
                    "orientation": "portrait", 
                    "color": "monochrome", 
                    "duplex": "simplex",
                    "has_color": False,
                    "supported_papers": ["A4", "A5", "Letter"],
                    "supported_bins": ["Manual Feed", "Tray 1"]
                }
            }]
        else:
            printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
            logger.info(f"Found {len(printers)} printers in Windows spooler")
            discovered_printers = []

            # Filter out virtual/software printers that can't physically print
            virtual_kw = ['pdf', 'microsoft print', 'onenote', 'xps', 'fax',
                          'send to', 'one note', 'document writer', 'adobe pdf']

            for p in printers:
                name = p[2]
                if any(kw in name.lower() for kw in virtual_kw):
                    logger.info(f"  - Skipping virtual printer: {name}")
                    continue
                props = get_printer_properties(name)
                presets = get_all_presets(name)
                # Use real Windows spooler status from properties
                real_status = props.get('hw_status', 'online')
                discovered_printers.append({
                    "uid": name,
                    "name": name,
                    "status": real_status,
                    "properties": props,
                    "presets": presets
                })

        payload = {"printers": discovered_printers, "server_uid": SERVER_ID, "os_user": getpass.getuser()}
        logger.info(f"Reporting {len(discovered_printers)} printers to SaaS...")
        response = requests.post(f"{API}/api/agent/printers", json=payload, headers=HEADERS, timeout=60)
        if response.status_code == 200: 
            logger.info("Successfully reported printers to SaaS")
            if icon:
                update_status(icon, "Online")
        else: 
            logger.error(f"Failed to report printers: HTTP {response.status_code} - {response.text}")
            if icon:
                update_status(icon, f"Error {response.status_code}")
    except Exception as e:
        logger.critical(f"CRITICAL ERROR in printer discovery: {e}")
        if icon:
            update_status(icon, "Offline")

def run_agent_loop(icon):
    # 1. Initial Discovery
    sync_printers(icon)

    # 2. Long-Poll Loop (replaces the 5s polling)
    logger.info("Entering long-poll loop (server holds connection for ~25s per cycle)")
    error_backoff = 1  # Start with 1s backoff on errors
    while icon.visible:
        try:
            # Long-poll: server holds this request for up to 25 seconds
            # Timeout is 35s to allow 25s server hold + 10s network buffer
            response = requests.get(f"{API}/api/agent/poll", headers=HEADERS, timeout=35)

            if response.status_code == 200:
                update_status(icon, "Online")
                error_backoff = 1  # Reset backoff on success
                data = response.json()

                if data:
                    # Check for remote log request
                    if data.get('send_logs'):
                        lines_to_get = data.get('log_lines', 100)
                        threading.Thread(target=upload_logs, args=(lines_to_get,), daemon=True).start()

                    # Check for printer sync request
                    if data.get('sync_printers'):
                        threading.Thread(target=sync_printers, args=(icon,), daemon=True).start()

                    # Process print job if present
                    if data.get('job_id'):
                        job = data
                        logger.info(f"New job received: {job.get('job_id')} for {job.get('printer_uid')}")
                        icon.notify(f"Printing to {job.get('printer_uid')}", "New Print Job")
                        
                        copies = job.get('copies', 1)
                        if copies < 1: copies = 1
                        
                        try:
                            for i in range(copies):
                                if copies > 1:
                                    logger.info(f"Printing copy {i+1} of {copies}...")
                                    
                                if job.get("format") in ["raw", "zpl"]:
                                    logger.info(f"Processing RAW/ZPL job...")
                                    print_raw(job["content"], job["printer_uid"])
                                else:
                                    logger.info(f"Processing PDF job: Orientation={job.get('orientation')}, Bin={job.get('bin_name')}")
                                    print_pdf(
                                        job["content"], 
                                        job["printer_uid"], 
                                        orientation=job.get("orientation", "portrait"),
                                        color_mode=job.get("color_mode"),
                                        duplex_mode=job.get("duplex_mode"),
                                        paper_size=job.get("paper_size"),
                                        bin_name=job.get("bin_name")
                                    )
                            
                            requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "done"}, headers=HEADERS)
                            logger.info(f"Job {job.get('job_id')} completed ({copies} copies) and reported")
                        except Exception as e:
                            logger.error(f"Job execution failed: {e}")
                            requests.post(f"{API}/api/jobs/status", json={"job_id": job["job_id"], "status": "error", "error": str(e)}, headers=HEADERS)

                # No sleep needed — the long-poll itself IS the wait
                # Reconnect immediately for the next cycle

            elif response.status_code != 204:
                logger.warning(f"Unexpected poll response: HTTP {response.status_code}")
                time.sleep(error_backoff)

        except requests.exceptions.Timeout:
            # Server didn't respond within 35s — normal, just reconnect
            logger.debug("Long-poll timeout, reconnecting...")
        except requests.exceptions.ConnectionError:
            logger.error(f"Connection lost. Retrying in {error_backoff}s...")
            update_status(icon, "Offline")
            time.sleep(error_backoff)
            error_backoff = min(error_backoff * 2, 30)  # Max 30s backoff
        except Exception as e:
            logger.error(f"Poll error: {e}")
            time.sleep(error_backoff)
            error_backoff = min(error_backoff * 2, 30)

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
    m_name = f"Global\\OdooPrintAgent_v2" 
    mutex = win32event.CreateMutex(None, False, m_name)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        sys.exit(0)

    init_paths()

    # 1. Load Config
    config = configparser.ConfigParser()
    if os.path.exists(config_file):
        try: config.read(config_file)
        except: pass
    
    API_DEFAULT = config['General'].get('api', "http://localhost:8019") if 'General' in config else "http://localhost:8019"
    LICENSE_KEY_DEFAULT = config['General'].get('license_key', "") if 'General' in config else ""
    SERVER_ID_DEFAULT = config['General'].get('server_id', "") if 'General' in config else ""
    DEV_MODE = config['General'].getboolean('dev_mode', False) if 'General' in config else False
    AUTO_START = config['General'].getboolean('auto_start', True) if 'General' in config else True
    
    # 2. Parse Args
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default=API_DEFAULT)
    parser.add_argument('--license-key', default=LICENSE_KEY_DEFAULT)
    parser.add_argument('--server-id', default=SERVER_ID_DEFAULT)
    parser.add_argument('--dev', action='store_true', default=DEV_MODE)
    args, _ = parser.parse_known_args()
    
    API = args.api
    LICENSE_KEY = args.license_key
    DEV_MODE = args.dev
    
    # 3. Finalize Identity
    if not LICENSE_KEY:
        STARTUP_ERROR = "setup_needed"
        SERVER_ID = "NewSetup"
    else:
        mac = uuid.getnode()
        SERVER_ID = args.server_id or generate_server_id(LICENSE_KEY, mac)
        
        global HEADERS
        HEADERS = {
            "X-License-Key": LICENSE_KEY, 
            "X-Server-ID": SERVER_ID, 
            "X-Agent-Version": AGENT_VERSION,
            "X-OS-User": getpass.getuser()
        }

    # 4. Redirect Logs & Rotation
    if not os.environ.get('AGENT_CONSOLE_DEBUG'):
        setup_logging()
        logger.info("--- Print Agent Started ---")
        logger.info(f"App Path: {application_path}")
        logger.info(f"OS: {platform.system()} {platform.version()}")
        logger.info(f"User: {getpass.getuser()}")
    else:
        logger.info("Skipping file logging (AGENT_CONSOLE_DEBUG is set)")

    # 5. Startup Registration
    if platform.system() == "Windows":
        set_run_at_startup("OdooPrintAgent", action="install" if AUTO_START else "remove")

    # 6. Start GUI (Almost Instant)
    icon = pystray.Icon("CloudPrintAgent")
    icon.menu = pystray.Menu(
        pystray.MenuItem(f"Version: {AGENT_VERSION}", lambda i, item: None, enabled=False),
        pystray.MenuItem("Server: " + SERVER_ID, lambda i, item: None, enabled=False),
        pystray.MenuItem("Status: Initializing...", lambda i, item: None, enabled=False),
        pystray.MenuItem("View Log", on_open_log),
        pystray.MenuItem("Edit Config", on_open_config),
        pystray.MenuItem("Exit", on_exit)
    )
    icon.icon = load_logo()
    icon.title = f"Cloud Print Agent v{AGENT_VERSION} ({SERVER_ID})"

    # Surface startup errors immediately instead of silently failing
    if STARTUP_ERROR == "setup_needed":
        logger.warning("No license key configured. Agent will not connect.")
        def _show_setup_error(i):
            time.sleep(2)  # Wait for tray icon to be visible
            update_status(i, "No License Key", tooltip="Setup Required - Edit agent.ini")
            i.notify("License key missing. Right-click tray icon > Edit Config to set up.", "Setup Required")
        threading.Thread(target=_show_setup_error, args=(icon,), daemon=True).start()
    else:
        threading.Thread(target=run_agent_loop, args=(icon,), daemon=True).start()
    icon.run()

if __name__ == '__main__':
    run()
