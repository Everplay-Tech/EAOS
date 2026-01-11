"""Core matrix utilities and models used across the BioAgent services."""

from .models import Msg, Reply, new_id, now  # noqa: F401
from .utils import canonical, state_hash  # noqa: F401
from .errors import (  # noqa: F401
    BIOworkError,
    InvalidInputError,
    AgentProcessingError,
    AgentNotFoundError,
    create_error_response,
    validate_msg_input,
)
from .logging_config import setup_logging, log_request, log_response, log_error  # noqa: F401
from .config import settings  # noqa: F401
from .cache import cache, cached  # noqa: F401

# Authentication (optional imports - won't fail if dependencies not installed)
try:
    from .auth import (  # noqa: F401
        hash_password,
        verify_password,
        create_access_token,
        create_refresh_token,
        decode_token,
        get_user_id_from_token,
        generate_api_key,
        hash_api_key,
        verify_api_key,
    )
    from .auth_dependencies import (  # noqa: F401
        get_current_user,
        get_current_active_user,
        get_optional_user,
        require_admin,
    )
except ImportError:
    pass  # Auth dependencies not installed
