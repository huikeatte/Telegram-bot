"""
Telegram group poller for GitHub Actions -> n8n webhook.

Runs on a schedule, logs in as a Telegram USER (Telethon + session string),
reads recent group messages (including messages sent by other bots) and POSTs
them to an n8n Webhook in one batch. Overlapping runs are expected; n8n
removes duplicates by chat id + message id.

Env vars (set as GitHub Actions secrets):
  TG_API_ID, TG_API_HASH   from https://my.telegram.org
  TG_SESSION_STRING        output of generate_session.py
  TG_CHAT_IDS              comma-separated chat ids, e.g. -5344007020
  N8N_WEBHOOK_URL          production URL of the n8n Webhook node (/webhook/...)
  N8N_WEBHOOK_SECRET       shared secret, must match the n8n Code node
Optional:
  LOOKBACK_MINUTES         how far back each run reads (default 60)
  ONLY_BOTS                "true" = forward bot messages only (default true)

NOTE: logs of public repos are public - never print message content here.
"""
import os
import sys
import json
import asyncio
import urllib.request
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, utils
from telethon.sessions import StringSession
from telethon.tl.types import User, Channel, Chat

# .strip(): pasted secrets often carry a trailing newline or space
API_ID = int(os.environ["TG_API_ID"].strip())
API_HASH = os.environ["TG_API_HASH"].strip()
SESSION_STRING = os.environ["TG_SESSION_STRING"].strip()
CHAT_IDS = [int(x) for x in os.environ["TG_CHAT_IDS"].split(",") if x.strip()]
WEBHOOK_URL = os.environ["N8N_WEBHOOK_URL"].strip()
WEBHOOK_SECRET = os.environ.get("N8N_WEBHOOK_SECRET", "").strip()
LOOKBACK_MINUTES = int(os.environ.get("LOOKBACK_MINUTES") or 60)
ONLY_BOTS = (os.environ.get("ONLY_BOTS") or "true").lower() == "true"


def sender_dict(sender):
    if isinstance(sender, User):
        return {
            "id": sender.id,
            "is_bot": bool(sender.bot),
            "first_name": sender.first_name,
            "last_name": sender.last_name,
            "username": sender.username,
        }
    if isinstance(sender, Channel):  # anonymous admin / channel signature
        return {"id": sender.id, "is_bot": False, "first_name": sender.title, "username": sender.username}
    return None


def chat_dict(chat):
    if isinstance(chat, Channel):
        chat_type = "supergroup" if chat.megagroup else "channel"
    elif isinstance(chat, Chat):
        chat_type = "group"
    else:
        chat_type = "private"
    return {"id": utils.get_peer_id(chat), "title": getattr(chat, "title", None), "type": chat_type}


async def collect(client):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)
    await client.get_dialogs()  # populate entity cache so numeric chat ids resolve
    messages = []

    for chat_id in CHAT_IDS:
        chat = await client.get_entity(chat_id)
        checked = 0
        async for msg in client.iter_messages(chat, limit=500):  # newest first
            if msg.date < cutoff:
                break
            if getattr(msg, "action", None):  # service messages: joins, pins, title changes...
                continue
            checked += 1
            sender = sender_dict(await msg.get_sender())
            if ONLY_BOTS and not (sender and sender["is_bot"]):
                continue
            messages.append({
                "message_id": msg.id,
                "from": sender,
                "chat": chat_dict(chat),
                "date": int(msg.date.timestamp()),
                "text": msg.message or "",
                "has_media": msg.media is not None,
                "reply_to_message_id": msg.reply_to_msg_id,
            })
        # Counts only - logs of public repos are public
        print(f"Chat {chat_id}: {checked} message(s) in the last {LOOKBACK_MINUTES} min, "
              f"{sum(1 for m in messages if m['chat']['id'] == utils.get_peer_id(chat))} to forward.")

    messages.sort(key=lambda m: (m["date"], m["message_id"]))  # oldest first
    return messages


def post(messages):
    body = json.dumps({"source": "github-poller", "messages": messages}).encode()
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-webhook-secret": WEBHOOK_SECRET,
            # n8n Cloud's firewall rejects the default "Python-urllib" agent with 403
            "User-Agent": "telegram-poller/1.0 (+github-actions)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"Forwarded {len(messages)} message(s) -> n8n HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        # Server's reply only (e.g. firewall page or n8n error) - never message content
        detail = e.read(300).decode("utf-8", "replace").replace("\n", " ")
        sys.exit(f"n8n refused the delivery: HTTP {e.code} - {detail}")


async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            sys.exit("TG_SESSION_STRING is invalid or was revoked - run generate_session.py again.")
        if await client.is_bot():
            sys.exit("TG_SESSION_STRING is a BOT login - run generate_session.py again with a phone number, not a bot token.")
        messages = await collect(client)
    finally:
        await client.disconnect()

    if not messages:
        print(f"No new messages in the last {LOOKBACK_MINUTES} min.")
        return
    post(messages)


if __name__ == "__main__":
    asyncio.run(main())
