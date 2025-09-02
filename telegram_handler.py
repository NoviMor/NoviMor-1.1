import logging
import os
import asyncio
import shutil
from datetime import datetime
from typing import List, Optional
from PIL import Image

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

from auth_manager import AuthManager
from image_processor import ImageProcessor
from video_processor import VideoProcessor
from media_processor import GIFConverter
from utils import FileValidator
from watermark_engine import WatermarkEngine
from add_music_to_video import MusicAdder
from combine_user_changes import MediaCombiner
from state_machine import States
from add_video_effects import EffectsEngine

media_counter = 1
MAX_AUTH_ATTEMPTS = 3

# --- Helper Functions ---
def get_media_dimensions(path: str) -> Optional[tuple]:
    try:
        if is_video_file(path):
            import moviepy.editor as mp
            with mp.VideoFileClip(path) as clip: return clip.size
        else:
            with Image.open(path) as img: return img.size
    except Exception as e:
        logging.error(f"Could not get dimensions for {path}: {e}"); return None

def get_video_duration(path: str) -> Optional[float]:
    try:
        import moviepy.editor as mp
        with mp.VideoFileClip(path) as clip:
            return clip.duration
    except Exception as e:
        logging.error(f"Could not get duration for video {path}: {e}")
        return None

def is_video_file(path: str) -> bool:
    return path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))

# --- Authentication Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logging.info("'/start' command received. Initiating authentication.")
    context.user_data['auth_attempts'] = 0
    ig_manager: AuthManager = context.application.bot_data['ig_manager']
    success, status = await asyncio.to_thread(ig_manager.login)
    if success:
        await update.message.reply_text("✅ Connection to Telegram and Instagram is successful.")
        return await send_welcome_message(update, context)
    if status == "2FA_REQUIRED":
        await update.message.reply_text("🔐 Please enter your 2FA code (from your authenticator app).")
        return States.AUTH_2FA
    elif status == "SMS_REQUIRED":
        await update.message.reply_text("📱 Please enter the SMS code sent to your phone.")
        return States.AUTH_SMS
    else:
        await update.message.reply_text(f"❌ Instagram login failed: {ig_manager.login_error_message}")
        return ConversationHandler.END

async def handle_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == '❌ Cancel': return await cancel(update, context)
    context.user_data['auth_attempts'] += 1
    if context.user_data['auth_attempts'] > MAX_AUTH_ATTEMPTS:
        await update.message.reply_text("❌ Too many incorrect attempts. Halting operation.")
        return ConversationHandler.END
    code = update.message.text.strip()
    ig_manager: AuthManager = context.application.bot_data['ig_manager']
    success, status = await asyncio.to_thread(ig_manager.login, two_factor_code=code)
    if success:
        await update.message.reply_text("✅ Instagram connection successful!")
        return await send_welcome_message(update, context)
    else:
        remaining_attempts = MAX_AUTH_ATTEMPTS - context.user_data['auth_attempts']
        await update.message.reply_text(f"❌ Incorrect 2FA code. Please try again. ({remaining_attempts} attempts remaining)")
        return States.AUTH_2FA

async def handle_sms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == '❌ Cancel': return await cancel(update, context)
    context.user_data['auth_attempts'] += 1
    if context.user_data['auth_attempts'] > MAX_AUTH_ATTEMPTS:
        await update.message.reply_text("❌ Too many incorrect attempts. Halting operation.")
        return ConversationHandler.END
    code = update.message.text.strip()
    ig_manager: AuthManager = context.application.bot_data['ig_manager']
    success, status = await asyncio.to_thread(ig_manager.login, verification_code=code)
    if success:
        await update.message.reply_text("✅ Instagram connection successful!")
        return await send_welcome_message(update, context)
    else:
        remaining_attempts = MAX_AUTH_ATTEMPTS - context.user_data['auth_attempts']
        await update.message.reply_text(f"❌ Incorrect SMS code. Please try again. ({remaining_attempts} attempts remaining)")
        return States.AUTH_SMS

async def send_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # --- Directory Cleanup Logic ---
    # Per user request, clear the contents of the downloads folder at the start of any new workflow.
    downloads_path = context.application.bot_data['downloads_path']
    try:
        if not os.path.exists(downloads_path):
            os.makedirs(downloads_path)
            logging.info(f"Downloads directory created at: {downloads_path}")
        else:
            logging.info(f"Clearing contents of downloads directory: {downloads_path}")
            for filename in os.listdir(downloads_path):
                file_path = os.path.join(downloads_path, filename)
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            logging.info("Downloads directory contents cleared.")
    except Exception as e:
        logging.error(f"Could not clear downloads directory {downloads_path}: {e}")
        await update.message.reply_text("⚠️ Warning: Could not clean up temporary file directory. Please check bot logs.")

    await update.message.reply_text("Welcome! You can send 'Cancel' at any point to stop the current operation.")
    keyboard = [['📤 Album', '📎 Single'], ['❌ Cancel']]
    await update.message.reply_text('🤖 Please choose an upload mode:', reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True))
    context.user_data.clear()
    return States.MEDIA_TYPE

# --- Media Handling and Validation ---
async def handle_media_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    mode = 'album' if 'Album' in text else 'single'
    context.user_data['mode'] = mode
    msg = "Please send up to 10 photos or videos. Press 'Done' when you have sent all your files." if mode == 'album' else "Please send one photo or video."
    keyboard = [['🏁 Done', '❌ Cancel']] if mode == 'album' else [['❌ Cancel']]
    context.user_data['files'] = []
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
    return States.RECEIVE_MEDIA

async def download_media(update: Update, context: ContextTypes.DEFAULT_TYPE, downloads_path: str) -> Optional[str]:
    global media_counter
    msg = update.message
    file_id = None
    ext = '.jpg' # Default
    if msg.photo:
        file_id = msg.photo[-1].file_id
    elif msg.video:
        file_id = msg.video.file_id
        ext = '.mp4'
    elif msg.animation:
        file_id = msg.animation.file_id
        ext = '.gif'
    
    if not file_id:
        await msg.reply_text('⚠️ Could not identify file to download!'); return None

    file = await context.bot.get_file(file_id)
    name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{media_counter:03d}{ext}"
    media_counter += 1
    path = os.path.join(downloads_path, name)
    await file.download_to_drive(path)
    logging.info(f'Downloaded: {path}')
    return path

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mode = context.user_data.get('mode', 'single')
    files = context.user_data.setdefault('files', [])
    if mode == 'album' and len(files) >= 10:
        await update.message.reply_text("You have already sent 10 files. Please press 'Done'.")
        return States.RECEIVE_MEDIA
    path = await download_media(update, context, context.application.bot_data['downloads_path'])
    if not path: return States.RECEIVE_MEDIA
    files.append(path)
    if mode == 'single':
        return await process_media(update, context)
    else:
        await update.message.reply_text(f"✅ Received file {len(files)} of 10.")
        return States.RECEIVE_MEDIA

async def process_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    files = context.user_data.get('files', [])
    mode = context.user_data.get('mode')
    if mode == 'album' and len(files) < 2:
        await update.message.reply_text("❌ Album uploads require at least 2 files. Your operation has been cancelled.", reply_markup=ReplyKeyboardRemove())
        return await start(update, context)
    await update.message.reply_text(f"Received {len(files)} file(s). Now starting validation...", reply_markup=ReplyKeyboardRemove())
    
    validated_files = []
    original_files = list(files) # Create a copy to iterate over
    conversion_occurred = False # Flag to check for GIF conversions

    for i, file_path in enumerate(original_files):
        try:
            file_type = FileValidator.validate(file_path)
            if file_type == 'gif':
                new_path = await asyncio.to_thread(GIFConverter.convert, file_path)
                original_files[i] = new_path
                file_path = new_path
                file_type = 'video'
                conversion_occurred = True # Set flag
            if file_type == 'video':
                duration = get_video_duration(file_path)
                if duration is None: raise ValueError(f"Could not read video duration for {os.path.basename(file_path)}.")
                if duration > 60:
                    await update.message.reply_text(f"❌ Video '{os.path.basename(file_path)}' is longer than 60 seconds ({duration:.1f}s) and cannot be processed.")
                    return await start(update, context)
            validated_files.append(file_path)
        except ValueError as e:
            await update.message.reply_text(f"❌ File '{os.path.basename(file_path)}' is not a supported type. Error: {e}")
            return await start(update, context)
            
    if not validated_files:
        await update.message.reply_text('No valid files to process.')
        return await start(update, context)
        
    context.user_data['processed'] = validated_files
    await update.message.reply_text('✅ File validation complete.')

    if conversion_occurred:
        await update.message.reply_text('Your GIF file(s) have been converted to video. Here is the preview:')
        return await send_previews(update, validated_files)
    else:
        # No conversion, so no need for an initial preview
        await update.message.reply_text('Do you want to continue with editing?', reply_markup=ReplyKeyboardMarkup([['✅ Yes, continue', '❌ No, Upload As Is'], ['❌ Cancel']], resize_keyboard=True))
        return States.CONFIRM

async def send_previews(update: Update, files: List[str]) -> int:
    media_group = [InputMediaPhoto(media=open(f, 'rb')) if not is_video_file(f) else InputMediaVideo(media=open(f, 'rb')) for f in files]
    await update.message.reply_media_group(media=media_group)
    await update.message.reply_text('Do you want to continue with editing?', reply_markup=ReplyKeyboardMarkup([['✅ Yes, continue', '❌ No, Upload As Is'], ['❌ Cancel']], resize_keyboard=True))
    return States.CONFIRM

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'Yes' in update.message.text:
        await update.message.reply_text('Do you want to add an image watermark?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No'], ['❌ Cancel']], one_time_keyboard=True))
        return States.ASK_IMAGE_WATERMARK
    else: # User chose 'No, Upload As Is'
        context.user_data['combined_files'] = context.user_data['processed']
        return await start_final_processing(update, context)

# --- Watermark Handlers ---
async def ask_image_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == 'Yes':
        await update.message.reply_text('Please send the watermark image file.', reply_markup=ReplyKeyboardRemove())
        return States.RECEIVE_IMAGE_WATERMARK
    else:
        return await ask_text_watermark(update, context)

async def receive_image_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text('That is not an image. Please send an image file.')
        return States.RECEIVE_IMAGE_WATERMARK
    
    watermark_file = await update.message.photo[-1].get_file()
    watermark_path = os.path.join(context.application.bot_data['downloads_path'], 'watermark_img.png')
    await watermark_file.download_to_drive(watermark_path)
    
    with Image.open(watermark_path) as img:
        w, h = img.size
        if not (120 <= max(w, h) <= 480):
            await update.message.reply_text('Watermark size invalid (must be 120-480px). Please try again.')
            return States.RECEIVE_IMAGE_WATERMARK
            
    context.user_data['image_watermark_path'] = watermark_path
    kb = [['top-left', 'top-center', 'top-right'], ['middle-left', 'middle-center', 'middle-right'], ['bottom-left', 'bottom-center', 'bottom-right'], ['❌ Cancel']]
    await update.message.reply_text('Choose watermark position:', reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
    return States.CHOOSE_IMG_WATERMARK_POSITION

async def handle_img_position(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['img_watermark_position'] = update.message.text.lower()
    keyboard = [['50', '60', '70'], ['80', '90', '100'], ['❌ Cancel']]
    await update.message.reply_text('Choose scale (50-100%):', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return States.CHOOSE_IMG_WATERMARK_SCALE

async def handle_img_scale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['img_watermark_scale'] = int(update.message.text)
    keyboard = [['100', '90', '80'], ['70', '60', '50'], ['❌ Cancel']]
    await update.message.reply_text('Choose opacity (50-100%):', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return States.CHOOSE_IMG_WATERMARK_OPACITY

async def generate_and_preview_image_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['img_watermark_opacity'] = int(update.message.text)
    await update.message.reply_text('⏳ Generating preview...', reply_markup=ReplyKeyboardRemove())
    
    media_dims = get_media_dimensions(context.user_data['processed'][0])
    if not media_dims:
        await update.message.reply_text('Error: Could not get media dimensions.'); return await cancel(update, context)
        
    output_path = os.path.join(context.application.bot_data['downloads_path'], 'S1_preview.png')
    try:
        await asyncio.to_thread(
            WatermarkEngine.create_image_watermark_layer,
            media_dimensions=media_dims,
            watermark_path=context.user_data['image_watermark_path'],
            position=context.user_data['img_watermark_position'],
            scale_percent=context.user_data['img_watermark_scale'],
            opacity_percent=context.user_data['img_watermark_opacity'],
            output_path=output_path
        )
        await update.message.reply_photo(photo=open(output_path, 'rb'), caption="Is this watermark okay?")
        await update.message.reply_text('Confirm this watermark?', reply_markup=ReplyKeyboardMarkup([['✅ Yes, Confirm', '❌ No, Retry'], ['❌ Cancel']], one_time_keyboard=True))
        return States.CONFIRM_IMG_WATERMARK
    except Exception as e:
        await update.message.reply_text(f"Error creating watermark preview: {e}"); return await cancel(update, context)

async def handle_img_watermark_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'No' in update.message.text:
        await update.message.reply_text('Do you want to add an image watermark?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No'], ['❌ Cancel']], one_time_keyboard=True))
        return States.ASK_IMAGE_WATERMARK
        
    await update.message.reply_text("Applying image watermark to all media...", reply_markup=ReplyKeyboardRemove())
    s1_layers = []
    downloads_path = context.application.bot_data['downloads_path']
    for i, media_path in enumerate(context.user_data['processed']):
        media_dims = get_media_dimensions(media_path)
        if not media_dims: continue
        output_path = os.path.join(downloads_path, f'S1_{i+1}.png')
        try:
            await asyncio.to_thread(
                WatermarkEngine.create_image_watermark_layer,
                media_dimensions=media_dims,
                watermark_path=context.user_data['image_watermark_path'],
                position=context.user_data['img_watermark_position'],
                scale_percent=context.user_data['img_watermark_scale'],
                opacity_percent=context.user_data['img_watermark_opacity'],
                output_path=output_path
            )
            s1_layers.append(output_path)
        except Exception as e:
            logging.error(f"Failed to create image watermark for {media_path}: {e}")
    context.user_data['S1_layers'] = s1_layers
    await update.message.reply_text('Image watermark layers created.')
    return await ask_text_watermark(update, context)

async def ask_text_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Do you want to add a text watermark?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No'], ['❌ Cancel']], one_time_keyboard=True))
    return States.ASK_TEXT_WATERMARK

async def handle_ask_text_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'Yes' in update.message.text:
        await update.message.reply_text('Please enter the text for the watermark.', reply_markup=ReplyKeyboardRemove())
        return States.RECEIVE_TEXT
    else:
        return await _check_and_ask_music(update, context)

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == '❌ Cancel': return await cancel(update, context)
    context.user_data['text_watermark_text'] = update.message.text
    font_names = [os.path.basename(f) for f in context.application.bot_data['font_files']]
    if not font_names:
        if context.application.bot_data['font_warning']:
            await update.message.reply_text(context.application.bot_data['font_warning'])
        return await _check_and_ask_music(update, context)
    keyboard = [[name] for name in font_names]
    keyboard.append(['❌ Cancel'])
    await update.message.reply_text('Choose a font:', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return States.CHOOSE_FONT

async def handle_font(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == '❌ Cancel': return await cancel(update, context)
    context.user_data['text_watermark_font'] = update.message.text
    keyboard = [['10', '15', '20'], ['25', '30', '35'], ['40', '45', '50'], ['❌ Cancel']]
    await update.message.reply_text('Choose font size (10-50):', reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return States.CHOOSE_FONT_SIZE

async def handle_font_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['text_watermark_size'] = int(update.message.text)
    colors = [['White', 'Black', 'Red'], ['Blue', 'Yellow', 'Green'], ['❌ Cancel']]
    await update.message.reply_text('Choose a color:', reply_markup=ReplyKeyboardMarkup(colors, one_time_keyboard=True))
    return States.CHOOSE_COLOR

async def handle_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['text_watermark_color'] = update.message.text
    positions = [['top–center'], ['middle–center'], ['bottom–center'], ['❌ Cancel']]
    await update.message.reply_text('Choose text position:', reply_markup=ReplyKeyboardMarkup(positions, one_time_keyboard=True))
    return States.CHOOSE_TEXT_POSITION

async def generate_and_preview_text_watermark(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['text_watermark_position'] = update.message.text.lower()
    await update.message.reply_text('⏳ Generating preview...', reply_markup=ReplyKeyboardRemove())

    media_dims = get_media_dimensions(context.user_data['processed'][0])
    if not media_dims:
        await update.message.reply_text('Error: Could not get media dimensions.'); return await cancel(update, context)
        
    font_name = context.user_data['text_watermark_font']
    font_path = next((f for f in context.application.bot_data['font_files'] if os.path.basename(f) == font_name), None)
    if not font_path:
        await update.message.reply_text(f"Error: Font '{font_name}' not found.")
        return await _check_and_ask_music(update, context)
        
    output_path = os.path.join(context.application.bot_data['downloads_path'], 'S2_preview.png')
    try:
        await asyncio.to_thread(
            WatermarkEngine.create_text_watermark_layer,
            media_dimensions=media_dims,
            text=context.user_data['text_watermark_text'],
            font_path=font_path,
            font_size=context.user_data['text_watermark_size'],
            color=context.user_data['text_watermark_color'],
            position=context.user_data['text_watermark_position'],
            output_path=output_path
        )
        await update.message.reply_photo(photo=open(output_path, 'rb'), caption="Is this text watermark okay?")
        await update.message.reply_text('Confirm this text watermark?', reply_markup=ReplyKeyboardMarkup([['✅ Yes, Confirm', '❌ No, Retry'], ['❌ Cancel']], one_time_keyboard=True))
        return States.CONFIRM_TEXT_WATERMARK
    except Exception as e:
        await update.message.reply_text(f"Error creating watermark preview: {e}"); return await cancel(update, context)

async def handle_text_watermark_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if 'No' in update.message.text:
        await update.message.reply_text('Do you want to add a text watermark?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No'], ['❌ Cancel']], one_time_keyboard=True))
        return States.ASK_TEXT_WATERMARK
        
    await update.message.reply_text("Applying text watermark to all media...", reply_markup=ReplyKeyboardRemove())
    s2_layers = []
    downloads_path = context.application.bot_data['downloads_path']
    font_name = context.user_data['text_watermark_font']
    font_path = next((f for f in context.application.bot_data['font_files'] if os.path.basename(f) == font_name), None)
    
    for i, media_path in enumerate(context.user_data['processed']):
        media_dims = get_media_dimensions(media_path)
        if not media_dims: continue
        output_path = os.path.join(downloads_path, f'S2_{i+1}.png')
        try:
            await asyncio.to_thread(
                WatermarkEngine.create_text_watermark_layer,
                media_dimensions=media_dims,
                text=context.user_data['text_watermark_text'],
                font_path=font_path,
                font_size=context.user_data['text_watermark_size'],
                color=context.user_data['text_watermark_color'],
                position=context.user_data['text_watermark_position'],
                output_path=output_path
            )
            s2_layers.append(output_path)
        except Exception as e:
            logging.error(f"Failed to create text watermark for {media_path}: {e}")
    context.user_data['S2_layers'] = s2_layers
    await update.message.reply_text('Text watermark layers created.')
    return await _check_and_ask_music(update, context)

# --- Music Handlers (Step 12) ---
async def _check_and_ask_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Checks if any videos were sent and asks the user about adding music."""
    has_video = any(is_video_file(p) for p in context.user_data.get('processed', []))
    if not has_video:
        logging.info("No videos in batch, skipping music step.")
        # In the future, this will go to step 13 (combine_user_changes)
        await update.message.reply_text("No videos found, skipping music step.")
        return await combine_changes(update, context)

    await update.message.reply_text('Do you want to add music to the video(s)?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No'], ['❌ Cancel']], one_time_keyboard=True))
    return States.ASK_ADD_MUSIC

async def ask_add_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles user's decision to add music or not."""
    if 'Yes' in update.message.text:
        await update.message.reply_text('Please send the music file (as an audio file).', reply_markup=ReplyKeyboardRemove())
        return States.RECEIVE_MUSIC
    else:
        # Skip to the next major step
        return await combine_changes(update, context)

async def receive_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the audio file from the user."""
    if not update.message.audio:
        await update.message.reply_text('That is not a valid audio file. Please try again.')
        return States.RECEIVE_MUSIC
    
    audio_file = await update.message.audio.get_file()
    audio_path = os.path.join(context.application.bot_data['downloads_path'], 'music.mp3')
    await audio_file.download_to_drive(audio_path)
    context.user_data['music_path'] = audio_path
    
    await update.message.reply_text('Please enter the start time for the music in MM:SS format (e.g., 01:23).')
    return States.RECEIVE_MUSIC_START_TIME

async def receive_music_start_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the music start time and generates a preview based on the longest video."""
    if update.message.text == '❌ Cancel': return await cancel(update, context)
    start_time_str = update.message.text
    context.user_data['music_start_time'] = start_time_str
    
    video_paths = [p for p in context.user_data.get('processed', []) if is_video_file(p)]
    if not video_paths:
        await update.message.reply_text("No videos found to add music to. Skipping music step.")
        return await combine_changes(update, context)

    # Use the duration of the longest video for the preview trim
    durations = [get_video_duration(p) for p in video_paths if get_video_duration(p) is not None]
    preview_duration = max(durations) if durations else 60.0
    
    await update.message.reply_text(
        "⏳ Trimming audio for preview based on your longest video. "
        "The final audio will be matched to each video's individual length.",
        reply_markup=ReplyKeyboardRemove()
    )
    output_path = os.path.join(context.application.bot_data['downloads_path'], 'S3_preview.mp3')
    
    try:
        await asyncio.to_thread(
            MusicAdder.trim_audio,
            audio_path=context.user_data['music_path'],
            video_duration=preview_duration,
            start_time_str=start_time_str,
            output_path=output_path
        )
        await update.message.reply_audio(audio=open(output_path, 'rb'), caption="Here is a preview of the trimmed audio.")
        await update.message.reply_text('Is this correct?', reply_markup=ReplyKeyboardMarkup([['✅ Yes, Confirm', '❌ No, Retry'], ['❌ Cancel']], one_time_keyboard=True))
        return States.CONFIRM_MUSIC
    except ValueError as e:
        await update.message.reply_text(f"❌ Error: {e}. Please enter a valid start time.")
        return States.RECEIVE_MUSIC_START_TIME
    except Exception as e:
        await update.message.reply_text(f"An unexpected error occurred while processing the audio: {e}")
        return await cancel(update, context)

async def handle_music_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles user confirmation of the trimmed audio."""
    if 'No' in update.message.text:
        # If user retries, we clean up the preview file to avoid confusion
        preview_path = os.path.join(context.application.bot_data['downloads_path'], 'S3_preview.mp3')
        if os.path.exists(preview_path):
            os.remove(preview_path)
        await update.message.reply_text('Do you want to add music to the video(s)?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No'], ['❌ Cancel']], one_time_keyboard=True))
        return States.ASK_ADD_MUSIC

    # Don't create a single final audio file here.
    # Just confirm that music should be added in the next step.
    context.user_data['music_confirmed'] = True
    
    await update.message.reply_text('✅ Music confirmed. It will be added to each video individually.')
    return await combine_changes(update, context)

# --- Final Combination and Upload (Step 13) ---
async def combine_changes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Combines all selected edits (watermarks, audio) onto the base media files."""
    await update.message.reply_text(
        "Applying selected edits (watermarks/audio)...", 
        reply_markup=ReplyKeyboardRemove()
    )
    
    s1_layers = context.user_data.get('S1_layers', [])
    s2_layers = context.user_data.get('S2_layers', [])
    music_confirmed = context.user_data.get('music_confirmed', False)
    base_files = context.user_data.get('processed', [])
    
    # If no edits were made, just copy the files and proceed
    if not any([s1_layers, s2_layers, music_confirmed]):
        context.user_data['combined_files'] = base_files
        await update.message.reply_text("No edits were selected. Proceeding to final processing.")
        return await start_final_processing(update, context)

    combiner = MediaCombiner()
    combined_files = []
    downloads_path = context.application.bot_data['downloads_path']

    for i, file_path in enumerate(base_files):
        s1 = s1_layers[i] if i < len(s1_layers) else None
        s2 = s2_layers[i] if i < len(s2_layers) else None
        audio_for_this_video = None

        # --- Per-video audio trimming logic ---
        if music_confirmed and is_video_file(file_path):
            video_duration = get_video_duration(file_path)
            if video_duration:
                trimmed_audio_path = os.path.join(downloads_path, f"S3_{i+1}.mp3")
                try:
                    # This is now a synchronous call inside an asyncio.to_thread context
                    MusicAdder.trim_audio(
                        audio_path=context.user_data['music_path'],
                        video_duration=video_duration,
                        start_time_str=context.user_data['music_start_time'],
                        output_path=trimmed_audio_path
                    )
                    audio_for_this_video = trimmed_audio_path
                except Exception as e:
                    logging.error(f"Failed to trim audio for {file_path}: {e}")
                    await update.message.reply_text(f"⚠️ Could not apply audio to {os.path.basename(file_path)} due to an error.")
        
        output_filename = f"combined_{i}_{os.path.basename(file_path)}"
        output_path = os.path.join(downloads_path, output_filename)
        
        try:
            path = await asyncio.to_thread(
                combiner.combine,
                base_path=file_path,
                output_path=output_path,
                s1_layer_path=s1,
                s2_layer_path=s2,
                s3_audio_path=audio_for_this_video # Pass the unique audio path
            )
            combined_files.append(path)
        except Exception as e:
            logging.error(f"Failed to combine media {file_path}: {e}")
            await update.message.reply_text(f"❌ An error occurred while applying edits to {os.path.basename(file_path)}.")
            return await cancel(update, context)

    context.user_data['combined_files'] = combined_files
    await update.message.reply_text('Edits applied. Here is a preview of the result:')
    
    media_group = [InputMediaPhoto(media=open(f, 'rb')) if not is_video_file(f) else InputMediaVideo(media=open(f, 'rb')) for f in combined_files]
    await update.message.reply_media_group(media=media_group)
    
    await update.message.reply_text(
        'Are these edits correct?',
        reply_markup=ReplyKeyboardMarkup([['✅ Yes, continue', '❌ No, restart edits'], ['❌ Cancel']], one_time_keyboard=True)
    )
    return States.CONFIRM_COMBINED_MEDIA

async def handle_combined_media_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles user confirmation of the combined media."""
    if 'No' in update.message.text:
        # Restart the editing process from the beginning
        await update.message.reply_text("Restarting editing process...")
        await update.message.reply_text('Do you want to add an image watermark?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No'], ['❌ Cancel']], one_time_keyboard=True))
        return States.ASK_IMAGE_WATERMARK
    
    # Proceed to the final processing step
    return await start_final_processing(update, context)

async def start_final_processing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Processes the combined media to their final dimensions and quality for Instagram.
    """
    await update.message.reply_text(
        "Starting final processing (resizing and padding)...", 
        reply_markup=ReplyKeyboardRemove()
    )
    
    final_files = []
    downloads_path = context.application.bot_data['downloads_path']
    
    for i, file_path in enumerate(context.user_data['combined_files']):
        output_filename = f"final_{i}_{os.path.basename(file_path)}"
        output_path = os.path.join(downloads_path, output_filename)
        
        try:
            if is_video_file(file_path):
                path = await asyncio.to_thread(VideoProcessor.process, path=file_path, output_path=output_path)
            else:
                path = await asyncio.to_thread(ImageProcessor.process, path=file_path, output_path=output_path)
            final_files.append(path)
        except Exception as e:
            logging.error(f"Failed during final processing for {file_path}: {e}")
            await update.message.reply_text(f"❌ An error occurred during final processing for {os.path.basename(file_path)}.")
            return await cancel(update, context)

    context.user_data['final_files'] = final_files
    await update.message.reply_text('This is the final result. Please confirm.')
    
    media_group = [InputMediaPhoto(media=open(f, 'rb')) if not is_video_file(f) else InputMediaVideo(media=open(f, 'rb')) for f in final_files]
    await update.message.reply_media_group(media=media_group)
    
    keyboard = [['✅ Yes, looks good', '❌ No, restart edits']]
    # Only offer video effects if there is at least one video
    if any(is_video_file(f) for f in final_files):
        keyboard[0].insert(1, 'Add Video Effects')

    keyboard.append(['❌ Cancel'])
    await update.message.reply_text(
        'Is this result okay?',
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return States.CONFIRM_FINAL_MEDIA

async def handle_final_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles user confirmation of the final processed media."""
    text = update.message.text
    if 'restart' in text:
        await update.message.reply_text("Restarting editing process...")
        await update.message.reply_text('Do you want to add an image watermark?', reply_markup=ReplyKeyboardMarkup([['Yes', 'No']], one_time_keyboard=True))
        return States.ASK_IMAGE_WATERMARK
    elif 'Effects' in text:
        return await ask_video_effects(update, context)
    else: # 'looks good'
        await update.message.reply_text('Please enter the final caption for your post.', reply_markup=ReplyKeyboardRemove())
        return States.CAPTION

# --- Video Effects Handlers (Step 16) ---
async def ask_video_effects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user to select video effects."""
    context.user_data['selected_effects'] = []
    effects_list = [
        'Black & White', 'Color Saturation', 'Contrast / Brightness',
        'Chromatic Aberration', 'Pixelated Effect',
        'Invert Colors', 'Speed Control', 'Rotate',
        'VHS Look', 'Film Grain', 'Glitch',
        'Rolling Shutter', 'Neon Glow',
        'Cartoon / Painterly', 'Vignette', 'Fade In/Out'
    ]
    # Create a 3-column keyboard layout
    keyboard = [effects_list[i:i + 3] for i in range(0, len(effects_list), 3)]
    keyboard.append(['✅ Done Selecting', '❌ Cancel'])
    await update.message.reply_text(
        "Select up to 3 video effects. You can click an effect again to deselect it. Press 'Done Selecting' when finished.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )
    return States.CHOOSE_EFFECTS

async def choose_effects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles user's selection of video effects."""
    choice = update.message.text
    if choice == '❌ Cancel': return await cancel(update, context)
    selected = context.user_data.get('selected_effects', [])

    if 'Done' in choice:
        if not selected:
            await update.message.reply_text("No effects selected. Please enter the final caption.", reply_markup=ReplyKeyboardRemove())
            return States.CAPTION
        else:
            await update.message.reply_text(f"Applying effects: {', '.join(selected)}. Please wait...", reply_markup=ReplyKeyboardRemove())
            return await process_and_confirm_effects(update, context)

    if choice not in selected and len(selected) < 3:
        selected.append(choice)
        await update.message.reply_text(f"Added '{choice}'. Current effects: {', '.join(selected)}.")
    elif choice in selected:
        selected.remove(choice)
        await update.message.reply_text(f"Removed '{choice}'. Current effects: {', '.join(selected)}.")
    else:
        await update.message.reply_text("You can only select up to 3 effects.")

    return States.CHOOSE_EFFECTS

async def process_and_confirm_effects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Applies the selected effects and sends a preview for confirmation."""
    engine = EffectsEngine()
    effects_applied_files = []
    
    for i, file_path in enumerate(context.user_data['final_files']):
        if is_video_file(file_path):
            output_path = os.path.join(context.application.bot_data['downloads_path'], f"effects_{i}_{os.path.basename(file_path)}")
            try:
                path = await asyncio.to_thread(
                    engine.apply_effects_in_sequence,
                    video_path=file_path,
                    effects=context.user_data['selected_effects'],
                    output_path=output_path
                )
                effects_applied_files.append(path)
            except Exception as e:
                logging.error(f"Error applying effects to {file_path}: {e}")
                await update.message.reply_text(f"❌ An error occurred while applying effects to {os.path.basename(file_path)}.")
                effects_applied_files.append(file_path) # Append original if effect fails
        else:
            effects_applied_files.append(file_path) # Keep non-video files as they are

    context.user_data['final_files_with_effects'] = effects_applied_files
    await update.message.reply_text('Preview of video(s) with effects:')
    
    media_group = [InputMediaVideo(media=open(f, 'rb')) for f in effects_applied_files if is_video_file(f)]
    if media_group:
        await update.message.reply_media_group(media=media_group)
    
    await update.message.reply_text(
        'Confirm final result with effects?',
        reply_markup=ReplyKeyboardMarkup([['✅ Yes, upload', '❌ No, restart effects'], ['❌ Cancel']], one_time_keyboard=True)
    )
    return States.CONFIRM_EFFECTS

async def handle_effects_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the final confirmation after applying effects."""
    if 'Yes' in update.message.text:
        context.user_data['final_files'] = context.user_data['final_files_with_effects']
        await update.message.reply_text('Effects confirmed. Please enter the final caption.', reply_markup=ReplyKeyboardRemove())
        return States.CAPTION
    else: # 'No, restart effects'
        await update.message.reply_text("Restarting effect selection...")
        return await ask_video_effects(update, context)

async def handle_caption_and_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receives the caption and uploads the final media to Instagram."""
    if update.message.text == '❌ Cancel': return await cancel(update, context)
    caption = update.message.text
    await update.message.reply_text("🚀 Uploading to Instagram...", reply_markup=ReplyKeyboardRemove())

    try:
        files_to_upload = context.user_data.get('final_files', [])
        if not files_to_upload:
            await update.message.reply_text("❌ Error: No final files were found to upload.")
            return await cancel(update, context)

        mode = context.user_data.get('mode')
        ig_uploader = context.application.bot_data['ig_uploader']
        ig_client = context.application.bot_data['ig_manager'].client

        if mode == 'album':
            await asyncio.to_thread(ig_uploader.upload_album, client=ig_client, paths=files_to_upload, caption=caption)
        else:
            file_path = files_to_upload[0]
            if is_video_file(file_path):
                await asyncio.to_thread(ig_uploader.upload_video, client=ig_client, path=file_path, caption=caption)
            else:
                await asyncio.to_thread(ig_uploader.upload_photo, client=ig_client, path=file_path, caption=caption)
        
        await update.message.reply_text('✅ Upload successful!')

    except Exception as e:
        logging.exception("Upload to Instagram failed.")
        await update.message.reply_text(f'❌ An error occurred during upload: {e}')
    
    # Restart the conversation for a new upload
    await update.message.reply_text("Let's start a new project!")
    return await send_welcome_message(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the current operation and returns to the main menu."""
    await update.message.reply_text('♻️ Operation cancelled. Returning to the main menu.', reply_markup=ReplyKeyboardRemove())
    # Instead of ending, we restart the conversation from the beginning
    return await send_welcome_message(update, context)

def get_conversation_handler() -> ConversationHandler:
    """Builds the main conversation handler."""
    return ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            # Authentication
            States.AUTH_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_2fa)],
            States.AUTH_SMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sms)],
            # Media Handling
            States.MEDIA_TYPE: [MessageHandler(filters.Regex('^📤 Album$|^📎 Single$') & ~filters.COMMAND, handle_media_type)],
            States.RECEIVE_MEDIA: [
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.ANIMATION, handle_media),
                MessageHandler(filters.TEXT & filters.Regex(r'^🏁 Done$'), process_media)
            ],
            States.CONFIRM: [MessageHandler(filters.Regex('^✅ Yes, continue$|^❌ No, Upload As Is$') & ~filters.COMMAND, handle_confirmation)],
            # Image Watermark
            States.ASK_IMAGE_WATERMARK: [MessageHandler(filters.Regex('^Yes$|^No$'), ask_image_watermark)],
            States.RECEIVE_IMAGE_WATERMARK: [MessageHandler(filters.PHOTO, receive_image_watermark)],
            States.CHOOSE_IMG_WATERMARK_POSITION: [MessageHandler(filters.Regex('^(top|middle|bottom)-(left|center|right)$'), handle_img_position)],
            States.CHOOSE_IMG_WATERMARK_SCALE: [MessageHandler(filters.Regex('^50$|^60$|^70$|^80$|^90$|^100$'), handle_img_scale)],
            States.CHOOSE_IMG_WATERMARK_OPACITY: [MessageHandler(filters.Regex('^100$|^90$|^80$|^70$|^60$|^50$'), generate_and_preview_image_watermark)],
            States.CONFIRM_IMG_WATERMARK: [MessageHandler(filters.Regex('^✅ Yes, Confirm$|^❌ No, Retry$'), handle_img_watermark_confirmation)],
            # Text Watermark
            States.ASK_TEXT_WATERMARK: [MessageHandler(filters.Regex('^Yes$|^No$'), handle_ask_text_watermark)],
            States.RECEIVE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
            States.CHOOSE_FONT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_font)],
            States.CHOOSE_FONT_SIZE: [MessageHandler(filters.Regex('^10$|^15$|^20$|^25$|^30$|^35$|^40$|^45$|^50$'), handle_font_size)],
            States.CHOOSE_COLOR: [MessageHandler(filters.Regex('^White$|^Black$|^Red$|^Blue$|^Yellow$|^Green$'), handle_color)],
            States.CHOOSE_TEXT_POSITION: [MessageHandler(filters.Regex('^top–center$|^middle–center$|^bottom–center$'), generate_and_preview_text_watermark)],
            States.CONFIRM_TEXT_WATERMARK: [MessageHandler(filters.Regex('^✅ Yes, Confirm$|^❌ No, Retry$'), handle_text_watermark_confirmation)],
            # Music
            States.ASK_ADD_MUSIC: [MessageHandler(filters.Regex('^Yes$|^No$'), ask_add_music)],
            States.RECEIVE_MUSIC: [MessageHandler(filters.AUDIO, receive_music)],
            States.RECEIVE_MUSIC_START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_music_start_time)],
            States.CONFIRM_MUSIC: [MessageHandler(filters.Regex('^✅ Yes, Confirm$|^❌ No, Retry$'), handle_music_confirmation)],
            # Combination & Final Processing
            States.CONFIRM_COMBINED_MEDIA: [MessageHandler(filters.Regex('^✅ Yes, continue$|^❌ No, restart edits$'), handle_combined_media_confirmation)],
            States.CONFIRM_FINAL_MEDIA: [MessageHandler(filters.Regex('^✅ Yes, looks good$|^❌ No, restart edits$|^Add Video Effects$'), handle_final_confirmation)],
            # Video Effects
            States.ASK_VIDEO_EFFECTS: [MessageHandler(filters.TEXT, ask_video_effects)],
            States.CHOOSE_EFFECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_effects)],
            States.CONFIRM_EFFECTS: [MessageHandler(filters.Regex('^✅ Yes, upload$|^❌ No, restart effects$'), handle_effects_confirmation)],
            # Caption and Upload
            States.CAPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_caption_and_upload)],
        },
        fallbacks=[CommandHandler('cancel', cancel), MessageHandler(filters.Regex('^❌ Cancel$'), cancel)],
        conversation_timeout=1440, # 24 minutes
        allow_reentry=True
    )
