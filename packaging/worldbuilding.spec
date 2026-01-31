# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Worldbuilding Interactive Program.

Build with:
    pyinstaller worldbuilding.spec

Produces a --onedir bundle in dist/WorldbuildingApp/
"""

import os
import sys

# Project root
ROOT = os.path.dirname(os.path.abspath(SPEC))

# Data files to bundle (source, dest_in_bundle)
datas = [
    (os.path.join(ROOT, 'templates'), 'templates'),
    (os.path.join(ROOT, 'reference-databases'), 'reference-databases'),
    (os.path.join(ROOT, 'app', 'theme'), os.path.join('app', 'theme')),
    (os.path.join(ROOT, 'app', 'resources'), os.path.join('app', 'resources')),
    (os.path.join(ROOT, 'engine', '*.json'), 'engine'),
    (os.path.join(ROOT, 'generation'), 'generation'),
    (os.path.join(ROOT, 'VERSION'), '.'),
]

# Filter out non-existent paths (skip glob patterns from filtering)
import glob as _glob
_filtered = []
for src, dst in datas:
    if '*' in src:
        if _glob.glob(src):
            _filtered.append((src, dst))
    elif os.path.exists(src):
        _filtered.append((src, dst))
datas = _filtered

# Hidden imports that PyInstaller may miss
hiddenimports = [
    'app.panels.chat_panel',
    'app.panels.entity_browser',
    'app.panels.entity_detail',
    'app.panels.knowledge_graph',
    'app.panels.option_comparison',
    'app.panels.progress_sidebar',
    'app.services.agent_worker',
    'app.services.claude_client',
    'app.services.context_builder',
    'app.services.enforcement',
    'app.services.event_bus',
    'app.services.prompt_builder',
    'app.services.retry_manager',
    'app.services.session_manager',
    'app.services.state_store',
    'app.services.tools',
    'app.services.update_checker',
    'app.services.validation_pipeline',
    'app.widgets.entity_form',
    'app.widgets.loading_overlay',
    'app.widgets.option_card',
    'app.widgets.toast',
    'app.widgets.welcome_dialog',
    'engine.engine_manager',
    'engine.utils',
    'engine.models.base',
    'engine.models.factory',
    'engine.models.validators',
    'pydantic',
    'networkx',
    'platformdirs',
    'qasync',
    'anthropic',
]

# Qt modules to exclude (reduce size)
excludes = [
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DRender',
    'PySide6.QtBluetooth',
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtQuick',
    'PySide6.QtQuickControls2',
    'PySide6.QtQuickWidgets',
    'PySide6.QtRemoteObjects',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtSql',
    'PySide6.QtTest',
    'PySide6.QtTextToSpeech',
    'PySide6.QtWebChannel',
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebSockets',
    'PySide6.QtXml',
    'matplotlib',
    'numpy',
    'scipy',
    'PIL',
    'tkinter',
]

a = Analysis(
    [os.path.join(ROOT, 'app', 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WorldbuildingApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=os.path.join(ROOT, 'app', 'resources', 'icon.ico')
    if os.path.exists(os.path.join(ROOT, 'app', 'resources', 'icon.ico'))
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WorldbuildingApp',
)
