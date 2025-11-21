import motor.motor_asyncio
import logging
from config import DB_NAME, DB_URI

logger = logging.getLogger(__name__)

class Database:
    """
    Asynchronous MongoDB client using motor.
    Handles tracking state and user sessions.
    """
    
    def __init__(self, uri, database_name):
        # Initialize client, check if DB_URI is set
        if not uri:
            logger.error("DB_URI is not set! Database functions will fail.")
            # Use a dummy client to prevent immediate crash, but operations will fail
            self._client = None
        else:
            self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
            self.db = self._client[database_name]
            # Use a collection dedicated to tracking states, separate from user data
            self.state_col = self.db.tracking_state
            self.user_col = self.db.users # For general user management (e.g., sessions)

    # --- Tracking State (User Status / Forum Threads) ---
    
    async def get_state(self, key):
        """Retrieves a specific tracking state (e.g., user status, forum threads)."""
        if not self._client: return None
        data = await self.state_col.find_one({'_id': key})
        return data.get('value') if data else None

    async def set_state(self, key, value):
        """Saves a specific tracking state."""
        if not self._client: return
        await self.state_col.update_one(
            {'_id': key},
            {'$set': {'value': value}},
            upsert=True
        )

    # --- User Management (General) ---

    def new_user(self, id, name):
        """Creates a default user dictionary."""
        return dict(
            id = id,
            name = name,
            session = None,
        )
    
    async def add_user(self, id, name):
        """Adds a new user to the users collection."""
        if not self._client: return
        if not await self.is_user_exist(id):
            user = self.new_user(id, name)
            await self.user_col.insert_one(user)
    
    async def is_user_exist(self, id):
        """Checks if a user exists in the users collection."""
        if not self._client: return False
        user = await self.user_col.find_one({'id':int(id)})
        return bool(user)
    
    async def total_users_count(self):
        """Counts the total number of users."""
        if not self._client: return 0
        count = await self.user_col.count_documents({})
        return count

    async def get_all_users(self):
        """Retrieves a cursor of all users."""
        if not self._client: return []
        return self.user_col.find({})

    async def delete_user(self, user_id):
        """Deletes a user from the users collection."""
        if not self._client: return
        await self.user_col.delete_many({'id': int(user_id)})

    async def set_session(self, id, session):
        """Sets a user's session data."""
        if not self._client: return
        await self.user_col.update_one({'id': int(id)}, {'$set': {'session': session}})

    async def get_session(self, id):
        """Retrieves a user's session data."""
        if not self._client: return None
        user = await self.user_col.find_one({'id': int(id)})
        return user.get('session') if user else None

# Initialize the database object
db = Database(DB_URI, DB_NAME)
