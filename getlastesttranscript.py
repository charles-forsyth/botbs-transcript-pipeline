import os
import re
from pytubefix import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from datetime import datetime

# Configuration
CHANNEL_ID = "UCpwXkp5XwIw_WVswz9bzBUw"
API_KEY = "AIzaSyA-MIvoI7M3SlMiskp37Z8tJhOTEsKl1Kk"
COMBINED_FILE = "all-transcripts.txt"

def slugify(text):
    """Sanitize text for filenames"""
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s:]+', '_', text)
    return text.lower().strip('_')

def get_channel_videos():
    """Fetch all video IDs from specified channel with verbose logging"""
    print(f"\n{'='*40}")
    print(f"Fetching videos for channel ID: {CHANNEL_ID}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    youtube = build("youtube", "v3", developerKey=API_KEY)
    
    try:
        channel = youtube.channels().list(
            part="contentDetails",
            id=CHANNEL_ID
        ).execute()
        playlist_id = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        print(f"Found uploads playlist: {playlist_id}")
    except Exception as e:
        print(f"Error fetching channel info: {str(e)}")
        return []

    video_ids = []
    next_page_token = None
    page_count = 1

    while True:
        try:
            print(f"\nFetching page {page_count}...")
            playlist = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            ).execute()

            new_ids = [item["snippet"]["resourceId"]["videoId"] for item in playlist["items"]]
            video_ids.extend(new_ids)
            print(f"Page {page_count}: Found {len(new_ids)} videos (Total: {len(video_ids)})")

            next_page_token = playlist.get("nextPageToken")
            if not next_page_token:
                print("\nReached end of playlist")
                break
                
            page_count += 1

        except Exception as e:
            print(f"Error fetching page {page_count}: {str(e)}")
            break

    print(f"\nTotal videos found: {len(video_ids)}")
    print(f"Fetch complete at: {datetime.now().strftime('%H:%M:%S')}")
    return video_ids

def process_videos(video_ids):
    """Download transcripts with enhanced logging and combining"""
    print(f"\n{'='*40}")
    print("Starting transcript processing")
    
    existing_files = set(os.listdir())
    new_count = 0
    skip_count = 0
    error_count = 0

    try:
        with open(COMBINED_FILE, "a", encoding="utf-8") as combined:
            combined.write(f"\n\n{'='*40}\n")
            combined.write(f"Processing Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            combined.write(f"Channel ID: {CHANNEL_ID}\n")
            combined.write('='*40 + "\n\n")

            for idx, vid in enumerate(video_ids, 1):
                try:
                    print(f"\nProcessing video {idx}/{len(video_ids)}:")
                    print(f"Video ID: {vid}")
                    
                    # Get video metadata
                    yt = YouTube(f"https://youtube.com/watch?v={vid}")
                    title = slugify(yt.title)
                    filename = f"{title}-{vid}-transcript.txt"
                    print(f"Video Title: {yt.title}")
                    print(f"Generated Filename: {filename}")

                    # Skip existing files
                    if filename in existing_files:
                        print("🟡 Existing transcript found - skipping")
                        skip_count += 1
                        continue
                    
                    # Download transcript
                    print("🔵 Downloading transcript...")
                    transcript = YouTubeTranscriptApi.get_transcript(vid)
                    text = " ".join([entry['text'] for entry in transcript])
                    
                    # Save individual file
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(text)
                    print(f"🟢 Saved individual transcript: {filename}")
                    
                    # Add to combined file with metadata
                    combined.write(f"## Transcript File: {filename}\n")
                    combined.write(f"## Video Title: {yt.title}\n")
                    combined.write(f"## Video ID: {vid}\n")
                    combined.write(f"## Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    combined.write('-'*40 + "\n")
                    combined.write(text + "\n\n")
                    new_count += 1

                except Exception as e:
                    error_count += 1
                    print(f"🔴 Error processing {vid}: {str(e)}")

        print(f"\n{'='*40}")
        print("Processing Complete")
        print(f"Total Videos: {len(video_ids)}")
        print(f"New Transcripts: {new_count}")
        print(f"Skipped Existing: {skip_count}")
        print(f"Errors: {error_count}")

    except Exception as e:
        print(f"Fatal error during processing: {str(e)}")

if __name__ == "__main__":
    print(f"🚀 Starting YouTube Transcript Archiver 🚀")
    print(f"Channel ID: {CHANNEL_ID}")
    print(f"Combined Output: {COMBINED_FILE}")
    
    videos = get_channel_videos()
    
    if videos:
        process_videos(videos)
        print(f"\n✅ Operation completed successfully ✅")
    else:
        print("\n❌ No videos found or error fetching channel content ❌")

