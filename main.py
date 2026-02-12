from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
import os

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
# FRONTEND HTML (FULL REVAMP)
# -----------------------
html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* {
    box-sizing: border-box;
}

body {
    margin: 0;
    font-family: "Segoe UI", sans-serif;
    background: #1e1f22;
    color: white;
    display: flex;
    height: 100vh;
}

/* Sidebar */
.sidebar {
    width: 220px;
    background: #2b2d31;
    padding: 20px;
    display: flex;
    flex-direction: column;
}

.sidebar h2 {
    margin: 0;
    margin-bottom: 20px;
    font-size: 18px;
}

.channel {
    padding: 8px;
    border-radius: 6px;
    cursor: pointer;
}

.channel:hover {
    background: #3a3c42;
}

/* Main chat area */
.chat-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
}

.header {
    background: #313338;
    padding: 15px 20px;
    font-weight: bold;
    border-bottom: 1px solid #1e1f22;
}

.chat-container {
    flex: 1;
    padding: 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

/* Message bubbles */
.message {
    max-width: 70%;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 14px;
    line-height: 1.4;
    word-wrap: break-word;
}

.other {
    background: #383a40;
    align-self: flex-start;
}

.me {
    background: #5865f2;
    align-self: flex-end;
}

/* Input area */
.message-input {
    padding: 15px;
    background: #2b2d31;
    display: flex;
    gap: 10px;
}

.message-input input {
    flex: 1;
    padding: 12px;
    border-radius: 8px;
    border: none;
    outline: none;
    background: #1e1f22;
    color: white;
}

.message-input button {
    padding: 12px 18px;
    border-radius: 8px;
    border: none;
    background: #5865f2;
    color: white;
    cursor: pointer;
    font-weight: bold;
}

.message-input button:hover {
    background: #4752c4;
}

/* Login screen */
#login {
    position: absolute;
    inset: 0;
    background: #1e1f22;
    display: flex;
    justify-content: center;
    align-items: center;
}

.login-box {
    background: #2b2d31;
    padding: 30px;
    border-radius: 10px;
    width: 300px;
    text-align: center;
}

.login-box input {
    width: 100%;
    padding: 10px;
    margin-bottom: 15px;
    border-radius: 6px;
    border: none;
}

.login-box button {
    width: 100%;
    padding: 10px;
    border-radius: 6px;
    border: none;
    background: #5865f2;
    color: white;
    font-weight: bold;
    cursor: pointer;
}
</style>
</head>
<body>

<div class="sidebar">
    <h2>NOTCORD</h2>
    <div class="channel"># general</div>
</div>

<div class="chat-wrapper">
    <div class="header"># general</div>
    <div id="messages" class="chat-container"></div>
    <div class="message-input">
        <input id="messageInput" placeholder="Message #general">
        <button onclick="sendMessage()">Send</button>
    </div>
</div>

<div id="login">
    <div class="login-box">
        <h2>Welcome to NOTCORD</h2>
        <input id="username" placeholder="Enter username">
        <button onclick="joinChat()">Join Chat</button>
    </div>
</div>

<script>
let ws;
let username;
let usertag;

function generateTag() {
    return Math.floor(Math.random() * 9000 + 1000);
}

// Auto login from localStorage
if(localStorage.getItem("notcordUser")){
    const data = JSON.parse(localStorage.getItem("notcordUser"));
    username = data.username;
    usertag = data.usertag;
    connectWebSocket();
}

function joinChat(){
    username = document.getElementById("username").value.trim();
    if(!username) return alert("Enter username");

    usertag = generateTag();
    localStorage.setItem("notcordUser", JSON.stringify({username, usertag}));
    connectWebSocket();
}

function connectWebSocket(){
    let protocol = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(protocol + location.host + "/ws");

    ws.onmessage = function(event){
        addMessage(event.data);
    };

    document.getElementById("login").style.display = "none";
}

function addMessage(text){
    const messages = document.getElementById("messages");
    const div = document.createElement("div");

    if(text.startsWith(username + "#" + usertag)){
        div.className = "message me";
    } else {
        div.className = "message other";
    }

    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function sendMessage(){
    const input = document.getElementById("messageInput");
    if(input.value.trim()==="") return;

    const msg = username + "#" + usertag + ": " + input.value;
    ws.send(msg);
    input.value = "";
}

document.addEventListener("keydown", function(event){
    if(event.key==="Enter"){
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

    messages = db.query(Message).all()
    for msg in messages:
        await websocket.send_text(msg.content)

    try:
        while True:
            data = await websocket.receive_text()

            new_msg = Message(content=data)
            db.add(new_msg)
            db.commit()

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
