#!/usr/bin/env python3

import argparse
import os
import sys
import datetime
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import storage
from google.api_core import exceptions

def upload_blob(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    print(f"Uploading {source_file_name} to gs://{bucket_name}/{destination_blob_name}", file=sys.stderr)
    blob.upload_from_filename(source_file_name)
    print(f"File {source_file_name} uploaded to {destination_blob_name}.", file=sys.stderr)
    return f"gs://{bucket_name}/{destination_blob_name}"

def delete_blob(bucket_name, blob_name):
    """Deletes a blob from the bucket."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        print(f"Deleting gs://{bucket_name}/{blob_name}", file=sys.stderr)
        blob.delete()
        print(f"Blob {blob_name} deleted.", file=sys.stderr)
    except exceptions.NotFound:
        print(f"Blob {blob_name} not found in bucket {bucket_name}, skipping delete.", file=sys.stderr)
    except Exception as e:
        print(f"Error deleting blob {blob_name}: {e}", file=sys.stderr)


def transcribe_gcs_long_running(project_id: str, gcs_uri: str) -> str | None:
    """Transcribes an audio file from Google Cloud Storage using the long-running operation."""
    print(f"Using project: '{project_id}'", file=sys.stderr)
    try:
        client = speech.SpeechClient()

        audio = speech.RecognitionAudio(uri=gcs_uri)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.MP3,
            sample_rate_hertz=16000,
            language_code="en-US",
            model="default"
        )

        print(f"Sending audio for long-running transcription from GCS: {gcs_uri}", file=sys.stderr)
        operation = client.long_running_recognize(config=config, audio=audio)

        print("Waiting for operation to complete...", file=sys.stderr)
        response = operation.result(timeout=None)  # Wait indefinitely for transcription

        transcript = []
        for result in response.results:
            transcript.append(result.alternatives[0].transcript)
        
        return " ".join(transcript)

    except exceptions.GoogleAPICallError as e:
        print(f"Error during long-running speech transcription: {e}", file=sys.stderr)
        print("Please check your authentication, API permissions, and ensure the GCS URI is valid.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return None

def main():
    """Parses command-line arguments and calls the transcription function."""
    parser = argparse.ArgumentParser(
        description="Transcribe an MP3 audio file using Google Cloud Speech-to-Text, handling large files via GCS.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # --- Input Arguments ---
    input_group = parser.add_argument_group('Input Options')
    input_group.add_argument(
        "audio_file", type=str,
        help="Path to the MP3 audio file to transcribe."
    )

    # --- Output Arguments ---
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument(
        "--output-file", type=str, default=None,
        help="Path to save the transcription. If not specified, prints to stdout."
    )

    # --- GCS Configuration ---
    gcs_group = parser.add_argument_group('Google Cloud Storage Configuration')
    gcs_group.add_argument(
        "--gcs-bucket", type=str, required=True,
        help="The name of the GCS bucket to upload the audio file to for transcription."
    )

    # --- Project Configuration ---
    project_group = parser.add_argument_group('Project Configuration')
    project_group.add_argument(
        "--project-id", type=str, default=os.environ.get("GCLOUD_PROJECT", "ucr-research-computing"),
        help="Your Google Cloud project ID."
    )

    args = parser.parse_args()

    gcs_blob_name = None
    try:
        # Generate a unique blob name for the GCS upload
        file_basename = os.path.basename(args.audio_file)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        gcs_blob_name = f"audio_transcription/{timestamp}_{file_basename}"

        # Upload the audio file to GCS
        gcs_uri = upload_blob(args.gcs_bucket, args.audio_file, gcs_blob_name)
        if not gcs_uri:
            sys.exit(1)

        # Transcribe from GCS
        transcription = transcribe_gcs_long_running(args.project_id, gcs_uri)

        if transcription is not None:
            if args.output_file:
                with open(args.output_file, "w") as f:
                    f.write(transcription)
                print(f"Transcription written to '{args.output_file}'", file=sys.stderr)
            else:
                print(transcription)
        else:
            sys.exit(1) # Exit with error code if transcription failed

    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting.", file=sys.stderr)
        sys.exit(0)
    finally:
        # Clean up the GCS blob
        if gcs_blob_name:
            delete_blob(args.gcs_bucket, gcs_blob_name)


if __name__ == "__main__":
    main()
