#!/usr/bin/env python3
"""Download Back on the Broomstick / Stoned Witches Hour transcripts.

Channel listing uses yt-dlp (no API key). Transcript text comes from
YouTube captions via youtube-transcript-api by default; --use-whisper
downloads audio with yt-dlp and transcribes locally, --use-gcs uses
transcribe_audio.py (Google Cloud Speech).
"""

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime

from youtube_transcript_api import YouTubeTranscriptApi

# --- Configuration ---

CHANNELS = {
    "botbs": "UCpwXkp5XwIw_WVswz9bzBUw",
    "swh": "UCyUA6TXPI48F6JLXc6I41xw",
}
GCS_BUCKET = "chuck-transcription-bucket-20251118"
ID_RE = re.compile(r"-([A-Za-z0-9_-]{11})-transcript\.txt$")

# --- Utility Functions ---


def slugify(text):
    """Sanitize text for use in filenames."""
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s:]+", "_", text)
    return text.lower().strip("_")


def existing_ids():
    """Video IDs that already have a transcript file (titles can change, IDs don't)."""
    ids = set()
    for f in os.listdir():
        m = ID_RE.search(f)
        if m:
            ids.add(m.group(1))
    return ids


def yt_dlp(*args):
    return subprocess.run(["yt-dlp", "--no-update", *args], check=True, capture_output=True, text=True)


# --- Channel / video metadata ---


def get_channel_videos(channel_id):
    """Return [(video_id, title)] for every upload on the channel, newest first."""
    print(f"\n{'=' * 40}\nFetching videos for channel ID: {channel_id}")
    out = yt_dlp(
        "--flat-playlist",
        "--print",
        "%(id)s\t%(title)s",
        f"https://www.youtube.com/channel/{channel_id}/videos",
    ).stdout
    videos = [tuple(line.split("\t", 1)) for line in out.splitlines() if "\t" in line]
    print(f"Total videos found: {len(videos)}")
    return videos


def get_title(video_id):
    return yt_dlp("--skip-download", "--print", "%(title)s", f"https://www.youtube.com/watch?v={video_id}").stdout.strip()


# --- Transcription methods ---


def captions_text(video_id):
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US"])
    return " ".join(s.text for s in transcript.snippets)


def whisper_text(video_id):
    audio = f"{video_id}.mp3"
    try:
        yt_dlp("-x", "--audio-format", "mp3", "-o", f"{video_id}.%(ext)s", f"https://www.youtube.com/watch?v={video_id}")
        subprocess.run(["whisper", audio, "--model", "base", "--output_format", "txt"], check=True, capture_output=True)
        with open(f"{video_id}.txt", encoding="utf-8") as f:
            return f.read()
    finally:
        for ext in ["mp3", "txt", "json", "srt", "tsv", "vtt"]:
            if os.path.exists(f"{video_id}.{ext}"):
                os.remove(f"{video_id}.{ext}")


def gcs_text(video_id):
    audio = f"{video_id}.mp3"
    out = f"{video_id}.gcs.txt"
    try:
        yt_dlp("-x", "--audio-format", "mp3", "-o", f"{video_id}.%(ext)s", f"https://www.youtube.com/watch?v={video_id}")
        subprocess.run(
            [sys.executable, "transcribe_audio.py", audio, "--gcs-bucket", GCS_BUCKET, "--output-file", out],
            check=True,
            capture_output=True,
        )
        with open(out, encoding="utf-8") as f:
            return f.read()
    finally:
        for p in (audio, out):
            if os.path.exists(p):
                os.remove(p)


METHODS = {"captions": captions_text, "whisper": whisper_text, "gcs": gcs_text}


def download_and_save_transcript(video_id, title=None, method="captions", combined_file_handle=None, have=None):
    """Download and save one transcript. Returns (ok, status)."""
    try:
        if have is None:
            have = existing_ids()
        if video_id in have:
            print(f"🟡 Transcript already exists for {video_id}. Skipping.")
            return True, "skipped"

        title = title or get_title(video_id)
        filename = f"{slugify(title)}-{video_id}-transcript.txt"
        print(f"\nProcessing {video_id} - {title} [{method}]")

        text = METHODS[method](video_id)
        if not text.strip():
            raise RuntimeError("empty transcript")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"🟢 Saved: {filename}")

        if combined_file_handle:
            combined_file_handle.write(f"## Transcript File: {filename}\n")
            combined_file_handle.write(f"## Video Title: {title}\n")
            combined_file_handle.write(f"## Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            combined_file_handle.write("-" * 40 + "\n" + text + "\n\n")
        return True, "new"

    except subprocess.CalledProcessError as e:
        print(f"🔴 Subprocess error for {video_id}: {(e.stderr or '').strip()[-500:]}")
    except Exception as e:
        print(f"🔴 Error processing {video_id}: {type(e).__name__}: {str(e)[:300]}")
    return False, "error"


# --- Main Feature Functions ---


def process_channel(channel_id, output_file, method, delay):
    videos = get_channel_videos(channel_id)
    if not videos:
        return
    have = existing_ids()
    todo = [(v, t) for v, t in videos if v not in have]
    print(f"Already have {len(videos) - len(todo)}; {len(todo)} to fetch.")
    stats = {"new": 0, "skipped": len(videos) - len(todo), "error": 0}
    failed = []

    with open(output_file, "a", encoding="utf-8") as combined:
        for i, (vid, title) in enumerate(todo):
            ok, status = download_and_save_transcript(vid, title, method, combined, have)
            stats[status] += 1
            if not ok:
                failed.append((vid, title))
            combined.flush()
            if delay and i < len(todo) - 1:
                time.sleep(delay)

    print(f"\n{'=' * 40}\nChannel Processing Complete")
    print(f"Total Videos: {len(videos)}, New: {stats['new']}, Skipped: {stats['skipped']}, Errors: {stats['error']}")
    for vid, title in failed:
        print(f"  failed: {vid} {title}")
    if failed:
        print("Retry failures with --use-whisper (or --video-id ID --use-whisper).")


def combine_local_files(output_file):
    print("🚀 Starting local transcript combination...")
    # the output name ends in "-transcript.txt" too; skip it or the file reads its own half-written self back in
    files = [
        f
        for f in os.listdir()
        if f.endswith("-transcript.txt") and os.path.abspath(f) != os.path.abspath(output_file)
    ]
    if not files:
        print("❌ No transcript files found.")
        return
    with open(output_file, "w", encoding="utf-8") as combined:
        combined.write(
            f"Combined Transcripts (from local files)\nGenerated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'=' * 40}\n\n"
        )
        for filename in sorted(files):
            try:
                with open(filename, encoding="utf-8") as f:
                    content = f.read()
                combined.write(f"## Episode Transcript: {filename}\n{content}\n\n")
            except Exception as e:
                print(f"❌ Error processing {filename}: {e}")
    print(f"\n✅ All local transcripts combined into: {output_file}")


# --- Main Execution ---


def main():
    parser = argparse.ArgumentParser(
        description="Download and manage YouTube transcripts for the podcast channels.",
        epilog="Default method is YouTube captions; no API key needed.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel", choices=CHANNELS.keys(), help="Channel to process.")
    group.add_argument("--video-id", help="A single YouTube video ID.")
    group.add_argument("--combine-only", action="store_true", help="Combine all local *-transcript.txt files and exit.")
    group.add_argument("--list-channels", action="store_true", help="List configured channels and exit.")

    parser.add_argument("--output-file", default="master-transcript.txt", help="Combined output file.")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between caption fetches (avoids rate limits).")
    method_group = parser.add_mutually_exclusive_group()
    method_group.add_argument("--use-whisper", action="store_true", help="yt-dlp audio + local whisper.")
    method_group.add_argument("--use-gcs", action="store_true", help="yt-dlp audio + Google Cloud Speech.")
    args = parser.parse_args()

    if args.list_channels:
        for name, channel_id in CHANNELS.items():
            print(f"  - {name}: {channel_id}")
        return
    if args.combine_only:
        combine_local_files(args.output_file)
        return

    method = "whisper" if args.use_whisper else "gcs" if args.use_gcs else "captions"
    if args.channel:
        process_channel(CHANNELS[args.channel], args.output_file, method, args.delay)
    if args.video_id:
        ok, _ = download_and_save_transcript(args.video_id, method=method)
        print(f"\n✅ Single transcript operation {'completed' if ok else 'failed'}.")


if __name__ == "__main__":
    main()
