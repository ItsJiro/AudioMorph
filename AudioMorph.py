import os
import time
import logging
from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.video.io.ImageSequenceClip import ImageSequenceClip
from moviepy.video.VideoClip import ImageClip
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import traceback
import requests
from googleapiclient.errors import HttpError

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()

# Directories
mp3_folder = 'Songs'
cover_folder = 'Covers'
output_folder = 'Output'
default_cover_path = 'default.jpg'

# Google API setup
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def authenticate_youtube():
    """Authenticate and create a YouTube API client."""
    try:
        # Check if the token.pickle file exists
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(requests.Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'client_secret.json', SCOPES)
                creds = flow.run_local_server(port=8080)

            # Save credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        youtube = build('youtube', 'v3', credentials=creds)
        logger.debug("YouTube authentication successful.")
        return youtube
    except Exception as e:
        logger.error(f"Error during YouTube authentication: {e}")
        traceback.print_exc()

def get_cover_art(audio_path, cover_folder):
    """Extract cover art for MP3 files or fetch cover for WAV files."""
    if audio_path.endswith(".mp3"):
        try:
            audio = MP3(audio_path, ID3=ID3)
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    cover_art_path = os.path.join(cover_folder, os.path.basename(audio_path) + '_cover.jpg')
                    with open(cover_art_path, 'wb') as img_file:
                        img_file.write(tag.data)
                    logger.debug(f"Cover art extracted from MP3: {cover_art_path}")
                    return cover_art_path
        except Exception as e:
            logger.error(f"Error extracting cover art: {e}")
            traceback.print_exc()

    # Handle WAV files
    song_name = os.path.splitext(os.path.basename(audio_path))[0]
    potential_cover = os.path.join(cover_folder, f"{song_name}.jpg")

    # Check if user-provided cover exists
    if os.path.exists(potential_cover):
        logger.debug(f"Using user-provided cover art: {potential_cover}")
        return potential_cover

    # Fetch cover art from iTunes if user-provided cover art isn't found
    cover_url = fetch_cover_art(song_name)
    if cover_url:
        response = requests.get(cover_url, timeout=5)
        if response.status_code == 200:
            with open(potential_cover, "wb") as img_file:
                img_file.write(response.content)
            logger.debug(f"Downloaded cover art: {potential_cover}")
            return potential_cover

    # Default cover if no match found
    logger.debug("Using default cover art.")
    return default_cover_path


def fetch_cover_art(song_name):
    """Fetch cover art from iTunes API based on the song name."""
    try:
        search_url = f"https://itunes.apple.com/search?term={song_name}&entity=song&limit=1"
        response = requests.get(search_url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data["resultCount"] > 0:
                cover_url = data["results"][0]["artworkUrl100"].replace("100x100", "600x600")  # Get higher quality
                return cover_url
    except Exception as e:
        logger.error(f"Error fetching cover art: {e}")
        traceback.print_exc()
    
    return None


def create_video(mp3_path, cover_art_path, output_path):
    """Create a video from MP3 and cover art."""
    try:
        # Load audio file
        audio = AudioFileClip(mp3_path)

        # Create a still image video
        image = ImageClip(cover_art_path).with_duration(audio.duration).with_fps(24)
        video = image.with_audio(audio)

        video.write_videofile(output_path, codec='libx264', audio_codec='aac', threads=4)
        logger.debug(f"Video created: {output_path}")
    except Exception as e:
        logger.error(f"Error creating video: {e}")
        traceback.print_exc()

def upload_to_youtube(video_file, title, youtube):
    """Upload video to YouTube."""
    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=dict(
                snippet=dict(
                    title=title,
                    categoryId="10",  # Music category
                ),
                status=dict(
                    privacyStatus="unlisted"
                ),
            ),
            media_body=video_file
        )
        response = request.execute()
        logger.debug(f"Video uploaded: {response['id']}")
    except HttpError as e:
        logger.error(f"Error uploading to YouTube: {e}")
        traceback.print_exc()

def process_and_upload(mp3_folder, cover_folder, output_folder, youtube):
    """Process MP3 files, create videos, and upload to YouTube."""
    try:
        for filename in os.listdir(mp3_folder):
            if filename.endswith((".mp3", ".wav")):
                mp3_path = os.path.join(mp3_folder, filename)
                logger.debug(f"Processing MP3: {mp3_path}")

                # Get cover art (either from metadata or default)
                cover_art_path = get_cover_art(mp3_path, cover_folder)
                # Create video file path
                output_video_path = os.path.join(output_folder, f"{os.path.splitext(filename)[0]}.mp4")

                # Create the video
                create_video(mp3_path, cover_art_path, output_video_path)

                # Upload the video to YouTube
                title = f"{os.path.splitext(filename)[0]}"
                upload_to_youtube(output_video_path, title, youtube)

                # Clean up cover art
                if cover_art_path != default_cover_path and os.path.exists(cover_art_path):
                    os.remove(cover_art_path)
                    logger.debug(f"Cover art deleted: {cover_art_path}")

                # Wait a moment between uploads to avoid API rate limit
                time.sleep(5)

    except Exception as e:
        logger.error(f"Error during processing: {e}")
        traceback.print_exc()

def main():
    """Main function to execute the script."""
    try:
        logger.debug("Script started.")
        youtube = authenticate_youtube()
        process_and_upload(mp3_folder, cover_folder, output_folder, youtube)
        logger.debug("Script finished.")
    except Exception as e:
        logger.error(f"Critical error in main function: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
