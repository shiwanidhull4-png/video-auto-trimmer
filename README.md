# Clean Cuts — Auto Video Trimmer (Web App)

Browser-based tool: upload a video, silence aur blurry parts automatically
cut ho jaate hain, aur clean video download kar sakte ho.

## Setup

1. FFmpeg install karo:
   - Windows: https://ffmpeg.org/download.html (PATH mein add karo)
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

2. Python libraries install karo:
   ```
   pip install -r requirements.txt
   ```

## Run Karna

```
python3 app.py
```

Phir browser mein kholo: **http://localhost:5000**

Video upload karo (drag-drop ya click), processing hote hi timeline aur
download button dikh jayega.

## Settings Badalna

`app.py` ke top mein settings hain (SILENCE_THRESHOLD_DB, BLUR_THRESHOLD, etc.)
— inhe adjust kar sakte ho zyada/kam strict cutting ke liye.

## Kaise Kaam Karta Hai

- **Silence detection**: FFmpeg ke audio analysis se pata chalta hai kahan
  volume threshold se neeche gaya (dead air).
- **Blur detection**: Har frame ki "sharpness" check hoti hai
  (Laplacian variance method) — kam sharp frames blurry maane jaate hain.
- Dono se mile "bad" parts cut karke baaki segments jod diye jaate hain.

Sab kuch aapke laptop pe locally chalta hai — koi video kahin upload/send
nahi hota.
