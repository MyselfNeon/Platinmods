import asyncio
import json
import os
import logging
from bs4 import BeautifulSoup
from config import USER_TARGETS, FORUM_TARGETS, NOTIFICATION_CHAT_ID

# Configure Logger for this module
logger = logging.getLogger(__name__)
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
async def check_user_status(http_client, bot):
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
        status_element = soup.find('span', class_='userTitle') 
        
        if soup.find(string="Online now") or (status_element and "Online" in status_element.get_text()):
            is_online = True

        state_key = f"user_{target['name']}"
        current_state = await load_state()
        was_online = current_state.get(state_key, False)

        if is_online and not was_online:
            # User just came online
            msg = f"🚨 **__USER ALERT__**\n\n👤 **__{target['name']}** is now **ONLINE__**! 🟢\n🔗 **__[Profile Link]({target['url']})__**"
            try:
                await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                current_state[state_key] = True
                await save_state(current_state)
            except Exception as e:
                logger.error(f"Telegram Error: {e}")
        
        elif not is_online and was_online:
            # User just went offline
            msg = f"💤 **__STATUS UPDATE__**\n\n👤 **__{target['name']}** is now **OFFLINE__** 🔴"
            try:
                await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                current_state[state_key] = False
                await save_state(current_state)
            except Exception as e:
                logger.error(f"Telegram Error: {e}")
        
        user_status[target['name']] = "Online" if is_online else "Offline"
        
    return user_status

async def check_forums(http_client, bot):
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
                    msg = f"🚨 **__NEW THREAD** \n– in {forum_name}__\n\n📝 __{item['title']}\n🔗 **[View Thread]({item['url']})__**"
                    try:
                        await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                    except Exception as e:
                        logger.error(f"Telegram Error: {e}")

        # Process Removed Threads
        if removed_urls:
            for item in previous_threads:
                if item['url'] in removed_urls:
                    msg = f"🗑 **__THREAD REMOVED** \n– from {forum_name}__\n\n📝 __{item['title']}__"
                    try:
                        await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                    except Exception as e:
                        logger.error(f"Telegram Error: {e}")

        # Save new state
        state[forum_name] = current_threads
        await save_state(state)

    return forum_counts
