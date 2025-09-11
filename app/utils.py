import re
import uuid
from datetime import timezone
from typing import Tuple
from urllib.parse import urlparse

def parse_repo_url(repo_url: str) -> Tuple[str, str]:
    """
    Parse a GitHub repo URL and return (owner, repo)
    Accepts: https://github.com/owner/repo, git@github.com:owner/repo.git, owner/repo
    """
    if repo_url.startswith("http"):
        parsed = urlparse(repo_url.rstrip("/"))
        host = parsed.netloc.lower()
        if host not in ("github.com", "www.github.com"):
            raise ValueError("Unsupported host; only github.com is allowed")
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError("Malformed GitHub URL")
        owner = parts[-2]
        repo = parts[-1].replace(".git", "")
        return owner, repo
    if repo_url.startswith("git@"):
        m = re.match(r"git@github\.com:([^/]+)/(.+?)(\.git)?$", repo_url)
        if m:
            return m.group(1), m.group(2)
        raise ValueError("Unsupported git SSH URL; only github.com is allowed")
    if "/" in repo_url:
        owner, repo = repo_url.split("/", 1)
        return owner, repo.replace(".git", "")
    raise ValueError("Unsupported repo URL format")

def safe_isoformat(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        return dt
    if hasattr(dt, "isoformat"):
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)

def generate_extraction_id():
    return uuid.uuid4().hex[:12]
