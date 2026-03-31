from typing import Any, Dict, List, Optional

from db.connection import DatabaseConnection


class TrackerRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    async def get_config(self, guild_id: int) -> Optional[Dict[str, Any]]:
        return await self.db.execute_one(
            "SELECT * FROM tracker_configs WHERE guild_id = ?", (guild_id,)
        )

    async def create_or_update_config(self, guild_id: int, **kwargs):
        existing = await self.get_config(guild_id)
        if existing:
            if not kwargs:
                return
            kwargs['updated_at'] = 'CURRENT_TIMESTAMP'
            set_clause = ", ".join([
                f"{k} = CURRENT_TIMESTAMP" if v == 'CURRENT_TIMESTAMP' else f"{k} = ?"
                for k, v in kwargs.items()
            ])
            values = [v for v in kwargs.values() if v != 'CURRENT_TIMESTAMP']
            values.append(guild_id)
            await self.db.execute_write(
                f"UPDATE tracker_configs SET {set_clause} WHERE guild_id = ?",
                tuple(values)
            )
        else:
            columns = ["guild_id"] + list(kwargs.keys())
            placeholders = ", ".join(["?" for _ in columns])
            values = [guild_id] + list(kwargs.values())
            await self.db.execute_write(
                f"INSERT INTO tracker_configs ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(values)
            )

    async def delete_config(self, guild_id: int):
        await self.db.execute_write(
            "DELETE FROM tracker_configs WHERE guild_id = ?", (guild_id,)
        )

    async def get_all_enabled(self) -> List[Dict[str, Any]]:
        return await self.db.execute_many(
            "SELECT * FROM tracker_configs WHERE enabled = 1"
        )

    async def record_response(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        response_type: str,
        calendar_event: Optional[str],
        prompt_message_id: Optional[int],
        response_date: str,
    ):
        await self.db.execute_write(
            """INSERT INTO tracker_responses
               (guild_id, user_id, username, response_type, calendar_event,
                prompt_message_id, response_date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (guild_id, user_id, username, response_type, calendar_event,
             prompt_message_id, response_date)
        )

    async def get_responses_for_date(
        self, guild_id: int, date: str
    ) -> List[Dict[str, Any]]:
        return await self.db.execute_many(
            """SELECT * FROM tracker_responses
               WHERE guild_id = ? AND response_date = ?
               ORDER BY responded_at""",
            (guild_id, date)
        )

    async def clear_responses_for_guild(self, guild_id: int):
        await self.db.execute_write(
            "DELETE FROM tracker_responses WHERE guild_id = ?", (guild_id,)
        )
