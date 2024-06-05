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
    local = {"frontend": "http://localhost:3000", "backend": "http://localhost:3200"}
    appStaging = {"frontend": "https://staging.nevermined.app", "backend": "https://one-backend.staging.nevermined.app"}
    appTesting = {"frontend": "https://testing.nevermined.app", "backend": "https://one-backend.testing.nevermined.app"}
    appArbitrum = {"frontend": "https://nevermined.app", "backend": "https://one-backend.arbitrum.nevermined.app"}
    # Define more environments as needed...