#!/usr/bin/env python3.11
"""Simple test following official chzzkpy example."""

import asyncio
from chzzkpy import Client, Message, UserPermission

client_id = "bd2df002-45be-46a6-93d4-a4886f25dd1a"
client_secret = "2HGVpBDoAGMoQMznDCDjrHLPudJWcKg_Jdpi3MY0sPc"

client = Client(client_id, client_secret)

@client.event
async def on_chat(message: Message):
    print(f"[CHAT] {message.profile.nickname}: {message.content}")

async def main():
    print("Starting authentication...")

    # Generate authorization URL
    auth_url = client.generate_authorization_token_url(
        redirect_url="http://localhost:8080",
        state="nokchart_oauth_state_12345"
    )

    print(f"\n{'='*80}")
    print("치지직 API 인증이 필요합니다")
    print(f"{'='*80}")
    print(f"\n1. 아래 URL을 브라우저에서 열어 로그인하세요:")
    print(f"\n   {auth_url}\n")
    print("2. 로그인 후 리디렉션 URL에서 'code=' 뒤의 코드를 복사하세요")
    print(f"\n{'='*80}\n")

    code = input("인증 코드를 입력하세요: ").strip()

    print("\n사용자 클라이언트 생성 중...")
    user_client = await client.generate_user_client(code, "nokchart_oauth_state_12345")

    print(f"✅ 인증 성공!")
    print(f"UserClient: {user_client}")
    print(f"Access token: {user_client.access_token.access_token[:20]}...")

    print("\n채팅 연결 시도 중...")
    await user_client.connect(UserPermission.all())

if __name__ == "__main__":
    asyncio.run(main())
