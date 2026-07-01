import asyncio
import sys
from db.models import DBManager

async def test():
    db = DBManager()
    u = await db.get_user(6811891287)
    print("User: ", u)

if __name__ == "__main__":
    asyncio.run(test())
