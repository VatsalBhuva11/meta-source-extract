"""
Component tests for GitHubMetadataActivities.
Tests the integration between activities and external services.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from app.activities import GitHubMetadataActivities


class TestActivitiesComponent:
    """Component tests for GitHubMetadataActivities."""

    @pytest.fixture
    def activities(self):
        """Create activities instance with mocked external dependencies."""
        with patch('app.activities.Github'), \
             patch('app.activities.boto3'), \
             patch('os.makedirs'):
            return GitHubMetadataActivities()

    @pytest.fixture
    def mock_github_repo(self):
        """Create mock GitHub repository with realistic data."""
        repo = Mock()
        repo.full_name = "facebook/react"
        repo.html_url = "https://github.com/facebook/react"
        repo.description = "A declarative, efficient, and flexible JavaScript library"
        repo.language = "JavaScript"
        repo.stargazers_count = 200000
        repo.forks_count = 40000
        repo.open_issues_count = 100
        repo.created_at = datetime(2013, 5, 24, tzinfo=timezone.utc)
        repo.updated_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        repo.default_branch = "main"
        repo.fork = False
        
        # Mock languages
        repo.get_languages.return_value = {
            "JavaScript": 1000000,
            "TypeScript": 500000,
            "CSS": 100000
        }
        
        # Mock license
        license_mock = Mock()
        license_mock.license = Mock(spdx_id="MIT")
        repo.get_license.return_value = license_mock
        
        return repo

    @pytest.fixture
    def mock_github_commits(self):
        """Create mock GitHub commits with realistic data."""
        commits = []
        for i in range(5):
            commit = Mock()
            commit.sha = f"abc{i:03d}"
            commit.commit.message = f"Commit message {i}"
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
    def mock_github_issues(self):
        """Create mock GitHub issues with realistic data."""
        issues = []
        for i in range(3):
            issue = Mock()
            issue.number = i + 1
            issue.title = f"Issue {i + 1}"
            issue.state = "open" if i % 2 == 0 else "closed"
            issue.user.login = "testuser"
            issue.labels = [Mock(name="bug"), Mock(name="enhancement")]
            issue.created_at = datetime(2023, 1, i+1, tzinfo=timezone.utc)
            issue.closed_at = datetime(2023, 1, i+2, tzinfo=timezone.utc) if i % 2 == 1 else None
            issue.html_url = f"https://github.com/test/repo/issues/{i+1}"
            issues.append(issue)
        return issues

    @pytest.fixture
    def mock_github_contributors(self):
        """Create mock GitHub contributors with realistic data."""
        contributors = []
        for i in range(3):
            contributor = Mock()
            contributor.login = f"user{i+1}"
            contributor.contributions = 100 - (i * 20)
            contributor.html_url = f"https://github.com/user{i+1}"
            contributors.append(contributor)
        return contributors

    @pytest.mark.asyncio
    async def test_repository_metadata_extraction_integration(self, activities, mock_github_repo):
        """Test repository metadata extraction with real GitHub API integration."""
        with patch.object(activities, '_get_repo', return_value=mock_github_repo):
            result = await activities.extract_repository_metadata([
                "https://github.com/facebook/react",
                "test123"
            ])
            
            assert result["repository"] == "facebook/react"
            assert result["url"] == "https://github.com/facebook/react"
            assert result["description"] == "A declarative, efficient, and flexible JavaScript library"
            assert result["primary_language"] == "JavaScript"
            assert result["stars"] == 200000
            assert result["forks"] == 40000
            assert result["open_issues"] == 100
            assert result["license"] == "MIT"
            assert result["is_fork"] is False
            assert result["languages"] == {
                "JavaScript": 1000000,
                "TypeScript": 500000,
                "CSS": 100000
            }
            assert "extraction_provenance" in result

    @pytest.mark.asyncio
    async def test_commit_metadata_extraction_integration(self, activities, mock_github_commits):
        """Test commit metadata extraction with real GitHub API integration."""
        mock_repo = Mock()
        mock_repo.get_commits.return_value = mock_github_commits
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_commit_metadata([
                "https://github.com/test/repo",
                50,
                "test123"
            ])
            
            assert len(result) == 5
            assert result[0]["sha"] == "abc000"
            assert result[0]["message"] == "Commit message 0"
            assert result[0]["author"] == "testuser"
            assert result[0]["additions"] == 10
            assert result[0]["deletions"] == 5
            assert "url" in result[0]

    @pytest.mark.asyncio
    async def test_issues_metadata_extraction_integration(self, activities, mock_github_issues):
        """Test issues metadata extraction with real GitHub API integration."""
        mock_repo = Mock()
        mock_repo.get_issues.return_value = mock_github_issues
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_issues_metadata([
                "https://github.com/test/repo",
                30,
                "test123"
            ])
            
            assert len(result) == 3
            assert result[0]["number"] == 1
            assert result[0]["title"] == "Issue 1"
            assert result[0]["state"] == "open"
            assert result[0]["author"] == "testuser"
            assert "bug" in result[0]["labels"]
            assert "enhancement" in result[0]["labels"]
            assert "url" in result[0]

    @pytest.mark.asyncio
    async def test_contributors_extraction_integration(self, activities, mock_github_contributors):
        """Test contributors extraction with real GitHub API integration."""
        mock_repo = Mock()
        mock_repo.get_contributors.return_value = mock_github_contributors
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_contributors([
                "https://github.com/test/repo",
                "test123"
            ])
            
            assert len(result) == 3
            assert result[0]["login"] == "user1"
            assert result[0]["contributions"] == 100
            assert result[0]["url"] == "https://github.com/user1"

    @pytest.mark.asyncio
    async def test_dependencies_extraction_integration(self, activities):
        """Test dependencies extraction with real file content integration."""
        mock_repo = Mock()
        
        # Mock file content for package.json
        package_json_content = '{"dependencies": {"react": "^18.0.0", "lodash": "^4.17.21"}}'
        mock_file = Mock()
        mock_file.decoded_content = package_json_content.encode()
        mock_repo.get_contents.return_value = mock_file
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_dependencies_from_repo([
                "https://github.com/test/repo",
                "test123"
            ])
            
            assert len(result) == 1
            assert result[0]["manifest"] == "package.json"
            assert len(result[0]["dependencies"]) == 2
            assert any(dep["name"] == "react" for dep in result[0]["dependencies"])
            assert any(dep["name"] == "lodash" for dep in result[0]["dependencies"])

    @pytest.mark.asyncio
    async def test_fork_lineage_extraction_integration(self, activities):
        """Test fork lineage extraction with real GitHub API integration."""
        mock_repo = Mock()
        mock_repo.fork = True
        mock_repo.parent = Mock()
        mock_repo.parent.full_name = "original/repo"
        mock_repo.parent.html_url = "https://github.com/original/repo"
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_fork_lineage([
                "https://github.com/test/repo",
                "test123"
            ])
            
            assert result["is_fork"] is True
            assert result["parent_repository"] == "original/repo"
            assert result["parent_url"] == "https://github.com/original/repo"

    @pytest.mark.asyncio
    async def test_commit_lineage_extraction_integration(self, activities):
        """Test commit lineage extraction with real GitHub API integration."""
        mock_repo = Mock()
        
        # Mock commit with parents
        mock_commit = Mock()
        mock_commit.parents = [Mock(sha="parent1"), Mock(sha="parent2")]
        mock_commit.files = [
            Mock(filename="file1.py", additions=10, deletions=5),
            Mock(filename="file2.js", additions=20, deletions=10)
        ]
        
        mock_repo.get_commit.return_value = mock_commit
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_commit_lineage([
                "https://github.com/test/repo",
                [{"sha": "abc123", "author": "testuser", "date": "2023-01-01T00:00:00Z"}],
                "test123"
            ])
            
            assert "file_lineage_summary" in result
            assert "total_files_analyzed" in result
            assert "total_commits_analyzed" in result

    @pytest.mark.asyncio
    async def test_bus_factor_extraction_integration(self, activities, mock_github_contributors):
        """Test bus factor extraction with real GitHub API integration."""
        mock_repo = Mock()
        mock_repo.get_contributors.return_value = mock_github_contributors
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_bus_factor([
                "https://github.com/test/repo",
                "test123"
            ])
            
            assert "top1_pct" in result
            assert "top3_pct" in result
            assert "top10_pct" in result
            assert "bus_factor" in result
            assert "top_contributors" in result

    @pytest.mark.asyncio
    async def test_pr_metrics_extraction_integration(self, activities):
        """Test PR metrics extraction with real GitHub API integration."""
        mock_repo = Mock()
        
        # Mock PRs with different states
        mock_prs = []
        for i in range(5):
            pr = Mock()
            pr.number = i + 1
            pr.merged = i % 2 == 0
            pr.created_at = datetime(2023, 1, i+1, tzinfo=timezone.utc)
            pr.merged_at = datetime(2023, 1, i+2, tzinfo=timezone.utc) if pr.merged else None
            pr.closed_at = datetime(2023, 1, i+2, tzinfo=timezone.utc) if not pr.merged else None
            mock_prs.append(pr)
        
        mock_repo.get_pulls.return_value = mock_prs
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_pr_metrics([
                "https://github.com/test/repo",
                mock_prs,
                "test123"
            ])
            
            assert "merge_rate" in result
            assert "avg_merge_time_seconds" in result
            assert "avg_close_time_seconds" in result
            assert "total_prs" in result
            assert "merged_prs" in result

    @pytest.mark.asyncio
    async def test_issue_metrics_extraction_integration(self, activities, mock_github_issues):
        """Test issue metrics extraction with real GitHub API integration."""
        with patch.object(activities, '_get_repo', return_value=Mock()):
            result = await activities.extract_issue_metrics([
                "https://github.com/test/repo",
                mock_github_issues,
                "test123"
            ])
            
            assert "closure_rate" in result
            assert "avg_resolution_time_seconds" in result
            assert "total_issues" in result
            assert "closed_issues" in result

    @pytest.mark.asyncio
    async def test_commit_activity_extraction_integration(self, activities, mock_github_commits):
        """Test commit activity extraction with real GitHub API integration."""
        with patch.object(activities, '_get_repo', return_value=Mock()):
            result = await activities.extract_commit_activity([
                "https://github.com/test/repo",
                mock_github_commits,
                "test123"
            ])
            
            assert "per_week" in result
            assert "per_author" in result
            assert "total_commits" in result
            assert "unique_authors" in result

    @pytest.mark.asyncio
    async def test_release_cadence_extraction_integration(self, activities):
        """Test release cadence extraction with real GitHub API integration."""
        mock_repo = Mock()
        
        # Mock tags
        mock_tags = []
        for i in range(10):
            tag = Mock()
            tag.name = f"v1.{i}.0"
            tag.commit.sha = f"tag{i:03d}"
            tag.commit.commit.author.date = datetime(2023, 1, i+1, tzinfo=timezone.utc)
            mock_tags.append(tag)
        
        mock_repo.get_tags.return_value = mock_tags
        
        with patch.object(activities, '_get_repo', return_value=mock_repo):
            result = await activities.extract_release_cadence([
                "https://github.com/test/repo",
                "test123"
            ])
            
            assert "tag_count_100" in result
            assert "tag_count_365" in result
            assert "avg_days_between_tags" in result
            assert "latest_tag" in result

    @pytest.mark.asyncio
    async def test_save_metadata_integration(self, activities):
        """Test save metadata integration with file system and S3."""
        metadata = {"test": "data"}
        repo_url = "https://github.com/test/repo"
        extraction_id = "test123"
        
        with patch('aiofiles.open', AsyncMock()) as mock_open, \
             patch('json.dumps', return_value='{"test": "data"}') as mock_json, \
             patch('app.config.METADATA_UPLOAD_TO_S3', True), \
             patch('app.config.S3_BUCKET', 'test-bucket'):
            
            result = await activities.save_metadata_to_file([
                metadata, repo_url, extraction_id
            ])
            
            assert result.startswith("s3://")
            assert "test-bucket" in result
            mock_open.assert_called_once()
            mock_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_extraction_summary_integration(self, activities):
        """Test extraction summary generation integration."""
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
        
        result = await activities.get_extraction_summary([
            "https://github.com/test/repo",
            metadata,
            "test123"
        ])
        
        assert result["repository"] == "test/repo"
        assert result["commits_count"] == 2
        assert result["issues_count"] == 1
        assert result["prs_count"] == 2
        assert result["contributors_count"] == 1
        assert result["dependencies_count"] == 1
        assert result["stars"] == 100
        assert result["forks"] == 50
        assert "extracted_at" in result

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, activities):
        """Test error handling integration across activities."""
        # Test with invalid repository URL
        with pytest.raises(ValueError):
            await activities.extract_repository_metadata([
                "https://invalid-url",
                "test123"
            ])
        
        # Test with GitHub API error
        with patch.object(activities, '_get_repo', side_effect=Exception("GitHub API Error")):
            with pytest.raises(Exception):
                await activities.extract_repository_metadata([
                    "https://github.com/test/repo",
                    "test123"
                ])

    @pytest.mark.asyncio
    async def test_caching_integration(self, activities):
        """Test caching integration across activities."""
        # First call should hit GitHub API
        with patch.object(activities, '_get_repo', return_value=Mock()) as mock_get_repo:
            result1 = await activities.extract_repository_metadata([
                "https://github.com/test/repo",
                "test123"
            ])
            mock_get_repo.assert_called_once()
        
        # Second call should use cache
        with patch.object(activities, '_get_repo', return_value=Mock()) as mock_get_repo:
            result2 = await activities.extract_repository_metadata([
                "https://github.com/test/repo",
                "test123"
            ])
            mock_get_repo.assert_not_called()
        
        # Results should be the same
        assert result1 == result2
