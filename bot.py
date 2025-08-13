import asyncio
import json
import os
from collections import defaultdict
import websockets
import discord
from discord.ext import commands
from dotenv import load_dotenv

# โหลดค่าจาก .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
WS_URI = os.getenv("WS_URI")

# ------------ DATA STORE ------------
latest_data = {
    "gear": [],
    "seeds": [],
    "cosmetics": [],
    "honey": [],
    "eggs": [],
    "timestamp": 0,
}

# ------------ UTILS ------------
def combine_items_by_name(items):
    combined = defaultdict(int)
    for item in items:
        combined[item["name"]] += item.get("quantity", 0)
    return [{"name": name, "quantity": qty} for name, qty in combined.items()]

def clean_items(items, keys_to_keep={"name", "quantity"}):
    return [{k: item[k] for k in keys_to_keep if k in item} for item in items]

# ------------ DISCORD BOT ------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    asyncio.create_task(websocket_listener())

# ------------ SPECIAL ITEMS ------------
with open("special.txt", "r", encoding="utf-8") as f:
    special_items = {line.strip() for line in f if line.strip()}

# ------------ CHECK & NOTIFY ------------
pending_update = False  # ตัวแปร batch update

async def schedule_update(prev_data, latest_data, delay=1.0):
    global pending_update
    if pending_update:
        return
    pending_update = True
    await asyncio.sleep(delay)  # รวบรวมหลายรอบก่อนส่ง
    await check_and_notify(prev_data, latest_data)
    pending_update = False

async def check_and_notify(prev, current):
    channel = bot.get_channel(DISCORD_CHANNEL_ID)
    if not channel:
        return

    categories_to_notify = ["gear", "eggs", "honey", "seeds"]

    # ลบข้อความเก่าทั้งหมด (ถ้าต้องการ)
    try:
        await channel.purge(limit=100)
    except Exception as e:
        print(f"❌ ลบข้อความล้มเหลว: {e}")

    embed = discord.Embed(
        title=f"✨ อัปเดตล่าสุด ✨",
        description="นี่คือข้อมูลล่าสุดทั้งหมด",
        color=0xFFB966
    )

    for category in categories_to_notify:
        items = current.get(category, [])
        if not items:
            continue

        changes = []
        for item in items:
            name = item["name"]
            qty = item.get("quantity", 0)
            if name in special_items:
                changes.append(f"```fix\n{name} — X{qty}```")
            else:
                changes.append(f"**{name}** — `X{qty}`")

        if changes:
            icon = {
                "gear": "⚙️",
                "eggs": "🥚",
                "honey": "🍯",
                "seeds": "🌱",
            }.get(category, "📢")

            category_name = category.capitalize()
            field_value = "\n".join(f"  {change}" for change in changes)
            embed.add_field(name=f"{icon} {category_name}", value=field_value, inline=False)

    await channel.send(embed=embed)

# ------------ WEBSOCKET LISTENER ------------
async def websocket_listener():
    prev_data = {}
    while True:
        try:
            async with websockets.connect(WS_URI) as websocket:
                print("🌐 Connected to WebSocket")
                async for message in websocket:
                    data = json.loads(message)
                    if data.get("type"):
                        latest_data.update(data["data"])
                        for category in ["gear", "seeds", "cosmetics", "honey"]:
                            if category in latest_data:
                                latest_data[category] = clean_items(latest_data[category])
                        if "eggs" in latest_data:
                            latest_data["eggs"] = combine_items_by_name(latest_data["eggs"])

                        # ใช้ schedule_update รวมหลายรอบ
                        asyncio.create_task(schedule_update(prev_data, latest_data))
                        prev_data = latest_data.copy()
        except Exception as e:
            print(f"❌ WebSocket error: {e}, retrying in 5s...")
            await asyncio.sleep(5)

# ------------ RUN BOT ------------
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
