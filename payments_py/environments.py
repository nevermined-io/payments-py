from enum import Enum

class Environment(Enum):
    """
    Enum class to define the different environments

    Attributes:
        local: Local environment
        appStaging: Staging environment
        appTesting: Testing environment
        appArbitrum: Arbitrum environment
    """
    local = {"frontend": "http://localhost:3000", "backend": "http://localhost:3200", "websocket": "ws://localhost:3200", "proxy": "http://localhost:3100"}
    appStaging = {"frontend": "https://staging.nevermined.app", "backend": "https://one-backend.staging.nevermined.app", "websocket": "wss://one-backend.staging.nevermined.app", "proxy": "https://proxy.staging.nevermined.app"}
    appTesting = {"frontend": "https://testing.nevermined.app", "backend": "https://one-backend.testing.nevermined.app", "websocket": "wss://one-backend.testing.nevermined.app", "proxy": "https://proxy.testing.nevermined.app"}
    appArbitrum = {"frontend": "https://nevermined.app", "backend": "https://one-backend.arbitrum.nevermined.app", "websocket": "wss://one-backend.arbitrum.nevermined.app", "proxy": "https://proxy.arbitrum.nevermined.app"}
    # Define more environments as needed...