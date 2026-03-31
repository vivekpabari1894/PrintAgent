"""Generate version_info.txt for PyInstaller."""

content = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 1, 0, 0),
    prodvers=(1, 1, 0, 0),
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
        StringStruct(u'FileVersion', u'1.1.0.0'),
        StringStruct(u'InternalName', u'OdooPrintAgent'),
        StringStruct(u'LegalCopyright', u'Copyright 2026 TheERPBot'),
        StringStruct(u'OriginalFilename', u'OdooPrintAgent.exe'),
        StringStruct(u'ProductName', u'Odoo Cloud Print Agent'),
        StringStruct(u'ProductVersion', u'1.1.0.0')
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""

with open('version_info.txt', 'w') as f:
    f.write(content)

print("version_info.txt generated.")
