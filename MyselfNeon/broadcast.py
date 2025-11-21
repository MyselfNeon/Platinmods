from pyrogram.errors import InputUserDeactivated, UserNotParticipant, FloodWait, UserIsBlocked, PeerIdInvalid
from MyselfNeon.db import db
from pyrogram import Client, filters
from config import ADMINS
import asyncio
import datetime
import time
from pyrogram.types import Message
import json
import os
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------
# Broadcast helper function
# ---------------------------------------------------
async def broadcast_messages(user_id, message):
    """
    Attempts to send a message copy to a single user and handles various Pyrogram errors.
    """
    try:
        await message.copy(chat_id=user_id)
        return True, "Success"
    except FloodWait as e:
        # Wait the required time and retry the broadcast
        logger.warning(f"FloodWait encountered for user {user_id}, waiting {e.value}s.")
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message)
    except (InputUserDeactivated, UserIsBlocked, UserNotParticipant):
        # User has blocked the bot or left the chat; delete them from the database
        await db.delete_user(int(user_id))
        return False, "Deleted/Blocked"
    except PeerIdInvalid:
        # Invalid ID, also delete to clean up
        await db.delete_user(int(user_id))
        return False, "Error"
    except Exception as e:
        logger.error(f"[!] Broadcast error for {user_id}: {e}")
        return False, "Error"

# ---------------------------------------------------
# /broadcast command
# ---------------------------------------------------
@Client.on_message(filters.command("broadcast") & filters.user(ADMINS))
async def broadcast_command(bot: Client, message: Message):
    """
    Sends a message to all users stored in the MongoDB database.
    Restricted to users defined in config.ADMINS.
    """
    b_msg = message.reply_to_message
    if not b_msg:
        return await message.reply_text(
            "**__Reply to this command with the message you want to broadcast.__**",
            quote=True
        )

    # Note: db.get_all_users() returns an async cursor
    users_cursor = db.get_all_users()
    sts = await message.reply_text(
        text='**__Broadcasting your message...__**',
        quote=True
    )

    start_time = time.time()
    total_users = await db.total_users_count()
    done = 0
    blocked_or_deleted = 0
    failed = 0
    success = 0

    async for user in users_cursor:
        user_id = user.get('id')
        if user_id:
            # Broadcast the message
            pti, sh = await broadcast_messages(int(user_id), b_msg)
            
            if pti:
                success += 1
            else:
                if sh == "Deleted/Blocked":
                    blocked_or_deleted += 1
                elif sh == "Error":
                    failed += 1
            
            done += 1

            # Update status message every 20 users
            if done % 20 == 0:
                time_elapsed = datetime.timedelta(seconds=int(time.time() - start_time))
                await sts.edit(
                    f"**__Broadcast In Progress:__**\n\n"
                    f"**👥 Total Users:** {total_users}\n"
                    f"**💫 Completed:** {done} / {total_users}\n"
                    f"**✅ Success:** {success}\n"
                    f"**🚫 Blocked/Deleted:** {blocked_or_deleted}\n"
                    f"**❌ Failed (Other Error):** {failed}\n"
                    f"**⏳ Time Elapsed:** {time_elapsed}"
                )
        else:
            done += 1
            failed += 1
            
            if done % 20 == 0:
                 time_elapsed = datetime.timedelta(seconds=int(time.time() - start_time))
                 await sts.edit(
                    f"**__Broadcast In Progress:__**\n\n"
                    f"**👥 Total Users:** {total_users}\n"
                    f"**💫 Completed:** {done} / {total_users}\n"
                    f"**✅ Success:** {success}\n"
                    f"**🚫 Blocked/Deleted:** {blocked_or_deleted}\n"
                    f"**❌ Failed (Other Error):** {failed}\n"
                    f"**⏳ Time Elapsed:** {time_elapsed}"
                )

    time_taken = datetime.timedelta(seconds=int(time.time() - start_time))
    await sts.edit(
        f"**__Broadcast Completed:__**\n"
        f"**⏰ Completed in:** {time_taken}\n\n"
        f"**👥 Total Users:** {total_users}\n"
        f"**✅ Success:** {success}\n"
        f"**🚫 Blocked/Deleted:** {blocked_or_deleted}\n"
        f"**❌ Failed (Other Error):** {failed}"
    )

# ---------------------------------------------------
# /users Command (Standalone + JSON export)
# ---------------------------------------------------
@Client.on_message(filters.command("users") & filters.user(ADMINS))
async def users_count(bot: Client, message: Message):
    """
    Displays the total user count and exports all user data to a JSON file.
    Restricted to users defined in config.ADMINS.
    """
    msg = await message.reply_text("⏳ <b>__Gathering User Data...__</b>", quote=True)
    
    try:
        total = await db.total_users_count()
        await msg.edit_text(
            f"""
🌀 <b><i>User Analytics Update</i></b> 🌀

👥 <b>Total Registered Users:</b> {total}
🛰 <b>System Status:</b> Active ✅
🧠 <b>Data Source:</b> MongoDB (async)
"""
        )

        users_cursor = db.get_all_users()
        users_list = []
        async for user in users_cursor:
            users_list.append({
                "name": user.get("name", "N/A"),
                # You might want to store 'username' upon start if available, 
                # but using 'name' (full name) as it's more reliable.
                "id": user.get("id"),
                "session_status": "Set" if user.get("session") else "None"
            })

        tmp_path = "user_data_export.json" # Changed filename to avoid conflict with example
        
        # Save JSON to a temporary file
        with open(tmp_path, "w", encoding="utf-8") as f:
            # Ensure serialization is JSON-compatible
            json.dump(users_list, f, indent=4, ensure_ascii=False)

        caption = f"📄 **Recorded {len(users_list)} Users**"
        await message.reply_document(
            document=tmp_path,
            caption=caption
        )

        # Cleanup the temporary file
        try:
            os.remove(tmp_path)
        except Exception as e:
            logger.error(f"[!] Failed to Delete File {tmp_path}: {e}")

    except Exception as e:
        await msg.edit_text(f"**__⚠️ Error Fetching User Data:__**\n<code>{e}</code>")
        logger.error(f"[!] /users error: {e}")
