import logging
from PIL import Image

class ImageProcessor:
    """
    Handles the final processing of images to prepare them for Instagram.
    """
    TARGET_SIZE = 1080  # For a 1080x1080 square canvas

    @staticmethod
    def process(path: str, output_path: str) -> str:
        """
        Processes a single image to fit within a 1080x1080 square with a black background,
        maintaining its original aspect ratio.

        Args:
            path (str): The path to the input image.
            output_path (str): The path to save the processed image.

        Returns:
            The path to the processed image.
        """
        try:
            # 14.2: Create a black background of size 1080x1080
            background = Image.new('RGB', (ImageProcessor.TARGET_SIZE, ImageProcessor.TARGET_SIZE), 'black')
            
            with Image.open(path) as img:
                # 14.1 & 14.3: Get dimensions and calculate new size
                img.thumbnail((ImageProcessor.TARGET_SIZE, ImageProcessor.TARGET_SIZE), Image.Resampling.LANCZOS)
                
                # 14.4: Calculate position to paste the image in the center
                paste_x = (ImageProcessor.TARGET_SIZE - img.width) // 2
                paste_y = (ImageProcessor.TARGET_SIZE - img.height) // 2
                
                # Paste the resized image onto the black background
                background.paste(img, (paste_x, paste_y))

            # Save the final image
            background.save(output_path, format='WEBP', quality=100, lossless=True, method=6, optimize=True, subsampling=0)
            logging.info(f"Successfully processed image '{path}' and saved to '{output_path}'")
            return output_path
            
        except Exception as e:
            logging.error(f"Failed to process image at {path}: {e}")
            raise
