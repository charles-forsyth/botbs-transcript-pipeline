import importlib
import youtube_transcript_api

print("Before reload:", dir(youtube_transcript_api))

# Attempt to reload the module
importlib.reload(youtube_transcript_api)

print("After reload:", dir(youtube_transcript_api))

# Try to access get_transcript directly (should fail if it's not exposed)
try:
    # This line is expected to fail with the AttributeError if the problem persists
    transcript_func = youtube_transcript_api.get_transcript
    print("get_transcript found directly in module.")
except AttributeError:
    print("get_transcript not found directly in module. Searching deeper...")
    
# Attempt to find get_transcript in potential submodules or classes
# This is a generic search, as we still don't know the exact internal structure if direct import fails.
found_get_transcript = False
for name in dir(youtube_transcript_api):
    attr = getattr(youtube_transcript_api, name)
    if callable(attr) and "get_transcript" in name:
        print(f"Found potential get_transcript function: {name}")
        found_get_transcript = True
    elif isinstance(attr, type) and hasattr(attr, 'get_transcript'):
        print(f"Found get_transcript method on class: {name}.{attr.get_transcript}")
        found_get_transcript = True

if not found_get_transcript:
    print("Could not find get_transcript anywhere obvious.")
