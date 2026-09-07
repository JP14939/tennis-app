import subprocess
import sys
import os

YT_DLP = r"C:\Users\jackp\AppData\Roaming\Python\Python313\Scripts\yt-dlp.exe"

OUTPUT_BASE = r"C:\Users\jackp\tennis_app\data\01_source_videos"

# YouTube stopped serving progressive (video+audio) mp4 for most videos in
# 2026 -- yt-dlp now has to download video-only + audio-only DASH streams and
# merge them, which needs ffmpeg. There's no system ffmpeg on this machine, so
# point yt-dlp at the one bundled in the scripts venv (imageio_ffmpeg, already
# used by scripts/00_utils/video_io.py and the audio-onset code).
def _ffmpeg_location():
    try:
        import imageio_ffmpeg  # noqa: PLC0415
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

# Add YouTube URLs here.
#  - single-shot slow-mo compilations -> shot_type forehand/backhand/serve,
#    processed by process_new_videos.py (one shot type per whole video).
#  - court-level practice / points footage (mixed shots, sometimes 2 players)
#    -> shot_type "practice", processed by ingest_practice_footage.py, which
#    detects + classifies + verifies each swing individually.
VIDEOS = [
    # Format: (url, shot_type, filename)
    ("https://www.youtube.com/watch?v=lgCokC--lyI", "forehand", "forehand_compilation_2"),
    ("https://www.youtube.com/watch?v=928wJjWeVyk", "forehand", "forehand_compilation_3"),
    ("https://www.youtube.com/watch?v=JWOc8IU0xMM", "backhand", "backhand_compilation_2"),
    ("https://www.youtube.com/watch?v=wFwidKBUt9M", "backhand", "backhand_compilation_3"),
    ("https://www.youtube.com/watch?v=bNeN2XevGLM", "backhand", "backhand_compilation_4"),
    ("https://www.youtube.com/watch?v=1CcGt9f7qT4", "serve",    "serve_compilation_2"),
    # 2026-09-02: court-level practice / points footage (Jack's picks)
    ("https://www.youtube.com/watch?v=C4Gl-T2dtss", "practice", "practice_01"),  # Djokovic+Alcaraz practice
    ("https://www.youtube.com/watch?v=0PJx1QL-0KM", "practice", "practice_02"),  # Federer+Berdych practice
    ("https://www.youtube.com/watch?v=F40FXdmOQ5E", "practice", "practice_03"),  # Alcaraz court-level points
    ("https://www.youtube.com/watch?v=qXtJDJ1U7_8", "practice", "practice_04"),  # multi-player court-level points
]

def download(url, shot_type, name):
    out_dir = os.path.join(OUTPUT_BASE, shot_type)
    os.makedirs(out_dir, exist_ok=True)
    if os.path.exists(os.path.join(out_dir, f"{name}.mp4")):
        print(f"Skipping {name} ({shot_type}) -- already on disk")
        return True
    out_path = os.path.join(out_dir, f"{name}.%(ext)s")
    print(f"Downloading {name} ({shot_type})...")
    cmd = [YT_DLP, "--js-runtimes", "node",
           "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
           "--merge-output-format", "mp4", "-o", out_path, url]
    ff = _ffmpeg_location()
    if ff:
        cmd[1:1] = ["--ffmpeg-location", ff]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  FAILED ({name}): {e} -- skipping, continuing with the rest")
        return False
    print(f"  Saved to {out_dir}\\{name}.mp4")
    return True

if __name__ == "__main__":
    if not VIDEOS:
        print("No videos listed. Add (url, shot_type, filename) tuples to the VIDEOS list.")
        sys.exit(0)
    only = set(sys.argv[1:])  # optional: filenames or shot types to restrict to
    failed = []
    for url, shot_type, name in VIDEOS:
        if only and name not in only and shot_type not in only:
            continue
        if not download(url, shot_type, name):
            failed.append(name)
    print("\nAll done." + (f"  Failed: {failed}" if failed else ""))
