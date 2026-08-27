# Video Auto-Trimmer

Video mein se silence aur blurry parts automatically cut karta hai.

## Setup (ek baar karna hai)

1. Python 3 install hona chahiye
2. FFmpeg install karo:
   - Windows: https://ffmpeg.org/download.html se download karo, PATH mein add karo
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
3. Python libraries install karo:
   ```
   pip install opencv-python numpy
   ```

## Use Kaise Karein

1. Apni video file `input/` folder mein daalo
2. Terminal/Command Prompt kholo is folder mein
3. Chalao:
   ```
   python3 auto_trim.py
   ```
4. Clean video `output/` folder mein mil jayegi (naam ke aage `_clean` lagega)

## Settings Badalna (agar zarurat ho)

`auto_trim.py` file ke top mein ye settings hain, inhe adjust kar sakte ho:

- `SILENCE_THRESHOLD_DB` - kitna quiet ho tabhi silence maana jaye (default: -35dB)
- `SILENCE_MIN_DURATION` - kam se kam kitni der silence ho (default: 0.6 second)
- `BLUR_THRESHOLD` - kitna blurry ho tabhi cut ho (default: 60 - kam number = zyada strict)
- `BLUR_MIN_DURATION` - kam se kam kitni der blur ho (default: 0.5 second)

Agar zyada cut ho raha hai (bahut zyada video kat raha hai), thresholds ko loose karo.
Agar kam cut ho raha hai, thresholds ko strict karo.
