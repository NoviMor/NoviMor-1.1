import os
import filetype
import logging
from typing import List

class FileValidator:
    """
    Validates files based on their type and extension as per Step 9 of the Holy Book.
    """
    IMAGE_EXTENSIONS: List[str] = ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']
    VIDEO_EXTENSIONS: List[str] = ['.mp4', '.avi', '.flv', '.webm', '.mov', '.mkv', '.wmv']
    GIF_EXTENSIONS: List[str] = ['.gif']

    @classmethod
    def validate(cls, file_path: str) -> str:
        """
        Validates a single file to ensure it is a supported image, video, or gif.

        Args:
            file_path (str): The path to the file to validate.

        Returns:
            str: The type of the file ('image', 'video', 'gif').

        Raises:
            ValueError: If the file type is not supported or the file does not exist.
        """
        if not os.path.exists(file_path):
            raise ValueError(f"File not found at path: {file_path}")

        # Primary validation using file extension as per Holy Book
        ext = os.path.splitext(file_path)[1].lower()

        if ext in cls.IMAGE_EXTENSIONS:
            logging.info(f"Validated {os.path.basename(file_path)} as 'image' based on extension.")
            return 'image'
        
        if ext in cls.VIDEO_EXTENSIONS:
            logging.info(f"Validated {os.path.basename(file_path)} as 'video' based on extension.")
            return 'video'
            
        if ext in cls.GIF_EXTENSIONS:
            logging.info(f"Validated {os.path.basename(file_path)} as 'gif' based on extension.")
            return 'gif'

        # Fallback to filetype library if extension is not recognized
        logging.warning(f"Extension '{ext}' not in known lists for {os.path.basename(file_path)}. Guessing with filetype library.")
        try:
            kind = filetype.guess(file_path)
            if kind:
                if kind.mime.startswith('image/gif'):
                    return 'gif'
                if kind.mime.startswith('image/'):
                    return 'image'
                if kind.mime.startswith('video/'):
                    return 'video'
        except Exception as e:
            logging.error(f"Could not use filetype library to guess type for {os.path.basename(file_path)}: {e}")

        # If all else fails, reject the file
        raise ValueError(f"Unsupported file type for file: {os.path.basename(file_path)}")
