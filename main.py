from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
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
# FRONTEND
# -----------------------
html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD</title>
<style>
body{margin:0;font-family:sans-serif;background:#1e1f22;color:white;display:flex;height:100vh}
.sidebar{width:200px;background:#2b2d31;padding:20px}
.chat-wrapper{flex:1;display:flex;flex-direction:column}
.header{background:#313338;padding:15px;display:flex;justify-content:space-between}
.chat-container{flex:1;padding:20px;overflow-y:auto}
.message{background:#383a40;padding:8px;border-radius:8px;margin-bottom:8px}
.message.me{background:#5865f2}
.message-input{display:flex;padding:10px;background:#2b2d31}
.message-input input{flex:1;padding:8px}
#login{position:fixed;inset:0;background:#1e1f22;display:flex;justify-content:center;align-items:center}
#adminPanel{position:fixed;right:20px;bottom:20px;background:#2b2d31;padding:15px;display:none}
</style>
</head>
<body>

<div class="sidebar"><h3>NOTCORD</h3></div>

<div class="chat-wrapper">
<div class="header">
<span># general</span>
<button id="adminToggle" style="display:none;" onclick="toggleAdmin()">Admin</button>
</div>

<div id="messages" class="chat-container"></div>

<div class="message-input">
<input id="messageInput">
<button onclick="sendMessage()">Send</button>
</div>
</div>

<div id="login">
<div>
<h2>Login / Create Account</h2>
<input id="username" placeholder="Username"><br><br>
<button onclick="joinChat()">Enter</button>
<p id="loginError" style="color:red;"></p>
</div>
</div>

<div id="adminPanel">
<h3>Admin Panel</h3>
<input id="banUserInput" placeholder="Username to ban"><br><br>
<button onclick="banUser()">Ban User</button><br><br>
<button onclick="clearChat()">Clear Chat (Server)</button><br><br>
<button onclick="toggleServiceMode()">Toggle Service Mode</button>
</div>

<script>
let ws;
let username;

function joinChat(){
    username=document.getElementById("username").value.trim();
    if(!username)return;

    let protocol=location.protocol==="https:"?"wss://":"ws://";
    ws=new WebSocket(protocol+location.host+"/ws");

    ws.onopen=function(){
        ws.send(JSON.stringify({type:"login",username:username}));
    }

    ws.onmessage=function(event){
        let data=JSON.parse(event.data);

        if(data.type==="banned"){
            document.getElementById("loginError").innerText="Account Banned";
            ws.close();
            return;
        }

        if(data.type==="login_success"){
            document.getElementById("login").style.display="none";
            if(username==="DavidDoesTech"){
                document.getElementById("adminToggle").style.display="inline";
            }
            return;
        }

        if(data.type==="message"){
            addMessage(data.username+": "+data.content);
        }

        if(data.type==="clear"){
            document.getElementById("messages").innerHTML="";
        }

        if(data.type==="service_mode"){
            alert("Service Mode: "+(data.state?"ON":"OFF"));
        }
    }
}

function addMessage(text){
    let div=document.createElement("div");
    div.className="message";
    if(text.startsWith(username+":"))div.classList.add("me");
    div.innerText=text;
    document.getElementById("messages").appendChild(div);
}

function sendMessage(){
    let input=document.getElementById("messageInput");
    if(!input.value.trim())return;
    ws.send(JSON.stringify({type:"message",content:input.value}));
    input.value="";
}

function toggleAdmin(){
    let panel=document.getElementById("adminPanel");
    panel.style.display=panel.style.display==="block"?"none":"block";
}

function banUser(){
    let target=document.getElementById("banUserInput").value;
    ws.send(JSON.stringify({type:"ban",target:target}));
}

function clearChat(){
    ws.send(JSON.stringify({type:"clear"}));
}

function toggleServiceMode(){
    ws.send(JSON.stringify({type:"toggle_service"}));
}
</script>
</body>
</html>
"""


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
    user_name = None

    try:
        while True:
            data = await websocket.receive_text()
            import json
            data = json.loads(data)

            # LOGIN / CREATE ACCOUNT
            if data["type"] == "login":
                user = db.query(User).filter_by(username=data["username"]).first()

                if not user:
                    user = User(username=data["username"], banned=False)
                    db.add(user)
                    db.commit()

                if user.banned:
                    await websocket.send_text(json.dumps({"type": "banned"}))
                    continue

                user_name = user.username
                connected_users[websocket] = user_name
                await websocket.send_text(json.dumps({"type": "login_success"}))

                messages = db.query(Message).all()
                for msg in messages:
                    await websocket.send_text(json.dumps({
                        "type": "message",
                        "username": msg.username,
                        "content": msg.content
                    }))

            # SEND MESSAGE
            elif data["type"] == "message":
                state = db.query(SystemState).first()
                if state.service_mode and user_name != "DavidDoesTech":
                    continue

                msg = Message(username=user_name, content=data["content"])
                db.add(msg)
                db.commit()

                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({
                        "type": "message",
                        "username": user_name,
                        "content": data["content"]
                    }))

            # BAN USER
            elif data["type"] == "ban" and user_name == "DavidDoesTech":
                target = db.query(User).filter_by(username=data["target"]).first()
                if target:
                    target.banned = True
                    db.commit()

            # CLEAR CHAT
            elif data["type"] == "clear" and user_name == "DavidDoesTech":
                db.query(Message).delete()
                db.commit()
                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({"type": "clear"}))

            # TOGGLE SERVICE MODE
            elif data["type"] == "toggle_service" and user_name == "DavidDoesTech":
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
