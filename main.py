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

# --- Helper Functions ---

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

async def get_soup(url, client):
    """Fetches a URL and returns a BeautifulSoup object."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = await client.get(url, headers=headers, follow_redirects=True)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        return None

# --- Tracking Logic ---

async def check_user_status(http_client):
    """Checks if the target users are online."""
    for target in USER_TARGETS:
        soup = await get_soup(target['url'], http_client)
        if not soup:
            continue

        # LOGIC: Check for specific indicators of online status.
        # This relies on the 'Online' text appearing in the profile header.
        # You might need to adjust logic depending on actual HTML structure.
        is_online = False
        
        # Example: Looking for a badge or text. 
        # Adjust 'userTitle' to the actual class found via Inspect Element.
        status_element = soup.find('span', class_='userTitle') 
        
        # Alternative: XenForo often puts "Online now" text in the header
        if soup.find(string="Online now") or (status_element and "Online" in status_element.get_text()):
            is_online = True

        # State tracking for user
        state_key = f"user_{target['name']}"
        current_state = load_state()
        was_online = current_state.get(state_key, False)

        if is_online and not was_online:
            msg = f"🚨 **USER ALERT**\n\n👤 **{target['name']}** is now **ONLINE**!\n🔗 [Profile Link]({target['url']})"
            try:
                await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                current_state[state_key] = True
                save_state(current_state)
            except Exception as e:
                logger.error(f"Telegram Error: {e}")

        elif not is_online and was_online:
            # User went offline, update state silently
            current_state[state_key] = False
            save_state(current_state)

async def check_forums(http_client):
    """Checks for new threads in forums."""
    state = load_state()
    
    for forum_name, url in FORUM_TARGETS.items():
        soup = await get_soup(url, http_client)
        if not soup:
            continue

        # XenForo 2 generic selector for thread titles
        # structItem-title is the class for the div containing the link
        thread_links = soup.select('.structItem-title a')
        
        current_threads = []
        for link in thread_links:
            text = link.get_text(strip=True)
            href = link.get('href')
            # Create a unique ID for the thread
            if href and "threads/" in href:
                full_url = f"https://platinmods.com{href}" if href.startswith('/') else href
                current_threads.append({"title": text, "url": full_url})

        previous_threads = state.get(forum_name, [])
        # Convert to sets of URL strings for comparison
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
        save_state(state)

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
    await message.reply(f"👋 **Bot is Online!**\n\nYour Chat ID is: `{message.chat.id}`\nAdd this to your environment variables to receive alerts.")

@bot.on_message(filters.command("check"))
async def force_check(client, message):
    await message.reply("🔄 Force check initiated...")
    # We create a temporary client just for this one-off check
    async with httpx.AsyncClient(timeout=20.0) as http_client:
        await check_user_status(http_client)
        await check_forums(http_client)
    await message.reply("✅ Check complete.")

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