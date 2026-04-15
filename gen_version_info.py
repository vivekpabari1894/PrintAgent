"""Generate version_info.txt for PyInstaller dynamically from agent source."""
import os
import sys

# 1. Import version from agent source
try:
    with open('agent.py', 'r', encoding='utf-8') as f:
        # Simple extraction to avoid executing code or complex imports
        lines = f.readlines()
        version = "1.0.0"
        for line in lines:
            if 'AGENT_VERSION =' in line:
                version = line.split('"')[1]
                break
except Exception as e:
    print(f"Error reading version: {e}")
    version = "1.0.0"

# Convert to Windows tuple format (e.g. 1.0.5.0)
v_parts = version.split('.')
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
        StringStruct(u'OriginalFilename', u'OdooPrintAgent_v{version}.exe'),
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

print(f"version_info.txt generated for v{v_str}")
