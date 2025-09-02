import os
import logging
from PIL import Image, ImageDraw, ImageFont
from typing import Tuple

import textwrap

class WatermarkEngine:
    """
    Handles the creation of both image and text watermark layers.
    """

    @staticmethod
    def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
        """Wraps text to fit a specified width."""
        
        # The textwrap library is a simpler and more robust way to handle this.
        # We need to estimate an average character width to tell textwrap how many chars to wrap at.
        avg_char_width = font.getbbox("x")[2]
        if avg_char_width == 0: # Handle potential empty or zero-width bbox
            avg_char_width = font.getbbox("a")[2] # Fallback
            if avg_char_width == 0:
                return text # Cannot wrap, return original text

        # Calculate wrap width in characters
        wrap_width = int(max_width / avg_char_width)
        
        # Use textwrap to handle wrapping
        lines = textwrap.wrap(text, width=wrap_width)
        
        # In case textwrap estimation is off, we do a final check
        # This is a fallback and might not be perfect, but more robust than full manual wrapping.
        final_lines = []
        for line in lines:
            while font.getbbox(line)[2] > max_width:
                # If a line is still too long, trim words from the end.
                # This can happen with very long words.
                line = line[:-1]
            final_lines.append(line)

        return "\n".join(final_lines)

    @staticmethod
    def _calculate_position(
        layer_size: Tuple[int, int],
        watermark_size: Tuple[int, int],
        position: str,
        margin: int = 0
    ) -> Tuple[int, int]:
        """Calculates the (x, y) coordinates for the watermark based on a position string and a margin."""
        layer_width, layer_height = layer_size
        wm_width, wm_height = watermark_size
        
        # Horizontal positioning
        if 'left' in position:
            x = 50
        elif 'center' in position:
            x = (layer_width - wm_width) // 2
        elif 'right' in position:
            x = layer_width - wm_width - 50
        else: # Default to center
            x = (layer_width - wm_width) // 2

        # Vertical positioning
        if 'top' in position:
            y = 50
        elif 'middle' in position:
            y = (layer_height - wm_height) // 2
        elif 'bottom' in position:
            y = layer_height - wm_height - 50
        else: # Default to middle
            y = (layer_height - wm_height) // 2
            
        return (x, y)

    @staticmethod
    def create_image_watermark_layer(
        media_dimensions: Tuple[int, int],
        watermark_path: str,
        position: str,
        scale_percent: int,
        opacity_percent: int,
        output_path: str
    ) -> None:
        """
        Creates a transparent layer with a scaled and positioned image watermark.
        """
        logging.info(f"Creating image watermark layer for media size {media_dimensions}")
        
        # Create a transparent background layer matching the media size
        transparent_layer = Image.new('RGBA', media_dimensions, (0, 0, 0, 0))
        
        with Image.open(watermark_path).convert("RGBA") as watermark_img:
            # Scale the watermark
            scale_ratio = scale_percent / 100.0
            new_size = (int(watermark_img.width * scale_ratio), int(watermark_img.height * scale_ratio))
            watermark_img = watermark_img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Adjust opacity
            alpha = watermark_img.split()[3]
            alpha = alpha.point(lambda p: p * (opacity_percent / 100.0))
            watermark_img.putalpha(alpha)
            
            # Calculate position and paste
            paste_position = WatermarkEngine._calculate_position(media_dimensions, watermark_img.size, position)
            transparent_layer.paste(watermark_img, paste_position, watermark_img)

        # Save the final layer
        transparent_layer.save(output_path, "PNG")
        logging.info(f"Image watermark layer saved to {output_path}")

    @staticmethod
    def create_text_watermark_layer(
        media_dimensions: Tuple[int, int],
        text: str,
        font_path: str,
        font_size: int,
        color: str,
        position: str,
        output_path: str
    ) -> None:
        """
        Creates a transparent layer with rendered, wrapped text with margins.
        """
        logging.info(f"Creating text watermark layer for media size {media_dimensions}")
        
        MARGIN = 30
        
        # Create a transparent background layer
        transparent_layer = Image.new('RGBA', media_dimensions, (0, 0, 0, 0))
        draw = ImageDraw.Draw(transparent_layer)
        
        try:
            font = ImageFont.truetype(font_path, font_size)
        except IOError:
            logging.error(f"Font file not found at {font_path}. Using default font.")
            font = ImageFont.load_default()

        # --- Text Wrapping Logic ---
        max_text_width = media_dimensions[0] - (2 * MARGIN)
        wrapped_text = WatermarkEngine._wrap_text(text, font, max_text_width)
        
        # Get wrapped text block size
        bbox = draw.textbbox((0, 0), wrapped_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Calculate position with margin and draw text
        text_position = WatermarkEngine._calculate_position(
            media_dimensions, (text_width, text_height), position, margin=MARGIN
        )
        
        # Color mapping
        color_map = {
            'white': (255, 255, 255), 'black': (0, 0, 0), 'red': (255, 0, 0),
            'blue': (0, 0, 255), 'yellow': (255, 255, 0), 'green': (0, 128, 0)
        }
        text_color = color_map.get(color.lower(), (255, 255, 255)) # Default to white
        
        draw.text(text_position, wrapped_text, font=font, fill=text_color, align="center")

        # Save the final layer
        transparent_layer.save(output_path, "PNG")
        logging.info(f"Text watermark layer saved to {output_path}")
