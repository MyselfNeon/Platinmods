import asyncio
import json
import os
import logging
import random
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from config import USER_TARGETS, FORUM_TARGETS, NOTIFICATION_CHAT_ID

# Configure Logger for this module
logger = logging.getLogger(__name__)

STATE_FILE = 'platinmods_state.json'
COOKIE_FILE = 'cookies.json'

# Initialize UserAgent rotator
ua = UserAgent()

# --- Helper Functions (State Management) ---

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
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

async def load_state():
    return await asyncio.to_thread(_load_state_sync)

async def save_state(state):
    await asyncio.to_thread(_save_state_sync, state)

# --- Helper Functions (Cookie Management - FIX for Multiple Cookies) ---

def _load_cookies_sync():
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_cookies_sync(client):
    """
    Safely extracts cookies from the client jar. 
    Bypasses httpx.CookieConflict by manually iterating the jar 
    and flattening duplicates.
    """
    try:
        flat_cookies = {}
        
        # Check if we can access the raw jar (httpx standard)
        if hasattr(client.cookies, 'jar'):
            # Iterate over the standard python http.cookiejar
            # If duplicates exist (same name, different path), 
            # this loop simply overwrites the key with the latest value,
            # effectively flattening it and preventing the crash.
            for cookie in client.cookies.jar:
                flat_cookies[cookie.name] = cookie.value
        else:
            # Fallback: Try to access items directly (might raise conflict if not careful)
            # We wrap in try/except just in case
            try:
                for key, value in client.cookies.items():
                    flat_cookies[key] = value
            except Exception:
                pass # Ignore if dict access fails due to conflicts

        if flat_cookies:
            with open(COOKIE_FILE, 'w') as f:
                json.dump(flat_cookies, f)
            
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")

async def load_cookies():
    return await asyncio.to_thread(_load_cookies_sync)

async def save_cookies(client):
    await asyncio.to_thread(_save_cookies_sync, client)

# --- Helper Functions (Anti-Detection Headers) ---

def get_random_headers():
    """Generates high-quality browser headers to avoid detection."""
    # Randomize User Agent
    try:
        random_ua = ua.random
    except:
        random_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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

# --- Core Scraper Logic ---

async def get_soup(url, client):
    """
    Fetches a URL with retries, header rotation, cookie persistence,
    and specific handling for the 'Multiple cookies' crash.
    """
    max_retries = 3
    
    # Load previous session cookies to look like a returning user
    saved_cookies = await load_cookies()
    if saved_cookies:
        try:
            client.cookies.update(saved_cookies)
        except Exception:
            # If loading cookies causes a conflict, clear them and start fresh
            client.cookies.clear()

    for attempt in range(max_retries):
        headers = get_random_headers()
        
        try:
            # Jitter: Random sleep to look human
            await asyncio.sleep(random.uniform(2, 5))
            
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            # 1. Handle Bot Detection Codes (403 Forbidden / 429 Too Many Requests)
            if response.status_code in [403, 429, 503]:
                logger.warning(f"Detected/Blocked ({response.status_code}) on {url}. Retrying {attempt + 1}/{max_retries}...")
                
                # Clear cookies to get a new session ID
                client.cookies.clear()
                
                # Exponential backoff: Wait 5s, then 10s, then 15s...
                wait_time = (5 * (attempt + 1)) + random.uniform(0, 5)
                await asyncio.sleep(wait_time)
                continue
            
            response.raise_for_status()
            
            # 2. Save Cookies (Using safe flattener)
            await save_cookies(client)
            
            # 3. Handle Encoding (Fixes bs4.dammit warnings)
            # We use response.content (bytes) instead of .text to let BS4 detect encoding
            content = response.content
            
            # Move CPU-bound parsing work to a separate thread
            soup = await asyncio.to_thread(BeautifulSoup, content, 'html.parser')
            return soup

        except Exception as e:
            error_msg = str(e)
            
            # specific handler for the Cookie Conflict crash
            if "Multiple cookies exist" in error_msg:
                logger.error(f"Cookie conflict detected. Clearing cookies and retrying immediately.")
                client.cookies.clear()
                if os.path.exists(COOKIE_FILE):
                    try:
                        os.remove(COOKIE_FILE)
                    except:
                        pass
                # Do not wait long for this specific error, just retry clean
                await asyncio.sleep(1)
                continue
            
            logger.error(f"Attempt {attempt + 1} failed for {url}: {e}")
            await asyncio.sleep(random.uniform(2, 5))
    
    logger.error(f"Fatal: Could not fetch {url} after {max_retries} attempts.")
    return None

# --- Business Logic (Tracking) ---

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
        
        # Try to find the Online indicator
        # Method 1: Look for 'Online now' text directly
        if soup.find(string="Online now"):
            is_online = True
        else:
            # Method 2: Look for specific class
            status_element = soup.find('span', class_='userTitle') 
            if status_element and "Online" in status_element.get_text():
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

        # XenForo 2 generic selector for thread titles
        thread_links = soup.select('.structItem-title a')
        
        current_threads = []
        for link in thread_links:
            text = link.get_text(strip=True)
            href = link.get('href')
            
            # Basic validation to ensure it's a thread link
            if href and ("threads/" in href or "resources/" in href):
                full_url = f"https://platinmods.com{href}" if href.startswith('/') else href
                # Avoid duplicates in the list
                if not any(t['url'] == full_url for t in current_threads):
                    current_threads.append({"title": text, "url": full_url})
        
        forum_counts[forum_name] = len(current_threads)

        previous_threads = state.get(forum_name, [])
        # Create sets of URLs for easy comparison
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
