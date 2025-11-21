import asyncio
import logging
import httpx
import aiohttp 
from pyrogram import Client, filters
# Import ALL necessary config variables, including the new auth ones
from config import API_ID, API_HASH, BOT_TOKEN, NOTIFICATION_CHAT_ID, CHECK_INTERVAL, PORT, OWNER_ID, AUTH_USERS
from app import start_web_server

# Import tracking logic from the new module
from MyselfNeon.track import check_user_status, check_forums

# YOUR KEEP ALIVE URL HERE
KEEP_ALIVE_URL = "https://website-monitor-v0q9.onrender.com/" 

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global flag to track if the initial ready message has been sent
BOT_READY_MESSAGE_SENT = False

# --- Authorization Filter ---
def auth_user_filter(_, client, message):
    """Custom filter to check if the user is the owner or an authorized user."""
    # Check if the message has a user (not a channel post or other non-user message)
    if not message.from_user:
        return False
        
    user_id = message.from_user.id
    
    # Check for Owner ID first, then Authorized Users set
    is_authorized = user_id == OWNER_ID or user_id in AUTH_USERS
    
    if not is_authorized:
        logger.warning(f"Unauthorized access attempt by user ID: {user_id}")
        asyncio.create_task(message.reply("⛔ **__Access Denied__**\n__You are not authorized to use this command.__"))
        
    return is_authorized

# Pyrogram filters must be callable, we assign the function to a variable
authorized_users_only = filters.create(auth_user_filter)
# ---------------------------

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

# --- Bot Commands ---
@bot.on_message(filters.command("start"))
async def start_cmd(client, message):
    """
    Shows the user their chat ID. This command is NOT restricted 
    as users need it to configure NOTIFICATION_CHAT_ID.
    """
    chat_type = message.chat.type.name.lower()
    
    if chat_type == 'private':
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

@bot.on_message(filters.command("check") & authorized_users_only)
async def force_check(client, message):
    """
    Triggers an immediate check for authorized users.
    """
    # Send the temporary message
    tmp = await message.reply(
        "🔄 **__Manual Check Initiated...__**\n**__Please wait for the summary Report.__**"
    )
    # Wait 1 seconds, then delete it
    await asyncio.sleep(1)
    await tmp.delete()

    async def run_check_and_confirm(chat_id):
        """Runs the scraping task and sends a detailed summary report."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as http_client:
                # Pass the bot instance (client) to the tracking functions
                user_status = await check_user_status(http_client, client)
                forum_counts = await check_forums(http_client, client)

            # --- Compile Summary Report ---
            summary_parts = ["✅ **__Manual Check Completed__**\n"]
            
            # 1. User Status Summary
            summary_parts.append("👤 **__User Status__**")
            for name, status in user_status.items():
                emoji = "🟢" if status == "Online" else "🔴" if status == "Offline" else "❓"
                summary_parts.append(f"__• {name}: **{status}** {emoji}__")
            
            summary_parts.append("\n📚 **__Forum Thread Counts__**")
            
            # 2. Forum Counts Summary
            for forum, count in forum_counts.items():
                count_str = str(count) if isinstance(count, int) else "Error"
                summary_parts.append(f"__• {forum}: **{count_str} threads__**")

            final_message = "\n".join(summary_parts)
            
            # Send the detailed summary report
            await client.send_message(chat_id, final_message)

        except Exception as e:
            logger.error(f"Error during force check: {e}")
            await client.send_message(chat_id, f"❌ **__Check failed.**\nAn internal error occurred.__")

# Create a new, independent task to run the scraping in the background
    asyncio.create_task(run_check_and_confirm(message.chat.id))

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
