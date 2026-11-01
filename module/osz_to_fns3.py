# -*- coding: utf-8 -*-
"""
osz_to_fns3.py - Convert osu!mania .osz to FNS 3 .baked + .ogg
Usage: python osz_to_fns3.py <file.osz>
Requires: ffmpeg in PATH
"""

from __future__ import print_function
import os
import sys
import zipfile
import subprocess
import tempfile
import shutil
import re
from collections import defaultdict

FFMPEG = "ffmpeg"  # may be overridden at runtime

# --- ANSI colors ---
R = "\033[91m"; G = "\033[92m"; Y = "\033[93m"; C = "\033[96m"; W = "\033[0m"

def info(msg):  print(C + "[*]" + W + " " + msg)
def ok(msg):    print(G + "[+]" + W + " " + msg)
def warn(msg):  print(Y + "[!]" + W + " " + msg)
def die(msg):   print(R + "[x]" + W + " " + msg); sys.exit(1)

# --- OSU PARSER ---
def parse_osu(path):
    with open(path, "r") as f:
        content = f.read()

    def section(name):
        tag = "[" + name + "]"
        if tag not in content:
            return ""
        return content.split(tag)[1].split("\n[")[0].strip()

    # Metadata
    meta = {}
    for line in section("Metadata").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()

    # Timing points
    timing_points = []
    for line in section("TimingPoints").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        parts = line.split(",")
        if len(parts) < 7:
            continue
        try:
            time = float(parts[0])
            beat_len = float(parts[1])
            uninherited = int(parts[6])
            if uninherited == 1 and beat_len > 0:
                timing_points.append((time, 60000.0 / beat_len))
        except ValueError:
            continue

    # Hit objects
    hit_objects = []
    for line in section("HitObjects").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            x = int(parts[0])
            time_ms = int(parts[2])
            obj_type = int(parts[3])
            col = int(x * 4 / 512)
            sustain_ms = 0
            if obj_type & 128 and len(parts) > 5:
                end_time = int(parts[5].split(":")[0])
                sustain_ms = max(0, end_time - time_ms)
            hit_objects.append((time_ms, col, sustain_ms))
        except (ValueError, IndexError):
            continue

    hit_objects.sort(key=lambda h: (h[0], h[1]))
    return meta, timing_points, hit_objects

# --- DIFF PICKER ---
def pick_diff(osu_files):
    print("\n" + C + "Available difficulties:" + W)
    for i, f in enumerate(osu_files):
        name = os.path.basename(f)
        diff = name.split("[")[-1].rstrip("].osu") if "[" in name else name
        print("  " + Y + str(i) + W + "  " + diff)
    while True:
        try:
            choice = int(raw_input("\nPick difficulty number: ") if sys.version_info[0] < 3 else input("\nPick difficulty number: "))
            if 0 <= choice < len(osu_files):
                return osu_files[choice]
        except ValueError:
            pass
        warn("Invalid choice, try again.")

# --- INPUT HELPER ---
def ask(prompt):
    if sys.version_info[0] < 3:
        return raw_input(prompt)
    return input(prompt)


# --- STAGGER SIMULTANEOUS NOTES ---
def stagger_notes(notes):
    by_time = defaultdict(list)
    for i, n in enumerate(notes):
        by_time[n[0]].append(i)

    notes = [list(n) for n in notes]
    staggered = 0
    for t, indices in by_time.items():
        if len(indices) > 1:
            for offset, idx in enumerate(indices):
                notes[idx][0] = t + offset
            staggered += len(indices)

    notes.sort(key=lambda n: (n[0], n[1]))
    return notes, staggered

# --- WRITE BAKED ---
def write_baked(notes, scroll_speed, out_path):
    cam_events = [("0.0", "0")]
    out = [str(len(notes)) + " " + str(len(cam_events)) + " " + str(scroll_speed)]
    for n in notes:
        out.append(str(round(n[0], 1)) + " " + str(n[1]) + " " + str(int(n[2])) + " 0")
    out.append("0")
    for t, val in cam_events:
        out.append(t)
        out.append("FocusCamera")
        out.append(val)
    with open(out_path, "wb") as f:
        f.write("\r\n".join(out) + "\r\n")

# --- CONVERT AUDIO ---
def convert_audio(src_path, out_path, volume_db=0):
    cmd = [FFMPEG, "-y"]
    cmd += ["-i", src_path]
    if volume_db != 0:
        cmd += ["-af", "volume=" + str(volume_db) + "dB"]
    cmd += [
        "-ac", "1",
        "-c:a", "libvorbis",
        "-q:a", "4",
        "-map_metadata", "-1",
        out_path
    ]
    result = subprocess.call(cmd)
    if result != 0:
        die("ffmpeg failed.")

# --- MAIN ---
def main():
    if len(sys.argv) < 2:
        print("Usage: python osz_to_fns3.py <file.osz>")
        sys.exit(1)

    osz_path = sys.argv[1]
    if not os.path.isfile(osz_path):
        die("File not found: " + osz_path)
    # Look for ffmpeg: script dir first, then PATH
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ffmpeg_local = os.path.join(script_dir, "ffmpeg.exe") if sys.platform == "win32" else os.path.join(script_dir, "ffmpeg")
    if os.path.isfile(ffmpeg_local):
        global FFMPEG
        FFMPEG = ffmpeg_local
    elif hasattr(shutil, "which") and shutil.which("ffmpeg"):
        FFMPEG = "ffmpeg"
    else:
        die("ffmpeg not found. Put ffmpeg.exe in the same folder as this script.")

    tmpdir = tempfile.mkdtemp(prefix="fns3_")
    info("Extracting " + osz_path + " ...")

    try:
        with zipfile.ZipFile(osz_path, "r") as z:
            z.extractall(tmpdir)

        osu_files = sorted([
            os.path.join(tmpdir, f) for f in os.listdir(tmpdir)
            if f.endswith(".osu")
        ])
        if not osu_files:
            die("No .osu files found in archive.")

        audio_src = None
        for f in os.listdir(tmpdir):
            if f.endswith(".mp3") or f.endswith(".ogg") or f.endswith(".wav"):
                audio_src = os.path.join(tmpdir, f)
                break
        if not audio_src:
            die("No audio file found in archive.")
        info("Audio source: " + os.path.basename(audio_src))

        # Pick difficulty
        osu_path = pick_diff(osu_files)
        info("Parsing " + os.path.basename(osu_path) + " ...")
        meta, _, hit_objects = parse_osu(osu_path)

        title     = meta.get("Title", "unknown")
        artist    = meta.get("Artist", "unknown")
        diff_name = meta.get("Version", "chart")
        print("\n" + G + artist + " - " + title + " [" + diff_name + "]" + W)
        print("  Notes: " + str(len(hit_objects)))


        # Use full chart, no cutting
        shifted = list(hit_objects)

        # Stagger simultaneous notes
        shifted, staggered = stagger_notes(shifted)
        if staggered:
            warn("Staggered " + str(staggered) + " simultaneous notes (1ms apart).")

        # Scroll speed
        print()
        while True:
            try:
                scroll = float(ask("Enter scroll speed (e.g. 1.6): ").strip())
                if scroll > 0:
                    break
            except ValueError:
                pass
            warn("Enter a positive number.")

        # Volume boost
        while True:
            try:
                vol_input = ask("Volume boost in dB (0 = no boost, e.g. 5): ").strip()
                volume_db = float(vol_input) if vol_input else 0
                break
            except ValueError:
                warn("Enter a number (e.g. 0, 3, 5).")

        # Output names
        chart_name  = ask("\nChart name (without .baked, e.g. agoti-chart-nightmare): ").strip()
        if not chart_name:
            chart_name = title.lower().replace(" ", "_") + "-chart-" + diff_name.lower().replace(" ", "_")

        song_prefix = ask("Song prefix (e.g. agoti -> snd_agoti_inst / snd_agoti_voices_all): ").strip()
        if not song_prefix:
            song_prefix = title.lower().replace(" ", "_")

        baked_out  = chart_name + ".baked"
        inst_out   = "snd_" + song_prefix + "_inst.ogg"
        voices_out = "snd_" + song_prefix + "_voices_all.ogg"
        tmp_ogg    = chart_name + "_tmp.ogg"

        # Write .baked
        info("Writing " + baked_out + " ...")
        write_baked(shifted, scroll, baked_out)
        ok("Saved: " + baked_out + "  (" + str(len(shifted)) + " notes)")

        # Convert audio
        info("Converting audio ...")
        convert_audio(audio_src, tmp_ogg, volume_db)
        shutil.copy2(tmp_ogg, inst_out)
        shutil.copy2(tmp_ogg, voices_out)
        os.remove(tmp_ogg)
        if volume_db != 0:
            ok("Volume boost: +" + str(volume_db) + " dB applied")

        # Zip output files
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)
        safe_diff  = re.sub(r'[\\/:*?"<>|]', "_", diff_name)
        zip_name   = safe_title + "-" + safe_diff + ".zip"
        # Place zip next to the input .osz file
        zip_path   = os.path.join(os.path.dirname(os.path.abspath(osz_path)), zip_name)
        info("Zipping output files -> " + zip_name + " ...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(baked_out,  os.path.basename(baked_out))
            zf.write(inst_out,   os.path.basename(inst_out))
            zf.write(voices_out, os.path.basename(voices_out))

        # Clean up loose files
        os.remove(baked_out)
        os.remove(inst_out)
        os.remove(voices_out)

        print("\n" + G + "Done!" + W)
        print("  Output : " + zip_path)
        # Parseable line for batch script
        print("ZIP_OUTPUT=" + zip_path)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    main()
