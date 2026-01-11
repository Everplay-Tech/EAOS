"""Configuration management using Pydantic Settings."""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL Configuration
    postgres_host: str = Field(default="postgres", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_user: str = Field(default="biowerk", description="PostgreSQL user")
    postgres_password: str = Field(default="biowerk_dev_password", description="PostgreSQL password")
    postgres_db: str = Field(default="biowerk", description="PostgreSQL database name")

    # MongoDB Configuration
    mongo_host: str = Field(default="mongodb", description="MongoDB host")
    mongo_port: int = Field(default=27017, description="MongoDB port")
    mongo_user: str = Field(default="biowerk", description="MongoDB user")
    mongo_password: str = Field(default="biowerk_dev_password", description="MongoDB password")
    mongo_db: str = Field(default="biowerk", description="MongoDB database name")

    # Redis Configuration
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_db: int = Field(default=0, description="Redis database number")

    # Cache Configuration
    cache_ttl: int = Field(default=300, description="Default cache TTL in seconds")
    cache_enabled: bool = Field(default=True, description="Enable caching")

    # Session Configuration
    session_enabled: bool = Field(default=True, description="Enable Redis-based sessions")
    session_ttl_short: int = Field(default=900, description="Short session TTL in seconds (15 min)")
    session_ttl_default: int = Field(default=3600, description="Default session TTL in seconds (1 hour)")
    session_ttl_long: int = Field(default=28800, description="Long session TTL in seconds (8 hours)")
    session_ttl_workflow: int = Field(default=86400, description="Workflow session TTL in seconds (24 hours)")
    session_prefix: str = Field(default="session", description="Redis key prefix for sessions")

    # Application Configuration
    log_level: str = Field(default="INFO", description="Logging level")
    environment: str = Field(default="development", description="Environment (development, staging, production)")

    # Service Mesh Resilience Configuration
    # Circuit Breaker Settings
    circuit_breaker_enabled: bool = Field(default=True, description="Enable circuit breaker pattern")
    circuit_breaker_failure_threshold: int = Field(default=5, description="Consecutive failures before opening circuit")
    circuit_breaker_success_threshold: int = Field(default=2, description="Consecutive successes to close circuit in HALF_OPEN state")
    circuit_breaker_timeout: int = Field(default=60, description="Seconds to wait before transitioning OPEN -> HALF_OPEN")
    circuit_breaker_failure_rate_threshold: float = Field(default=0.5, description="Failure rate (0.0-1.0) to trigger circuit open")
    circuit_breaker_window_size: int = Field(default=10, description="Number of recent calls to track for failure rate")

    # Retry Settings
    retry_enabled: bool = Field(default=True, description="Enable retry with exponential backoff")
    retry_max_attempts: int = Field(default=3, description="Maximum number of retry attempts")
    retry_initial_delay: float = Field(default=0.1, description="Initial retry delay in seconds")
    retry_max_delay: float = Field(default=5.0, description="Maximum retry delay in seconds")
    retry_exponential_base: float = Field(default=2.0, description="Base for exponential backoff calculation")
    retry_jitter: bool = Field(default=True, description="Add random jitter to retry delays")

    # Bulkhead Settings
    bulkhead_enabled: bool = Field(default=True, description="Enable bulkhead pattern for resource isolation")
    bulkhead_max_concurrent: int = Field(default=10, description="Maximum concurrent requests per service")
    bulkhead_queue_size: int = Field(default=5, description="Maximum queued requests when at capacity")
    bulkhead_timeout: float = Field(default=5.0, description="Timeout waiting for bulkhead slot in seconds")

    # Health Check Settings
    health_check_enabled: bool = Field(default=True, description="Enable health-aware routing")
    health_check_interval: int = Field(default=10, description="Seconds between health checks")
    health_unhealthy_threshold: int = Field(default=3, description="Consecutive failures before marking unhealthy")
    health_healthy_threshold: int = Field(default=2, description="Consecutive successes before marking healthy")

    # Service Timeout Settings
    service_timeout_default: float = Field(default=30.0, description="Default service timeout in seconds")
    service_timeout_mesh: float = Field(default=30.0, description="Mesh gateway timeout in seconds")
    service_timeout_agent: float = Field(default=30.0, description="Agent service timeout in seconds")
    service_timeout_health: float = Field(default=5.0, description="Health check timeout in seconds")

    # Authentication Configuration
    jwt_secret_key: str = Field(default="dev-secret-key-change-in-production", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(default=30, description="Access token expiration in minutes")
    jwt_refresh_token_expire_days: int = Field(default=7, description="Refresh token expiration in days")
    api_key_header: str = Field(default="X-API-Key", description="API key header name")
    require_auth: bool = Field(default=False, description="Require authentication for all endpoints")

    # TLS/HTTPS Configuration
    tls_enabled: bool = Field(default=False, description="Enable TLS/HTTPS")
    tls_cert_file: str = Field(default="./certs/cert.pem", description="Path to TLS certificate file")
    tls_key_file: str = Field(default="./certs/key.pem", description="Path to TLS private key file")
    tls_ca_file: Optional[str] = Field(default=None, description="Path to TLS CA certificate file (for client cert verification)")
    tls_verify_client: bool = Field(default=False, description="Require and verify client certificates (mTLS)")
    tls_min_version: str = Field(default="TLSv1.2", description="Minimum TLS version (TLSv1.2 or TLSv1.3)")
    tls_ciphers: Optional[str] = Field(default=None, description="Custom TLS cipher suite (None = secure defaults)")

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Number of requests allowed per window")
    rate_limit_window: int = Field(default=60, description="Time window in seconds for rate limiting")
    rate_limit_strategy: str = Field(default="sliding_window", description="Rate limit strategy: 'fixed_window', 'sliding_window', or 'token_bucket'")
    rate_limit_per_ip: bool = Field(default=True, description="Apply rate limiting per IP address")
    rate_limit_per_user: bool = Field(default=True, description="Apply rate limiting per authenticated user")
    rate_limit_burst: int = Field(default=20, description="Burst size for token bucket strategy")
    rate_limit_exclude_paths: list = Field(default_factory=lambda: ["/health", "/metrics"], description="Paths to exclude from rate limiting")

    # Audit Logging Configuration
    audit_enabled: bool = Field(default=True, description="Enable comprehensive audit logging")
    audit_log_requests: bool = Field(default=True, description="Log all API requests")
    audit_log_responses: bool = Field(default=True, description="Log all API responses")
    audit_encrypt_sensitive: bool = Field(default=True, description="Encrypt sensitive fields in audit logs")
    audit_retention_days: int = Field(default=365, description="Default audit log retention period in days")
    audit_retention_auth_days: int = Field(default=90, description="Retention for authentication events")
    audit_retention_data_days: int = Field(default=2555, description="Retention for data modification events (7 years)")
    audit_retention_security_days: int = Field(default=730, description="Retention for security events (2 years)")
    audit_collect_geo: bool = Field(default=False, description="Collect geolocation data (requires external service)")
    audit_max_field_size: int = Field(default=65536, description="Maximum size for request/response fields (64KB)")
    audit_sensitive_fields: list = Field(
        default_factory=lambda: ["password", "token", "api_key", "secret", "credential", "authorization"],
        description="Field names to always encrypt"
    )
    audit_batch_size: int = Field(default=100, description="Batch size for bulk audit log writes")
    audit_async_write: bool = Field(default=True, description="Write audit logs asynchronously")

    # Encryption Configuration
    encryption_enabled: bool = Field(default=True, description="Enable encryption at rest for sensitive data")
    encryption_master_key: str = Field(
        default="change-this-master-key-in-production-min-32-chars-required",
        description="Master encryption key (KEK) - USE KMS IN PRODUCTION"
    )
    encryption_key_version: int = Field(default=1, description="Current encryption key version")
    encryption_key_rotation_days: int = Field(default=90, description="Days before key rotation is recommended")
    encryption_salt: Optional[str] = Field(default=None, description="Base64-encoded salt for key derivation")
    encryption_algorithm: str = Field(default="AES-256-GCM", description="Encryption algorithm")

    # LLM Provider Configuration
    llm_provider: str = Field(default="ollama", description="Primary LLM provider: 'openai', 'anthropic', 'deepseek', 'ollama', or 'local'")

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="OpenAI model to use")
    openai_max_tokens: int = Field(default=4096, description="OpenAI max tokens")
    openai_temperature: float = Field(default=0.7, description="OpenAI temperature")
    openai_timeout: int = Field(default=60, description="OpenAI API timeout in seconds")

    # Anthropic Configuration
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    anthropic_model: str = Field(default="claude-3-5-sonnet-20241022", description="Anthropic model to use")
    anthropic_max_tokens: int = Field(default=4096, description="Anthropic max tokens")
    anthropic_temperature: float = Field(default=0.7, description="Anthropic temperature")
    anthropic_timeout: int = Field(default=60, description="Anthropic API timeout in seconds")

    # DeepSeek Configuration
    deepseek_api_key: Optional[str] = Field(default=None, description="DeepSeek API key")
    deepseek_model: str = Field(default="deepseek-chat", description="DeepSeek model to use")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", description="DeepSeek API base URL")
    deepseek_max_tokens: int = Field(default=4096, description="DeepSeek max tokens")
    deepseek_temperature: float = Field(default=0.7, description="DeepSeek temperature")
    deepseek_timeout: int = Field(default=60, description="DeepSeek API timeout in seconds")

    # Ollama Configuration (Local/Open-Source LLMs)
    ollama_base_url: str = Field(default="http://ollama:11434", description="Ollama server URL")
    ollama_model: str = Field(default="phi3:mini", description="Ollama model to use (phi3:mini, llama3.2, mistral, etc.)")
    ollama_max_tokens: int = Field(default=4096, description="Ollama max tokens")
    ollama_temperature: float = Field(default=0.7, description="Ollama temperature")
    ollama_timeout: int = Field(default=120, description="Ollama API timeout in seconds")

    # Local Model Configuration (Standalone GGUF files)
    local_model_path: str = Field(default="./models", description="Path to local models directory")
    local_model_name: str = Field(default="phi3-mini", description="Local model name (subdirectory in models/)")
    local_model_file: str = Field(default="model.gguf", description="Model file name within model directory")
    local_max_tokens: int = Field(default=4096, description="Local model max tokens")
    local_temperature: float = Field(default=0.7, description="Local model temperature")
    local_context_size: int = Field(default=4096, description="Local model context window size")
    local_gpu_layers: int = Field(default=0, description="Number of layers to offload to GPU (0=CPU only)")

    # OpenTelemetry / Distributed Tracing Configuration
    otel_enabled: bool = Field(default=True, description="Enable OpenTelemetry distributed tracing")
    otel_service_name: str = Field(default="biowerk", description="OpenTelemetry service name")
    otel_exporter_type: str = Field(default="otlp", description="Exporter type: 'otlp', 'jaeger', 'console', or 'none'")
    otel_exporter_endpoint: str = Field(default="http://jaeger:4317", description="OTLP/Jaeger collector endpoint")
    otel_exporter_protocol: str = Field(default="grpc", description="OTLP protocol: 'grpc' or 'http/protobuf'")
    otel_sampling_ratio: float = Field(default=1.0, description="Trace sampling ratio (0.0-1.0, 1.0=100%)")
    otel_log_correlation: bool = Field(default=True, description="Enable trace context in logs")
    otel_export_timeout: int = Field(default=30, description="Span export timeout in seconds")
    otel_max_queue_size: int = Field(default=2048, description="Maximum queue size for spans")
    otel_max_export_batch_size: int = Field(default=512, description="Maximum batch size for span export")
    otel_instrument_db: bool = Field(default=True, description="Instrument database calls")
    otel_instrument_http: bool = Field(default=True, description="Instrument HTTP calls")
    otel_instrument_redis: bool = Field(default=True, description="Instrument Redis calls")

    # Health Check Configuration (Enhanced)
    health_enabled: bool = Field(default=True, description="Enable /health and /ready endpoints")
    health_check_db: bool = Field(default=True, description="Include database checks in health endpoints")
    health_check_redis: bool = Field(default=True, description="Include Redis checks in health endpoints")
    health_check_dependencies: bool = Field(default=True, description="Check external service dependencies")
    health_check_timeout: float = Field(default=5.0, description="Timeout for health checks in seconds")
    health_startup_grace_period: int = Field(default=30, description="Grace period for startup health checks in seconds")

    # Token Budget & Cost Tracking Configuration
    budget_enabled: bool = Field(default=True, description="Enable token budget enforcement")
    budget_cost_tracking: bool = Field(default=True, description="Track costs for all LLM requests")
    budget_enforce_limits: bool = Field(default=True, description="Enforce budget limits (vs. tracking only)")
    budget_auto_fallback: bool = Field(default=True, description="Enable automatic model fallback")
    budget_default_fallback_provider: str = Field(default="deepseek", description="Default fallback provider")
    budget_default_fallback_model: str = Field(default="deepseek-chat", description="Default fallback model")
    budget_spike_detection: bool = Field(default=True, description="Enable cost spike detection")
    budget_spike_multiplier: float = Field(default=3.0, description="Cost spike threshold multiplier")
    budget_spike_window_hours: int = Field(default=1, description="Window for spike detection (hours)")
    budget_auto_reset: bool = Field(default=True, description="Automatically reset budgets at period boundaries")
    budget_alert_dedup_hours: int = Field(default=1, description="Hours to deduplicate similar alerts")

    # Default Budget Limits (if no budget configured)
    budget_default_enabled: bool = Field(default=False, description="Enable default global budget")
    budget_default_limit_type: str = Field(default="cost", description="Default limit type (cost or tokens)")
    budget_default_limit_period: str = Field(default="monthly", description="Default limit period")
    budget_default_limit_value: float = Field(default=100.0, description="Default budget limit value")
    budget_default_warning_threshold: float = Field(default=0.8, description="Warning threshold (0.0-1.0)")
    budget_default_critical_threshold: float = Field(default=0.95, description="Critical threshold (0.0-1.0)")

    # Cost Optimization
    budget_prefer_cheaper: bool = Field(default=False, description="Prefer cheaper models when possible")
    budget_max_cost_per_request: Optional[float] = Field(default=None, description="Maximum cost per request (USD)")

    # Admin Override
    budget_admin_bypass: bool = Field(default=True, description="Allow admins to bypass budgets")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def postgres_url(self) -> str:
        """Generate PostgreSQL connection URL."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def postgres_url_sync(self) -> str:
        """Generate synchronous PostgreSQL connection URL for Alembic."""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def mongo_url(self) -> str:
        """Generate MongoDB connection URL."""
        if self.mongo_user and self.mongo_password:
            return f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}/{self.mongo_db}?authSource=admin"
        return f"mongodb://{self.mongo_host}:{self.mongo_port}/{self.mongo_db}"

    @property
    def redis_url(self) -> str:
        """Generate Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# Global settings instance
settings = Settings()
