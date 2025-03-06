from enum import Enum


class Environment(Enum):
    """
    Enum class to define the different environments

    Attributes:
        local: Local environment
        staging: Staging environment
        testing: Testing environment
        gnosis: Gnosis environment
        base: Base environment
        baseSepolia: Base Sepolia environment
        arbitrum: Arbitrum environment
        appPeaq: Peaq network
    """

    local = {
        "frontend": "http://localhost:3000",
        "backend": "http://localhost:3200",
        "websocket": "ws://localhost:3200",
        "proxy": "http://localhost:3100",
    }
    staging = {
        "frontend": "https://staging.nevermined.app",
        "backend": "https://one-backend.staging.nevermined.app",
        "websocket": "wss://one-backend.staging.nevermined.app",
        "proxy": "https://proxy.staging.nevermined.app",
    }
    testing = {
        "frontend": "https://testing.nevermined.app",
        "backend": "https://one-backend.testing.nevermined.app",
        "websocket": "wss://one-backend.testing.nevermined.app",
        "proxy": "https://proxy.testing.nevermined.app",
    }
    gnosis = {
        "frontend": "https://gnosis.nevermined.app",
        "backend": "https://one-backend.gnosis.nevermined.app",
        "websocket": "wss://one-backend.gnosis.nevermined.app",
        "proxy": "https://proxy.gnosis.nevermined.app",
    }
    base = {
        "frontend": "https://base.nevermined.app",
        "backend": "https://one-backend.base.nevermined.app",
        "websocket": "wss://one-backend.base.nevermined.app",
        "proxy": "https://proxy.base.nevermined.app",
    }
    baseSepolia = {
        "frontend": "https://base-sepolia.nevermined.app",
        "backend": "https://one-backend.base-sepolia.nevermined.app",
        "websocket": "wss://one-backend.base-sepolia.nevermined.app",
        "proxy": "https://proxy.base-sepolia.nevermined.app",
    }
    arbitrum = {
        "frontend": "https://nevermined.app",
        "backend": "https://one-backend.arbitrum.nevermined.app",
        "websocket": "wss://one-backend.arbitrum.nevermined.app",
        "proxy": "https://proxy.arbitrum.nevermined.app",
    }
    appPeaq = {
        "frontend": "https://peaq.nevermined.app",
        "backend": "https://one-backend.peaq.nevermined.app",
    }

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
