def snake_to_camel(name):
    """
    Convert snake_case to camelCase.
    
    :param name: str
    :return: str
    
    """
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])