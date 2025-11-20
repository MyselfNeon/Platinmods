import asyncio
import json
import os
import logging
import httpx
from pyrogram import Client, filters
from bs4 import BeautifulSoup
from config import *
from app import start_web_server

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Pyrogram Client
bot = Client(
    "platinmods_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

STATE_FILE = 'platinmods_state.json'

# --- Helper Functions (ASYNCHRONOUS File I/O) ---

def _load_state_sync():
    """Synchronous function to load state (to be run in a thread)."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_state_sync(state):
    """Synchronous function to save state (to be run in a thread)."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

async def load_state():
    """Asynchronously loads the state."""
    return await asyncio.to_thread(_load_state_sync)

async def save_state(state):
    """Asynchronously saves the state."""
    await asyncio.to_thread(_save_state_sync, state)

async def get_soup(url, client):
    """Fetches a URL and returns a BeautifulSoup object."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        
        # Move CPU-bound parsing work to a separate thread
        soup = await asyncio.to_thread(BeautifulSoup, response.content, 'html.parser')
        return soup
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None

# --- Tracking Logic ---

async def check_user_status(http_client):
    """
    Checks user online status and sends alerts (online/offline).
    Returns the user's current status (True/False).
    """
    user_status = {}
    for target in USER_TARGETS:
        soup = await get_soup(target['url'], http_client)
        if not soup:
            user_status[target['name']] = "Error"
            continue

        is_online = False
        
        # Adjust 'userTitle' to the actual class found via Inspect Element.
        # This selector is a placeholder!
        status_element = soup.find('span', class_='userTitle') 
        
        if soup.find(string="Online now") or (status_element and "Online" in status_element.get_text()):
            is_online = True

        state_key = f"user_{target['name']}"
        current_state = await load_state()
        was_online = current_state.get(state_key, False)

        if is_online and not was_online:
            # User just came online
            msg = f"🚨 **USER ALERT**\n\n👤 **{target['name']}** is now **ONLINE**! 🟢\n🔗 [Profile Link]({target['url']})"
            try:
                await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                current_state[state_key] = True
                await save_state(current_state)
            except Exception as e:
                logger.error(f"Telegram Error: {e}")
        
        elif not is_online and was_online:
            # User just went offline
            msg = f"💤 **STATUS UPDATE**\n\n👤 **{target['name']}** is now **OFFLINE** 🔴"
            try:
                await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                current_state[state_key] = False
                await save_state(current_state)
            except Exception as e:
                logger.error(f"Telegram Error: {e}")
        
        user_status[target['name']] = "Online" if is_online else "Offline"
        
    return user_status

async def check_forums(http_client):
    """
    Checks for new threads in forums.
    Returns a dictionary of forum names and their current thread counts.
    """
    state = await load_state()
    forum_counts = {}
    
    for forum_name, url in FORUM_TARGETS.items():
        soup = await get_soup(url, http_client)
        if not soup:
            forum_counts[forum_name] = "Error"
            continue

        # XenForo 2 generic selector for thread titles
        thread_links = soup.select('.structItem-title a')
        
        current_threads = []
        for link in thread_links:
            text = link.get_text(strip=True)
            href = link.get('href')
            if href and "threads/" in href:
                full_url = f"https://platinmods.com{href}" if href.startswith('/') else href
                current_threads.append({"title": text, "url": full_url})
        
        forum_counts[forum_name] = len(current_threads)

        previous_threads = state.get(forum_name, [])
        prev_urls = {t['url'] for t in previous_threads}
        curr_urls = {t['url'] for t in current_threads}

        new_urls = curr_urls - prev_urls
        removed_urls = prev_urls - curr_urls

        # Process New Threads
        if new_urls:
            for item in current_threads:
                if item['url'] in new_urls:
                    msg = f"✨ **NEW THREAD** in __{forum_name}__\n\n📝 **{item['title']}**\n🔗 [View Thread]({item['url']})"
                    try:
                        await bot.send_message(NOTIFICATION_CHAT_ID, msg)
                    except Exception as e:
                        logger.error(f"Telegram Error: {e}")

        # Process Removed Threads
        if removed_urls:
            for item in previous_threads:
                if item['url'] in removed_urls:
                    msg = f"🗑 **THREAD REMOVED** from __{forum_name}__\n\n📝 **{item['title']}**"
                    try:
                        await bot.send_message(NOTIFICATION_CHAT_ID, msg)
                    except Exception as e:
                        logger.error(f"Telegram Error: {e}")

        # Save new state
        state[forum_name] = current_threads
        await save_state(state)

    return forum_counts

async def scheduler():
    """Main loop."""
    async with httpx.AsyncClient(timeout=20.0) as http_client:
        while True:
            logger.info("Checking targets...")
            await check_user_status(http_client)
            await check_forums(http_client)
            logger.info(f"Sleeping for {CHECK_INTERVAL}s")
            await asyncio.sleep(CHECK_INTERVAL)

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
                # Run user check and get current status
                user_status = await check_user_status(http_client)
                # Run forum check and get current thread counts
                forum_counts = await check_forums(http_client)

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
    loop.create_task(scheduler())
    bot.run()
