import logging
import os
import moviepy.editor as mp
from PIL import Image

def is_video_file(path: str) -> bool:
    return path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))

class MediaCombiner:
    @staticmethod
    def combine(base_path: str, output_path: str, s1_layer_path: str = None, s2_layer_path: str = None, s3_audio_path: str = None) -> str:
        """
        Overlays watermark layers onto a media file and handles audio for videos.
        """
        if is_video_file(base_path):
            return MediaCombiner._combine_video(base_path, output_path, s1_layer_path, s2_layer_path, s3_audio_path)
        else:
            return MediaCombiner._combine_image(base_path, output_path, s1_layer_path, s2_layer_path)

    @staticmethod
    def _combine_image(base_image_path: str, output_path: str, s1_layer_path: str, s2_layer_path: str) -> str:
        try:
            base_image = Image.open(base_image_path).convert("RGBA")
            if s1_layer_path and os.path.exists(s1_layer_path):
                with Image.open(s1_layer_path) as layer1:
                    base_image.paste(layer1, (0, 0), layer1)
            if s2_layer_path and os.path.exists(s2_layer_path):
                with Image.open(s2_layer_path) as layer2:
                    base_image.paste(layer2, (0, 0), layer2)
            final_image = base_image.convert("RGB")
            final_image.save(output_path, format='JPEG', quality=100, optimize=True, subsampling=0)
            return output_path
        except Exception as e:
            logging.error(f"Error combining image {base_image_path}: {e}")
            raise

    @staticmethod
    def _combine_video(base_video_path: str, output_path: str, s1_layer_path: str, s2_layer_path: str, s3_audio_path: str) -> str:
        video_clip = s1_clip = s2_clip = audio_clip = None
        try:
            video_clip = mp.VideoFileClip(base_video_path)
            
            # Prepare video layers
            clips_to_composite = [video_clip]
            if s1_layer_path and os.path.exists(s1_layer_path):
                s1_clip = mp.ImageClip(s1_layer_path).set_duration(video_clip.duration).set_position(("center", "center"))
                clips_to_composite.append(s1_clip)
            if s2_layer_path and os.path.exists(s2_layer_path):
                s2_clip = mp.ImageClip(s2_layer_path).set_duration(video_clip.duration).set_position(("center", "center"))
                clips_to_composite.append(s2_clip)
            
            final_video = mp.CompositeVideoClip(clips_to_composite)

            # Step 12.7: Handle audio replacement
            if s3_audio_path and os.path.exists(s3_audio_path):
                logging.info(f"Replacing audio for {os.path.basename(base_video_path)} with {os.path.basename(s3_audio_path)}")
                audio_clip = mp.AudioFileClip(s3_audio_path)
                # The audio is already trimmed, just set it
                final_video = final_video.set_audio(audio_clip)
            else:
                # Keep original audio if no new audio is provided
                final_video.audio = video_clip.audio
                logging.info(f"Keeping original audio for {os.path.basename(base_video_path)}")

            final_video.write_videofile(
                output_path, 
                codec='libx264', 
                audio_codec='aac',
                preset='medium', 
                ffmpeg_params=['-crf', '18'], 
                threads=4
            )
            return output_path
        except Exception as e:
            logging.error(f"Error combining video {base_video_path}: {e}")
            raise
        finally:
            # Close all clips to free up resources
            if video_clip: video_clip.close()
            if s1_clip: s1_clip.close()
            if s2_clip: s2_clip.close()
            if audio_clip: audio_clip.close()
            if 'final_video' in locals() and final_video: final_video.close()
