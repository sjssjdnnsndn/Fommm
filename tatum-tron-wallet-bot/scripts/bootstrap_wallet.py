from __future__ import annotations

import argparse
import asyncio
import os
import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(description="Create/inspect the Tatum TRON HD wallet used by the bot.")
    parser.add_argument("--api-key", default=os.getenv("TATUM_API_KEY"))
    parser.add_argument("--mnemonic", default=os.getenv("TRON_MNEMONIC"))
    args = parser.parse_args()
    if not args.api_key:
        raise SystemExit("Missing TATUM_API_KEY")

    headers = {"x-api-key": args.api_key}
    params = {"mnemonic": args.mnemonic} if args.mnemonic else None
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        r = await client.get("https://api.tatum.io/v3/tron/wallet", params=params)
        r.raise_for_status()
        data = r.json()
    print("Tatum returned:")
    print(data)
    print("\nSave the returned mnemonic and xpub securely in your .env file.")


if __name__ == "__main__":
    asyncio.run(main())
