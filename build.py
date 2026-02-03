"""
Build script for Workwise Desktop Agent
macOS-specific build with proper tkinter support
"""

import PyInstaller.__main__
import customtkinter
import os
import platform
import shutil
import sys

# Get paths
ctk_path = os.path.dirname(customtkinter.__file__)
sep = ';' if platform.system() == 'Windows' else ':'
is_mac = platform.system() == 'Darwin'

print("🚀 Building Workwise Agent...")
print(f"📦 Platform: {platform.system()}")
print(f"📦 Python: {sys.version}")

# Ensure sync_config.json exists
if not os.path.exists("sync_config.json"):
    print("❌ ERROR: sync_config.json not found!")
    exit(1)

# Clean previous builds
for d in ["dist", "build"]:
    if os.path.exists(d):
        shutil.rmtree(d)

args = [
    'main.py',
    '--name=WorkwiseAgent',
    '--onedir',  # Directory mode for proper bundle
    '--windowed',  # No console
    f'--add-data={ctk_path}{sep}customtkinter/',
    f'--add-data=sync_config.json{sep}.',
    '--clean',
    '--noconfirm',
    # Explicitly collect tkinter and PIL
    '--hidden-import=PIL._tkinter_finder',
    '--hidden-import=PIL._imagingtk',
    '--hidden-import=PIL.ImageTk',
    '--collect-all=customtkinter',
    '--collect-all=darkdetect',
]

if is_mac:
    # macOS specific: Bundle icon (if you had one)
    # args.append('--icon=icon.icns')
    pass

print("\n🔨 Running PyInstaller...")
PyInstaller.__main__.run(args)

print("\n" + "="*60)
print("✅ BUILD COMPLETE!")
print("="*60)

if is_mac:
    print("\n🍎 Your app: dist/WorkwiseAgent.app")
    print("\n📝 To test:")
    print("   ./dist/WorkwiseAgent.app/Contents/MacOS/WorkwiseAgent")
    print("\n📤 To distribute:")
    print("   zip -r WorkwiseAgent.zip dist/WorkwiseAgent.app")
else:
    print("\n🪟 Your app: dist/WorkwiseAgent/WorkwiseAgent.exe")
