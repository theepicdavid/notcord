from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import List

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
    server = Column(String, default="general")

Base.metadata.create_all(bind=engine)

# -----------------------
# CONFIG
# -----------------------
MAINTENANCE_MODE = True # Set True to activate maintenance page

# -----------------------
# CONNECTIONS
# -----------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# -----------------------
# HTML & FRONTEND
# -----------------------
html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD 2.0</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body { margin:0; font-family: Arial, sans-serif; background:#36393f; color:white; }
.header { background:#2f3136; padding:15px; font-size:20px; display:flex; justify-content:space-between; align-items:center; }
#serverSelect { background:#40444b; color:white; border:none; padding:5px; border-radius:5px; }
.chat-container { padding:10px; height:60vh; overflow-y:auto; background:#2f3136; }
input { padding:10px; border:none; border-radius:5px; flex:1; }
button { padding:10px; background:#5865f2; color:white; border:none; border-radius:5px; cursor:pointer; }
.message-input { display:flex; position:fixed; bottom:0; width:100%; padding:10px; background:#40444b; gap:5px; }
.message { margin-bottom:5px; }
.username { font-weight:bold; color:#7289da; }
</style>
</head>
<body>

<div class="header">
    <span>NOTCORD 2.0</span>
    <select id="serverSelect" onchange="changeServer()">
        <option value="general">#general</option>
    </select>
</div>

<div id="login" style="padding:20px;">
    <input id="username" placeholder="Enter username">
    <button onclick="joinChat()">Join Chat</button>
</div>

<div id="chat" style="display:none;">
    <div id="messages" class="chat-container"></div>
    <div class="message-input">
        <input id="messageInput" placeholder="Type message">
        <button onclick="sendMessage()">Send</button>
    </div>
</div>

<script>
let ws;
let username;
let server = "general";

function joinChat() {
    username = document.getElementById("username").value.trim();
    if(!username) return alert("Enter username");

    ws = new WebSocket(
        location.protocol === "https:" ? "wss://" + location.host + "/ws" : "ws://" + location.host + "/ws"
    );

    ws.onopen = () => console.log("Connected!");
    ws.onmessage = function(event) {
        const messages = document.getElementById("messages");
        const data = JSON.parse(event.data);
        if(data.server !== server) return;

        const div = document.createElement("div");
        div.classList.add("message");
        const userSpan = document.createElement("span");
        userSpan.className = "username";
        userSpan.textContent = data.username + ": ";
        div.appendChild(userSpan);
        div.appendChild(document.createTextNode(data.content));
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    };

    ws.onclose = () => alert("Disconnected from server.");

    document.getElementById("login").style.display = "none";
    document.getElementById("chat").style.display = "block";
}

function sendMessage() {
    const input = document.getElementById("messageInput");
    if(input.value.trim()==="") return;
    ws.send(JSON.stringify({username: username, content: input.value, server: server}));
    input.value = "";
}

// Send message on Enter
document.getElementById("messageInput").addEventListener("keydown", function(e) {
    if(e.key === "Enter") sendMessage();
});

// Change server / room
function changeServer() {
    server = document.getElementById("serverSelect").value;
    document.getElementById("messages").innerHTML = "";
}
</script>

</body>
</html>
"""

maintenance_html = """
<html>
<head>
<title>NOTCORD Maintenance</title>
<style>
body { background:#36393f; color:white; font-family:Arial; text-align:center; padding-top:50px; }
h1 { color:#7289da; }
</style>
</head>
<body>
<h1>🚧 NOTCORD is temporarily offline for updates!</h1>
<p>We’ll be back shortly. Thanks for your patience.</p>
</body>
</html>
"""

# -----------------------
# ROUTES
# -----------------------
@app.get("/")
async def get(request: Request):
    if MAINTENANCE_MODE:
        return HTMLResponse(maintenance_html, status_code=503)
    return HTMLResponse(html)

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

    # Send previous messages
    messages = db.query(Message).all()
    for msg in messages:
        await websocket.send_text(f'{{"username":"{msg.content.split(": ")[0]}","content":"{": ".join(msg.content.split(": ")[1:])}","server":"general"}}')

    try:
        while True:
            data = await websocket.receive_text()
            import json
            msg = json.loads(data)
            # Save to database
            new_msg = Message(content=f'{msg["username"]}: {msg["content"]}', server=msg["server"])
            db.add(new_msg)
            db.commit()
            # Broadcast
            await manager.broadcast(json.dumps(msg))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        db.close()

