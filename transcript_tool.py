#!/usr/bin/env python3

import os
import re
import argparse
import subprocess
from pytubefix import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from datetime import datetime
from dotenv import load_dotenv

# --- Configuration ---

load_dotenv()

CHANNELS = {
    "botbs": "UCpwXkp5XwIw_WVswz9bzBUw",
    "swh": "UCyUA6TXPI48F6JLXc6I41xw"
}
GCS_BUCKET = "chuck-transcription-bucket-20251118"

# --- Utility Functions ---

def slugify(text):
    """Sanitize text for use in filenames."""
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s:]+', '_', text)
    return text.lower().strip('_')

# --- Core YouTube API Functions ---

def get_channel_videos(api_key, channel_id):
    """Fetches all video IDs from a specified YouTube channel."""
    print(f"\n{'='*40}")
    print(f"Fetching videos for channel ID: {channel_id}")
    youtube = build("youtube", "v3", developerKey=api_key)
    
    try:
        channel = youtube.channels().list(part="contentDetails", id=channel_id).execute()
        playlist_id = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"🔴 Error fetching channel info: {str(e)}")
        return []

    video_ids = []
    next_page_token = None
    while True:
        try:
            playlist = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            video_ids.extend([item["snippet"]["resourceId"]["videoId"] for item in playlist["items"]])
            next_page_token = playlist.get("nextPageToken")
            if not next_page_token:
                break
        except Exception as e:
            print(f"🔴 Error fetching playlist page: {str(e)}")
            break
            
    print(f"Total videos found: {len(video_ids)}")
    return video_ids

def download_and_save_transcript(video_id, use_whisper=False, use_api=False, combined_file_handle=None):
    """
    Downloads and saves a single transcript.
    Default method is Google Cloud Speech via transcribe_audio.py.
    """
    try:
        yt = YouTube(f"https://youtube.com/watch?v={video_id}")
        title = slugify(yt.title)
        filename = f"{title}-{video_id}-transcript.txt"
        print(f"\nProcessing Video ID: {video_id} - {yt.title}")

        if os.path.exists(filename):
            print(f"🟡 Transcript already exists: {filename}. Skipping.")
            return True, "skipped"

        text = ""
        # --- Transcription Method Logic ---
        if use_whisper:
            method_name = "Whisper"
            print("🔵 Using local transcription (yt-dlp + whisper)...")
            audio_filename = f"{video_id}.mp3"
            
            subprocess.run(['yt-dlp', '-x', '--audio-format', 'mp3', '-o', f"{video_id}.%(ext)s", f"https://www.youtube.com/watch?v={video_id}"], check=True, capture_output=True)
            print(f"🟢 Audio downloaded: {audio_filename}")
            
            subprocess.run(['whisper', audio_filename, '--model', 'base', '--output_format', 'txt'], check=True, capture_output=True)
            print("🟢 Transcription complete.")

            whisper_output_file = f"{video_id}.txt"
            with open(whisper_output_file, "r", encoding="utf-8") as f: text = f.read()
            
            os.rename(whisper_output_file, filename)
            for ext in ['mp3', 'json', 'srt', 'tsv', 'vtt']:
                if os.path.exists(f"{video_id}.{ext}"): os.remove(f"{video_id}.{ext}")

        elif use_api:
            method_name = "YouTube API"
            print("🔵 Downloading transcript via YouTube API...")
            transcript_object = YouTubeTranscriptApi.get_transcript(video_id)
            text = " ".join([entry['text'] for entry in transcript_object])
            with open(filename, "w", encoding="utf-8") as f: f.write(text)

        else: # Default GCS method
            method_name = "Google Cloud Speech"
            print("🔵 Using local transcription (yt-dlp + Google Cloud Speech)...")
            audio_filename = f"{video_id}.mp3"

            subprocess.run(['yt-dlp', '-x', '--audio-format', 'mp3', '-o', f"{video_id}.%(ext)s", f"https://www.youtube.com/watch?v={video_id}"], check=True, capture_output=True)
            print(f"🟢 Audio downloaded: {audio_filename}")
            
            subprocess.run(['python3', 'transcribe_audio.py', audio_filename, '--gcs-bucket', GCS_BUCKET, '--output-file', filename], check=True, capture_output=True)
            print("🟢 Transcription complete.")
            
            with open(filename, "r", encoding="utf-8") as f: text = f.read()
            os.remove(audio_filename)

        print(f"🟢 Saved transcript via {method_name}: {filename}")
        if combined_file_handle and text:
            combined_file_handle.write(f"## Transcript File: {filename}\n")
            combined_file_handle.write(f"## Video Title: {yt.title}\n")
            combined_file_handle.write(f"## Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            combined_file_handle.write('-'*40 + "\n" + text + "\n\n")
        
        return True, "new"

    except subprocess.CalledProcessError as e:
        print(f"🔴 Subprocess error for {video_id}: {e.stderr.decode('utf-8') if e.stderr else 'No stderr'}")
        return False, "error"
    except Exception as e:
        print(f"🔴 Error processing {video_id}: {str(e)}")
        return False, "error"

# --- Main Feature Functions ---

def process_channel(api_key, channel_id, output_file, **kwargs):
    """Processes all videos from a channel."""
    video_ids = get_channel_videos(api_key, channel_id)
    if not video_ids: return

    print(f"\n{'='*40}\nStarting transcript processing for the channel.")
    stats = {"new": 0, "skipped": 0, "error": 0}

    with open(output_file, "a", encoding="utf-8") as combined:
        for vid in video_ids:
            success, status = download_and_save_transcript(vid, combined_file_handle=combined, **kwargs)
            stats[status] += 1
            
    print(f"\n{'='*40}\nChannel Processing Complete")
    print(f"Total Videos: {len(video_ids)}, New: {stats['new']}, Skipped: {stats['skipped']}, Errors: {stats['error']}")

def combine_local_files(output_file):
    """Combines all local transcript files into one."""
    print(f"🚀 Starting local transcript combination...")
    files = [f for f in os.listdir() if f.endswith("-transcript.txt")]
    if not files:
        print("❌ No transcript files found.")
        return
    
    with open(output_file, "w", encoding="utf-8") as combined:
        combined.write(f"Combined Transcripts (from local files)\nGenerated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*40}\n\n")
        for filename in sorted(files):
            try:
                with open(filename, "r", encoding="utf-8") as f: content = f.read()
                combined.write(f"## Episode Transcript: {filename}\n{content}\n\n")
            except Exception as e:
                print(f"❌ Error processing {filename}: {str(e)}")
    
    print(f"\n✅ All local transcripts combined into: {output_file}")

# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser(description="A tool to download and manage YouTube video transcripts.", epilog=f"Default transcription method is Google Cloud Speech using bucket '{GCS_BUCKET}'.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--channel", choices=CHANNELS.keys(), help="The friendly name of the channel to process.")
    group.add_argument("--video-id", help="A single YouTube video ID to download a transcript for.")
    group.add_argument("--combine-only", action="store_true", help="Combine all local *-transcript.txt files and exit.")
    group.add_argument("--list-channels", action="store_true", help="List all pre-configured channels and exit.")

    parser.add_argument("--api-key", default=os.getenv("YOUTUBE_API_KEY"), help="YouTube Data API key.")
    parser.add_argument("--output-file", default="master-transcript.txt", help="The name of the combined output file.")
    
    method_group = parser.add_mutually_exclusive_group()
    method_group.add_argument("--use-whisper", action="store_true", help="Use local yt-dlp and whisper for transcription.")
    method_group.add_argument("--use-api", action="store_true", help="Use the (unreliable) youtube-transcript-api directly.")

    args = parser.parse_args()

    if args.list_channels:
        for name, channel_id in CHANNELS.items(): print(f"  - {name}: {channel_id}")
        return

    if args.combine_only:
        combine_local_files(args.output_file)
        return

    if (args.channel or args.video_id) and not args.api_key:
        parser.error("API key not found in .env file or via --api-key argument.")

    kwargs = {"use_whisper": args.use_whisper, "use_api": args.use_api}
    if args.channel:
        process_channel(args.api_key, CHANNELS[args.channel], args.output_file, **kwargs)
    
    if args.video_id:
        success, _ = download_and_save_transcript(args.video_id, **kwargs)
        print(f"\n✅ Single transcript operation {'completed' if success else 'failed'}.")

if __name__ == "__main__":
    main()
