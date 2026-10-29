#!/usr/bin/env python3
"""Run once on the server:  cd /opt/bot && /opt/bot/venv/bin/python install_most_shared.py
Makes .bak_ms backups, then adds 3 small hooks (safe to run twice). Does NOT restart the bot."""
import os, shutil, py_compile, sys
D = os.path.dirname(os.path.abspath(__file__))

def patch(fname, anchor, insert, marker, before=True, count_ok=1):
    p = os.path.join(D, fname)
    s = open(p, encoding="utf-8").read()
    if marker in s:
        print(f"[skip] {fname}: already patched"); return
    if s.count(anchor) < 1:
        sys.exit(f"[ERROR] {fname}: anchor not found -> {anchor!r}")
    shutil.copy(p, p + ".bak_ms")
    i = s.index(anchor)
    s = s[:i] + insert + s[i:] if before else s[:i + len(anchor)] + insert + s[i + len(anchor):]
    open(p, "w", encoding="utf-8").write(s)
    py_compile.compile(p, doraise=True)
    print(f"[ok]   {fname}: patched")

# 1) loader: add the new piece before runtime
p = os.path.join(D, "bot.py"); s = open(p, encoding="utf-8").read()
if '"most_shared"' in s:
    print("[skip] bot.py: already patched")
else:
    if '"commands", "runtime"]' not in s:
        sys.exit("[ERROR] bot.py: _PIECES line not as expected")
    shutil.copy(p, p + ".bak_ms")
    open(p, "w", encoding="utf-8").write(s.replace('"commands", "runtime"]', '"commands", "most_shared", "runtime"]'))
    print("[ok]   bot.py: patched")

# 2) deep link /start msr_<id>
patch("commands.py", '        if arg.startswith("cp_"):',
      '        if arg.startswith("msr_"):\n'
      '            await ms_send_record(context.bot, update.effective_chat.id, arg[4:])\n'
      '            return\n', "ms_send_record")

# 3) register commands + auto job
patch("runtime.py", "    # Public commands\n", "    register_most_shared(app)   # Most Shared Tokens (24H) feature\n\n", "register_most_shared")

for f in ("most_shared.py", "most_shared_video.py"):
    if not os.path.exists(os.path.join(D, f)):
        sys.exit(f"[ERROR] {f} is missing in {D} - copy it there first")
    py_compile.compile(os.path.join(D, f), doraise=True)
print("\nDONE. Now: systemctl restart bot   then in Telegram (owner): /mostsharedtest")
