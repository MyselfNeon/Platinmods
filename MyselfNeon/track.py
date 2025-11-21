import asyncio
import json
import os
import logging
import random
from bs4 import BeautifulSoup
from fake_useragent import UserAgent  # pip install fake-useragent
from config import USER_TARGETS, FORUM_TARGETS, NOTIFICATION_CHAT_ID

# Configure Logger for this module
logger = logging.getLogger(__name__)

STATE_FILE = 'platinmods_state.json'
COOKIE_FILE = 'cookies.json'

# Initialize UserAgent rotator
ua = UserAgent()

# --- Helper Functions (ASYNCHRONOUS File I/O) ---

def _load_state_sync():
    """Synchronous function to load state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_state_sync(state):
    """Synchronous function to save state."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

async def load_state():
    return await asyncio.to_thread(_load_state_sync)

async def save_state(state):
    await asyncio.to_thread(_save_state_sync, state)

# --- New Helper: Cookie Management ---

def _load_cookies_sync():
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cookies_sync(cookies_dict):
    with open(COOKIE_FILE, 'w') as f:
        json.dump(cookies_dict, f)

async def load_cookies():
    return await asyncio.to_thread(_load_cookies_sync)

async def save_cookies(client):
    # Extract cookies from httpx client and save them
    cookies_dict = {key: value for key, value in client.cookies.items()}
    await asyncio.to_thread(_save_cookies_sync, cookies_dict)

# --- New Helper: Anti-Detection Headers ---

def get_random_headers():
    """Generates high-quality browser headers to avoid detection."""
    random_ua = ua.random
    return {
        "User-Agent": random_ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://platinmods.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
        "DNT": "1",  # Do Not Track
    }

# --- Modified Core Function ---

async def get_soup(url, client):
    """
    Fetches a URL with retries, header rotation, and cookie management.
    """
    max_retries = 3
    
    # Load previous session cookies to look like a returning user
    saved_cookies = await load_cookies()
    if saved_cookies:
        client.cookies.update(saved_cookies)

    for attempt in range(max_retries):
        headers = get_random_headers()
        
        try:
            # Add a small random delay before request (Humanizing)
            await asyncio.sleep(random.uniform(1, 3))
            
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            # Handle Bot Detection Codes
            if response.status_code in [403, 429, 503]:
                logger.warning(f"Detected/Blocked ({response.status_code}) on {url}. Retrying {attempt + 1}/{max_retries}...")
                
                # If blocked, clear cookies to force a new identity on next try
                client.cookies.clear()
                
                # Exponential backoff with jitter (wait 5s, 10s, etc.)
                wait_time = (5 * (attempt + 1)) + random.uniform(0, 5)
                await asyncio.sleep(wait_time)
                continue
            
            response.raise_for_status()
            
            # Success: Save the valid cookies for next time
            await save_cookies(client)
            
            # Move CPU-bound parsing work to a separate thread
            soup = await asyncio.to_thread(BeautifulSoup, response.content, 'html.parser')
            return soup

        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed for {url}: {e}")
            await asyncio.sleep(random.uniform(2, 5))
    
    logger.error(f"Fatal: Could not fetch {url} after {max_retries} attempts.")
    return None

# --- Tracking Logic (Unchanged Logic, just using new get_soup) ---

async def check_user_status(http_client, bot):
    """
    Checks user online status and sends alerts (online/offline).
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
            msg = f"🚨 **USER ALERT**\n\n👤 **{target['name']}** is now **ONLINE**! 🟢\n🔗 [Profile Link]({target['url']})"
            try:
                await bot.send_message(NOTIFICATION_CHAT_ID, msg, disable_web_page_preview=True)
                current_state[state_key] = True
                await save_state(current_state)
            except Exception as e:
                logger.error(f"Telegram Error: {e}")
        
        elif not is_online and was_online:
            msg = f"💤 **STATUS UPDATE**\n\n👤 **{target['name']}** is now **OFFLINE** 🔴"
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
    """
    state = await load_state()
    forum_counts = {}
    
    for forum_name, url in FORUM_TARGETS.items():
        soup = await get_soup(url, http_client)
        if not soup:
            forum_counts[forum_name] = "Error"
            continue

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

        if new_urls:
            for item in current_threads:
                if item['url'] in new_urls:
                    msg = f"✨ **NEW THREAD** in __{forum_name}__\n\n📝 **{item['title']}**\n🔗 [View Thread]({item['url']})"
                    try:
                        await bot.send_message(NOTIFICATION_CHAT_ID, msg)
                    except Exception as e:
                        logger.error(f"Telegram Error: {e}")

        if removed_urls:
            for item in previous_threads:
                if item['url'] in removed_urls:
                    msg = f"🗑 **THREAD REMOVED** from __{forum_name}__\n\n📝 **{item['title']}**"
                    try:
                        await bot.send_message(NOTIFICATION_CHAT_ID, msg)
                    except Exception as e:
                        logger.error(f"Telegram Error: {e}")

        state[forum_name] = current_threads
        await save_state(state)

    return forum_counts
