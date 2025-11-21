## *Platinmods Monitor Bot*

***A fully automated monitoring bot for Platinmods.com built using Pyrogram, httpx, aiohttp, Flask, and asynchronous scraping with BeautifulSoup.***

---

### ✨ *Features*

- ***User Online/Offline tracking***  
- ***New forum thread detection***  
- ***Removed thread detection***  
- ***Manual `/check` command with summary***  
- ***Background scheduler***  
- ***Keep-alive support for Render/Railway***  
- ***Thread‑safe persistent state tracking***

---

### 🧩 *How It Works*

***The bot continuously:***
***1. Fetches Platinmods URLs using async HTTP clients  
2. Parses pages with BeautifulSoup  
3. Detects user status changes and new/removed threads  
4. Sends Telegram alerts  
5. Stores state in `platinmods_state.json`  
6. Runs forever using a scheduler + keep-alive pings***  

---

### 🚀 *Installation*

```bash
git clone https://github.com/MyselfNeon/Platinmods
cd Platinmods
pip install -r requirements.txt
```

---

### ⚙️ *Configuration*

```python
API_ID = 123
API_HASH = "your_hash"
BOT_TOKEN = "your_token"

NOTIFICATION_CHAT_ID = 123456789
CHECK_INTERVAL = 120

USER_TARGETS = [
    {"name": "Neon", "url": "https://platinmods.com/user/neon"}
]

FORUM_TARGETS = {
    "Mod Menu": "https://platinmods.com/forums/android-mod-menu"
}
```

---

### ▶️ *Running the Bot*

```bash
python main.py
```

---

### 🧪 *Commands*

**- `/start` *Shows your Chat ID***.  
**- `/check` *manual check + summary.***

---

### 🌐 *Deployment*

### *Render / Railway / Replit*

***1. Set `KEEP_ALIVE_URL`  
2. Add environment variables  
3. Deploy  
4. Bot stays awake using keep-alive task***  

---

## ❤️ *Author*

***Neon [MyselfNeon](https://t.me/myselfneon)***
