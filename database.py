
import os

from db.connection import DatabaseConnection
from db.repositories.campaign import CampaignRepository
from db.repositories.file_storage import FileStorageRepository
from db.repositories.memory import MemoryRepository
from db.repositories.tracker import TrackerRepository


class Database:
    _instance = None
    _initialized = False

    def __new__(cls, db_path: str = "data/lockedbot.db"):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = "data/lockedbot.db"):
        if self.__class__._initialized:
            return
        data_dir = os.path.dirname(db_path)
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        self.connection = DatabaseConnection(db_path)
        self.tracker = TrackerRepository(self.connection)
        self.campaigns = CampaignRepository(self.connection)
        self.file_storage = FileStorageRepository(self.connection)
        self.memories = MemoryRepository(self.connection)
        self.__class__._initialized = True

    async def connect(self):
        await self.connection.connect()

    async def close(self):
        await self.connection.close()

    # --- Low-level pass-throughs for repositories that import `db` directly ---

    async def execute_write(self, query: str, params: tuple = ()):
        await self.connection.execute_write(query, params)

    async def execute_one(self, query: str, params: tuple = ()):
        return await self.connection.execute_one(query, params)

    async def execute_many(self, query: str, params: tuple = ()):
        return await self.connection.execute_many(query, params)

    # --- Memory helpers (used by AI cog) ---

    async def add_user_memory(self, user_id: int, guild_id: int, content: str):
        return await self.memories.add_memory(user_id, guild_id, content)

    async def get_user_memories(self, user_id: int, guild_id: int, limit: int = 10):
        return await self.memories.get_memories(user_id, guild_id, limit)

    async def search_user_memories(self, user_id: int, guild_id: int, search_term: str, limit: int = 5):
        return await self.memories.search_memories(user_id, guild_id, search_term, limit)

    async def delete_user_memory(self, memory_id: int, user_id: int):
        await self.memories.delete_memory(memory_id, user_id)


db = Database()
