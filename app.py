#!/usr/bin/env python3
"""
Auto Video Trimmer - Web App
-----------------------------
Browser se video upload karo, silence + blur wale parts automatically
cut ho jaate hain, aur clean video download kar sakte ho.

Run: python3 app.py
Phir browser mein kholo: http://localhost:5000
"""

import os
import uuid
import json
import subprocess
import shutil

from flask import Flask, request, jsonify, render_template, send_from_directory
import cv2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
TEMP_DIR = os.path.join(BASE_DIR, "temp_work")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max

# ---------- SETTINGS ----------
SILENCE_THRESHOLD_DB = -35
SILENCE_MIN_DURATION = 0.6
BLUR_THRESHOLD = 60.0
BLUR_MIN_DURATION = 0.5
FRAME_SAMPLE_RATE = 5
# -------------------------------


def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout, result.stderr, result.returncode


def get_video_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path]
    out, err, code = run_cmd(cmd)
    if code != 0:
        raise RuntimeError(f"ffprobe failed: {err}")
    return float(json.loads(out)["format"]["duration"])


def detect_silence(path, duration):
    cmd = [
        "ffmpeg", "-i", path, "-af",
        f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={SILENCE_MIN_DURATION}",
        "-f", "null", "-"
    ]
    out, err, code = run_cmd(cmd)

    ranges = []
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
                ranges.append((start, end))
                start = None
            except (IndexError, ValueError):
                pass
    if start is not None and start < duration:
        ranges.append((start, duration))
    return ranges


def detect_blur(path, duration):
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

    ranges = []
    if blurry_timestamps:
        range_start = blurry_timestamps[0]
        prev = blurry_timestamps[0]
        gap_allowed = (frame_interval / fps) * 2
        for t in blurry_timestamps[1:]:
            if t - prev > gap_allowed:
                if prev - range_start >= BLUR_MIN_DURATION:
                    ranges.append((range_start, prev))
                range_start = t
            prev = t
        if prev - range_start >= BLUR_MIN_DURATION:
            ranges.append((range_start, prev))
    return ranges


def merge_ranges(ranges, duration):
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
    keep = []
    cursor = 0.0
    for s, e in cut_ranges:
        if s > cursor:
            keep.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        keep.append((cursor, duration))
    return keep


def cut_and_concat(path, keep_ranges, output_path, work_dir):
    segment_files = []
    for i, (s, e) in enumerate(keep_ranges):
        seg_path = os.path.join(work_dir, f"seg_{i:04d}.mp4")
        dur = e - s
        cmd = [
            "ffmpeg", "-y", "-ss", str(s), "-i", path, "-t", str(dur),
            "-c:v", "libx264", "-af", "aresample=async=1:first_pts=0", "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            seg_path
        ]
        out, err, code = run_cmd(cmd)
        if code == 0 and os.path.exists(seg_path):
            segment_files.append(seg_path)
        else:
            # retry once without audio filter as a fallback
            cmd_retry = [
                "ffmpeg", "-y", "-ss", str(s), "-i", path, "-t", str(dur),
                "-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "make_zero",
                seg_path
            ]
            out, err, code = run_cmd(cmd_retry)
            if code == 0 and os.path.exists(seg_path):
                segment_files.append(seg_path)

    if not segment_files:
        raise RuntimeError("Koi valid segment nahi bana.")

    concat_list_path = os.path.join(work_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for seg in segment_files:
            f.write(f"file '{os.path.abspath(seg)}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-c", "copy", output_path]
    out, err, code = run_cmd(cmd)
    if code != 0:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
               "-c:v", "libx264", "-c:a", "aac", output_path]
        out, err, code = run_cmd(cmd)
        if code != 0:
            raise RuntimeError(f"Final video banane mein fail: {err}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/process", methods=["POST"])
def process():
    if "video" not in request.files:
        return jsonify({"error": "Koi video file nahi mili."}), 400

    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "Koi file select nahi hui."}), 400

    job_id = uuid.uuid4().hex[:10]
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    input_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
    output_filename = f"{job_id}_clean{ext}"
    output_path = os.path.join(PROCESSED_DIR, output_filename)
    work_dir = os.path.join(TEMP_DIR, job_id)
    os.makedirs(work_dir, exist_ok=True)

    file.save(input_path)

    try:
        duration = get_video_duration(input_path)
        silence_ranges = detect_silence(input_path, duration)
        blur_ranges = detect_blur(input_path, duration)
        cut_ranges = merge_ranges(silence_ranges + blur_ranges, duration)

        if not cut_ranges:
            shutil.copy(input_path, output_path)
            final_duration = duration
        else:
            keep_ranges = invert_ranges(cut_ranges, duration)
            if not keep_ranges:
                return jsonify({"error": "Poora video hi 'bad' detect hua, kuch settings check karo."}), 400
            cut_and_concat(input_path, keep_ranges, output_path, work_dir)
            final_duration = get_video_duration(output_path)

        response = {
            "original_duration": round(duration, 2),
            "final_duration": round(final_duration, 2),
            "cuts": [{"start": round(s, 2), "end": round(e, 2)} for s, e in cut_ranges],
            "silence_count": len(silence_ranges),
            "blur_count": len(blur_ranges),
            "download_url": f"/api/download/{output_filename}",
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        if os.path.exists(input_path):
            os.remove(input_path)


@app.route("/api/download/<filename>")
def download(filename):
    return send_from_directory(PROCESSED_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    print("\nAuto Video Trimmer chal raha hai!")
    print("Browser mein kholo: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
