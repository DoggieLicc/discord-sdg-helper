import asqlite
import os

from dataclasses import dataclass


@dataclass(slots=True)
class BaseColumn:
    name: str
    datatype: str
    addit_schema: str | None = None


@dataclass(slots=True)
class BaseTable:
    name: str
    columns: list[BaseColumn]


class DatabaseHelper:
    def __init__(self, base_tables: list[BaseTable], user_version: int, *args, **kwargs):
        self.base_tables = base_tables
        self.user_version = user_version
        self.args, self.kwargs = args, kwargs
        self.db = None
        self.add_version = False

    async def startup(self):
        if not os.path.exists(self.args[0]):
            self.add_version = True

        self.db: asqlite.Connection = await asqlite.connect(*self.args, **self.kwargs)
        if self.add_version:
            await self.set_version()

        await self.create_table()

    async def conn(self):
        return await asqlite.connect(*self.args, **self.kwargs)

    async def set_version(self):
        async with self.db as conn:
            await conn.execute(f'PRAGMA user_version = {self.user_version}')

    async def create_table(self):
        async with self.db as conn:
            for table in self.base_tables:
                column_schema = ', '.join(
                    f'{col.name} {col.datatype}{" " + col.addit_schema if col.addit_schema else ""}' for col in table.columns
                )
                command = f"CREATE TABLE IF NOT EXISTS {table.name} ({column_schema})"
                await conn.execute(command)

            await conn.commit()
