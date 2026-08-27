#!/usr/bin/env python3
"""
Auto Video Trimmer
-------------------
Video ko input/ folder mein daalo, ye script silence aur blurry parts
detect karke cut karega, aur clean video output/ folder mein save karega.

Usage:
    python3 auto_trim.py

Requirements:
    - ffmpeg (system installed)
    - opencv-python (pip install opencv-python)
    - numpy (pip install numpy)
"""

import os
import sys
import subprocess
import json
import cv2
import numpy as np

INPUT_DIR = "input"
OUTPUT_DIR = "output"
TEMP_DIR = "temp_work"

# ---------- SETTINGS (aap inhe apni zarurat ke hisaab se badal sakte ho) ----------
SILENCE_THRESHOLD_DB = -35      # isse neeche volume ho toh "silence" mana jayega
SILENCE_MIN_DURATION = 0.6      # kam se kam itni der (seconds) silence ho tabhi cut hoga
BLUR_THRESHOLD = 60.0           # isse kam sharpness score ho toh "blurry" mana jayega
BLUR_MIN_DURATION = 0.5         # kam se kam itni der (seconds) blur ho tabhi cut hoga
FRAME_SAMPLE_RATE = 5           # har second mein kitne frames check karein (zyada = accurate but slow)
# ------------------------------------------------------------------------------


def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout, result.stderr, result.returncode


def get_video_duration(path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "json", path
    ]
    out, err, code = run_cmd(cmd)
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {err}")
    data = json.loads(out)
    return float(data["format"]["duration"])


def detect_silence(path, duration):
    """ffmpeg ke silencedetect filter se silence ranges nikaalta hai."""
    print("  -> Silence detect kar raha hoon...")
    cmd = [
        "ffmpeg", "-i", path, "-af",
        f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={SILENCE_MIN_DURATION}",
        "-f", "null", "-"
    ]
    out, err, code = run_cmd(cmd)

    silence_ranges = []
    start = None
    for line in err.splitlines():
        if "silence_start" in line:
            try:
                start = float(line.split("silence_start:")[1].strip())
            except (IndexError, ValueError):
                pass
        elif "silence_end" in line and start is not None:
            try:
                part = line.split("silence_end:")[1].strip()
                end = float(part.split("|")[0].strip())
                silence_ranges.append((start, end))
                start = None
            except (IndexError, ValueError):
                pass

    # Agar video silence pe hi khatam ho raha ho
    if start is not None and start < duration:
        silence_ranges.append((start, duration))

    print(f"     {len(silence_ranges)} silent parts mile.")
    return silence_ranges


def detect_blur(path, duration):
    """Frames sample karke blurry ranges nikaalta hai (Laplacian variance method)."""
    print("  -> Blur detect kar raha hoon...")
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = max(1, int(fps / FRAME_SAMPLE_RATE))

    blurry_timestamps = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
            timestamp = frame_idx / fps
            if sharpness < BLUR_THRESHOLD:
                blurry_timestamps.append(timestamp)
        frame_idx += 1
    cap.release()

    # Consecutive blurry timestamps ko ranges mein group karo
    blur_ranges = []
    if blurry_timestamps:
        range_start = blurry_timestamps[0]
        prev = blurry_timestamps[0]
        gap_allowed = (frame_interval / fps) * 2

        for t in blurry_timestamps[1:]:
            if t - prev > gap_allowed:
                if prev - range_start >= BLUR_MIN_DURATION:
                    blur_ranges.append((range_start, prev))
                range_start = t
            prev = t
        if prev - range_start >= BLUR_MIN_DURATION:
            blur_ranges.append((range_start, prev))

    print(f"     {len(blur_ranges)} blurry parts mile.")
    return blur_ranges


def merge_ranges(ranges, duration):
    """Overlapping ranges ko combine karta hai aur video ke bounds mein rakhta hai."""
    if not ranges:
        return []
    clean = [(max(0, s), min(duration, e)) for s, e in ranges if e > s]
    clean.sort()
    merged = [clean[0]]
    for s, e in clean[1:]:
        last_s, last_e = merged[-1]
        if s <= last_e:
            merged[-1] = (last_s, max(last_e, e))
        else:
            merged.append((s, e))
    return merged


def invert_ranges(cut_ranges, duration):
    """Cut karne wale ranges se, wo ranges nikaalta hai jo RAKHNE hain."""
    keep = []
    cursor = 0.0
    for s, e in cut_ranges:
        if s > cursor:
            keep.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        keep.append((cursor, duration))
    return keep


def cut_and_concat(path, keep_ranges, output_path):
    """Video ke keep_ranges wale parts nikaal ke, unhe jod ke final video banata hai."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    segment_files = []

    print(f"  -> {len(keep_ranges)} clean segments bana raha hoon...")
    for i, (s, e) in enumerate(keep_ranges):
        seg_path = os.path.join(TEMP_DIR, f"seg_{i:04d}.mp4")
        duration = e - s
        cmd = [
            "ffmpeg", "-y", "-ss", str(s), "-i", path, "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "make_zero",
            seg_path
        ]
        out, err, code = run_cmd(cmd)
        if code == 0 and os.path.exists(seg_path):
            segment_files.append(seg_path)
        else:
            print(f"     Warning: segment {i} fail ho gaya, skip kar raha hoon.")

    if not segment_files:
        raise RuntimeError("Koi bhi valid segment nahi bana - kuch galat hai.")

    # concat list file banao
    concat_list_path = os.path.join(TEMP_DIR, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for seg in segment_files:
            f.write(f"file '{os.path.abspath(seg)}'\n")

    print("  -> Final video jod raha hoon...")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
        "-c", "copy", output_path
    ]
    out, err, code = run_cmd(cmd)
    if code != 0:
        # fallback: re-encode karke try karo agar copy fail ho
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
            "-c:v", "libx264", "-c:a", "aac", output_path
        ]
        out, err, code = run_cmd(cmd)
        if code != 0:
            raise RuntimeError(f"Final video banane mein fail: {err}")

    # cleanup temp files
    for seg in segment_files:
        os.remove(seg)
    os.remove(concat_list_path)


def process_video(input_path, output_path):
    filename = os.path.basename(input_path)
    print(f"\n=== Processing: {filename} ===")

    duration = get_video_duration(input_path)
    print(f"  Video duration: {duration:.1f}s")

    silence_ranges = detect_silence(input_path, duration)
    blur_ranges = detect_blur(input_path, duration)

    all_cut_ranges = merge_ranges(silence_ranges + blur_ranges, duration)

    if not all_cut_ranges:
        print("  Koi bhi bad part nahi mila - video already sahi hai. Copy kar raha hoon.")
        import shutil
        shutil.copy(input_path, output_path)
        return

    total_cut = sum(e - s for s, e in all_cut_ranges)
    print(f"  Total cut hone wala: {total_cut:.1f}s / {duration:.1f}s")

    keep_ranges = invert_ranges(all_cut_ranges, duration)

    if not keep_ranges:
        print("  Warning: pura video hi 'bad' detect hua - kuch settings loose karo (thresholds check karo).")
        return

    cut_and_concat(input_path, keep_ranges, output_path)
    print(f"  Done! Saved: {output_path}")


def main():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    video_extensions = (".mp4", ".mov", ".avi", ".mkv", ".webm")
    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(video_extensions)]

    if not files:
        print(f"'{INPUT_DIR}' folder mein koi video nahi mila.")
        print(f"Video daalo '{INPUT_DIR}/' folder mein aur script dobara chalao.")
        sys.exit(0)

    for f in files:
        input_path = os.path.join(INPUT_DIR, f)
        name, ext = os.path.splitext(f)
        output_path = os.path.join(OUTPUT_DIR, f"{name}_clean{ext}")
        try:
            process_video(input_path, output_path)
        except Exception as e:
            print(f"  ERROR processing {f}: {e}")

    print("\nSab ho gaya! 'output/' folder check karo.")


if __name__ == "__main__":
    main()
