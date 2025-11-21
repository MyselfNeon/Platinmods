import asyncio
import logging
import httpx
from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID, AUTH_USERS # Import auth constants
from MyselfNeon.track import check_user_status, check_forums # Import tracking logic

logger = logging.getLogger(__name__)

# --- Authorization Filter (Defined here for the check command) ---
def auth_user_filter(_, client, message: Message):
    """Custom filter to check if the user is the owner or an authorized user."""
    # This filter handles the USER ID check only.
    if not message.from_user:
        return False
        
    user_id = message.from_user.id
    
    # Check for Owner ID first, then Authorized Users set
    is_authorized = user_id == OWNER_ID or user_id in AUTH_USERS
    
    if not is_authorized:
        logger.warning(f"Unauthorized access attempt to /check by user ID: {user_id}")
        # Send a reply only for unauthorized users
        asyncio.create_task(message.reply("⛔ **__Access Denied__**\n__You are not authorized to use this command.__"))
        
    return is_authorized

# Pyrogram filter variable
authorized_users_only = filters.create(auth_user_filter)
# ---------------------------

@Client.on_message(filters.command("check") & authorized_users_only & filters.private)
async def force_check(client: Client, message: Message):
    """
    Triggers an immediate check for authorized users.
    RESTRICTED to: Authorized Users + Private Chats Only.
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
            # Use httpx for asynchronous web requests
            async with httpx.AsyncClient(timeout=20.0) as http_client:
                # Run the monitoring functions
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
            
            # Send the detailed summary report back to the user's chat
            await client.send_message(chat_id, final_message)

        except Exception as e:
            logger.error(f"Error during force check: {e}")
            await client.send_message(chat_id, f"❌ **__Check failed.**\nAn internal error occurred.__")

    # Create a new, independent task to run the scraping in the background
    asyncio.create_task(run_check_and_confirm(message.chat.id))
