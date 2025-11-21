import os
from dotenv import load_dotenv

# Load variables from .env file if it exists (for local development)
load_dotenv()

# --- Telegram Credentials ---
# Get these from my.telegram.org
API_ID = int(os.getenv("API_ID", 0)) 
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# --- Application Config ---
# The Chat ID where alerts will be sent. 
# Send /start to your bot to get this ID if you don't have it.
NOTIFICATION_CHAT_ID = int(os.getenv("NOTIFICATION_CHAT_ID", 0))

# Check interval in seconds (Default: 5 minutes)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 30))

# Server Port (Required for cloud deployments)
PORT = int(os.getenv("PORT", 8080))

# --- Tracking Targets ---
USER_TARGETS = [
    {
        "name": "Darealpanda",
        "url": "https://platinmods.com/members/darealpanda.115207/",
        "selector": "span.userTitle" # NOTE: You must verify this selector via Inspect Element
    }
]

FORUM_TARGETS = {
    "Shared Android Mods": "https://platinmods.com/forums/untested-shared-android-mods.150/",
    "Android Apps": "https://platinmods.com/forums/untested-android-apps.155/"
}
