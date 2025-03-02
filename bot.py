import discord
import subprocess
import asyncio
import schedule
import time
import requests
import json
from datetime import datetime

import os

# 🛠️ 디스코드 봇 설정 (환경변수로 읽기)
TOKEN = os.environ.get("DISCORD_TOKEN", "")
CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID", "0"))

# 🛠️ 노션 API 설정 (환경변수로 읽기)
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 🛠️ 디스코드 웹훅 설정 (환경변수로 읽기)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


# 🔍 기존 회의 데이터를 저장할 파일
STATE_FILE = "meeting_state.json"

# 🔹 "Privileged Intents" 활성화
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.presences = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

@client.event
async def on_message(message):
    print(f"DEBUG: 받은 메시지 - {message.content}")  # 디버깅 메시지 추가

    if message.author == client.user:
        return  # 자기 자신이 보낸 메시지는 무시

    if message.content.startswith("!회의알림"):
        print("DEBUG: !회의알림 감지됨!")  # 디버깅 메시지 추가
        try:
            await send_meeting_schedule()
        except Exception as e:
            await message.channel.send(f"❌ 실행 중 오류 발생:\n```\n{str(e)}\n```")

client = discord.Client(intents=intents)

def load_previous_meeting():
    """이전 회의 일정을 불러온다"""
    try:
        with open(STATE_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def save_current_meeting(meeting):
    """현재 회의 일정을 파일로 저장한다"""
    with open(STATE_FILE, "w") as file:
        json.dump(meeting, file)

def get_notion_meetings():
    """노션 API에서 가장 빠른 미래 회의 데이터를 가져온다"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"

    try:
        response = requests.post(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ 노션 API 요청 실패: {e}")
        return None

    meetings = []
    today = datetime.today().date()

    for result in data.get("results", []):
        properties = result["properties"]

        # 📝 회의 제목 가져오기
        title = properties.get("Name", {}).get("title", [])
        title = title[0]["text"]["content"] if title else "제목 없음"

        # 📅 회의 날짜 가져오기
        date_str = properties.get("Meeting date", {}).get("date", {}).get("start")
        if not date_str:
            continue
        meeting_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # 📌 목표 가져오기
        goals = properties.get("목표", {}).get("rich_text", [])
        goals_str = goals[0]["text"]["content"] if goals else "목표 없음"

        # 미래 회의만 추가
        if meeting_date >= today:
            meetings.append({"title": title, "date": str(meeting_date), "goals": goals_str})

    meetings.sort(key=lambda x: x["date"])
    return meetings[0] if meetings else None

def send_discord_message(title, date, goals, update=False):
    """디스코드에 회의 일정 알림을 보낸다"""
    message_type = "🆕 **새로운 회의 일정이 추가되었습니다!**" if not update else "✏ **회의 일정이 수정되었습니다!**"

    message = {
        "content": f"{message_type}\n\n"
                   f"**📝 회의 이름:** {title}\n"
                   f"**📅 회의 날짜:** {date}\n"
                   f"**📌 목표:** {goals}"
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=message)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"❌ 디스코드 메시지 전송 실패: {e}")

async def send_meeting_schedule():
    """회의 일정을 확인하고 디스코드 채널에 전송"""
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("❌ 채널을 찾을 수 없습니다.")
        return

    await channel.send("📢 회의 일정을 확인 중...")

    current_meeting = get_notion_meetings()
    previous_meeting = load_previous_meeting()

    if current_meeting:
        if not previous_meeting:
            send_discord_message(current_meeting["title"], current_meeting["date"], current_meeting["goals"])
            save_current_meeting(current_meeting)
            await channel.send(f"✅ 다가오는 회의 일정이 전송되었습니다!")
        else:
            if (current_meeting["title"] != previous_meeting["title"] or
                current_meeting["date"] != previous_meeting["date"] or
                current_meeting["goals"] != previous_meeting["goals"]):
                
                send_discord_message(current_meeting["title"], current_meeting["date"], current_meeting["goals"], update=True)
                save_current_meeting(current_meeting)
                await channel.send(f"✏ 회의 일정이 업데이트되었습니다!")
            else:
                await channel.send("✅ 회의 일정 변경 없음.")
    else:
        await channel.send("⏳ 다가오는 회의 일정이 없습니다.")

@client.event
async def on_ready():
    print(f'✅ {client.user} 봇이 로그인되었습니다!')

    async def schedule_checker():
        while True:
            schedule.run_pending()
            await asyncio.sleep(60)  # 1분마다 체크

    # 매일 오전 9시에 자동 실행 (필요 시 변경 가능)
    schedule.every().day.at("09:00").do(lambda: asyncio.create_task(send_meeting_schedule()))

    client.loop.create_task(schedule_checker())  # 백그라운드에서 스케줄러 실행

@client.event
async def on_message(message):
    if message.author == client.user:
        return  # 자기 자신이 보낸 메시지는 무시

    if message.content.startswith("!회의알림"):
        try:
            await send_discord_message()
        except Exception as e:
            await message.channel.send(f"❌ 실행 중 오류 발생:\n```\n{str(e)}\n```")

async def send_simple_meeting_info(channel):
    """직접 !회의알림 호출 시, 다가오는 회의 일정만 간단히 안내"""
    current_meeting = get_notion_meetings()
    if current_meeting:
        await channel.send(
            f"**다가오는 회의 일정**\n\n"
            f"**📝 회의 이름:** {current_meeting['title']}\n"
            f"**📅 회의 날짜:** {current_meeting['date']}\n"
            f"**📌 목표:** {current_meeting['goals']}"
        )
    else:
        await channel.send("⏳ 현재 등록된 다가오는 회의 일정이 없습니다.")

@client.event
async def on_message(message):
    # 봇 자신이 보낸 메시지는 무시
    if message.author == client.user:
        return

    # "!회의알림" 명령어를 입력하면 단순 조회용 함수를 호출
    if message.content.startswith("!회의알림"):
        try:
            await send_simple_meeting_info(message.channel)
        except Exception as e:
            await message.channel.send(f"❌ 실행 중 오류 발생:\n\n{str(e)}\n")


# ✅ 봇 실행
client.run(TOKEN)
