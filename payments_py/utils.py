import uuid
from urllib.parse import urlparse


def snake_to_camel(name):
    """
    Convert snake_case to camelCase.

    :param name: str
    :return: str
    """
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def is_ethereum_address(address: str | None) -> bool:
    """
    Validates if a string is a valid Ethereum address.

    :param address: str or None
    :return: bool
    """
    if address and isinstance(address, str) and address.startswith("0x") and len(address) == 42:
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False
    return False


def generate_step_id() -> str:
    """
    Generate a random step id.

    :return: str
    """
    return f"step-{str(uuid.uuid4())}"


def is_step_id_valid(step_id: str) -> bool:
    """
    Check if the step id has the right format.

    :param step_id: str
    :return: bool
    """
    if not step_id.startswith("step-"):
        return False
    try:
        uuid.UUID(step_id[5:])
        return True
    except ValueError:
        return False


def get_query_protocol_endpoints(server_host: str):
    """
    Returns the list of endpoints that are used by agents/services implementing the Nevermined Query Protocol.

    :param server_host: str
    :return: list
    """
    url = urlparse(server_host)
    origin = f"{url.scheme}://{url.netloc}"
    return [
        {"POST": f"{origin}/api/v1/agents/(.*)/tasks"},
        {"GET": f"{origin}/api/v1/agents/(.*)/tasks/(.*)"},
    ]


def get_ai_hub_open_api_url(server_host: str) -> str:
    """
    Returns the URL to the OpenAPI documentation of the AI Hub.

    :param server_host: str
    :return: str
    """
    url = urlparse(server_host)
    origin = f"{url.scheme}://{url.netloc}"
    return f"{origin}/api/v1/rest/docs-json"
