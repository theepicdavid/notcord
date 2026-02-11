from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import List
import json
import os
import uuid
from pathlib import Path

# -----------------------
# APP SETUP
# -----------------------
app = FastAPI()

# Serve static files (images, profile pics)
Path("static/uploads").mkdir(parents=True, exist_ok=True)
Path("static/pfps").mkdir(parents=True, exist_ok=True)
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
    username = Column(String)
    server = Column(String, default="general")
    content = Column(String)
    img_path = Column(String, default="")  # Optional image
    pfp_path = Column(String, default="")  # Optional profile picture

class Server(Base):
    __tablename__ = "servers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)

Base.metadata.create_all(bind=engine)

# -----------------------
# CONFIG
# -----------------------
MAINTENANCE_MODE = False

# -----------------------
# WEBSOCKET CONNECTION MANAGER
# -----------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict, server: str):
        for connection in self.active_connections:
            await connection.send_text(json.dumps(message))

manager = ConnectionManager()

# -----------------------
# ROUTES
# -----------------------
@app.get("/")
async def home(request: Request):
    if MAINTENANCE_MODE:
        return HTMLResponse("""
        <html><head><title>NOTCORD Maintenance</title>
        <style>body{background:#36393f;color:white;font-family:Arial;text-align:center;padding-top:50px;}
        h1{color:#7289da}</style></head>
        <body>
        <h1>🚧 NOTCORD is temporarily offline for updates!</h1>
        <p>We'll be back shortly.</p>
        </body></html>""", status_code=503)

    return HTMLResponse(open("frontend.html", "r").read())  # External HTML file for GUI

# Upload profile picture
@app.post("/upload_pfp")
async def upload_pfp(username: str = Form(...), file: UploadFile = File(...)):
    ext = Path(file.filename).suffix
    filename = f"{username}_{uuid.uuid4().hex}{ext}"
    filepath = Path("static/pfps") / filename
    with open(filepath, "wb") as f:
        f.write(await file.read())
    return {"pfp_path": f"/static/pfps/{filename}"}

# Upload image in message
@app.post("/upload_image")
async def upload_image(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = Path("static/uploads") / filename
    with open(filepath, "wb") as f:
        f.write(await file.read())
    return {"img_path": f"/static/uploads/{filename}"}

# Create server
@app.post("/create_server")
async def create_server(name: str = Form(...)):
    db = SessionLocal()
    if db.query(Server).filter_by(name=name).first():
        db.close()
        return {"error": "Server already exists"}
    new_server = Server(name=name)
    db.add(new_server)
    db.commit()
    db.close()
    return {"success": True}

# -----------------------
# WEBSOCKET
# -----------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if MAINTENANCE_MODE:
        await websocket.close(code=1001)
        return

    await manager.connect(websocket)
    db = SessionLocal()
    try:
        # Receive server join info from client
        join_data = await websocket.receive_text()
        join_json = json.loads(join_data)
        server = join_json.get("server", "general")
        username = join_json.get("username", "Anon")

        # Send last 50 messages from this server (lazy-load)
        messages = db.query(Message).filter_by(server=server).order_by(Message.id.desc()).limit(50).all()
        for msg in reversed(messages):
            await websocket.send_text(json.dumps({
                "username": msg.username,
                "content": msg.content,
                "server": msg.server,
                "img_path": msg.img_path,
                "pfp_path": msg.pfp_path
            }))

        while True:
            data = await websocket.receive_text()
            msg_json = json.loads(data)

            # Save to DB immediately
            new_msg = Message(
                username=msg_json["username"],
                content=msg_json["content"],
                server=msg_json.get("server", "general"),
                img_path=msg_json.get("img_path", ""),
                pfp_path=msg_json.get("pfp_path", "")
            )
            db.add(new_msg)
            db.commit()

            # Broadcast and forget (not stored in RAM)
            await manager.broadcast(msg_json, server)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        db.close()
