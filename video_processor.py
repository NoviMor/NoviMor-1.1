import logging
import moviepy.editor as mp

class VideoProcessor:
    """
    Handles the final processing of videos to prepare them for Instagram.
    """

    LANDSCAPE_SIZE = (1280, 720)
    PORTRAIT_SIZE = (720, 1280)

    @staticmethod
    def process(path: str, output_path: str) -> str:
        """
        Processes a single video to fit within a 1280x720 or 720x1280 canvas
        with a black background, maintaining its original aspect ratio and quality.

        Args:
            path (str): The path to the input video.
            output_path (str): The path to save the processed video.

        Returns:
            The path to the processed video.
        """
        video_clip = None
        try:
            video_clip = mp.VideoFileClip(path)
            
            # 15.1: Check dimensions to determine orientation
            is_landscape = video_clip.w >= video_clip.h
            
            # 15.2: Set target canvas size
            if is_landscape:
                target_size = VideoProcessor.LANDSCAPE_SIZE
                logging.info(f"Processing '{path}' as landscape video.")
            else:
                target_size = VideoProcessor.PORTRAIT_SIZE
                logging.info(f"Processing '{path}' as portrait video.")

            # 15.3: Resize video to fit the target canvas while maintaining aspect ratio
            resized_clip = video_clip.resize(height=target_size[1]) if is_landscape else video_clip.resize(width=target_size[0])
            
            # 15.2 & 15.4: Create a black background and composite the video on top
            background_clip = mp.ColorClip(size=target_size, color=(0, 0, 0), duration=video_clip.duration)
            
            final_clip = mp.CompositeVideoClip([background_clip, resized_clip.set_position("center")])
            
            # Ensure the original audio is preserved
            final_clip.audio = resized_clip.audio

            # 15.3.1: Write with high-quality settings
            final_clip.write_videofile(
                output_path,
                codec='libx265',
                audio_codec='aac',
                preset='slow',
                ffmpeg_params=[
                    '-crf', '18',                                        
                    '-b:a', '192k',
                    '-tag:v','hvc1',
                    '-movflags', '+faststart',
                    '-pix_fmt', 'yuv420p'
                ],
                threads=4
            )           
            
            logging.info(f"Successfully processed video '{path}' and saved to '{output_path}'")
            return output_path

        except Exception as e:
            logging.error(f"Failed to process video at {path}: {e}")
            raise
        finally:
            if video_clip:
                video_clip.close()
            if 'resized_clip' in locals() and resized_clip:
                resized_clip.close()
            if 'final_clip' in locals() and final_clip:
                final_clip.close()
            if 'background_clip' in locals() and background_clip:
                background_clip.close()
