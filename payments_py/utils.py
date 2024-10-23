import uuid

def snake_to_camel(name):
    """
    Convert snake_case to camelCase.
    
    :param name: str
    :return: str
    
    """
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def generate_step_id():
    """
    Generate a random ID.
    
    :return: str
    
    """
    return f"step-${str(uuid.uuid4())}"

def is_id_valid(id):
    """
    Check if the ID is valid.
    
    :param id: str
    :return: bool

    """
    if not id.startswith('step-'):
        return False 
    else:
        try:
            uuid.UUID(id)
            return True
        except ValueError:
            return False
        
def get_query_protocol_endpoints(server_host: str):
    """
    Get the query protocol endpoints.
    
    :return: dict
    
    """
    return [
        {'POST': f'{server_host}/api/v1/agents/(.*)/tasks'},
        {'GET': f'{server_host}/api/v1/agents/(.*)/tasks/(.*)'},
    ]

def get_ai_hub_open_api_url(server_host: str):
    """
    Get the AI Hub Open API URL.
    
    :return: str
    
    """
    return f'{server_host}/api/v1/rest/docs-json'