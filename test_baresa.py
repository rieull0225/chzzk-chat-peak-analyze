#!/usr/bin/env python3.11
"""Test Baresa channel chat collection."""

import asyncio
import sys
from chzzkpy import Client, Message, UserPermission

client_id = "bd2df002-45be-46a6-93d4-a4886f25dd1a"
client_secret = "2HGVpBDoAGMoQMznDCDjrHLPudJWcKg_Jdpi3MY0sPc"

client = Client(client_id, client_secret)

message_count = 0

@client.event
async def on_chat(message: Message):
    global message_count
    message_count += 1
    print(f"[{message_count}] {message.profile.nickname}: {message.content}")
    sys.stdout.flush()

async def main():
    print("Starting authentication...")

    # Load token from cache
    import json
    from pathlib import Path
    from chzzkpy.authorization import AccessToken

    token_file = Path.home() / ".nokchart_token.json"
    with open(token_file, "r") as f:
        token_data = json.load(f)

    access_token = AccessToken(**token_data)
    print(f"✅ Loaded token")

    from chzzkpy.client import UserClient
    user_client = UserClient(client, access_token)

    print(f"🔌 Connecting to chat...")
    await user_client.connect(UserPermission.all())
    print("연결 종료됨")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n\n총 {message_count}개 메시지 수신")
