import json
import requests
import socketio
import asyncio
import jwt
from typing import Optional, Dict, List, Any, Union

from payments_py.data_models import AgentExecutionStatus, ServiceTokenResultDto
from payments_py.environments import Environment

class BackendApiOptions:
    """
    Represents the backend API options.

    Args:
        environment (Environment): The environment.
        api_key (Optional[str]): The Nevermined API Key. This key identify your user and is required to interact with the Nevermined API. You can get your API key by logging in to the Nevermined App. See https://docs.nevermined.app/docs/tutorials/integration/nvm-api-keys
        headers (Optional[Dict[str, str]]): Additional headers to send with the requests
    """
    def __init__(self,
                 environment: Environment,
                 api_key: Optional[str] = None,
                 headers: Optional[Dict[str, str]] = None,
                ):
        self.api_key = api_key
        self.backend_host = environment.value['backend']
        self.web_socket_host = environment.value['websocket']
        self.proxy_host = environment.value['proxy']
        self.headers = headers or {}


class NVMBackendApi:
    def __init__(self, opts: BackendApiOptions):
        self.opts = opts
        self.socket_client = socketio.AsyncClient(logger=True, engineio_logger=True)
        self.user_room_id = None
        self.has_key = False
        self.callback = None
        self.join_account_room = None
        self.join_agent_rooms = None
        self.subscribe_event_types = None
        self.get_pending_events_on_subscribe = None
        self.did = None
        
        default_headers = {
            'Accept': 'application/json',
            **(opts.headers or {}),
            **({'Authorization': f'Bearer {opts.api_key}'} if opts.api_key else {})
        }
        self.opts.headers = default_headers

        try:
            if self.opts.api_key and len(self.opts.api_key) > 0:
                decoded_jwt = jwt.decode(self.opts.api_key, options={"verify_signature": False})
                client_id = decoded_jwt.get('sub')
                
                # Check if the client_id exists and does not match the specified pattern
                if client_id:# and not re.match(r'^0x[a-fA-F0-9]{40}$', client_id):
                    self.user_room_id = f"room:{client_id}"
                    self.has_key = True
        except Exception:
            self.has_key = False
            self.user_room_id = None 

        try:
            backend_url = self.opts.backend_host.rstrip('/')
            self.opts.backend_host = backend_url
        except Exception as error:
            raise ValueError(f"Invalid URL: {self.opts.backend_host} - {str(error)}")


    async def connect_socket_subscriber(self, callback, join_account_room, join_agent_rooms, subscribe_event_types, get_pending_events_on_subscribe):
        self.callback = callback
        self.join_account_room = join_account_room
        self.join_agent_rooms = join_agent_rooms
        self.subscribe_event_types = subscribe_event_types
        self.get_pending_events_on_subscribe = get_pending_events_on_subscribe
        self.socket_client.on('_connected', self._subscribe)
        await self.connect_socket()

    async def connect_socket(self):
        if not self.has_key:
            raise ValueError('Unable to subscribe to the server because a key was not provided')

        if self.socket_client and self.socket_client.connected:
            return
        
        try:
            print(f"nvm-backend:: Connecting to websocket server: {self.opts.web_socket_host}")
            auth = {"token" : f'Bearer {self.opts.api_key}' if self.opts.api_key else {} }
            await self.socket_client.connect(self.opts.web_socket_host, auth=auth, transports=["websocket"])
            for i in range(5):
                await self.socket_client.sleep(1)  
                if self.socket_client.connected:
                    break
            print(f"nvm-backend:: Connected: {self.socket_client.connected}")
        except Exception as error:
            raise ConnectionError(f"Unable to initialize websocket client: {self.opts.web_socket_host} - {str(error)}")

    async def disconnect_socket(self):
        if self.socket_client and self.socket_client.connected:
            await self.socket_client.disconnect()    

    async def _subscribe(self, data):
        if not self.join_account_room and not self.join_agent_rooms:
            raise ValueError('No rooms to join in configuration')
        if not self.socket_client.connected:
            raise ConnectionError('Failed to connect to the WebSocket server.')
            
        async def event_handler(data):
            try:
                parsed_data = json.loads(data)
                self.did = parsed_data.get('did')
            except Exception as e:
                print('nvm-backend:: Unable to parse data', e)
                return
            asyncio.create_task(self.callback(parsed_data))

        await self.join_room(self.join_account_room, self.join_agent_rooms)

        if self.subscribe_event_types:
            for event in self.subscribe_event_types:
                print(f"nvm-backend:: Subscribing to event: {event}")
                self.socket_client.on(event, event_handler)
        else:
            self.socket_client.on('step-updated', event_handler)
        
        if self.get_pending_events_on_subscribe:
            try: 
                print('Emitting pending events')
                if self.get_pending_events_on_subscribe and self.join_agent_rooms: 
                    await self._emit_step_events(AgentExecutionStatus.Pending, self.join_agent_rooms)
            except Exception as e:
                print('query-api:: Unable to get pending events', e)
            
            
    async def _emit_step_events(self, status: AgentExecutionStatus = AgentExecutionStatus.Pending, dids: List[str] = []):
        message = { "status": status.value, "dids": dids }
        print(f"nvm-backend:: Emitting step: {json.dumps(message)}")
        await self.socket_client.emit(event='_emit-steps', data=json.dumps(message))

    async def join_room(self, join_account_room: bool, room_ids: Optional[Union[str, List[str]]] = None):
        print(f"event:: Joining rooms: {room_ids} and {self.user_room_id}")

        data = { 'joinAccountRoom': join_account_room }
        
        if room_ids:
            data['joinAgentRooms'] = [room_ids] if isinstance(room_ids, str) else room_ids
        
        await self.socket_client.emit('_join-rooms', json.dumps(data))
        
        print(f"event:: Joined rooms: {room_ids} and {self.user_room_id}")

    async def disconnect(self):
        await self.disconnect_socket()
        print("nvm-backend:: Disconnected from the server")

    def parse_url_to_proxy(self, uri: str) -> str:
        return f"{self.opts.proxy_host}{uri}"
    
    def parse_url_to_backend(self, uri: str) -> str:
        return f"{self.opts.backend_host}{uri}"
    
    def parse_headers(self, additional_headers: dict[str, str]) -> dict[str, str]:
        return {
            **self.opts.headers,
            **additional_headers,
        }

    def get(self, url: str, headers: Optional[Dict[str, str]] = None):
        headers = self.parse_headers(headers or {})

        response = requests.get(url, headers=headers) 
        if response.status_code >= 400:
            raise Exception({"data": response.json(), "status": response.status_code, "headers": response.headers})
        return response

    def post(self, url: str, data: Any, headers: Optional[Dict[str, str]] = None):
        headers = self.parse_headers(headers or {})

        response = requests.post(url, json=data, headers=headers)
        if response.status_code >= 400:
            raise Exception({"data": response.json(), "status": response.status_code, "headers": response.headers})
        return response

    def put(self, url: str, data: Any, headers: Optional[Dict[str, str]] = None):
        headers = self.parse_headers(headers or {})
        
        response = requests.put(url, json=data, headers=headers)
        if response.status_code >= 400:
            raise Exception({"data": response.json(), "status": response.status_code, "headers": response.headers})
        return response
      
    def delete(self, url: str, data: Any, headers: Optional[Dict[str, str]] = None):
        headers = self.parse_headers(headers or {})
        
        response = requests.delete(url, json=data, headers=headers)
        if response.status_code >= 400:
            raise Exception({"data": response.json(), "status": response.status_code, "headers": response.headers})
        return response

    def get_service_token(self, service_did: str) -> ServiceTokenResultDto:
        """
        Gets the service token.

        Args:
            service_did (str): The DID of the service.

        Returns:
            ServiceTokenResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.get_service_token(service_did="did:nv:xyz789")
            print(response)
        """
        url = f"{self.opts.backend_host}/api/v1/payments/service/token/{service_did}"
        response = self.get(url)
        return ServiceTokenResultDto.model_validate(response.json()['token'])