import asyncio
import logging
import httpx
import aiohttp 
from pyrogram import Client, filters
from config import *
from app import start_web_server

# Import tracking logic from the new module
from MyselfNeon.track import check_user_status, check_forums

# ---------------------------------------------------------
# HARDCODE YOUR KEEP ALIVE URL HERE
# Example: "https://your-app-name.onrender.com/health"
# ---------------------------------------------------------
KEEP_ALIVE_URL = "https://platinmods.onrender.com/" 

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global flag to track if the initial ready message has been sent
# This flag is reset to False every time the Python process restarts (e.g., after server sleep/wake).
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
    
    # Wait until the bot client is fully started (ready to send messages)
    while not bot.is_running:
        logger.info("Scheduler waiting for Telegram client to start...")
        await asyncio.sleep(5) 

    # *** Send ready message once per process startup/restart ***
    if not BOT_READY_MESSAGE_SENT:
        try:
            msg = "✅ **Bot Online & Monitoring:**\n\nI have successfully reconnected to Telegram. The monitoring schedule has been initialized (This happens after every server restart/wake-up)."
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
    if not KEEP_ALIVE_URL or KEEP_ALIVE_URL == "https://platinmods.onrender.com/":
        logging.warning("KEEP_ALIVE_URL is not configured properly — skipping keep-alive task.")
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
    chat_type = message.chat.type.name.lower()
    
    if chat_type == 'private':
        reply_text = (
            f"👋 **Bot is Online!**\n\n"
            f"Your **PRIVATE** Chat ID is: `{message.chat.id}`\n\n"
            f"**Action Required:** Set this **positive** ID as your `NOTIFICATION_CHAT_ID` "
            f"in your configuration to receive private alerts."
        )
    else:
         reply_text = (
            f"👋 **Bot is Online!**\n\n"
            f"The Chat ID for this **{chat_type.upper()}** is: `{message.chat.id}`\n\n"
            f"**NOTE:** If you want **private notifications**, use `/start` in a direct message "
            f"to the bot and use that **positive** ID instead."
        )
    
    await message.reply(reply_text)

@bot.on_message(filters.command("check"))
async def force_check(client, message):
    # This reply runs immediately, preventing the hang
    await message.reply("🔄 **Force check initiated...** Please wait for the summary report.")

    async def run_check_and_confirm(chat_id):
        """Runs the scraping task and sends a detailed summary report."""
        try:
            async with httpx.AsyncClient(timeout=20.0) as http_client:
                # Pass the bot instance (client) to the tracking functions
                user_status = await check_user_status(http_client, client)
                forum_counts = await check_forums(http_client, client)

            # --- Compile Summary Report ---
            summary_parts = ["✅ **MANUAL CHECK COMPLETE**\n\n"]
            
            # 1. User Status Summary
            summary_parts.append("👤 **User Status**")
            for name, status in user_status.items():
                emoji = "🟢" if status == "Online" else "🔴" if status == "Offline" else "❓"
                summary_parts.append(f"• {name}: **{status}** {emoji}")
            
            summary_parts.append("\n📚 **Forum Thread Counts**")
            
            # 2. Forum Counts Summary
            for forum, count in forum_counts.items():
                count_str = str(count) if isinstance(count, int) else "Error"
                summary_parts.append(f"• {forum}: **{count_str}** threads")

            final_message = "\n".join(summary_parts)
            
            # Send the detailed summary report
            await client.send_message(chat_id, final_message)

        except Exception as e:
            logger.error(f"Error during force check: {e}")
            await client.send_message(chat_id, f"❌ **Check failed.** An internal error occurred.")


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
    
    # Create Keep Alive Task
    if KEEP_ALIVE_URL and KEEP_ALIVE_URL != "YOUR_KEEP_ALIVE_URL_HERE":
        loop.create_task(keep_alive())
        logging.info("🌐 Keep-alive task started.")
    else:
        logging.warning("⚠️ Keep-alive task skipped: URL not set or is default placeholder.")
        
    bot.run()
