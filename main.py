from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import json

app = FastAPI()

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
    content = Column(String)

Base.metadata.create_all(bind=engine)

# -----------------------
# GLOBAL STATE
# -----------------------
connected_users = {}
service_mode = False

# -----------------------
# FRONTEND
# -----------------------
html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body { margin:0; font-family:Segoe UI; background:#1e1f22; color:white; }
.sidebar { width:220px; background:#2b2d31; position:fixed; top:0; bottom:0; padding:20px; }
.chat { margin-left:220px; height:100vh; display:flex; flex-direction:column; }
.header { background:#313338; padding:15px; font-weight:bold; }
.messages { flex:1; padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:8px;}
.message { background:#383a40; padding:10px 14px; border-radius:8px; max-width:70%; position:relative;}
.message.me { background:#5865f2; align-self:flex-end;}
.username { font-weight:bold; cursor:pointer; }
.input-area { display:flex; padding:15px; background:#2b2d31; }
.input-area input { flex:1; padding:10px; border:none; border-radius:6px; }
.input-area button { margin-left:10px; padding:10px 15px; border:none; border-radius:6px; background:#5865f2; color:white; cursor:pointer;}
#login { position:fixed; inset:0; background:#1e1f22; display:flex; justify-content:center; align-items:center;}
.login-box { background:#2b2d31; padding:30px; border-radius:8px;}
.popup { position:fixed; background:#2b2d31; padding:20px; border-radius:8px; display:none;}
.admin-panel { position:fixed; right:20px; bottom:20px; background:#2b2d31; padding:15px; border-radius:8px; display:none;}
</style>
</head>
<body>

<div class="sidebar">
<h2>NOTCORD</h2>
<div># general</div>
</div>

<div class="chat">
<div class="header"># general</div>
<div id="messages" class="messages"></div>
<div class="input-area">
<input id="messageInput" placeholder="Type message...">
<button onclick="sendMessage()">Send</button>
</div>
</div>

<div id="login">
<div class="login-box">
<h2>Join NOTCORD</h2>
<input id="username" placeholder="Username">
<button onclick="join()">Join</button>
<p id="error" style="color:red;"></p>
</div>
</div>

<div id="profilePopup" class="popup"></div>

<div id="adminPanel" class="admin-panel">
<h3>Admin Panel</h3>
<button onclick="clearMessages()">Clear All Messages</button><br><br>
<button onclick="toggleService()">Toggle Service Mode</button>
</div>

<script>
let ws;
let username;
let isAdmin = false;

function join(){
    username = document.getElementById("username").value.trim();
    if(!username) return;

    ws = new WebSocket((location.protocol==="https:"?"wss://":"ws://")+location.host+"/ws");

    ws.onopen = ()=> {
        ws.send(JSON.stringify({type:"join", username:username}));
    };

    ws.onmessage = (event)=>{
        const data = JSON.parse(event.data);

        if(data.type==="error"){
            document.getElementById("error").innerText = data.message;
        }

        if(data.type==="init"){
            document.getElementById("login").style.display="none";
            if(data.admin){
                isAdmin = true;
                document.getElementById("adminPanel").style.display="block";
            }
            data.messages.forEach(addMessage);
        }

        if(data.type==="message"){
            addMessage(data);
        }

        if(data.type==="delete"){
            const el = document.getElementById("msg-"+data.id);
            if(el) el.remove();
        }

        if(data.type==="service"){
            alert("Service Mode is now " + (data.enabled ? "ENABLED" : "DISABLED"));
        }
    };
}

function addMessage(data){
    const div = document.createElement("div");
    div.className = "message" + (data.username===username ? " me":"");
    div.id = "msg-"+data.id;
    div.innerHTML = '<span class="username" onclick="showProfile(\\''+data.username+'\\')">'+data.username+'</span>: '+data.content;

    if(isAdmin){
        const del = document.createElement("button");
        del.innerText="X";
        del.style.position="absolute";
        del.style.right="5px";
        del.onclick=()=>ws.send(JSON.stringify({type:"delete", id:data.id}));
        div.appendChild(del);
    }

    document.getElementById("messages").appendChild(div);
}

function sendMessage(){
    const input=document.getElementById("messageInput");
    if(!input.value.trim()) return;
    ws.send(JSON.stringify({type:"message", content:input.value}));
    input.value="";
}

function showProfile(name){
    const popup=document.getElementById("profilePopup");
    popup.innerHTML="<h3>"+name+"</h3><p>User profile popup</p>";
    popup.style.display="block";
    popup.style.top="100px";
    popup.style.left="300px";
}

function clearMessages(){
    ws.send(JSON.stringify({type:"clear"}));
}

function toggleService(){
    ws.send(JSON.stringify({type:"service"}));
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
    global service_mode
    await websocket.accept()
    db = SessionLocal()
    username = None

    try:
        while True:
            data = json.loads(await websocket.receive_text())

            if data["type"] == "join":
                if data["username"] in connected_users:
                    await websocket.send_text(json.dumps({
                        "type":"error",
                        "message":"Username already taken."
                    }))
                    continue

                username = data["username"]
                connected_users[username] = websocket

                messages = db.query(Message).all()
                await websocket.send_text(json.dumps({
                    "type":"init",
                    "messages":[{"id":m.id,"username":m.username,"content":m.content} for m in messages],
                    "admin": username=="DavidDoesTech"
                }))

            elif data["type"] == "message":
                if service_mode and username!="DavidDoesTech":
                    continue

                new_msg = Message(username=username, content=data["content"])
                db.add(new_msg)
                db.commit()
                db.refresh(new_msg)

                for user in connected_users.values():
                    await user.send_text(json.dumps({
                        "type":"message",
                        "id":new_msg.id,
                        "username":username,
                        "content":data["content"]
                    }))

            elif data["type"] == "delete" and username=="DavidDoesTech":
                msg = db.query(Message).filter(Message.id==data["id"]).first()
                if msg:
                    db.delete(msg)
                    db.commit()
                    for user in connected_users.values():
                        await user.send_text(json.dumps({
                            "type":"delete",
                            "id":data["id"]
                        }))

            elif data["type"] == "clear" and username=="DavidDoesTech":
                db.query(Message).delete()
                db.commit()

            elif data["type"] == "service" and username=="DavidDoesTech":
                service_mode = not service_mode
                for user in connected_users.values():
                    await user.send_text(json.dumps({
                        "type":"service",
                        "enabled":service_mode
                    }))

    except WebSocketDisconnect:
        if username in connected_users:
            del connected_users[username]
        db.close()

# -----------------------
# RUN APP
# -----------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
