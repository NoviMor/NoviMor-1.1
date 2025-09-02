import os
import logging
import moviepy.editor as mp
from datetime import datetime

class GIFConverter:
    @staticmethod
    def convert(path: str) -> str:
        """
        Converts a GIF file to an MP4 video, preserving quality and dimensions.
        The output file will have a new name to avoid conflicts.
        """
        logging.info(f"Starting GIF to MP4 conversion for: {os.path.basename(path)}")
        clip = None
        try:
            clip = mp.VideoFileClip(path)
            
            # Create a new, unique filename for the output
            base_name = os.path.splitext(os.path.basename(path))[0]
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            out_name = f"{base_name}_{timestamp}.mp4"
            out_path = os.path.join(os.path.dirname(path), out_name)

            # Write the video file with a standard codec and no audio
            clip.write_videofile(out_path, codec='libx264', preset='slow', ffmpeg_params=['-crf','18'], audio=False, logger='bar', threads=4)
            
            logging.info(f"Successfully converted GIF to MP4: {out_name}")
            return out_path
        except Exception as e:
            logging.error(f"Error converting GIF {path} to MP4: {e}")
            raise
        finally:
            # Ensure the clip is closed to release file locks
            if clip:
                clip.close()
