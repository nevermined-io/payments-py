import pytest
import socketio
import asyncio

# Create a SocketIO client
socket_client = socketio.AsyncClient()

# Global variable to store the response data and an Event for synchronization
response_data = None
response_event = asyncio.Event()

# Callback function to handle the server's response
@socket_client.on('my_event_response')
async def my_event_response(data):
    global response_data
    print('Response from server:', data)
    response_data = data  # Store the received data for assertion
    response_event.set()  # Notify that the response has been received

@socket_client.on('rooms_list')
async def handle_rooms_list(data):
    print('Active rooms:', data['rooms'])

@pytest.mark.asyncio
async def test_event_callback():
    await socket_client.connect('http://localhost:6666')
    
    global response_data

    # await socket_client.emit('list_rooms')

    # Join the room before emitting the event
    room_id = 'test_room'
    print('Joining room:', room_id)
    await socket_client.emit('join_room', {'room': room_id})

    # await socket_client.emit('list_rooms')


    # Emit the event to the server, including the room ID
    test_data = {'message': 'Hello from the client!', 'room': room_id}
    print('Emitting my_event to server:', test_data)
    await socket_client.emit('my_event', test_data)

    # Wait until the response event is set
    await response_event.wait()

    # Assert that the callback received the correct data
    assert response_data == {'data': 'Response from server'}

    await socket_client.disconnect()
