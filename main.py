from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import os
import uuid
import json
import random

# -----------------------
# APP & STATIC SETUP
# -----------------------
app = FastAPI()

os.makedirs("static/images", exist_ok=True)
os.makedirs("static/pfps", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# -----------------------
# DATABASE SETUP
# -----------------------
DATABASE_URL = "sqlite:///./notcord.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    server = Column(String, default="general")
    username = Column(String)
    tag = Column(String)
    content = Column(String)
    img_path = Column(String, nullable=True)
    timestamp = Column(String)

Base.metadata.create_all(bind=engine)

# -----------------------
# GLOBALS
# -----------------------
connected_users = {}  # {server_name: [websocket, ...]}
MAINTENANCE_MODE = False

DEFAULT_PFP = "data:image/png;base64,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"

# -----------------------
# FRONTEND HTML
# -----------------------
html_file = "frontend.html"
if os.path.exists(html_file):
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()
else:
    html_content = "<h1>NOTCORD Frontend Missing!</h1>"

@app.get("/")
async def get():
    if MAINTENANCE_MODE:
        return HTMLResponse("<h1>🛠️ Maintenance Mode Active</h1><p>Please check back later.</p>")
    return HTMLResponse(html_content)

# -----------------------
# WEBSOCKET
# -----------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        init_data = await websocket.receive_text()
        init_json = json.loads(init_data)
        username = init_json.get("username", "Guest")
        tag = init_json.get("tag", str(random.randint(1000,9999)))
        server = init_json.get("server", "general")
    except:
        await websocket.close()
        return

    if server not in connected_users:
        connected_users[server] = []
    connected_users[server].append(websocket)

    # Send previous messages
    db = SessionLocal()
    messages = db.query(Message).filter(Message.server==server).all()
    for msg in messages:
        await websocket.send_text(json.dumps({
            "username": msg.username,
            "tag": msg.tag,
            "content": msg.content,
            "img_path": msg.img_path,
            "timestamp": msg.timestamp,
            "pfp_path": f"/static/pfps/{msg.username}.png" if os.path.exists(f"static/pfps/{msg.username}.png") else DEFAULT_PFP
        }))

    try:
        while True:
            data = await websocket.receive_text()
            msg_json = json.loads(data)

            new_msg = Message(
                server=server,
                username=msg_json.get("username"),
                tag=msg_json.get("tag"),
                content=msg_json.get("content",""),
                img_path=msg_json.get("img_path"),
                timestamp=datetime.now().strftime("%H:%M")
            )
            db.add(new_msg)
            db.commit()

            for user_ws in connected_users[server]:
                try:
                    await user_ws.send_text(json.dumps({
                        "username": new_msg.username,
                        "tag": new_msg.tag,
                        "content": new_msg.content,
                        "img_path": new_msg.img_path,
                        "timestamp": new_msg.timestamp,
                        "pfp_path": f"/static/pfps/{new_msg.username}.png" if os.path.exists(f"static/pfps/{new_msg.username}.png") else DEFAULT_PFP
                    }))
                except:
                    continue

    except WebSocketDisconnect:
        connected_users[server].remove(websocket)
        db.close()

# -----------------------
# IMAGE UPLOADS
# -----------------------
@app.post("/upload_image")
async def upload_image(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = f"static/images/{filename}"
    with open(filepath, "wb") as f:
        f.write(await file.read())
    return JSONResponse({"path": f"/static/images/{filename}"})

@app.post("/upload_pfp")
async def upload_pfp(username: str = Form(...), file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1]
    filepath = f"static/pfps/{username}{ext}"
    with open(filepath, "wb") as f:
        f.write(await file.read())
    return JSONResponse({"path": f"/static/pfps/{username}{ext}"})

# -----------------------
# MAINTENANCE MODE
# -----------------------
@app.post("/toggle_maintenance")
async def toggle_maintenance():
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    return {"maintenance_mode": MAINTENANCE_MODE}
