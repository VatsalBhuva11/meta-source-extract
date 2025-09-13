"""
Pytest configuration and shared fixtures for all tests.
"""
import pytest
import asyncio
import os
import tempfile
from unittest.mock import Mock, patch
from datetime import datetime, timezone

# Set test environment variables
os.environ["GITHUB_TOKEN"] = "test_token"
os.environ["METADATA_DIR"] = "extracted_metadata"
os.environ["METADATA_UPLOAD_TO_S3"] = "false"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["SCHEMA_VERSION"] = "1"
os.environ["GITHUB_API_PER_PAGE"] = "100"
os.environ["DEFAULT_USER_AGENT"] = "test-agent"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_github_token():
    """Mock GitHub token for testing."""
    return "test_token"


@pytest.fixture
def mock_github_repo():
    """Mock GitHub repository for testing."""
    repo = Mock()
    repo.full_name = "test/repo"
    repo.html_url = "https://github.com/test/repo"
    repo.description = "Test repository"
    repo.language = "Python"
    repo.stargazers_count = 100
    repo.forks_count = 50
    repo.open_issues_count = 10
    repo.created_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    repo.updated_at = datetime(2023, 12, 1, tzinfo=timezone.utc)
    repo.default_branch = "main"
    repo.fork = False
    repo.get_languages.return_value = {"Python": 1000, "JavaScript": 500}
    repo.get_license.return_value = Mock(license=Mock(spdx_id="MIT"))
    return repo


@pytest.fixture
def mock_github_commits():
    """Mock GitHub commits for testing."""
    commits = []
    for i in range(5):
        commit = Mock()
        commit.sha = f"abc{i:03d}"
        commit.commit.message = f"Test commit {i}"
        commit.commit.author.name = "testuser"
        commit.commit.author.date = datetime(2023, 1, i+1, tzinfo=timezone.utc)
        commit.html_url = f"https://github.com/test/repo/commit/abc{i:03d}"
        commit.stats = Mock()
        commit.stats.additions = 10 + i
        commit.stats.deletions = 5 + i
        commit.files = []
        commits.append(commit)
    return commits


@pytest.fixture
def mock_github_issues():
    """Mock GitHub issues for testing."""
    issues = []
    for i in range(3):
        issue = Mock()
        issue.number = i + 1
        issue.title = f"Test issue {i + 1}"
        issue.state = "open" if i % 2 == 0 else "closed"
        issue.user.login = "testuser"
        issue.labels = [Mock(name="bug"), Mock(name="enhancement")]
        issue.created_at = datetime(2023, 1, i+1, tzinfo=timezone.utc)
        issue.closed_at = datetime(2023, 1, i+2, tzinfo=timezone.utc) if i % 2 == 1 else None
        issue.html_url = f"https://github.com/test/repo/issues/{i+1}"
        issues.append(issue)
    return issues


@pytest.fixture
def mock_github_contributors():
    """Mock GitHub contributors for testing."""
    contributors = []
    for i in range(3):
        contributor = Mock()
        contributor.login = f"user{i+1}"
        contributor.contributions = 100 - (i * 20)
        contributor.html_url = f"https://github.com/user{i+1}"
        contributors.append(contributor)
    return contributors


@pytest.fixture
def mock_s3_client():
    """Mock S3 client for testing."""
    s3_client = Mock()
    s3_client.upload_file.return_value = None
    return s3_client


@pytest.fixture
def mock_boto3():
    """Mock boto3 for testing."""
    with patch('app.activities.boto3') as mock_boto3:
        mock_boto3.client.return_value = Mock()
        yield mock_boto3


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "repository": "test/repo",
        "url": "https://github.com/test/repo",
        "description": "Test repository",
        "stars": 100,
        "forks": 50,
        "open_issues": 10,
        "primary_language": "Python",
        "created_at": "2023-01-01T00:00:00Z",
        "last_updated": "2023-12-01T00:00:00Z",
        "default_branch": "main",
        "license": "MIT",
        "is_fork": False,
        "languages": {"Python": 1000, "JavaScript": 500},
        "extraction_provenance": {
            "extraction_id": "test123",
            "extracted_by": "github-metadata-extractor",
            "extracted_at": "2023-12-01T00:00:00Z",
            "schema_version": "1",
            "source": "github"
        }
    }


@pytest.fixture
def sample_workflow_config():
    """Sample workflow configuration for testing."""
    return {
        "repo_url": "https://github.com/test/repo",
        "commit_limit": 50,
        "issues_limit": 30,
        "pr_limit": 20,
        "selections": {
            "repository": True,
            "commits": True,
            "issues": True,
            "pull_requests": False,
            "contributors": True,
            "dependencies": False,
            "fork_lineage": False,
            "commit_lineage": False,
            "bus_factor": False,
            "pr_metrics": False,
            "issue_metrics": False,
            "commit_activity": False,
            "release_cadence": False
        }
    }


@pytest.fixture
def sample_frontend_request():
    """Sample frontend request for testing."""
    return {
        "repoUrl": "https://github.com/test/repo",
        "commitLimit": 50,
        "issuesLimit": 30,
        "prLimit": 20,
        "selections": {
            "repository": True,
            "commits": True,
            "issues": True,
            "pullRequests": False,
            "contributors": True,
            "dependencies": False,
            "forkLineage": False,
            "commitLineage": False,
            "busFactor": False,
            "prMetrics": False,
            "issueMetrics": False,
            "commitActivity": False,
            "releaseCadence": False
        }
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "component: mark test as a component test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on file location."""
    for item in items:
        # Add markers based on file location
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "component" in str(item.fspath):
            item.add_marker(pytest.mark.component)
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Add slow marker for tests that might be slow
        if "integration" in str(item.fspath) or "component" in str(item.fspath):
            item.add_marker(pytest.mark.slow)
