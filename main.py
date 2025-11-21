import asyncio
import logging
import httpx
import aiohttp 
from pyrogram import Client, filters
from config import API_ID, API_HASH, BOT_TOKEN, NOTIFICATION_CHAT_ID, CHECK_INTERVAL, PORT
from app import start_web_server

from MyselfNeon.track import check_user_status, check_forums
from MyselfNeon.db import db 

# Import the modules containing bot commands (this ensures they are registered)
from MyselfNeon import broadcast
from MyselfNeon import checks # New import for the /check command

# YOUR KEEP ALIVE URL HERE
KEEP_ALIVE_URL = "https://website-monitor-v0q9.onrender.com/" 

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global flag to track if the initial ready message has been sent
BOT_READY_MESSAGE_SENT = False

# Initialize Pyrogram Client
bot = Client(
    "platinmods_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# --- Scheduler ---
async def scheduler():
    """Main loop. Waits for the Pyrogram client to be running before executing."""
    global BOT_READY_MESSAGE_SENT
    
    # Wait until the bot client is fully started (Pyrogram 2.x uses .is_connected)
    while not bot.is_connected:
        logger.info("Scheduler waiting for Telegram client to start...")
        await asyncio.sleep(5)

    # *** Send ready message once per process startup/restart ***
    if not BOT_READY_MESSAGE_SENT:
        try:
            msg = "✅ **__Bot Online & Monitoring:\n\nI have Successfully Reconnected to Telegram. The monitoring schedule has been initialized (Happens after every server Restart).__**"
            await bot.send_message(NOTIFICATION_CHAT_ID, msg)
            logger.info("Sent 'Bot Ready' message after restart.")
            BOT_READY_MESSAGE_SENT = True
        except Exception as e:
            logger.error(f"Failed to send ready message: {e}")
            
    # *********************************************
    async with httpx.AsyncClient(timeout=20.0) as http_client:
        while True:
            logger.info("Checking targets...")
            # Pass the bot instance to the tracking functions
            await check_user_status(http_client, bot)
            await check_forums(http_client, bot)
            logger.info(f"Sleeping for {CHECK_INTERVAL}s")
            await asyncio.sleep(CHECK_INTERVAL)

# --- Keep-Alive Function ---
async def keep_alive():
    """Send a request every 300 seconds to keep the bot alive (if required)."""
    if not KEEP_ALIVE_URL:
        logging.warning("KEEP_ALIVE_URL is not configured — skipping keep-alive task.")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(KEEP_ALIVE_URL) as resp:
                    if resp.status == 200:
                        logging.info("✅ Keep-alive ping successful.")
                    else:
                        logging.warning(f"⚠️ Keep-alive returned status {resp.status}")
            except Exception as e:
                logging.error(f"❌ Keep-alive request failed: {e}")
            await asyncio.sleep(300)

# --- Bot Commands (Only /start remains) ---
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    """
    Shows the user their chat ID and registers the user in MongoDB.
    """
    user = message.from_user
    chat_type = message.chat.type.name.lower()
    
    if user and chat_type == 'private':
        # --- USER REGISTRATION LOGIC ---
        user_id = user.id
        user_name = user.full_name
        
        # Add user if they don't exist
        if not await db.is_user_exist(user_id):
            await db.add_user(user_id, user_name)
            logger.info(f"New user registered: {user_name} ({user_id})")
        # -------------------------------
        
        reply_text = (
            f"👋 **__Bot is Online!__**\n\n"
            f"__**Your PRIVATE Chat ID is:__** `{message.chat.id}`\n\n"
            f"**__Action Required: Set this positive ID __**"
            f"**__in your configuration to receive alerts.__**"
        )
    else:
         reply_text = (
            f"👋 **__Bot is Online!__**\n\n"
            f"**__The Chat ID for this {chat_type.upper()} is:__** `{message.chat.id}`\n\n"
            f"**__NOTE: If you want private notifications, use `/start` in a direct message __**"
            f"**__to theComplane use that positive ID instead.__**"
        )
    
    await message.reply(reply_text)

# --- Entry Point ---
if __name__ == "__main__":
    # 1. Start the Fake Web Server (for cloud binding)
    logger.info(f"Starting Web Server on port {PORT}")
    start_web_server(PORT)

    # 2. Start the Bot
    logger.info("Starting Telegram Bot...")
    loop = asyncio.get_event_loop()
    
    # Create Background Tasks
    loop.create_task(scheduler())
    
    # Create Keep Alive Task (updated as requested)
    if KEEP_ALIVE_URL:
        loop.create_task(keep_alive())
        logging.info("🌐 Keep-alive task started.")
    else:
        logging.warning("⚠️ Keep-alive task skipped: URL not set.")
        
    bot.run()
