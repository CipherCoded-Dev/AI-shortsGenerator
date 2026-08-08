import os
import shutil
import urllib.request
import zipfile

URL = "https://github.com/GyanD/codexffmpeg/releases/download/7.0.2/ffmpeg-7.0.2-essentials_build.zip"
ZIP_NAME = "ffmpeg.zip"
TARGET_DIR = os.path.dirname(os.path.abspath(__file__))

print("1. Downloading FFmpeg binary package (this may take 15-30 seconds)...")
urllib.request.urlretrieve(URL, ZIP_NAME)

print("2. Extracting ffmpeg.exe and ffprobe.exe...")
with zipfile.ZipFile(ZIP_NAME, "r") as z:
    for file in z.namelist():
        if file.endswith("ffmpeg.exe") or file.endswith("ffprobe.exe"):
            filename = os.path.basename(file)
            source = z.open(file)
            target_path = os.path.join(TARGET_DIR, filename)
            with open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
            print(f"   -> Extracted {filename} to {target_path}")

print("3. Cleaning up download archive...")
if os.path.exists(ZIP_NAME):
    os.remove(ZIP_NAME)

print("\nSUCCESS! FFmpeg executables are now in your backend folder.")