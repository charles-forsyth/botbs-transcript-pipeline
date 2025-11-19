from youtube_transcript_api import YouTubeTranscriptApi
import os

# A known video ID that should have a transcript
VIDEO_ID = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up

try:
    print(f"Attempting to fetch transcript for video ID: {VIDEO_ID}")
    api_client = YouTubeTranscriptApi()
    transcript_object = api_client.fetch(video_id=VIDEO_ID)

    print("Successfully fetched transcript object!")

    if hasattr(transcript_object, 'snippets') and isinstance(transcript_object.snippets, list):
        print(f"Found 'snippets' attribute, which is a list. Length: {len(transcript_object.snippets)}")
        if transcript_object.snippets:
            first_snippet = transcript_object.snippets[0]
            print(f"Type of first snippet: {type(first_snippet)}")
            print(f"Attributes of first snippet: {dir(first_snippet)}")
            
            # Attempt to find the text attribute on the snippet
            if hasattr(first_snippet, 'text'):
                print(f"Found 'text' attribute on first snippet: {first_snippet.text}")
            else:
                print("No 'text' attribute found on first snippet. Searching for other text-like attributes...")
                for attr_name in dir(first_snippet):
                    if "text" in attr_name and not attr_name.startswith('_'):
                        print(f"Found potential text-like attribute: {attr_name} = {getattr(first_snippet, attr_name)}")

        else:
            print("'snippets' list is empty.")
    else:
        print("'transcript_object' does not have a 'snippets' attribute or it is not a list.")

except Exception as e:
    print(f"An error occurred while fetching transcript: {e}")
