import logging
from typing import List
from instagrapi import Client

class InstagramUploader:
    def upload_photo(self, client: Client, path: str, caption: str):
        """Uploads a single photo to Instagram."""
        logging.info(f"Uploading photo from {path} with caption: '{caption[:30]}...'")
        try:
            client.photo_upload(path, caption=caption)
            logging.info("Photo upload successful.")
        except Exception as e:
            logging.error(f"Failed to upload photo {path}: {e}")
            raise

    def upload_video(self, client: Client, path: str, caption: str):
        """Uploads a single video to Instagram."""
        logging.info(f"Uploading video from {path} with caption: '{caption[:30]}...'")
        try:
            client.video_upload(path, caption=caption)
            logging.info("Video upload successful.")
        except Exception as e:
            logging.error(f"Failed to upload video {path}: {e}")
            raise

    def upload_album(self, client: Client, paths: List[str], caption: str):
        """Uploads an album of photos and videos to Instagram."""
        if not paths or len(paths) < 2:
            raise ValueError("An album must contain at least 2 media files.")
        
        logging.info(f"Uploading album with {len(paths)} items and caption: '{caption[:30]}...'")
        try:
            client.album_upload(paths, caption=caption)
            logging.info("Album upload successful.")
        except Exception as e:
            logging.error(f"Failed to upload album: {e}")
            raise
