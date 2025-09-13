"""
Unit tests for utility functions.
"""
import pytest
from unittest.mock import patch, Mock
from datetime import datetime, timezone
import uuid

from app.utils import generate_extraction_id, safe_isoformat, parse_repo_url


class TestUtils:
    """Unit tests for utility functions."""

    def test_generate_extraction_id(self):
        """Test extraction ID generation."""
        extraction_id = generate_extraction_id()
        
        # Should be a string
        assert isinstance(extraction_id, str)
        
        # Should be 12 characters long (uuid4().hex[:12])
        assert len(extraction_id) == 12
        
        # Should be alphanumeric
        assert extraction_id.isalnum()
        
        # Should be different each time
        extraction_id2 = generate_extraction_id()
        assert extraction_id != extraction_id2

    def test_safe_isoformat_with_datetime(self):
        """Test safe_isoformat with datetime object."""
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = safe_isoformat(dt)
        
        assert result == "2023-01-01T12:00:00+00:00"

    def test_safe_isoformat_with_none(self):
        """Test safe_isoformat with None."""
        result = safe_isoformat(None)
        assert result is None

    def test_safe_isoformat_with_string(self):
        """Test safe_isoformat with string."""
        result = safe_isoformat("2023-01-01T12:00:00Z")
        assert result == "2023-01-01T12:00:00Z"

    def test_safe_isoformat_with_invalid_type(self):
        """Test safe_isoformat with invalid type."""
        result = safe_isoformat(123)
        assert result == "123"  # Should convert to string

    def test_parse_repo_url_valid(self):
        """Test parsing valid GitHub URL."""
        owner, repo = parse_repo_url("https://github.com/facebook/react")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_with_www(self):
        """Test parsing URL with www."""
        owner, repo = parse_repo_url("https://www.github.com/microsoft/vscode")
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_parse_repo_url_with_trailing_slash(self):
        """Test parsing URL with trailing slash."""
        owner, repo = parse_repo_url("https://github.com/tensorflow/tensorflow/")
        assert owner == "tensorflow"
        assert repo == "tensorflow"

    def test_parse_repo_url_with_dot_git(self):
        """Test parsing URL with .git extension."""
        owner, repo = parse_repo_url("https://github.com/facebook/react.git")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_invalid_host(self):
        """Test parsing URL with invalid host."""
        with pytest.raises(ValueError, match="Unsupported host; only github.com is allowed"):
            parse_repo_url("https://gitlab.com/user/repo")

    def test_parse_repo_url_malformed(self):
        """Test parsing malformed URL."""
        with pytest.raises(ValueError, match="Malformed GitHub URL"):
            parse_repo_url("https://github.com/user")

    def test_parse_repo_url_insufficient_parts(self):
        """Test parsing URL with insufficient parts."""
        with pytest.raises(ValueError, match="Malformed GitHub URL"):
            parse_repo_url("https://github.com")

    def test_parse_repo_url_http(self):
        """Test parsing HTTP URL."""
        owner, repo = parse_repo_url("http://github.com/facebook/react")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_with_subdomain(self):
        """Test parsing URL with subdomain."""
        owner, repo = parse_repo_url("https://github.com/facebook/react")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_with_query_params(self):
        """Test parsing URL with query parameters."""
        owner, repo = parse_repo_url("https://github.com/facebook/react?tab=repositories")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_with_fragment(self):
        """Test parsing URL with fragment."""
        owner, repo = parse_repo_url("https://github.com/facebook/react#readme")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_empty_string(self):
        """Test parsing empty string."""
        with pytest.raises(ValueError, match="Unsupported repo URL format"):
            parse_repo_url("")

    def test_parse_repo_url_none(self):
        """Test parsing None."""
        with pytest.raises(AttributeError):
            parse_repo_url(None)

    def test_parse_repo_url_git_ssh(self):
        """Test parsing git SSH URL."""
        owner, repo = parse_repo_url("git@github.com:facebook/react.git")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_git_ssh_without_git(self):
        """Test parsing git SSH URL without .git extension."""
        owner, repo = parse_repo_url("git@github.com:facebook/react")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_simple_format(self):
        """Test parsing simple owner/repo format."""
        owner, repo = parse_repo_url("facebook/react")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_simple_format_with_git(self):
        """Test parsing simple owner/repo.git format."""
        owner, repo = parse_repo_url("facebook/react.git")
        assert owner == "facebook"
        assert repo == "react"

    def test_parse_repo_url_invalid_git_ssh(self):
        """Test parsing invalid git SSH URL."""
        with pytest.raises(ValueError, match="Unsupported git SSH URL; only github.com is allowed"):
            parse_repo_url("git@gitlab.com:user/repo.git")
