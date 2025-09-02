import logging
import moviepy.editor as mp

class MusicAdder:
    """
    Handles audio processing, specifically trimming audio to match video duration.
    """

    @staticmethod
    def _parse_time(time_str: str) -> float:
        """Converts MM:SS format to seconds."""
        try:
            minutes, seconds = map(int, time_str.split(':'))
            return float(minutes * 60 + seconds)
        except ValueError:
            logging.error(f"Invalid time format for '{time_str}'. Must be MM:SS.")
            raise ValueError("Invalid time format. Please use MM:SS.")

    @staticmethod
    def trim_audio(audio_path: str, video_duration: float, start_time_str: str, output_path: str) -> None:
        """
        Trims an audio file to match the video's duration, starting from a specific time.

        Args:
            audio_path (str): Path to the input audio file.
            video_duration (float): Duration of the video in seconds.
            start_time_str (str): The start time for the audio in "MM:SS" format.
            output_path (str): Path to save the trimmed audio file.
        
        Raises:
            ValueError: If the start time is invalid or longer than the audio duration.
        """
        audio_clip = None
        try:
            start_time_sec = MusicAdder._parse_time(start_time_str)
            
            logging.info(f"Trimming audio '{audio_path}' to {video_duration}s, starting at {start_time_sec}s.")
            
            audio_clip = mp.AudioFileClip(audio_path)
            
            if start_time_sec >= audio_clip.duration:
                raise ValueError("The requested start time is after the audio clip ends.")

            # Trim the audio clip
            end_time_sec = min(start_time_sec + video_duration, audio_clip.duration)
            trimmed_clip = audio_clip.subclip(start_time_sec, end_time_sec)
            
            # If the trimmed audio is shorter than the video, it will just be that length.
            # The final combination step will handle looping or silence if needed,
            # but for now, we just provide the trimmed segment.
            
            trimmed_clip.write_audiofile(output_path, codec='mp3')
            logging.info(f"Trimmed audio saved to '{output_path}'.")

        finally:
            if audio_clip:
                audio_clip.close()
            if 'trimmed_clip' in locals() and trimmed_clip:
                trimmed_clip.close()
