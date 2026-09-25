"""
Run ONCE on any PC to log in and print a TG_SESSION_STRING.
Asks for phone number, login code and 2FA password.
The printed string = full access to the account. Store it like a password.
"""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("api_id: "))
api_hash = input("api_hash: ")

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nTG_SESSION_STRING=" + client.session.save())
