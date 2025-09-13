"""
Integration tests for the complete GitHub metadata extractor.
Tests the full end-to-end flow from frontend request to final output.
"""
import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from app.workflow import GitHubMetadataWorkflow
from app.activities import GitHubMetadataActivities


class TestIntegration:
    """Integration tests for the complete system."""

    @pytest.fixture
    def mock_github_data(self):
        """Mock GitHub data for integration testing."""
        return {
            "repo": {
                "full_name": "facebook/react",
                "html_url": "https://github.com/facebook/react",
                "description": "A declarative, efficient, and flexible JavaScript library",
                "language": "JavaScript",
                "stargazers_count": 200000,
                "forks_count": 40000,
                "open_issues_count": 100,
                "created_at": datetime(2013, 5, 24, tzinfo=timezone.utc),
                "updated_at": datetime(2023, 1, 1, tzinfo=timezone.utc),
                "default_branch": "main",
                "fork": False,
                "get_languages.return_value": {
                    "JavaScript": 1000000,
                    "TypeScript": 500000,
                    "CSS": 100000
                },
                "get_license.return_value": Mock(license=Mock(spdx_id="MIT"))
            },
            "commits": [
                {
                    "sha": "abc123",
                    "message": "Initial commit",
                    "author": "testuser",
                    "date": "2023-01-01T00:00:00Z",
                    "url": "https://github.com/test/repo/commit/abc123"
                },
                {
                    "sha": "def456",
                    "message": "Add feature",
                    "author": "testuser",
                    "date": "2023-01-02T00:00:00Z",
                    "url": "https://github.com/test/repo/commit/def456"
                }
            ],
            "issues": [
                {
                    "number": 1,
                    "title": "Bug report",
                    "state": "open",
                    "author": "testuser",
                    "labels": ["bug"],
                    "created_at": "2023-01-01T00:00:00Z",
                    "closed_at": None,
                    "url": "https://github.com/test/repo/issues/1"
                }
            ],
            "pull_requests": [
                {
                    "number": 1,
                    "title": "Feature PR",
                    "state": "merged",
                    "author": "testuser",
                    "created_at": "2023-01-01T00:00:00Z",
                    "merged_at": "2023-01-02T00:00:00Z",
                    "url": "https://github.com/test/repo/pull/1"
                }
            ],
            "contributors": [
                {
                    "login": "testuser",
                    "contributions": 100,
                    "url": "https://github.com/testuser"
                }
            ],
            "dependencies": [
                {
                    "manifest": "package.json",
                    "dependencies": [
                        {"name": "react", "version": "^18.0.0"},
                        {"name": "lodash", "version": "^4.17.21"}
                    ]
                }
            ]
        }

    @pytest.fixture
    def sample_frontend_request(self):
        """Sample frontend request."""
        return {
            "repoUrl": "https://github.com/facebook/react",
            "commitLimit": 50,
            "issuesLimit": 30,
            "prLimit": 20,
            "selections": {
                "repository": True,
                "commits": True,
                "issues": True,
                "pullRequests": True,
                "contributors": True,
                "dependencies": True,
                "forkLineage": False,
                "commitLineage": False,
                "busFactor": False,
                "prMetrics": False,
                "issueMetrics": False,
                "commitActivity": False,
                "releaseCadence": False
            }
        }

    @pytest.mark.asyncio
    async def test_full_extraction_flow(self, sample_frontend_request, mock_github_data):
        """Test complete extraction flow from frontend request to final output."""
        # Mock the GitHub API responses
        mock_repo = Mock()
        mock_repo.full_name = mock_github_data["repo"]["full_name"]
        mock_repo.html_url = mock_github_data["repo"]["html_url"]
        mock_repo.description = mock_github_data["repo"]["description"]
        mock_repo.language = mock_github_data["repo"]["language"]
        mock_repo.stargazers_count = mock_github_data["repo"]["stargazers_count"]
        mock_repo.forks_count = mock_github_data["repo"]["forks_count"]
        mock_repo.open_issues_count = mock_github_data["repo"]["open_issues_count"]
        mock_repo.created_at = mock_github_data["repo"]["created_at"]
        mock_repo.updated_at = mock_github_data["repo"]["updated_at"]
        mock_repo.default_branch = mock_github_data["repo"]["default_branch"]
        mock_repo.fork = mock_github_data["repo"]["fork"]
        mock_repo.get_languages.return_value = mock_github_data["repo"]["get_languages.return_value"]
        mock_repo.get_license.return_value = mock_github_data["repo"]["get_license.return_value"]
        
        # Mock commit data
        mock_commits = []
        for commit_data in mock_github_data["commits"]:
            commit = Mock()
            commit.sha = commit_data["sha"]
            commit.commit.message = commit_data["message"]
            commit.commit.author.name = commit_data["author"]
            commit.commit.author.date = datetime.fromisoformat(commit_data["date"].replace("Z", "+00:00"))
            commit.html_url = commit_data["url"]
            commit.stats = Mock()
            commit.stats.additions = 10
            commit.stats.deletions = 5
            commit.files = []
            mock_commits.append(commit)
        
        mock_repo.get_commits.return_value = mock_commits
        
        # Mock issues data
        mock_issues = []
        for issue_data in mock_github_data["issues"]:
            issue = Mock()
            issue.number = issue_data["number"]
            issue.title = issue_data["title"]
            issue.state = issue_data["state"]
            issue.user.login = issue_data["author"]
            issue.labels = [Mock(name=label) for label in issue_data["labels"]]
            issue.created_at = datetime.fromisoformat(issue_data["created_at"].replace("Z", "+00:00"))
            issue.closed_at = datetime.fromisoformat(issue_data["closed_at"].replace("Z", "+00:00")) if issue_data["closed_at"] else None
            issue.html_url = issue_data["url"]
            mock_issues.append(issue)
        
        mock_repo.get_issues.return_value = mock_issues
        
        # Mock pull requests data
        mock_prs = []
        for pr_data in mock_github_data["pull_requests"]:
            pr = Mock()
            pr.number = pr_data["number"]
            pr.title = pr_data["title"]
            pr.state = pr_data["state"]
            pr.user.login = pr_data["author"]
            pr.created_at = datetime.fromisoformat(pr_data["created_at"].replace("Z", "+00:00"))
            pr.merged_at = datetime.fromisoformat(pr_data["merged_at"].replace("Z", "+00:00")) if pr_data["merged_at"] else None
            pr.html_url = pr_data["url"]
            pr.merged = pr_data["state"] == "merged"
            mock_prs.append(pr)
        
        mock_repo.get_pulls.return_value = mock_prs
        
        # Mock contributors data
        mock_contributors = []
        for contrib_data in mock_github_data["contributors"]:
            contrib = Mock()
            contrib.login = contrib_data["login"]
            contrib.contributions = contrib_data["contributions"]
            contrib.html_url = contrib_data["url"]
            mock_contributors.append(contrib)
        
        mock_repo.get_contributors.return_value = mock_contributors
        
        # Mock dependencies data
        mock_file = Mock()
        mock_file.decoded_content = json.dumps({
            "dependencies": {
                "react": "^18.0.0",
                "lodash": "^4.17.21"
            }
        }).encode()
        mock_repo.get_contents.return_value = mock_file
        
        # Create workflow and activities
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.activities.Github'), \
             patch('app.activities.boto3'), \
             patch('os.makedirs'), \
             patch.object(GitHubMetadataActivities, '_get_repo', return_value=mock_repo), \
             patch('aiofiles.open', AsyncMock()), \
             patch('json.dumps', return_value='{"test": "data"}'):
            
            activities = GitHubMetadataActivities()
            
            # Test the complete flow
            workflow_config = sample_frontend_request
            
            with patch('app.workflow.generate_extraction_id', return_value="test123"):
                await workflow.run(workflow_config)
            
            # Verify that the workflow executed successfully
            # (In a real test, you would check the actual output file or S3 upload)

    @pytest.mark.asyncio
    async def test_partial_extraction_flow(self, mock_github_data):
        """Test extraction flow with only some metadata selected."""
        # Test with minimal selection
        minimal_request = {
            "repoUrl": "https://github.com/facebook/react",
            "selections": {
                "repository": True,
                "commits": False,
                "issues": False,
                "pullRequests": False,
                "contributors": False,
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
        
        # Mock repository data
        mock_repo = Mock()
        mock_repo.full_name = mock_github_data["repo"]["full_name"]
        mock_repo.html_url = mock_github_data["repo"]["html_url"]
        mock_repo.description = mock_github_data["repo"]["description"]
        mock_repo.language = mock_github_data["repo"]["language"]
        mock_repo.stargazers_count = mock_github_data["repo"]["stargazers_count"]
        mock_repo.forks_count = mock_github_data["repo"]["forks_count"]
        mock_repo.open_issues_count = mock_github_data["repo"]["open_issues_count"]
        mock_repo.created_at = mock_github_data["repo"]["created_at"]
        mock_repo.updated_at = mock_github_data["repo"]["updated_at"]
        mock_repo.default_branch = mock_github_data["repo"]["default_branch"]
        mock_repo.fork = mock_github_data["repo"]["fork"]
        mock_repo.get_languages.return_value = mock_github_data["repo"]["get_languages.return_value"]
        mock_repo.get_license.return_value = mock_github_data["repo"]["get_license.return_value"]
        
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.activities.Github'), \
             patch('app.activities.boto3'), \
             patch('os.makedirs'), \
             patch.object(GitHubMetadataActivities, '_get_repo', return_value=mock_repo), \
             patch('aiofiles.open', AsyncMock()), \
             patch('json.dumps', return_value='{"test": "data"}'):
            
            activities = GitHubMetadataActivities()
            
            with patch('app.workflow.generate_extraction_id', return_value="test123"):
                await workflow.run(minimal_request)
            
            # Verify that only repository metadata was extracted
            # (In a real test, you would check the actual output)

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, sample_frontend_request):
        """Test error handling in the complete flow."""
        # Test with invalid repository URL
        invalid_request = {
            "repoUrl": "https://invalid-url",
            "selections": {"repository": True}
        }
        
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            with pytest.raises(ValueError):
                await workflow.run(invalid_request)

    @pytest.mark.asyncio
    async def test_caching_integration(self, sample_frontend_request, mock_github_data):
        """Test caching in the complete flow."""
        # Mock repository data
        mock_repo = Mock()
        mock_repo.full_name = mock_github_data["repo"]["full_name"]
        mock_repo.html_url = mock_github_data["repo"]["html_url"]
        mock_repo.description = mock_github_data["repo"]["description"]
        mock_repo.language = mock_github_data["repo"]["language"]
        mock_repo.stargazers_count = mock_github_data["repo"]["stargazers_count"]
        mock_repo.forks_count = mock_github_data["repo"]["forks_count"]
        mock_repo.open_issues_count = mock_github_data["repo"]["open_issues_count"]
        mock_repo.created_at = mock_github_data["repo"]["created_at"]
        mock_repo.updated_at = mock_github_data["repo"]["updated_at"]
        mock_repo.default_branch = mock_github_data["repo"]["default_branch"]
        mock_repo.fork = mock_github_data["repo"]["fork"]
        mock_repo.get_languages.return_value = mock_github_data["repo"]["get_languages.return_value"]
        mock_repo.get_license.return_value = mock_github_data["repo"]["get_license.return_value"]
        
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.activities.Github'), \
             patch('app.activities.boto3'), \
             patch('os.makedirs'), \
             patch.object(GitHubMetadataActivities, '_get_repo', return_value=mock_repo), \
             patch('aiofiles.open', AsyncMock()), \
             patch('json.dumps', return_value='{"test": "data"}'):
            
            activities = GitHubMetadataActivities()
            
            # First call should hit GitHub API
            with patch('app.workflow.generate_extraction_id', return_value="test123"):
                await workflow.run(sample_frontend_request)
            
            # Second call should use cache
            with patch('app.workflow.generate_extraction_id', return_value="test456"):
                await workflow.run(sample_frontend_request)
            
            # Verify caching behavior
            # (In a real test, you would verify that the second call used cached data)

    @pytest.mark.asyncio
    async def test_s3_upload_integration(self, sample_frontend_request, mock_github_data):
        """Test S3 upload integration in the complete flow."""
        # Mock repository data
        mock_repo = Mock()
        mock_repo.full_name = mock_github_data["repo"]["full_name"]
        mock_repo.html_url = mock_github_data["repo"]["html_url"]
        mock_repo.description = mock_github_data["repo"]["description"]
        mock_repo.language = mock_github_data["repo"]["language"]
        mock_repo.stargazers_count = mock_github_data["repo"]["stargazers_count"]
        mock_repo.forks_count = mock_github_data["repo"]["forks_count"]
        mock_repo.open_issues_count = mock_github_data["repo"]["open_issues_count"]
        mock_repo.created_at = mock_github_data["repo"]["created_at"]
        mock_repo.updated_at = mock_github_data["repo"]["updated_at"]
        mock_repo.default_branch = mock_github_data["repo"]["default_branch"]
        mock_repo.fork = mock_github_data["repo"]["fork"]
        mock_repo.get_languages.return_value = mock_github_data["repo"]["get_languages.return_value"]
        mock_repo.get_license.return_value = mock_github_data["repo"]["get_license.return_value"]
        
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.activities.Github'), \
             patch('app.activities.boto3') as mock_boto3, \
             patch('os.makedirs'), \
             patch.object(GitHubMetadataActivities, '_get_repo', return_value=mock_repo), \
             patch('aiofiles.open', AsyncMock()), \
             patch('json.dumps', return_value='{"test": "data"}'), \
             patch('app.config.METADATA_UPLOAD_TO_S3', True), \
             patch('app.config.S3_BUCKET', 'test-bucket'):
            
            # Mock S3 client
            mock_s3_client = Mock()
            mock_s3_client.upload_file.return_value = None
            mock_boto3.client.return_value = mock_s3_client
            
            activities = GitHubMetadataActivities()
            
            with patch('app.workflow.generate_extraction_id', return_value="test123"):
                await workflow.run(sample_frontend_request)
            
            # Verify S3 upload was called
            mock_s3_client.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_parameter_validation_integration(self):
        """Test workflow parameter validation in the complete flow."""
        # Test with no selections
        no_selections_request = {
            "repoUrl": "https://github.com/test/repo",
            "selections": {
                "repository": False,
                "commits": False,
                "issues": False,
                "pullRequests": False,
                "contributors": False,
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
        
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            with pytest.raises(ValueError, match="At least one metadata type must be selected"):
                await workflow.run(no_selections_request)

    @pytest.mark.asyncio
    async def test_workflow_activity_failure_integration(self, sample_frontend_request, mock_github_data):
        """Test workflow behavior when activities fail."""
        # Mock repository data
        mock_repo = Mock()
        mock_repo.full_name = mock_github_data["repo"]["full_name"]
        mock_repo.html_url = mock_github_data["repo"]["html_url"]
        mock_repo.description = mock_github_data["repo"]["description"]
        mock_repo.language = mock_github_data["repo"]["language"]
        mock_repo.stargazers_count = mock_github_data["repo"]["stargazers_count"]
        mock_repo.forks_count = mock_github_data["repo"]["forks_count"]
        mock_repo.open_issues_count = mock_github_data["repo"]["open_issues_count"]
        mock_repo.created_at = mock_github_data["repo"]["created_at"]
        mock_repo.updated_at = mock_github_data["repo"]["updated_at"]
        mock_repo.default_branch = mock_github_data["repo"]["default_branch"]
        mock_repo.fork = mock_github_data["repo"]["fork"]
        mock_repo.get_languages.return_value = mock_github_data["repo"]["get_languages.return_value"]
        mock_repo.get_license.return_value = mock_github_data["repo"]["get_license.return_value"]
        
        # Make one activity fail
        mock_repo.get_commits.side_effect = Exception("GitHub API Error")
        
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.activities.Github'), \
             patch('app.activities.boto3'), \
             patch('os.makedirs'), \
             patch.object(GitHubMetadataActivities, '_get_repo', return_value=mock_repo), \
             patch('aiofiles.open', AsyncMock()), \
             patch('json.dumps', return_value='{"test": "data"}'):
            
            activities = GitHubMetadataActivities()
            
            with patch('app.workflow.generate_extraction_id', return_value="test123"):
                # Should not raise exception, should handle gracefully
                await workflow.run(sample_frontend_request)
            
            # Verify that the workflow continued despite the error
            # (In a real test, you would check the actual output)

    @pytest.mark.asyncio
    async def test_workflow_output_structure_integration(self, sample_frontend_request, mock_github_data):
        """Test workflow output structure in the complete flow."""
        # Mock repository data
        mock_repo = Mock()
        mock_repo.full_name = mock_github_data["repo"]["full_name"]
        mock_repo.html_url = mock_github_data["repo"]["html_url"]
        mock_repo.description = mock_github_data["repo"]["description"]
        mock_repo.language = mock_github_data["repo"]["language"]
        mock_repo.stargazers_count = mock_github_data["repo"]["stargazers_count"]
        mock_repo.forks_count = mock_github_data["repo"]["forks_count"]
        mock_repo.open_issues_count = mock_github_data["repo"]["open_issues_count"]
        mock_repo.created_at = mock_github_data["repo"]["created_at"]
        mock_repo.updated_at = mock_github_data["repo"]["updated_at"]
        mock_repo.default_branch = mock_github_data["repo"]["default_branch"]
        mock_repo.fork = mock_github_data["repo"]["fork"]
        mock_repo.get_languages.return_value = mock_github_data["repo"]["get_languages.return_value"]
        mock_repo.get_license.return_value = mock_github_data["repo"]["get_license.return_value"]
        
        # Mock other data
        mock_repo.get_commits.return_value = []
        mock_repo.get_issues.return_value = []
        mock_repo.get_pulls.return_value = []
        mock_repo.get_contributors.return_value = []
        mock_repo.get_contents.return_value = Mock(decoded_content=b'{}')
        
        workflow = GitHubMetadataWorkflow()
        
        with patch('app.activities.Github'), \
             patch('app.activities.boto3'), \
             patch('os.makedirs'), \
             patch.object(GitHubMetadataActivities, '_get_repo', return_value=mock_repo), \
             patch('aiofiles.open', AsyncMock()), \
             patch('json.dumps', return_value='{"test": "data"}'):
            
            activities = GitHubMetadataActivities()
            
            with patch('app.workflow.generate_extraction_id', return_value="test123"):
                await workflow.run(sample_frontend_request)
            
            # Verify that the workflow executed successfully
            # (In a real test, you would check the actual output structure)
