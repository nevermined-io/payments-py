from enum import Enum

class Environment(Enum):
    """
    Enum class to define the different environments

    Attributes:
        local: Local environment
        staging: Staging environment
        testing: Testing environment
        arbitrum: Arbitrum environment
        appPeaq: Peaq network
    """
    local = {"frontend": "http://localhost:3000", "backend": "http://localhost:3200", "websocket": "ws://localhost:3200", "proxy": "http://localhost:3100"}
    staging = {"frontend": "https://staging.nevermined.app", "backend": "https://one-backend.staging.nevermined.app", "websocket": "wss://one-backend.staging.nevermined.app", "proxy": "https://proxy.staging.nevermined.app"}
    testing = {"frontend": "https://testing.nevermined.app", "backend": "https://one-backend.testing.nevermined.app", "websocket": "wss://one-backend.testing.nevermined.app", "proxy": "https://proxy.testing.nevermined.app"}
    arbitrum = {"frontend": "https://nevermined.app", "backend": "https://one-backend.arbitrum.nevermined.app", "websocket": "wss://one-backend.arbitrum.nevermined.app", "proxy": "https://proxy.arbitrum.nevermined.app"}
    appPeaq = {"frontend": "https://peaq.nevermined.app", "backend": "https://one-backend.peaq.nevermined.app"}

    @classmethod
    def get_environment(cls, name):
        """
        Get the environment by name

        Args:
            name (str): The name of the environment

        Example:
            env = Environment.get_environment('local')
        """
        try:
            return cls[name]
        except KeyError:
            raise ValueError(f"Environment '{name}' is not defined.")
