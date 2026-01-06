#!/usr/bin/env python3.11
"""Generate authentication token for NokChart."""

import asyncio
import sys
import yaml
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from nokchart.collector import ChzzkClient


async def main():
    # Load config
    config_file = Path("config.yaml")
    if not config_file.exists():
        print("Error: config.yaml not found")
        return 1

    with open(config_file) as f:
        config = yaml.safe_load(f)

    client_id = config.get("chzzk_client_id")
    client_secret = config.get("chzzk_client_secret")

    if not client_id or not client_secret:
        print("Error: chzzk_client_id and chzzk_client_secret must be set in config.yaml")
        return 1

    # Create client and initialize (this will do OAuth flow)
    client = ChzzkClient(client_id, client_secret)

    try:
        await client.initialize()
        print(f"\n✅ 토큰이 {client.token_cache_file}에 저장되었습니다!")
        print("이제 Docker를 실행할 수 있습니다.\n")
        return 0
    except Exception as e:
        print(f"\n❌ 인증 실패: {e}\n")
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
