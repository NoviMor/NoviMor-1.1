from enum import IntEnum, auto

class States(IntEnum):
    AUTH_2FA = auto()
    AUTH_SMS = auto()
    MEDIA_TYPE = auto()
    RECEIVE_MEDIA = auto()
    CONFIRM = auto()
    
    # Image Watermark (Step 10)
    ASK_IMAGE_WATERMARK = auto()
    RECEIVE_IMAGE_WATERMARK = auto()
    CHOOSE_IMG_WATERMARK_POSITION = auto()
    CHOOSE_IMG_WATERMARK_SCALE = auto()
    CHOOSE_IMG_WATERMARK_OPACITY = auto()
    CONFIRM_IMG_WATERMARK = auto()
    
    # Text Watermark (Step 11)
    ASK_TEXT_WATERMARK = auto()
    RECEIVE_TEXT = auto()
    CHOOSE_FONT = auto()
    CHOOSE_FONT_SIZE = auto()
    CHOOSE_COLOR = auto()
    CHOOSE_TEXT_POSITION = auto()
    CONFIRM_TEXT_WATERMARK = auto()
    
    # Music (Step 12)
    ASK_ADD_MUSIC = auto()
    RECEIVE_MUSIC = auto()
    RECEIVE_MUSIC_START_TIME = auto()
    CONFIRM_MUSIC = auto()
    
    # Combine (Step 13)
    CONFIRM_COMBINED_MEDIA = auto()

    # Final Processing (Steps 14 & 15)
    CONFIRM_FINAL_MEDIA = auto()

    # Video Effects (Step 16)
    ASK_VIDEO_EFFECTS = auto()
    CHOOSE_EFFECTS = auto()
    CONFIRM_EFFECTS = auto()
    
    # Finalize
    CAPTION = auto()
