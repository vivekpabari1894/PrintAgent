import subprocess
import os
import sys
import shutil

# 1. Import version directly from agent source
try:
    from agent import AGENT_VERSION
except ImportError:
    print("Error: Could not find agent.py in current directory.")
    sys.exit(1)

def generate_version_info():
    """Update gen_version_info.py content to match AGENT_VERSION and run it."""
    v_parts = AGENT_VERSION.split('.')
    while len(v_parts) < 4:
        v_parts.append('0')
    v_tuple = ", ".join(v_parts)
    v_str = ".".join(v_parts)

    content = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({v_tuple}),
    prodvers=({v_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040904B0', [
        StringStruct(u'CompanyName', u'TheERPBot'),
        StringStruct(u'FileDescription', u'Odoo Cloud Print Agent'),
        StringStruct(u'FileVersion', u'{v_str}'),
        StringStruct(u'InternalName', u'OdooPrintAgent'),
        StringStruct(u'LegalCopyright', u'Copyright 2026 TheERPBot'),
        StringStruct(u'OriginalFilename', u'OdooPrintAgent_v{AGENT_VERSION}.exe'),
        StringStruct(u'ProductName', u'Odoo Cloud Print Agent'),
        StringStruct(u'ProductVersion', u'{v_str}')
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    with open('version_info.txt', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated version_info.txt to v{v_str}")

def run_build():
    print(f"--- Starting Build for Odoo Print Agent v{AGENT_VERSION} ---")
    
    # Generate fresh version metadata
    generate_version_info()
    
    # Output file settings
    exe_name = f"OdooPrintAgent_v{AGENT_VERSION}"
    
    # Build command
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--icon=agent_icon.ico",
        f"--name={exe_name}",
        "--add-data=agent_logo.png;.", # Note: ; for Windows, : for Linux
        "--version-file=version_info.txt",
        "agent.py"
    ]
    
    # Check if SumatraPDF exists to bundle it
    if os.path.exists("SumatraPDF.exe"):
        cmd.insert(cmd.index("agent.py"), "--add-data=SumatraPDF.exe;.")
        print("Found SumatraPDF.exe - including in bundle.")
    else:
        print("WARNING: SumatraPDF.exe not found. Build will proceed but agent will require local SumatraPDF installation.")

    print(f"Executing: {' '.join(cmd)}")
    subprocess.run(cmd, shell=True)
    
    print("\n--- Build Complete ---")
    print(f"Target: dist/{exe_name}.exe")

if __name__ == "__main__":
    run_build()
