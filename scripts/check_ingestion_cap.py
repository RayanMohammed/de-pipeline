"""
Decides whether a scheduled-ingestion run should do anything at all.

Queries the real patient count directly against Postgres -- not through the
API -- because the API isn't deployed anywhere persistent; it only runs when
someone has uvicorn open locally. A scheduled GitHub Actions job can't reach
that, but it can reach Supabase directly, the same way any other database
client would.

Writes two values to $GITHUB_ENV for the rest of the workflow to consume:
  SHOULD_INGEST=true/false
  BATCH_SIZE=<int>   (a random 100-200, clamped to whatever headroom is left)

This intentionally has no side effects of its own -- it only decides and
reports. The actual writing happens later, in batch_ingest.py.
"""
import os
import random
import sys

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
MAX_PATIENTS = int(os.getenv("MAX_PATIENTS", "3000"))
MIN_BATCH = 100
MAX_BATCH = 200


def compute_batch_size(current_count: int, cap: int) -> int:
    """
    Pure function, deliberately separated from the DB call so it's testable
    without a database: a random 100-200 patients, clamped so a run can
    never push the total past the cap. Returns 0 if there's no headroom left
    (the cap is already reached or exceeded) -- 0 means "do nothing," not
    "an error."
    """
    headroom = cap - current_count
    if headroom <= 0:
        return 0
    random_draw = random.randint(MIN_BATCH, MAX_BATCH)
    return min(random_draw, headroom)


async def main():
    # Same statement_cache_size=0 reasoning as batch_ingest.py -- this needs
    # to work whether DATABASE_URL is a direct connection or the pooler.
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)
    try:
        current_count = await conn.fetchval("SELECT COUNT(*) FROM patients;")
    finally:
        await conn.close()

    batch_size = compute_batch_size(current_count, MAX_PATIENTS)
    should_ingest = batch_size > 0

    print(f"Current patient count: {current_count} (cap: {MAX_PATIENTS})")
    if should_ingest:
        print(f"Headroom available -- generating {batch_size} new patients this run.")
    else:
        print("Cap reached or exceeded -- skipping this run entirely.")

    github_env = os.getenv("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"SHOULD_INGEST={'true' if should_ingest else 'false'}\n")
            f.write(f"BATCH_SIZE={batch_size}\n")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
