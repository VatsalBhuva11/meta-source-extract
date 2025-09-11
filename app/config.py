import os

APP_NAME = os.getenv("APP_NAME", "github-metadata-extractor")
DEFAULT_PORT = int(os.getenv("PORT", 8000))

# metadata storage
METADATA_DIR = os.getenv("METADATA_DIR", "extracted_metadata")
METADATA_UPLOAD_TO_S3 = os.getenv("METADATA_UPLOAD_TO_S3", "false").lower() in ("1", "true", "yes")
S3_BUCKET = os.getenv("S3_BUCKET")

# schema
SCHEMA_VERSION = os.getenv("SCHEMA_VERSION", "1")

# GitHub / API controls
GITHUB_API_PER_PAGE = int(os.getenv("GITHUB_API_PER_PAGE", 30))
DEFAULT_USER_AGENT = os.getenv("DEFAULT_USER_AGENT", "github-metadata-extractor/1.0")

# workflow defaults
WORKFLOW_DEFAULT_COMMIT_LIMIT = int(os.getenv("WORKFLOW_DEFAULT_COMMIT_LIMIT", 200))
WORKFLOW_DEFAULT_ISSUES_LIMIT = int(os.getenv("WORKFLOW_DEFAULT_ISSUES_LIMIT", 200))
WORKFLOW_DEFAULT_PR_LIMIT = int(os.getenv("WORKFLOW_DEFAULT_PR_LIMIT", 200))
WORKFLOW_ACTIVITY_TIMEOUT_SECONDS = int(os.getenv("WORKFLOW_ACTIVITY_TIMEOUT_SECONDS", 300))

# Resilience settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3"))
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "30"))
CACHE_DEFAULT_TTL = int(os.getenv("CACHE_DEFAULT_TTL", "600"))  # 10 minutes default TTL
