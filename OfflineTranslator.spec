# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# torch/stanza/spacy не нужны: Argos переводит через CTranslate2.
SKIP_PREFIXES = (
    "torch",
    "stanza",
    "spacy",
    "torchvision",
    "torchaudio",
    "nvidia",
    "cv2",
    "sklearn",
)


def _skipped_name(name: str) -> bool:
    root = str(name).replace("\\", "/").split("/")[-1]
    root = root.split(".")[0].lower()
    lowered = str(name).replace("\\", "/").lower()
    for skip in SKIP_PREFIXES:
        if root == skip or lowered.startswith(skip + ".") or f"/{skip}/" in f"/{lowered}/":
            return True
        if f"\\{skip}\\" in str(name).lower():
            return True
    return False


def _keep_tuple(item) -> bool:
    source = item[0] if isinstance(item, (tuple, list)) else item
    return not _skipped_name(str(source))


datas = [("assets", "assets")]
binaries = []
hiddenimports = [
    "pystray._util.win32",
    "PIL._tkinter_finder",
    "PIL.ImageTk",
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
    "marian_engine",
    "marian_packages",
    "app_settings",
    "packages",
    "settings_window",
    "translation_engine",
    "translation_result",
    "threaded_engine",
    "translation_route",
    "app_logging",
    "app_version",
    "fxtranslate",
    "fxtranslate._engine",
    "zstandard",
    "pyperclip",
    "requests",
    "packaging",
    "sentencepiece",
    "six",
    "numpy",
    "yaml",
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
    "numpy",
    "yaml",
    "six",
):
    collected_datas, collected_binaries, collected_hidden = collect_all(package_name)
    datas += [item for item in collected_datas if _keep_tuple(item)]
    binaries += [item for item in collected_binaries if _keep_tuple(item)]
    hiddenimports += [name for name in collected_hidden if not _skipped_name(name)]

hiddenimports = [name for name in hiddenimports if not _skipped_name(name)]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "unittest",
        "torch",
        "stanza",
        "spacy",
        "torchvision",
        "torchaudio",
    ],
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
