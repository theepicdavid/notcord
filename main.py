from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
import json
import os

app = FastAPI()

# -----------------------
# DATABASE
# -----------------------
DATABASE_URL = "sqlite:///./notcord.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    content = Column(String)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    banned = Column(Boolean, default=False)
    muted = Column(Boolean, default=False)


class SystemState(Base):
    __tablename__ = "system_state"
    id = Column(Integer, primary_key=True)
    service_mode = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)

# Ensure system state exists
db = SessionLocal()
if not db.query(SystemState).first():
    db.add(SystemState(service_mode=False))
    db.commit()
db.close()

connected_users = {}  # websocket -> username

# -----------------------
# YOUR ORIGINAL GUI (MINIMALLY MODIFIED)
# -----------------------
html = """ YOUR ORIGINAL HTML HERE EXACTLY AS YOU HAD IT """

@app.get("/")
async def get():
    return HTMLResponse(html)

# -----------------------
# WEBSOCKET
# -----------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    db = SessionLocal()
    username = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            # ---------------- LOGIN / CREATE ACCOUNT ----------------
            if data["type"] == "login":
                user = db.query(User).filter_by(username=data["username"]).first()

                if not user:
                    user = User(username=data["username"])
                    db.add(user)
                    db.commit()

                if user.banned:
                    await websocket.send_text(json.dumps({
                        "type": "banned"
                    }))
                    continue

                username = user.username
                connected_users[websocket] = username

                await websocket.send_text(json.dumps({
                    "type": "login_success"
                }))

                # Send chat history
                messages = db.query(Message).all()
                for msg in messages:
                    await websocket.send_text(json.dumps({
                        "type": "message",
                        "username": msg.username,
                        "content": msg.content
                    }))

            # ---------------- SEND MESSAGE ----------------
            elif data["type"] == "message":
                if not username:
                    continue

                user = db.query(User).filter_by(username=username).first()
                state = db.query(SystemState).first()

                if user.banned:
                    continue

                if user.muted:
                    continue

                if state.service_mode and username != "DavidDoesTech":
                    continue

                msg = Message(username=username, content=data["content"])
                db.add(msg)
                db.commit()

                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({
                        "type": "message",
                        "username": username,
                        "content": data["content"]
                    }))

            # ---------------- BAN USER ----------------
            elif data["type"] == "ban" and username == "DavidDoesTech":
                target = db.query(User).filter_by(username=data["target"]).first()
                if target:
                    target.banned = True
                    db.commit()

                    # Disconnect live if online
                    for ws_conn, name in list(connected_users.items()):
                        if name == data["target"]:
                            await ws_conn.send_text(json.dumps({"type": "banned"}))
                            await ws_conn.close()
                            del connected_users[ws_conn]

            # ---------------- UNBAN USER ----------------
            elif data["type"] == "unban" and username == "DavidDoesTech":
                target = db.query(User).filter_by(username=data["target"]).first()
                if target:
                    target.banned = False
                    db.commit()

            # ---------------- MUTE USER ----------------
            elif data["type"] == "mute" and username == "DavidDoesTech":
                target = db.query(User).filter_by(username=data["target"]).first()
                if target:
                    target.muted = True
                    db.commit()

            # ---------------- UNMUTE USER ----------------
            elif data["type"] == "unmute" and username == "DavidDoesTech":
                target = db.query(User).filter_by(username=data["target"]).first()
                if target:
                    target.muted = False
                    db.commit()

            # ---------------- CLEAR CHAT ----------------
            elif data["type"] == "clear" and username == "DavidDoesTech":
                db.query(Message).delete()
                db.commit()

                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({
                        "type": "clear"
                    }))

            # ---------------- TOGGLE SERVICE MODE ----------------
            elif data["type"] == "toggle_service" and username == "DavidDoesTech":
                state = db.query(SystemState).first()
                state.service_mode = not state.service_mode
                db.commit()

                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({
                        "type": "service_mode",
                        "state": state.service_mode
                    }))

    except WebSocketDisconnect:
        if websocket in connected_users:
            del connected_users[websocket]
        db.close()


# -----------------------
# RUN
# -----------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
