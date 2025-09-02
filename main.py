import logging
import os
from telegram.ext import Application

os.environ['XDG_RUNTIME_DIR'] = '/tmp/runtime'
os.environ['ALSA_CONFIG_PATH'] = '/dev/null'
from setup_manager import initialize_app
from auth_manager import AuthManager
from telegram_handler import get_conversation_handler
from instagram_uploader import InstagramUploader

def main():
    """Main function to configure and run the bot."""
    # Run the setup process and get the configuration
    config = initialize_app()

    # Create instances of the managers
    ig_manager = AuthManager(
        username=config["instagram_user"],
        password=config["instagram_pass"]
    )
    ig_uploader = InstagramUploader()

    # Create the Telegram Application using the token from setup
    builder = Application.builder().token(config["telegram_token"])
    
    # Set a high connection pool size to avoid issues with multiple media uploads
    builder.get_updates_http_version("1.1")
    builder.http_version("1.1")
    
    # Increase timeouts to handle large files and slow connections, per user request
    builder.read_timeout(300)
    builder.write_timeout(300)

    app = builder.build()

    # --- Share instances and config with the application context ---
    # This makes them accessible in all handlers via context.application.bot_data
    app.bot_data['ig_manager'] = ig_manager
    app.bot_data['ig_uploader'] = ig_uploader
    app.bot_data['downloads_path'] = config["downloads_path"]
    app.bot_data['font_files'] = config["font_files"]
    app.bot_data['font_warning'] = config["font_warning"]
    
    # Add the conversation handler to the application
    conv_handler = get_conversation_handler()
    app.add_handler(conv_handler)

    # Start the bot
    logging.info("Bot is starting to poll for updates...")
    app.run_polling()

if __name__ == '__main__':
    main()
