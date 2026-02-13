from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
import hashlib
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


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    banned = Column(Boolean, default=False)


class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    content = Column(String)
    channel_id = Column(Integer, ForeignKey("channels.id"))


class SystemState(Base):
    __tablename__ = "system_state"
    id = Column(Integer, primary_key=True)
    service_mode = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)

# Create defaults on first run
db = SessionLocal()
if not db.query(Channel).first():
    db.add_all([
        Channel(name="general"),
        Channel(name="announcements"),
        Channel(name="gaming")
    ])
    db.commit()

if not db.query(SystemState).first():
    db.add(SystemState(service_mode=False))
    db.commit()

db.close()

connected_users = {}  # websocket -> {"username": str, "channel": str}


# -----------------------
# PASSWORD HASH FUNCTION
# -----------------------
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# -----------------------
# FRONTEND (Original Style + Password Field Added)
# -----------------------

html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { box-sizing: border-box; }
body { margin:0;font-family:"Segoe UI",sans-serif;background:#1e1f22;color:white;display:flex;height:100vh;}
.sidebar { width:230px;background:#2b2d31;padding:20px;display:flex;flex-direction:column;}
.sidebar h2 { margin:0 0 20px 0;}
.channel { padding:6px;border-radius:6px;cursor:pointer;}
.channel:hover { background:#3a3c43;}
.active-channel { background:#5865f2;}
.chat-wrapper { flex:1;display:flex;flex-direction:column;}
.header { background:#313338;padding:15px 20px;font-weight:bold;display:flex;justify-content:space-between;}
.chat-container { flex:1;padding:20px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;}
.message { max-width:70%;padding:10px 14px;border-radius:10px;background:#383a40;}
.message.me { align-self:flex-end;background:#5865f2;}
.message-input { padding:15px;background:#2b2d31;display:flex;gap:10px;}
.message-input input { flex:1;padding:12px;border-radius:8px;border:none;background:#1e1f22;color:white;}
.message-input button { padding:12px 18px;border-radius:8px;border:none;background:#5865f2;color:white;cursor:pointer;}
#login { position:fixed;inset:0;background:#1e1f22;display:flex;justify-content:center;align-items:center;}
#adminPanel { position:fixed;right:20px;bottom:20px;background:#2b2d31;padding:15px;border-radius:10px;display:none;}
</style>
</head>
<body>

<div class="sidebar">
    <h2>NOTCORD</h2>
    <div id="channelList"></div>
</div>

<div class="chat-wrapper">
    <div class="header">
        <span id="channelTitle"># general</span>
        <button id="adminToggle" style="display:none;" onclick="toggleAdmin()">Admin</button>
    </div>

    <div id="messages" class="chat-container"></div>

    <div class="message-input">
        <input id="messageInput" placeholder="Message">
        <button onclick="sendMessage()">Send</button>
    </div>
</div>

<div id="login">
    <div>
        <h2>Login / Create Account</h2>
        <input id="username" placeholder="Username"><br><br>
        <input id="password" type="password" placeholder="Password"><br><br>
        <button onclick="joinChat()">Enter</button>
        <p id="loginError" style="color:red;"></p>
    </div>
</div>

<div id="adminPanel">
    <h3>Admin Panel</h3>
    <input id="newChannelName" placeholder="New Channel"><br><br>
    <button onclick="createChannel()">Create Channel</button><br><br>
    <input id="banUserInput" placeholder="Ban Username"><br><br>
    <button onclick="banUser()">Ban User</button><br><br>
    <button onclick="clearChat()">Clear Channel</button><br><br>
    <button onclick="toggleService()">Toggle Service Mode</button>
</div>

<script>
let ws;
let username;
let currentChannel="general";

function joinChat(){
    username=document.getElementById("username").value.trim();
    let password=document.getElementById("password").value;
    if(!username || !password) return;

    ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");

    ws.onopen=function(){
        ws.send(JSON.stringify({
            type:"login",
            username:username,
            password:password
        }));
    };

    ws.onmessage=function(event){
        let data=JSON.parse(event.data);

        if(data.type==="error"){
            document.getElementById("loginError").innerText=data.message;
        }

        if(data.type==="banned"){
            document.getElementById("loginError").innerText="Account Banned";
            ws.close();
        }

        if(data.type==="login_success"){
            document.getElementById("login").style.display="none";
            if(username==="DavidDoesTech"){
                document.getElementById("adminToggle").style.display="inline";
            }
        }

        if(data.type==="channel_list"){
            renderChannels(data.channels);
        }

        if(data.type==="message"){
            addMessage(data.username+": "+data.content);
        }

        if(data.type==="clear"){
            document.getElementById("messages").innerHTML="";
        }
    };
}

function renderChannels(channels){
    let list=document.getElementById("channelList");
    list.innerHTML="";
    channels.forEach(c=>{
        let div=document.createElement("div");
        div.className="channel";
        if(c===currentChannel)div.classList.add("active-channel");
        div.innerText="# "+c;
        div.onclick=function(){switchChannel(c)};
        list.appendChild(div);
    });
}

function switchChannel(channel){
    currentChannel=channel;
    document.getElementById("channelTitle").innerText="# "+channel;
    document.getElementById("messages").innerHTML="";
    ws.send(JSON.stringify({type:"switch_channel",channel:channel}));
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
    ws.send(JSON.stringify({type:"message",content:input.value,channel:currentChannel}));
    input.value="";
}

function toggleAdmin(){
    let panel=document.getElementById("adminPanel");
    panel.style.display=panel.style.display==="block"?"none":"block";
}

function createChannel(){
    ws.send(JSON.stringify({type:"create_channel",name:document.getElementById("newChannelName").value}));
}

function banUser(){
    ws.send(JSON.stringify({type:"ban",target:document.getElementById("banUserInput").value}));
}

function clearChat(){
    ws.send(JSON.stringify({type:"clear",channel:currentChannel}));
}

function toggleService(){
    ws.send(JSON.stringify({type:"toggle_service"}));
}

document.getElementById("messageInput").addEventListener("keydown",function(e){
    if(e.key==="Enter"){ e.preventDefault(); sendMessage(); }
});
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
    username = None

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            # LOGIN / CREATE ACCOUNT
            if data["type"] == "login":
                user = db.query(User).filter_by(username=data["username"]).first()

                if not user:
                    user = User(
                        username=data["username"],
                        password_hash=hash_password(data["password"]),
                        banned=False
                    )
                    db.add(user)
                    db.commit()
                else:
                    if user.password_hash != hash_password(data["password"]):
                        await websocket.send_text(json.dumps({
                            "type":"error",
                            "message":"Invalid Password"
                        }))
                        continue

                if user.banned:
                    await websocket.send_text(json.dumps({"type":"banned"}))
                    continue

                username = user.username
                connected_users[websocket]={"username":username,"channel":"general"}

                await websocket.send_text(json.dumps({"type":"login_success"}))

                channels=db.query(Channel).all()
                await websocket.send_text(json.dumps({
                    "type":"channel_list",
                    "channels":[c.name for c in channels]
                }))

            elif data["type"]=="switch_channel":
                connected_users[websocket]["channel"]=data["channel"]
                channel=db.query(Channel).filter_by(name=data["channel"]).first()
                messages=db.query(Message).filter_by(channel_id=channel.id).all()

                for msg in messages:
                    await websocket.send_text(json.dumps({
                        "type":"message",
                        "username":msg.username,
                        "content":msg.content
                    }))

            elif data["type"]=="message":
                state=db.query(SystemState).first()
                if state.service_mode and username!="DavidDoesTech":
                    continue

                channel=db.query(Channel).filter_by(name=data["channel"]).first()
                msg=Message(username=username,content=data["content"],channel_id=channel.id)
                db.add(msg)
                db.commit()

                for ws_conn,user_data in connected_users.items():
                    if user_data["channel"]==data["channel"]:
                        await ws_conn.send_text(json.dumps({
                            "type":"message",
                            "username":username,
                            "content":data["content"]
                        }))

            elif data["type"]=="create_channel" and username=="DavidDoesTech":
                if not db.query(Channel).filter_by(name=data["name"]).first():
                    db.add(Channel(name=data["name"]))
                    db.commit()

                channels=db.query(Channel).all()
                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({
                        "type":"channel_list",
                        "channels":[c.name for c in channels]
                    }))

            elif data["type"]=="ban" and username=="DavidDoesTech":
                target=db.query(User).filter_by(username=data["target"]).first()
                if target:
                    target.banned=True
                    db.commit()

                    for ws_conn,user_data in list(connected_users.items()):
                        if user_data["username"]==data["target"]:
                            await ws_conn.send_text(json.dumps({"type":"banned"}))
                            await ws_conn.close()
                            del connected_users[ws_conn]

            elif data["type"]=="clear" and username=="DavidDoesTech":
                channel=db.query(Channel).filter_by(name=data["channel"]).first()
                db.query(Message).filter_by(channel_id=channel.id).delete()
                db.commit()

                for ws_conn,user_data in connected_users.items():
                    if user_data["channel"]==data["channel"]:
                        await ws_conn.send_text(json.dumps({"type":"clear"}))

            elif data["type"]=="toggle_service" and username=="DavidDoesTech":
                state=db.query(SystemState).first()
                state.service_mode=not state.service_mode
                db.commit()

    except WebSocketDisconnect:
        if websocket in connected_users:
            del connected_users[websocket]
        db.close()


if __name__ == "__main__":
    import uvicorn
    port=int(os.environ.get("PORT",8000))
    uvicorn.run("main:app",host="0.0.0.0",port=port)
