import asqlite

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
    def __init__(self, base_tables: list[BaseTable], *args, **kwargs):
        self.base_tables = base_tables
        self.args, self.kwargs = args, kwargs
        self.db = None

    async def startup(self):
        self.db: asqlite.Connection = await asqlite.connect(*self.args, **self.kwargs)
        await self.create_table()

    async def conn(self):
        return await asqlite.connect(*self.args, **self.kwargs)

    async def create_table(self):
        async with self.db as conn:
            for table in self.base_tables:
                column_schema = ', '.join(
                    f'{col.name} {col.datatype} {col.addit_schema or ""}' for col in table.columns
                )
                command = f"CREATE TABLE IF NOT EXISTS {table.name} ({column_schema})"
                await conn.execute(command)

            await conn.commit()
