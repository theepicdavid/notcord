from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, declarative_base

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
# FRONTEND HTML
# -----------------------
html = """
<!DOCTYPE html>
<html>
<head>
<title>NOTCORD</title>
<style>
body { margin:0; font-family: Arial; background:#36393f; color:white; }
.header { background:#2f3136; padding:15px; font-size:20px; }
.chat-container { padding:20px; height:70vh; overflow-y:auto; }
input { padding:10px; border:none; border-radius:5px; }
button { padding:10px; background:#5865f2; color:white; border:none; border-radius:5px; cursor:pointer; }
.message-input { position:fixed; bottom:0; width:100%; padding:15px; background:#40444b; display:flex; gap:10px; }
.message { margin-bottom:5px; }
.username { font-weight:bold; color:#7289da; }
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
        <input id="messageInput" style="flex:1;" placeholder="Type message">
        <button onclick="sendMessage()">Send</button>
    </div>
</div>

<script>
let ws;
let username;

function joinChat() {
    username = document.getElementById("username").value.trim();
    if(!username) return alert("Enter username");

    // Use WSS if page is HTTPS
    ws = new WebSocket(
        location.protocol === "https:" ? "wss://" + location.host + "/ws" : "ws://" + location.host + "/ws"
    );

    ws.onopen = () => console.log("Connected to NOTCORD!");

    ws.onmessage = function(event) {
        const messages = document.getElementById("messages");
        const div = document.createElement("div");
        div.classList.add("message");
        
        // Optional: highlight username
        const parts = event.data.split(": ");
        if(parts.length > 1){
            const userSpan = document.createElement("span");
            userSpan.className = "username";
            userSpan.textContent = parts[0] + ": ";
            div.appendChild(userSpan);
            
            const msgText = document.createTextNode(parts.slice(1).join(": "));
            div.appendChild(msgText);
        } else {
            div.textContent = event.data;
        }

        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    };

    ws.onclose = () => alert("Disconnected from server.");

    document.getElementById("login").style.display = "none";
    document.getElementById("chat").style.display = "block";
}

function sendMessage() {
    const input = document.getElementById("messageInput");
    if(input.value.trim() === "") return;
    ws.send(username + ": " + input.value);
    input.value = "";
}
</script>

</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html)

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
