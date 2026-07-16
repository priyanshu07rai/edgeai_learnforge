import os
import urllib.request
import json
import sys

# Fetch latest release info from GitHub API
api_url = "https://api.github.com/repos/ollama/ollama/releases/latest"
print("Fetching latest Ollama release info...")
try:
    req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response:
        release_info = json.loads(response.read().decode())
except Exception as e:
    print(f"Error fetching release: {e}")
    sys.exit(1)

tag = release_info['tag_name']
print(f"Latest Ollama Release: {tag}")

# Find standard arm64 asset (lightweight, ~100MB) to save disk space
download_url = None
asset_name = None
for asset in release_info['assets']:
    name = asset['name']
    if "arm64" in name and name.endswith(".tar.zst") and "jetpack" not in name:
        download_url = asset['browser_download_url']
        asset_name = name
        break

# Fallback to any arm64 zst if standard not found
if not download_url:
    for asset in release_info['assets']:
        name = asset['name']
        if "arm64" in name and name.endswith(".tar.zst"):
            download_url = asset['browser_download_url']
            asset_name = name
            break

if not download_url:
    print("Could not find suitable arm64 asset.")
    sys.exit(1)

print(f"Downloading {asset_name} from {download_url}...")
home_dir = os.path.expanduser("~")
zst_path = os.path.join(home_dir, "ollama.tar.zst")
try:
    urllib.request.urlretrieve(download_url, zst_path)
    print("Download complete.")
except Exception as e:
    print(f"Error downloading asset: {e}")
    sys.exit(1)

# Decompress and extract using zstandard python library
print("Installing 'zstandard' python library inside virtual env to extract...")
import subprocess
try:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "zstandard"])
except Exception as e:
    print(f"Error installing zstandard pip package: {e}")
    sys.exit(1)

import zstandard as zstd
import tarfile

print("Streaming decompress and extract directly in memory (0MB intermediate disk usage)...")
try:
    dctx = zstd.ZstdDecompressor()
    with open(zst_path, 'rb') as ifh:
        with dctx.stream_reader(ifh) as reader:
            with tarfile.open(fileobj=reader, mode='r|') as tar:
                tar.extractall(path=home_dir)
    print("Extraction complete!")
    
    # Cleanup file
    if os.path.exists(zst_path):
        os.remove(zst_path)
    
    # Locate ollama binary in extracted folders
    binary_path = os.path.join(home_dir, "bin", "ollama")
    if os.path.exists(binary_path):
        os.chmod(binary_path, 0o755)
        print(f"\n======================================================================")
        print(f"Ollama successfully installed to: {binary_path}")
        print(f"======================================================================")
    else:
        print("Warning: Could not find ollama binary at ~/bin/ollama after extraction.")
        
except Exception as e:
    print(f"Error during decompression/extraction: {e}")
    sys.exit(1)
