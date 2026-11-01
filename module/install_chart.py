# -*- coding: utf-8 -*-
"""
install_chart.py - Install FNS 3 chart files to PS3 via FTP
Usage: python install_chart.py <converted_zip>
"""

from __future__ import print_function
import os
import sys
import zipfile
import ftplib
import tempfile
import shutil

# --- ANSI colors ---
R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"; C = "\033[96m"; W = "\033[0m"

def info(msg):  print(C + "[*]" + W + " " + msg)
def ok(msg):    print(G + "[+]" + W + " " + msg)
def warn(msg):  print(Y + "[!]" + W + " " + msg)
def die(msg):   print(R + "[x]" + W + " " + msg); sys.exit(1)

def ask(prompt):
    if sys.version_info[0] < 3:
        return raw_input(prompt)
    return input(prompt)

# --- PS3 PATHS ---
OGG_DIR   = "/dev_hdd0/game/NPXS00020/USRDIR"
BAKED_DIR = "/dev_hdd0/game/NPXS00020/USRDIR/baked_files"

def ftp_upload(ftp, local_path, remote_path):
    filename = os.path.basename(local_path)
    info("Uploading " + filename + " ...")
    with open(local_path, "rb") as f:
        ftp.storbinary("STOR " + remote_path, f)
    ok("Done: " + remote_path)

def main():
    if len(sys.argv) < 2:
        print("Usage: python install_chart.py <converted_zip>")
        sys.exit(1)

    zip_path = sys.argv[1]
    if not os.path.isfile(zip_path):
        die("File not found: " + zip_path)
    if not zip_path.lower().endswith(".zip"):
        die("Expected a .zip file from the converter.")

    # Get PS3 IP
    print()
    while True:
        ip = ask("Enter PS3 IP address (e.g. 192.168.1.100): ").strip()
        if ip:
            break
        warn("IP address cannot be empty.")

    # Extract zip to temp folder
    tmpdir = tempfile.mkdtemp(prefix="fns3_install_")
    try:
        info("Extracting " + os.path.basename(zip_path) + " ...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmpdir)

        # Categorize files
        baked_files = []
        ogg_files   = []
        for f in os.listdir(tmpdir):
            full = os.path.join(tmpdir, f)
            if f.endswith(".baked"):
                baked_files.append(full)
            elif f.endswith(".ogg"):
                ogg_files.append(full)

        if not baked_files and not ogg_files:
            die("No .baked or .ogg files found in zip.")

        print()
        info("Files to install:")
        for f in baked_files:
            print("  " + Y + "[chart]" + W + " " + os.path.basename(f) + " -> " + BAKED_DIR)
        for f in ogg_files:
            print("  " + Y + "[audio]" + W + " " + os.path.basename(f) + " -> " + OGG_DIR)

        print()
        info("Connecting to " + ip + ":21 ...")
        try:
            ftp = ftplib.FTP()
            ftp.connect(ip, 21, timeout=10)
            ftp.login()
            ok("Connected!")
        except Exception as e:
            die("FTP connection failed: " + str(e))

        # Upload chart files
        for f in baked_files:
            remote = BAKED_DIR + "/" + os.path.basename(f)
            try:
                ftp_upload(ftp, f, remote)
            except Exception as e:
                die("Failed to upload " + os.path.basename(f) + ": " + str(e))

        # Upload ogg files
        for f in ogg_files:
            remote = OGG_DIR + "/" + os.path.basename(f)
            try:
                ftp_upload(ftp, f, remote)
            except Exception as e:
                die("Failed to upload " + os.path.basename(f) + ": " + str(e))

        ftp.quit()

        print("\n" + G + "All files installed successfully!" + W)
        print("  PS3 : " + ip)
        print("  Zip : " + os.path.basename(zip_path))

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    main()
