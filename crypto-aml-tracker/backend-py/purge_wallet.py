import asyncio
from db.mysql import get_pool, connect_mysql

async def main():
    await connect_mysql()
    pool = get_pool()
    target = '0xf977814e90da44bfa03b6295a0616a897441acec'
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM transactions WHERE LOWER(from_address) = %s OR LOWER(to_address) = %s", (target, target))
            print(f"Purged {cur.rowcount} cached synthetic records for {target}")

if __name__ == '__main__':
    asyncio.run(main())
