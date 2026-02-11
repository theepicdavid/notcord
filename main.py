from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import random

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
    content = Column(String)

Base.metadata.create_all(bind=engine)

# -----------------------
# WEBSOCKET CONNECTIONS
# -----------------------
connected_users = []

# -----------------------
# FRONTEND HTML (embedded)
# -----------------------
html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD</title>
<style>
body { margin:0; font-family: Arial; background-color: #36393f; color: white; }
.header { background: #2f3136; padding: 15px; font-size: 20px; }
.chat-container { padding: 20px; height: 70vh; overflow-y: auto; }
input { padding: 10px; border: none; border-radius: 5px; }
button { padding: 10px; background: #5865f2; color: white; border: none; border-radius: 5px; }
.message-input { position: fixed; bottom: 0; width: 100%; padding: 15px; background: #40444b; }
.message { margin-bottom: 5px; }
</style>
</head>
<body>

<div class="header">NOTCORD - #general</div>

<div id="login">
  <div style="padding:20px;">
    <input id="username" placeholder="Enter username">
    <button onclick="joinChat()">Join NOTCORD</button>
  </div>
</div>

<div id="chat" style="display:none;">
  <div id="messages" class="chat-container"></div>
  <div class="message-input">
    <input id="messageInput" style="width:80%;" placeholder="Type message">
    <button onclick="sendMessage()">Send</button>
  </div>
</div>

<script>
// -----------------------
// USER ACCOUNT
// -----------------------
let ws;
let username;
let usertag;

function generateTag() {
    return Math.floor(Math.random() * 9000 + 1000); // 4-digit tag
}

// Load account from LocalStorage if exists
if(localStorage.getItem("notcordUser")){
    const data = JSON.parse(localStorage.getItem("notcordUser"));
    username = data.username;
    usertag = data.usertag;
    joinChat(true);
}

function joinChat(fromStorage=false) {
    if(!fromStorage){
        username = document.getElementById("username").value.trim();
        if(!username) return alert("Enter username");
        usertag = generateTag();
        localStorage.setItem("notcordUser", JSON.stringify({username, usertag}));
    }

    ws = new WebSocket("ws://" + location.host + "/ws");

    ws.onmessage = function(event){
        const messages = document.getElementById("messages");
        const div = document.createElement("div");
        div.textContent = event.data;
        div.className = "message";
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    };

    document.getElementById("login").style.display = "none";
    document.getElementById("chat").style.display = "block";
}

// -----------------------
// SEND MESSAGE
// -----------------------
function sendMessage(){
    const input = document.getElementById("messageInput");
    if(input.value.trim()==="") return;
    const msg = username + "#" + usertag + ": " + input.value;
    ws.send(msg);
    input.value = "";
}

// -----------------------
// ENTER KEY SEND
// -----------------------
document.addEventListener("keydown", function(event){
    if(event.key==="Enter" && document.getElementById("chat").style.display==="block"){
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
# WEBSOCKET ENDPOINT
# -----------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_users.append(websocket)
    db = SessionLocal()

    # Send previous messages
    messages = db.query(Message).all()
    for msg in messages:
        await websocket.send_text(msg.content)

    try:
        while True:
            data = await websocket.receive_text()

            # Save to database
            new_msg = Message(content=data)
            db.add(new_msg)
            db.commit()

            # Broadcast to all users
            for user in connected_users:
                await user.send_text(data)

    except WebSocketDisconnect:
        connected_users.remove(websocket)
        db.close()

# -----------------------
# RUN APP (Render compatible)
# -----------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
