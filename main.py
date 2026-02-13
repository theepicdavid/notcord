from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
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


Base.metadata.create_all(bind=engine)

# Create default channels if none exist
db = SessionLocal()
if not db.query(Channel).first():
    db.add(Channel(name="general"))
    db.add(Channel(name="announcements"))
    db.add(Channel(name="gaming"))
    db.commit()
db.close()

connected_users = {}  # websocket -> {"username": str, "channel": str}

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
.sidebar{width:220px;background:#2b2d31;padding:15px;display:flex;flex-direction:column}
.channel{padding:6px;cursor:pointer;border-radius:6px}
.channel:hover{background:#3a3c43}
.active{background:#5865f2}
.chat-wrapper{flex:1;display:flex;flex-direction:column}
.header{background:#313338;padding:12px;display:flex;justify-content:space-between}
.chat-container{flex:1;padding:15px;overflow-y:auto}
.message{background:#383a40;padding:8px;border-radius:8px;margin-bottom:8px}
.message.me{background:#5865f2}
.message-input{display:flex;padding:10px;background:#2b2d31}
.message-input input{flex:1;padding:8px}
#login{position:fixed;inset:0;background:#1e1f22;display:flex;justify-content:center;align-items:center}
#adminPanel{position:fixed;right:20px;bottom:20px;background:#2b2d31;padding:15px;display:none}
</style>
</head>
<body>

<div class="sidebar">
<h3>NOTCORD</h3>
<div id="channelList"></div>
<button onclick="showCreateChannel()" id="createChannelBtn" style="display:none;">+ Create Channel</button>
</div>

<div class="chat-wrapper">
<div class="header">
<span id="currentChannel"># general</span>
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
<h2>Login</h2>
<input id="username" placeholder="Username"><br><br>
<button onclick="joinChat()">Enter</button>
<p id="loginError" style="color:red;"></p>
</div>
</div>

<div id="adminPanel">
<h3>Admin Panel</h3>
<input id="newChannelName" placeholder="New Channel Name"><br><br>
<button onclick="createChannel()">Create Channel</button><br><br>
<input id="deleteChannelName" placeholder="Channel To Delete"><br><br>
<button onclick="deleteChannel()">Delete Channel</button>
</div>

<script>
let ws;
let username;
let currentChannel="general";

function joinChat(){
    username=document.getElementById("username").value.trim();
    if(!username)return;

    ws=new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");

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
                document.getElementById("createChannelBtn").style.display="block";
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
    }
}

function renderChannels(channels){
    let list=document.getElementById("channelList");
    list.innerHTML="";
    channels.forEach(c=>{
        let div=document.createElement("div");
        div.className="channel";
        if(c===currentChannel)div.classList.add("active");
        div.innerText="# "+c;
        div.onclick=function(){switchChannel(c);}
        list.appendChild(div);
    });
}

function switchChannel(channel){
    currentChannel=channel;
    document.getElementById("currentChannel").innerText="# "+channel;
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
    let p=document.getElementById("adminPanel");
    p.style.display=p.style.display==="block"?"none":"block";
}

function createChannel(){
    let name=document.getElementById("newChannelName").value;
    ws.send(JSON.stringify({type:"create_channel",name:name}));
}

function deleteChannel(){
    let name=document.getElementById("deleteChannelName").value;
    ws.send(JSON.stringify({type:"delete_channel",name:name}));
}

document.getElementById("messageInput").addEventListener("keydown",function(e){
    if(e.key==="Enter"){
        e.preventDefault();
        sendMessage();
    }
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
    current_channel = "general"

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            if data["type"] == "login":
                user = db.query(User).filter_by(username=data["username"]).first()
                if not user:
                    user = User(username=data["username"])
                    db.add(user)
                    db.commit()

                if user.banned:
                    await websocket.send_text(json.dumps({"type":"banned"}))
                    continue

                username = user.username
                connected_users[websocket] = {"username":username,"channel":"general"}

                await websocket.send_text(json.dumps({"type":"login_success"}))

                channels = db.query(Channel).all()
                await websocket.send_text(json.dumps({
                    "type":"channel_list",
                    "channels":[c.name for c in channels]
                }))

            elif data["type"] == "switch_channel":
                current_channel = data["channel"]
                connected_users[websocket]["channel"]=current_channel

                channel_obj = db.query(Channel).filter_by(name=current_channel).first()
                messages = db.query(Message).filter_by(channel_id=channel_obj.id).all()

                for msg in messages:
                    await websocket.send_text(json.dumps({
                        "type":"message",
                        "username":msg.username,
                        "content":msg.content
                    }))

            elif data["type"] == "message":
                channel_obj = db.query(Channel).filter_by(name=data["channel"]).first()
                msg = Message(username=username,content=data["content"],channel_id=channel_obj.id)
                db.add(msg)
                db.commit()

                for ws_conn,data_user in connected_users.items():
                    if data_user["channel"]==data["channel"]:
                        await ws_conn.send_text(json.dumps({
                            "type":"message",
                            "username":username,
                            "content":data["content"]
                        }))

            elif data["type"] == "create_channel" and username=="DavidDoesTech":
                if not db.query(Channel).filter_by(name=data["name"]).first():
                    db.add(Channel(name=data["name"]))
                    db.commit()

                channels = db.query(Channel).all()
                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({
                        "type":"channel_list",
                        "channels":[c.name for c in channels]
                    }))

            elif data["type"] == "delete_channel" and username=="DavidDoesTech":
                ch = db.query(Channel).filter_by(name=data["name"]).first()
                if ch and ch.name!="general":
                    db.query(Message).filter_by(channel_id=ch.id).delete()
                    db.delete(ch)
                    db.commit()

                channels = db.query(Channel).all()
                for ws_conn in connected_users:
                    await ws_conn.send_text(json.dumps({
                        "type":"channel_list",
                        "channels":[c.name for c in channels]
                    }))

    except WebSocketDisconnect:
        if websocket in connected_users:
            del connected_users[websocket]
        db.close()

if __name__ == "__main__":
    import uvicorn
    port=int(os.environ.get("PORT",8000))
    uvicorn.run("main:app",host="0.0.0.0",port=port)
