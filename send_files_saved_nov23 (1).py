# send_files_saved_nov23.py - /opt/bot ki 16 live .py files -> @yowziuh Saved Messages
# Userbot session ki COPY use karta hai, live bot ki session file ko touch nahi karta.
# Run: cd /opt/bot && /opt/bot/venv/bin/python send_files_saved_nov23.py
import os, shutil, asyncio
from telethon import TelegramClient

shutil.copy('/root/bigbang/userbot_session.session', '/tmp/send_session.session')

def load_env(path):
    d = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return d

env = {}
for p in ['/opt/bot/.env', '/root/bigbang/.env']:
    env.update(load_env(p))

api_id = None
api_hash = None
for k in ['USERBOT_API_ID', 'API_ID', 'TG_API_ID', 'TELEGRAM_API_ID', 'APP_ID']:
    if k in env and env[k]:
        try:
            api_id = int(env[k])
            break
        except ValueError:
            pass
for k in ['USERBOT_API_HASH', 'API_HASH', 'TG_API_HASH', 'TELEGRAM_API_HASH', 'APP_HASH']:
    if k in env and env[k]:
        api_hash = env[k]
        break
if not api_id or not api_hash:
    print('API_ID/API_HASH nahi mila .env me')
    raise SystemExit

files = ['bot.py','core.py','runtime.py','dropped_call.py','skipcall.py','x_alert.py','leaderboard.py','most_shared.py','commands.py','champion_video.py','champion_green_trio.py','champion_rocket_neon.py','champion_cyberhud_orange.py','champion_gauge_neon.py','champion_rankup.py','binance_trending.py']

async def main():
    async with TelegramClient('/tmp/send_session', api_id, api_hash) as client:
        me = await client.get_me()
        print('logged in as:', me.username or me.id)
        for fn in files:
            p = '/opt/bot/' + fn
            if os.path.exists(p):
                await client.send_file('me', p, caption=fn)
                print('sent', fn)
            else:
                print('missing', fn)
        print('DONE - sab files Saved Messages me hain')

asyncio.run(main())
