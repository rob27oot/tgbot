from fastapi import FastAPI
import threading
import uvicorn

app = FastAPI()


@app.get("/")
def home():
    return {"status": "running", "bot": "online"}


def run():
    uvicorn.run(app, host="0.0.0.0", port=7860)


def keep_alive():
    threading.Thread(target=run, daemon=True).start()