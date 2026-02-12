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
# FRONTEND (REVAMPED GUI ONLY)
# -----------------------
html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
* { box-sizing: border-box; }

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
    width: 230px;
    background: #2b2d31;
    padding: 20px;
    display: flex;
    flex-direction: column;
}

.sidebar h2 {
    margin: 0 0 20px 0;
}

/* Chat layout */
.chat-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
}

.header {
    background: #313338;
    padding: 15px 20px;
    font-weight: bold;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.chat-container {
    flex: 1;
    padding: 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

/* Message bubble */
.message {
    max-width: 70%;
    padding: 10px 14px;
    border-radius: 10px;
    background: #383a40;
    word-wrap: break-word;
    position: relative;
}

.message.me {
    align-self: flex-end;
    background: #5865f2;
}

/* Username */
.username {
    font-weight: bold;
    cursor: pointer;
}

/* Input */
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
}

/* Login */
#login {
    position: fixed;
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

/* Profile popup */
#profilePopup {
    position: fixed;
    background: #2b2d31;
    padding: 20px;
    border-radius: 10px;
    display: none;
}

/* Admin panel */
#adminPanel {
    position: fixed;
    right: 20px;
    bottom: 20px;
    background: #2b2d31;
    padding: 15px;
    border-radius: 10px;
    display: none;
}
</style>
</head>
<body>

<div class="sidebar">
    <h2>NOTCORD</h2>
    <div># general</div>
</div>

<div class="chat-wrapper">
    <div class="header">
        # general
        <button id="adminToggle" style="display:none;" onclick="toggleAdmin()">Admin</button>
    </div>

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
        <button onclick="joinChat()">Join</button>
    </div>
</div>

<div id="profilePopup"></div>

<div id="adminPanel">
    <h3>Admin Panel</h3>
    <button onclick="clearChat()">Clear Chat (Local)</button><br><br>
    <button onclick="toggleServiceMode()">Toggle Service Mode</button>
</div>

<script>
let ws;
let username;
let serviceMode = false;

function joinChat(){
    username = document.getElementById("username").value.trim();
    if(!username) return;

    if(username === "DavidDoesTech"){
        document.getElementById("adminToggle").style.display="inline-block";
    }

    let protocol = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(protocol + location.host + "/ws");

    ws.onmessage = function(event){
        addMessage(event.data);
    };

    document.getElementById("login").style.display="none";
}

function addMessage(text){
    const messages = document.getElementById("messages");

    const div = document.createElement("div");
    div.className="message";

    if(text.startsWith(username + ":")){
        div.classList.add("me");
    }

    const split = text.split(": ");
    const user = split[0];
    const content = split.slice(1).join(": ");

    div.innerHTML = '<span class="username" onclick="showProfile(\\''+user+'\\')">'+user+'</span>: '+content;

    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function sendMessage(){
    if(serviceMode && username !== "DavidDoesTech"){
        alert("Service Mode Enabled");
        return;
    }

    const input=document.getElementById("messageInput");
    if(input.value.trim()==="") return;

    ws.send(username + ": " + input.value);
    input.value="";
}

function showProfile(name){
    const popup=document.getElementById("profilePopup");
    popup.innerHTML="<h3>"+name+"</h3><p>Profile popup</p><button onclick='closeProfile()'>Close</button>";
    popup.style.display="block";
    popup.style.top="100px";
    popup.style.left="300px";
}

function closeProfile(){
    document.getElementById("profilePopup").style.display="none";
}

function toggleAdmin(){
    const panel=document.getElementById("adminPanel");
    panel.style.display = panel.style.display==="block" ? "none" : "block";
}

function clearChat(){
    document.getElementById("messages").innerHTML="";
}

function toggleServiceMode(){
    serviceMode=!serviceMode;
    alert("Service Mode: " + (serviceMode ? "ON":"OFF"));
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
# RUN APP
# -----------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
