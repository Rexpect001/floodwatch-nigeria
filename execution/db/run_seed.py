"""
Run DB seed — loads states, LGAs, stations into PostgreSQL.
Usage in Render shell:
    python3 execution/db/run_seed.py
"""
import asyncio
import asyncpg
import os
import pathlib

async def run():
    url = os.environ['DATABASE_URL']
    conn = await asyncpg.connect(url)

    base = pathlib.Path('execution/db')
    for fname in ['schema.sql', 'seed.sql', 'schema_voice.sql']:
        fpath = base / fname
        if not fpath.exists():
            print(f'  SKIP  {fname} (not found)')
            continue
        sql = fpath.read_text()
        try:
            await conn.execute(sql)
            print(f'  OK    {fname}')
        except Exception as e:
            print(f'  WARN  {fname}: {e}')

    # Verify
    states = await conn.fetchval("SELECT COUNT(*) FROM states")
    lgas   = await conn.fetchval("SELECT COUNT(*) FROM lgas")
    print(f'\n  States: {states}  |  LGAs: {lgas}')
    await conn.close()
    print('Done.')

asyncio.run(run())
