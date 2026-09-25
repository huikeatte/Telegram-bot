"""
Run ONCE on any PC to log in and print a TG_SESSION_STRING.
Asks for phone number, login code and 2FA password.
The printed string = full access to the account. Store it like a password.

Must be a USER account (phone number). A bot token will not work:
bots cannot see other bots' messages, which is the point of this poller.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def ask_phone():
    while True:
        phone = input("Phone number of the Telegram USER account (e.g. +60123456789): ").strip()
        if ":" in phone:
            print("That looks like a bot token. Enter the phone number of a user account instead.")
            continue
        return phone


api_id = int(input("api_id: "))
api_hash = input("api_hash: ")

client = TelegramClient(StringSession(), api_id, api_hash)
client.start(phone=ask_phone)
try:
    if client.is_bot():
        raise SystemExit("Logged in as a bot - run again and enter a phone number, not a bot token.")
    print("\nTG_SESSION_STRING=" + client.session.save())
finally:
    client.disconnect()
