import os, threading
from dashboard import app
from bot import run_bot

def start_bot():
    run_bot()

if __name__ == "__main__":
    t=threading.Thread(target=start_bot,daemon=True,name="telegram-bot")
    t.start()
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","8000")),use_reloader=False)
