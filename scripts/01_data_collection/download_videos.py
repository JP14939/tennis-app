import subprocess
import sys
import os

YT_DLP = r"C:\Users\jackp\AppData\Roaming\Python\Python313\Scripts\yt-dlp.exe"

OUTPUT_BASE = r"C:\Users\jackp\tennis_app\data\01_source_videos"

# Add YouTube URLs here — slow-mo clips preferred, 20-30 seconds of a single shot
VIDEOS = [
    # Format: (url, shot_type, filename)
    ("https://www.youtube.com/watch?v=lgCokC--lyI", "forehand", "forehand_compilation_2"),
    ("https://www.youtube.com/watch?v=928wJjWeVyk", "forehand", "forehand_compilation_3"),
    ("https://www.youtube.com/watch?v=JWOc8IU0xMM", "backhand", "backhand_compilation_2"),
    ("https://www.youtube.com/watch?v=wFwidKBUt9M", "backhand", "backhand_compilation_3"),
    ("https://www.youtube.com/watch?v=bNeN2XevGLM", "backhand", "backhand_compilation_4"),
    ("https://www.youtube.com/watch?v=1CcGt9f7qT4", "serve",    "serve_compilation_2"),
]

def download(url, shot_type, name):
    out_dir = os.path.join(OUTPUT_BASE, shot_type)
    out_path = os.path.join(out_dir, f"{name}.%(ext)s")
    print(f"Downloading {name} ({shot_type})...")
    subprocess.run([
        YT_DLP,
        "--js-runtimes", "node",
        "-f", "best[ext=mp4]/best",
        "-o", out_path,
        url
    ], check=True)
    print(f"  Saved to {out_dir}\\{name}.mp4")

if __name__ == "__main__":
    if not VIDEOS:
        print("No videos listed. Add (url, shot_type, filename) tuples to the VIDEOS list.")
        sys.exit(0)
    for url, shot_type, name in VIDEOS:
        download(url, shot_type, name)
    print("\nAll done.")
