import os
import sys
import logging
import subprocess
from importlib import import_module
from dotenv import load_dotenv
from typing import List, Tuple, Optional

# Step 2: Check for required libraries
def check_and_install_dependencies():
    """
    Checks if all required Python libraries are installed and installs them if not.
    """
    REQUIRED_LIBRARIES = {
        'python-telegram-bot': 'telegram',
        'instagrapi': 'instagrapi',
        'Pillow': 'PIL',
        'python-dotenv': 'dotenv',
        'moviepy': 'moviepy.editor',
        'filetype': 'filetype',
        'nest-asyncio': 'nest-asyncio'
    }
    
    missing_libraries = []
    for package_name, import_name in REQUIRED_LIBRARIES.items():
        try:
            import_module(import_name)
            logging.info(f"'{package_name}' is already installed.")
        except ImportError:
            logging.warning(f"'{package_name}' is not installed.")
            missing_libraries.append(package_name)
    
    if missing_libraries:
        logging.info(f"Attempting to install missing libraries: {', '.join(missing_libraries)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing_libraries])
            logging.info("All missing dependencies have been successfully installed.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to install dependencies: {e}. Please install them manually and restart the bot.")
            sys.exit(1)

# Step 3: Check and prepare folders
def prepare_folders() -> Tuple[str, List[str], Optional[str]]:
    """
    Ensures that the necessary folders ('downloads', 'fonts') exist and are prepared.

    Returns:
        A tuple containing:
        - The absolute path to the downloads folder.
        - A list of paths to available .ttf font files.
        - A warning message if no fonts are found, otherwise None.
    """
    # 3.1: Downloads folder
    downloads_path = os.path.join(os.getcwd(), 'downloads')
    if os.path.exists(downloads_path):
        logging.info("Downloads folder exists. Clearing its contents.")
        for f in os.listdir(downloads_path):
            try:
                os.remove(os.path.join(downloads_path, f))
            except Exception as e:
                logging.error(f"Could not remove file {f} from downloads: {e}")
    else:
        logging.info("Downloads folder not found. Creating it.")
        os.makedirs(downloads_path)

    # 3.2: Fonts folder
    fonts_path = os.path.join(os.getcwd(), 'fonts')
    if not os.path.exists(fonts_path):
        logging.info("Fonts folder not found. Creating it.")
        os.makedirs(fonts_path)
    
    # 3.3: Check for .ttf files
    font_files = [os.path.join(fonts_path, f) for f in os.listdir(fonts_path) if f.lower().endswith('.ttf')]
    font_warning = None
    if not font_files:
        font_warning = "Warning: The 'fonts' directory is empty or contains no .ttf files. Text watermarking will not be available."
        logging.warning(font_warning)
    else:
        logging.info(f"Found {len(font_files)} font(s): {', '.join([os.path.basename(f) for f in font_files])}")
        
    return downloads_path, font_files, font_warning

# Step 4: Check .env file
def load_environment_variables() -> Tuple[str, str, str]:
    """
    Loads required variables from a .env file and ensures they are present.

    Returns:
        A tuple containing the Telegram token, Instagram username, and Instagram password.
    """
    load_dotenv()
    
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    instagram_user = os.getenv('INSTAGRAM_USER')
    instagram_pass = os.getenv('INSTAGRAM_PASS')

    missing_vars = []
    if not telegram_token:
        missing_vars.append('TELEGRAM_TOKEN')
    if not instagram_user:
        missing_vars.append('INSTAGRAM_USER')
    if not instagram_pass:
        missing_vars.append('INSTAGRAM_PASS')

    if missing_vars:
        error_message = f"Error: The .env file is missing or invalid. The following variables are required: {', '.join(missing_vars)}"
        logging.error(error_message)
        # This error is critical and should be communicated to the user via Telegram if possible,
        # but the bot can't start without the token, so we exit.
        sys.exit(error_message)
        
    return telegram_token, instagram_user, instagram_pass

def setup_logging():
    """Configures the root logger for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("bot_activity.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Reduce the noise from the HTTP library used by python-telegram-bot
    logging.getLogger("httpx").setLevel(logging.WARNING)

def initialize_app() -> dict:
    """
    Runs all setup steps and returns a configuration dictionary for the bot.
    """
    setup_logging()
    logging.info("--- Starting Bot Setup ---")
    
    check_and_install_dependencies()
    
    telegram_token, instagram_user, instagram_pass = load_environment_variables()
    downloads_path, font_files, font_warning = prepare_folders()
    
    try:
        import nest_asyncio
        nest_asyncio.apply()
        logging.info("nest_asyncio has been applied.")
    except ImportError:
        pass
        
    logging.info("--- Bot Setup Complete ---")
    
    return {
        "telegram_token": telegram_token,
        "instagram_user": instagram_user,
        "instagram_pass": instagram_pass,
        "downloads_path": downloads_path,
        "font_files": font_files,
        "font_warning": font_warning
    }
