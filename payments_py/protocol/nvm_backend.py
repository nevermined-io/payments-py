import requests
import socketio
import jwt
from typing import Optional, Dict, List, Any


class BackendApiOptions:
    def __init__(self,
                 backend_host: str,
                 bearer_token: str,
                 web_socket_host: Optional[str] = None,
                 proxy_host: Optional[str] = None,
                 headers: Optional[Dict[str, str]] = None,
                 web_socket_options: Optional[Dict[str, Any]] = None):
        self.backend_host = backend_host
        self.bearer_token = bearer_token
        self.web_socket_host = web_socket_host
        self.proxy_host = proxy_host
        self.headers = headers or {}
        self.web_socket_options = web_socket_options or {}


class BackendWebSocketOptions:
    def __init__(self,
                 path: Optional[str] = None,
                 transports: Optional[List[str]] = None,
                 bearer_token: Optional[str] = None,
                 transport_options: Optional[Dict[str, Any]] = None):
        self.path = path
        self.transports = transports or ['websocket']
        self.bearer_token = bearer_token
        self.transport_options = transport_options or {'websocket': {'extraHeaders': {}}}


class NVMBackendApi:
    def __init__(self, opts: BackendApiOptions):
        self.opts = opts
        self.socket_client = None
        self.room_id = None

        default_headers = {
            'Accept': 'application/json',
            **(opts.headers or {}),
            **({'Authorization': f'Bearer {opts.bearer_token}'} if opts.bearer_token else {})
        }

        # Setup WebSocket Options
        if opts.web_socket_options and opts.web_socket_options.get('bearer_token'):
            opts.web_socket_options['transport_options'] = {
                'websocket': {
                    'extraHeaders': {'Authorization': f'Bearer {opts.web_socket_options["bearer_token"]}'}
                }
            }

        # Merge default socket options
        self._default_socket_options = {
            'transports': ['websocket'],
            'transportOptions': {
                'websocket': {
                    'extraHeaders': {},
                },
            },
        }

        self.opts.headers = default_headers
        self.opts.web_socket_options = {
            **self._default_socket_options,
            **(opts.web_socket_options or {})
        }

        # Validate JWT
        try:
            decoded_jwt = jwt.decode(self.opts.bearer_token, options={"verify_signature": False})
            client_id = decoded_jwt.get('sub')
            if not client_id or not client_id.startswith('0x') or len(client_id) != 42:
                raise ValueError(f"Invalid ClientId from Bearer token: {client_id}")
            self.room_id = f"room:{client_id}"
        except jwt.DecodeError as error:
            raise ValueError(f"Error parsing bearer token: {str(error)}")

        # Validate URL
        try:
            self.opts.backend_host = self.opts.backend_host.rstrip('/')
        except Exception as error:
            raise ValueError(f"Invalid URL: {self.opts.backend_host} - {str(error)}")

    def connect_socket(self):
        if self.socket_client and self.socket_client.connected:
            return
        try:
            print(f"Connecting to websocket server: {self.opts.web_socket_host}")
            self.socket_client = socketio.Client()
            self.socket_client.connect(self.opts.web_socket_host, **self.opts.web_socket_options)
            print(f"is connected: {self.socket_client.connected}")
        except Exception as error:
            raise ConnectionError(
                f"Unable to initialize websocket client: {self.opts.web_socket_host} - {str(error)}"
            )

    def disconnect_socket(self):
        if self.socket_client and self.socket_client.connected:
            self.socket_client.disconnect()

    def _subscribe(self, callback):
        self.connect_socket()
        self.socket_client.on('connect', lambda: print("Subscribed:: Connected to the server"))
        print(f"Joining room: {self.room_id}")
        self.socket_client.on(self.room_id, callback)
        print(f"Joined room: {self.room_id}")

    def _emit_events(self, data: Any):
        self.connect_socket()
        self.socket_client.emit(self.room_id, data)

    def disconnect(self):
        self.disconnect_socket()
        print("Disconnected from the server")

    def parse_url(self, uri: str):
        return f"{self.opts.proxy_host}{uri}" if self.opts.proxy_host else f"{self.opts.backend_host}{uri}"

    def set_bearer_token(self, token: str):
        self.opts.headers['Authorization'] = f'Bearer {token}'

    def get(self, url: str):
        try:
            response = requests.get(self.parse_url(url), headers=self.opts.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            return {"data": err.response.json(), "status": err.response.status_code, "headers": err.response.headers}

    def post(self, url: str, data: Any):
        try:
            print(f"Sending POST: {self.parse_url(url)}")
            response = requests.post(self.parse_url(url), json=data, headers=self.opts.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            return {"data": err.response.json(), "status": err.response.status_code, "headers": err.response.headers}

    def put(self, url: str, data: Any):
        try:
            response = requests.put(self.parse_url(url), json=data, headers=self.opts.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            return {"data": err.response.json(), "status": err.response.status_code, "headers": err.response.headers}

    def delete(self, url: str, data: Any):
        try:
            response = requests.delete(self.parse_url(url), json=data, headers=self.opts.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as err:
            return {"data": err.response.json(), "status": err.response.status_code, "headers": err.response.headers}
