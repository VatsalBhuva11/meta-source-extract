"""
Unit tests for GitHubMetadataActivities class.
Tests individual methods in isolation with mocked dependencies.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone
import json
import os

from app.activities import GitHubMetadataActivities
from app.config import METADATA_DIR


class TestGitHubMetadataActivities:
    """Unit tests for GitHubMetadataActivities class."""

    @pytest.fixture
    def activities(self):
        """Create activities instance with mocked dependencies."""
        with patch('app.activities.Github'), \
             patch('app.activities.boto3'), \
             patch('os.makedirs'):
            return GitHubMetadataActivities()

    @pytest.fixture
    def sample_commit_data(self):
        """Sample commit data for testing."""
        return {
            "sha": "abc123",
            "message": "Test commit message",
            "author": "testuser",
            "date": "2023-01-01T00:00:00Z"
        }

    @pytest.fixture
    def sample_issue_data(self):
        """Sample issue data for testing."""
        return {
            "number": 1,
            "title": "Test Issue",
            "state": "open",
            "author": "testuser",
            "labels": ["bug", "enhancement"],
            "created_at": "2023-01-01T00:00:00Z",
            "closed_at": None,
            "url": "https://github.com/test/repo/issues/1"
        }

    def test_extract_repo_info_from_url_valid(self, activities):
        """Test extracting repo info from valid GitHub URL."""
        owner, repo = activities._extract_repo_info_from_url("https://github.com/facebook/react")
        assert owner == "facebook"
        assert repo == "react"

    def test_extract_repo_info_from_url_with_www(self, activities):
        """Test extracting repo info from URL with www."""
        owner, repo = activities._extract_repo_info_from_url("https://www.github.com/microsoft/vscode")
        assert owner == "microsoft"
        assert repo == "vscode"

    def test_extract_repo_info_from_url_trailing_slash(self, activities):
        """Test extracting repo info from URL with trailing slash."""
        owner, repo = activities._extract_repo_info_from_url("https://github.com/tensorflow/tensorflow/")
        assert owner == "tensorflow"
        assert repo == "tensorflow"

    def test_extract_repo_info_from_url_invalid(self, activities):
        """Test extracting repo info from invalid URL raises error."""
        with pytest.raises(ValueError):
            activities._extract_repo_info_from_url("https://gitlab.com/user/repo")

    def test_extract_repo_info_from_url_malformed(self, activities):
        """Test extracting repo info from malformed URL raises error."""
        with pytest.raises(ValueError):
            activities._extract_repo_info_from_url("https://github.com/user")

    def test_get_filepath(self, activities):
        """Test filepath generation."""
        filepath = activities._get_filepath("facebook", "react", "test123")
        assert "facebook_react_schema1_test123_" in filepath
        assert filepath.endswith(".json")
        assert filepath.startswith(METADATA_DIR)

    def test_safe_call_success(self, activities):
        """Test _safe_call with successful function."""
        result = activities._safe_call(lambda: "success")
        assert result == "success"

    def test_safe_call_exception(self, activities):
        """Test _safe_call with function that raises exception."""
        result = activities._safe_call(lambda: exec("raise ValueError('test')"))
        assert result is None

    def test_paginator_with_limit(self, activities):
        """Test paginator with limit."""
        mock_pager = [
            [1, 2, 3],
            [4, 5, 6],
            [7, 8, 9]
        ]
        result = activities._paginator(iter(mock_pager), limit=5)
        assert result == [1, 2, 3, 4, 5]

    def test_paginator_without_limit(self, activities):
        """Test paginator without limit."""
        mock_pager = [
            [1, 2, 3],
            [4, 5, 6]
        ]
        result = activities._paginator(iter(mock_pager))
        assert result == [1, 2, 3, 4, 5, 6]

    def test_paginator_exception(self, activities):
        """Test paginator with exception."""
        def failing_pager():
            yield [1, 2]
            raise ValueError("test error")
        
        with pytest.raises(ValueError):
            activities._paginator(failing_pager())

    def test_parse_manifest_text_package_json(self, activities):
        """Test parsing package.json manifest."""
        manifest_text = json.dumps({
            "dependencies": {
                "react": "^18.0.0",
                "lodash": "^4.17.21"
            },
            "devDependencies": {
                "jest": "^29.0.0"
            }
        })
        result = activities._parse_manifest_text("package.json", manifest_text)
        assert len(result) == 3
        assert any(dep["name"] == "react" and dep["scope"] == "dependencies" for dep in result)
        assert any(dep["name"] == "jest" and dep["scope"] == "devDependencies" for dep in result)

    def test_parse_manifest_text_requirements_txt(self, activities):
        """Test parsing requirements.txt manifest."""
        manifest_text = """
# This is a comment
requests==2.28.0
numpy>=1.21.0
pandas~=1.4.0
# Another comment
        """.strip()
        result = activities._parse_manifest_text("requirements.txt", manifest_text)
        assert len(result) == 3
        assert any(dep["name"] == "requests" and dep["version"] == "2.28.0" for dep in result)
        assert any(dep["name"] == "numpy" and dep["version"] == "1.21.0" for dep in result)

    def test_parse_manifest_text_pom_xml(self, activities):
        """Test parsing pom.xml manifest."""
        manifest_text = """
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>5.3.0</version>
        </dependency>
        <dependency>
            <groupId>junit</groupId>
            <artifactId>junit</artifactId>
            <version>4.13.2</version>
        </dependency>
        """
        result = activities._parse_manifest_text("pom.xml", manifest_text)
        assert len(result) == 2
        assert any(dep["group"] == "org.springframework" and dep["artifact"] == "spring-core" for dep in result)

    def test_parse_manifest_text_invalid_json(self, activities):
        """Test parsing invalid JSON returns empty list."""
        result = activities._parse_manifest_text("package.json", "invalid json")
        assert result == []

    def test_parse_manifest_text_unknown_format(self, activities):
        """Test parsing unknown manifest format returns empty list."""
        result = activities._parse_manifest_text("unknown.txt", "some content")
        assert result == []

    @pytest.mark.asyncio
    async def test_extract_repository_metadata_success(self, activities):
        """Test successful repository metadata extraction."""
        mock_repo = Mock()
        mock_repo.full_name = "facebook/react"
        mock_repo.html_url = "https://github.com/facebook/react"
        mock_repo.description = "A declarative, efficient, and flexible JavaScript library"
        mock_repo.language = "JavaScript"
        mock_repo.get_languages.return_value = {"JavaScript": 1000, "TypeScript": 500}
        mock_repo.stargazers_count = 200000
        mock_repo.forks_count = 40000
        mock_repo.open_issues_count = 100
        mock_repo.created_at = datetime(2013, 5, 24, tzinfo=timezone.utc)
        mock_repo.updated_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        mock_repo.default_branch = "main"
        mock_repo.fork = False
        mock_repo.get_license.return_value = Mock(license=Mock(spdx_id="MIT"))

        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_repository_metadata(["https://github.com/facebook/react", "test123"])
            
            assert result["repository"] == "facebook/react"
            assert result["url"] == "https://github.com/facebook/react"
            assert result["description"] == "A declarative, efficient, and flexible JavaScript library"
            assert result["primary_language"] == "JavaScript"
            assert result["stars"] == 200000
            assert result["forks"] == 40000
            assert result["open_issues"] == 100
            assert result["license"] == "MIT"
            assert result["is_fork"] is False
            assert "extraction_provenance" in result

    @pytest.mark.asyncio
    async def test_extract_repository_metadata_no_license(self, activities):
        """Test repository metadata extraction when no license."""
        mock_repo = Mock()
        mock_repo.full_name = "test/repo"
        mock_repo.html_url = "https://github.com/test/repo"
        mock_repo.description = None
        mock_repo.language = None
        mock_repo.get_languages.return_value = {}
        mock_repo.stargazers_count = 0
        mock_repo.forks_count = 0
        mock_repo.open_issues_count = 0
        mock_repo.created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        mock_repo.updated_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        mock_repo.default_branch = "main"
        mock_repo.fork = False
        mock_repo.get_license.return_value = None

        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_repository_metadata(["https://github.com/test/repo", "test123"])
            
            assert result["license"] is None
            assert result["description"] is None
            assert result["primary_language"] is None

    @pytest.mark.asyncio
    async def test_extract_repository_metadata_exception(self, activities):
        """Test repository metadata extraction with exception."""
        with patch.object(activities, '_get_repo', side_effect=Exception("API Error")):
            with pytest.raises(Exception):
                await activities.extract_repository_metadata(["https://github.com/test/repo", "test123"])

    @pytest.mark.asyncio
    async def test_save_metadata_to_file_success(self, activities):
        """Test successful metadata saving to file."""
        metadata = {"test": "data"}
        repo_url = "https://github.com/test/repo"
        extraction_id = "test123"

        # Mock aiofiles.open as an async context manager
        mock_file = AsyncMock()
        mock_file.__aenter__ = AsyncMock(return_value=mock_file)
        mock_file.__aexit__ = AsyncMock(return_value=None)
        mock_file.write = AsyncMock()

        with patch('aiofiles.open', return_value=mock_file), \
             patch('json.dumps', return_value='{"test": "data"}') as mock_json:
            
            result = await activities.save_metadata_to_file([metadata, repo_url, extraction_id])
            
            assert result.endswith(".json")
            mock_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_extraction_summary(self, activities):
        """Test extraction summary generation."""
        metadata = {
            "repository": "test/repo",
            "commits": [{"sha": "1"}, {"sha": "2"}],
            "issues": [{"number": 1}],
            "pull_requests": [{"number": 1}, {"number": 2}],
            "contributors": [{"login": "user1"}],
            "dependencies": [{"name": "dep1"}],
            "stars": 100,
            "forks": 50
        }
        
        result = await activities.get_extraction_summary(["https://github.com/test/repo", metadata, "test123"])
        
        assert result["repository"] == "test/repo"
        assert result["commits_count"] == 2
        assert result["issues_count"] == 1
        assert result["prs_count"] == 2
        assert result["contributors_count"] == 1
        assert result["dependencies_count"] == 1
        assert result["stars"] == 100
        assert result["forks"] == 50

    @pytest.mark.asyncio
    async def test_get_extraction_summary_with_metrics(self, activities):
        """Test extraction summary with PR and issue metrics."""
        metadata = {
            "repository": "test/repo",
            "pull_requests": [
                {"merged": True, "created_at": "2023-01-01T00:00:00Z", "merged_at": "2023-01-02T00:00:00Z"},
                {"merged": False, "created_at": "2023-01-01T00:00:00Z", "merged_at": None}
            ],
            "issues": [
                {"closed_at": "2023-01-02T00:00:00Z", "created_at": "2023-01-01T00:00:00Z"},
                {"closed_at": None, "created_at": "2023-01-01T00:00:00Z"}
            ]
        }
        
        result = await activities.get_extraction_summary(["https://github.com/test/repo", metadata, "test123"])
        
        assert result["pr_merge_rate"] == 0.5  # 1 out of 2 merged
        assert result["avg_issue_resolution_seconds"] is not None

    def test_data_directory_creation(self, activities):
        """Test that data directory is created on initialization."""
        assert activities.data_dir == METADATA_DIR
        # Directory creation is mocked in fixture, but we can test the path
        assert activities.data_dir == "extracted_metadata"
