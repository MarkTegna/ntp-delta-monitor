# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec file for NTP Delta Monitor
Creates a single executable file with all dependencies included
"""

import sys
from pathlib import Path

# Define the main script path
main_script = 'ntp_monitor.py'

# Analysis configuration
a = Analysis(
    [main_script],
    pathex=[],
    binaries=[],
    datas=[
        # Include the INI configuration file
        ('ntp_monitor.ini', '.'),
        # Include the sample configuration file for reference
        ('ntp_monitor_sample.ini', '.'),
        # Include documentation files
        ('README.md', '.'),
        ('INSTALL.md', '.'),
        ('EXAMPLES.md', '.'),
        ('DEPLOYMENT.md', '.'),
    ],
    hiddenimports=[
        # Core NTP and networking libraries
        'ntplib',
        'dns.resolver',
        'dns.reversename',
        'dns.rdatatype',
        'dns.rdataclass',
        'dns.name',
        'dns.query',
        'dns.message',
        'dns.exception',
        'dns.inet',
        'dns.rdata',
        'dns.rrset',
        'dns.rdtypes',
        'dns.rdtypes.IN',
        'dns.rdtypes.IN.A',
        'dns.rdtypes.ANY',
        'dns.rdtypes.ANY.CNAME',
        
        # Excel/XLSX support
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.styles.fonts',
        'openpyxl.styles.fills',
        'openpyxl.styles.colors',
        'openpyxl.styles.alignment',
        'openpyxl.styles.borders',
        'openpyxl.styles.numbers',
        'openpyxl.styles.protection',
        'openpyxl.styles.differential',
        'openpyxl.utils',
        'openpyxl.utils.cell',
        'openpyxl.workbook',
        'openpyxl.worksheet',
        'openpyxl.cell',
        'openpyxl.formatting',
        'openpyxl.formatting.rule',
        'openpyxl.formatting.formatting',
        'et_xmlfile',
        'et_xmlfile.xmlfile',
        
        # Standard library modules that might be missed
        'socket',
        'csv',
        'logging',
        'argparse',
        'pathlib',
        'datetime',
        'statistics',
        'concurrent.futures',
        'threading',
        'dataclasses',
        'enum',
        'sys',
        'typing',
        
        # DNS resolver dependencies
        'dns.resolver',
        'dns.reversename',
        'dns.tsig',
        'dns.update',
        'dns.zone',
        'dns.zonefile',
        
        # Additional DNS modules that may be dynamically imported
        'dns.dnssec',
        'dns.entropy',
        'dns.flags',
        'dns.grange',
        'dns.namedict',
        'dns.node',
        'dns.opcode',
        'dns.rcode',
        'dns.renderer',
        'dns.tokenizer',
        'dns.ttl',
        'dns.version',
        'dns.wire',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'wx',
        'tornado',
        'flask',
        'django',
        'requests',
        'urllib3',
        'certifi',
        'charset_normalizer',
        'idna',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# PYZ (Python ZIP) configuration
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# EXE (executable) configuration
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ntp_monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=None,
    icon=None,
)

# Optional: Create a COLLECT for debugging (creates directory with all files)
# Uncomment the following lines if you need to debug the packaging
# coll = COLLECT(
#     exe,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     strip=False,
#     upx=True,
#     upx_exclude=[],
#     name='ntp_monitor_debug'
# )