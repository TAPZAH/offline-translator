# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets")]
binaries = []
hiddenimports = [
    "pystray._util.win32",
    "PIL._tkinter_finder",
    "portable_env",
    "autostart",
    "language_detect",
    "language_packages",
    "languages_window",
    "selection_button",
    "firefox_engine",
    "argos_engine",
    "argos_packages",
    "nllb_engine",
    "nllb_packages",
    "app_settings",
    "packages",
    "settings_window",
    "translation_engine",
    "translation_result",
    "fxtranslate",
    "fxtranslate._engine",
    "zstandard",
    "pyperclip",
    "requests",
    "packaging",
    "sentencepiece",
]

for package_name in (
    "fxtranslate",
    "langdetect",
    "pystray",
    "zstandard",
    "requests",
    "certifi",
    "argostranslate",
    "ctranslate2",
    "sentencepiece",
    "packaging",
    "stanza",
    "torch",
):
    collected_datas, collected_binaries, collected_hidden = collect_all(package_name)
    datas += collected_datas
    binaries += collected_binaries
    hiddenimports += collected_hidden

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "unittest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OfflineTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OfflineTranslator",
)
