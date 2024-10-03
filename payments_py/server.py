import os
import socketio
from aiohttp import web

# Create a new Async SocketIO server
sio = socketio.AsyncServer()

active_rooms = set()


# Example event handlers
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.event
async def join_room(sid, data):
    room = data['room']
    print(f'Client {sid} joining room: {room}')
    await sio.enter_room(sid, room)
    active_rooms.add(room)

@sio.event
async def list_rooms(sid):
    # Emit the list of active rooms to the client
    await sio.emit('rooms_list', {'rooms': list(active_rooms)}, room=sid)

@sio.event
async def my_event(sid, data):
    print('Message from client:', data)
    
    room = data['room']
    # Emit a response back to the room
    await sio.emit('my_event_response', {'data': 'Response from server'}, room=room)

# Create a new Aiohttp web application
app = web.Application()

# Attach the SocketIO server to the web application
sio.attach(app)

# Start the server
if __name__ == '__main__':
    web.run_app(app, host='localhost', port=6666)
