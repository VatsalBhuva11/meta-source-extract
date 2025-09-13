"""
Component tests for GitHubMetadataWorkflow.
Tests the integration between workflow and activities with real data flow.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from app.workflow import GitHubMetadataWorkflow
from app.activities import GitHubMetadataActivities


class TestWorkflowComponent:
    """Component tests for GitHubMetadataWorkflow."""

    @pytest.fixture
    def workflow(self):
        """Create workflow instance."""
        return GitHubMetadataWorkflow()

    @pytest.fixture
    def mock_activities(self):
        """Create mock activities with realistic responses."""
        activities = Mock(spec=GitHubMetadataActivities)
        
        # Mock get_workflow_args
        activities.get_workflow_args = AsyncMock(return_value={
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
        })
        
        # Mock repository metadata
        activities.extract_repository_metadata = AsyncMock(return_value={
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
            "extraction_provenance": {
                "extraction_id": "test123",
                "extracted_by": "github-metadata-extractor",
                "extracted_at": "2023-12-01T00:00:00Z",
                "schema_version": "1",
                "source": "github"
            }
        })
        
        # Mock commit metadata
        activities.extract_commit_metadata = AsyncMock(return_value=[
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
        ])
        
        # Mock issues metadata
        activities.extract_issues_metadata = AsyncMock(return_value=[
            {
                "number": 1,
                "title": "Bug report",
                "state": "open",
                "author": "testuser",
                "labels": ["bug"],
                "created_at": "2023-01-01T00:00:00Z",
                "closed_at": None,
                "url": "https://github.com/test/repo/issues/1"
            },
            {
                "number": 2,
                "title": "Feature request",
                "state": "closed",
                "author": "testuser",
                "labels": ["enhancement"],
                "created_at": "2023-01-01T00:00:00Z",
                "closed_at": "2023-01-02T00:00:00Z",
                "url": "https://github.com/test/repo/issues/2"
            }
        ])
        
        # Mock contributors metadata
        activities.extract_contributors = AsyncMock(return_value=[
            {
                "login": "testuser",
                "contributions": 50,
                "url": "https://github.com/testuser"
            },
            {
                "login": "contributor2",
                "contributions": 25,
                "url": "https://github.com/contributor2"
            }
        ])
        
        # Mock save and summary
        activities.save_metadata_to_file = AsyncMock(return_value="/path/to/metadata.json")
        activities.get_extraction_summary = AsyncMock(return_value={
            "repository": "test/repo",
            "url": "https://github.com/test/repo",
            "extracted_at": "2023-12-01T00:00:00Z",
            "commits_count": 2,
            "issues_count": 2,
            "prs_count": 0,
            "contributors_count": 2,
            "dependencies_count": 0,
            "stars": 100,
            "forks": 50
        })
        
        return activities

    @pytest.mark.asyncio
    async def test_workflow_full_execution(self, workflow, mock_activities):
        """Test complete workflow execution with all selected components."""
        workflow_config = {
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
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            await workflow.run(workflow_config)
        
        # Verify all expected activities were called
        mock_activities.get_workflow_args.assert_called_once()
        mock_activities.extract_repository_metadata.assert_called_once()
        mock_activities.extract_commit_metadata.assert_called_once()
        mock_activities.extract_issues_metadata.assert_called_once()
        mock_activities.extract_contributors.assert_called_once()
        mock_activities.save_metadata_to_file.assert_called_once()
        mock_activities.get_extraction_summary.assert_called_once()
        
        # Verify non-selected activities were not called
        mock_activities.extract_pull_requests_metadata.assert_not_called()
        mock_activities.extract_dependencies_from_repo.assert_not_called()

    @pytest.mark.asyncio
    async def test_workflow_minimal_selection(self, workflow, mock_activities):
        """Test workflow with minimal selection (only repository)."""
        mock_activities.get_workflow_args.return_value = {
            "repo_url": "https://github.com/test/repo",
            "commit_limit": 50,
            "issues_limit": 30,
            "pr_limit": 20,
            "selections": {
                "repository": True,
                "commits": False,
                "issues": False,
                "pull_requests": False,
                "contributors": False,
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
        
        workflow_config = {"repo_url": "https://github.com/test/repo"\}
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            await workflow.run(workflow_config)
        
        # Verify only repository activity was called
        mock_activities.extract_repository_metadata.assert_called_once()
        mock_activities.save_metadata_to_file.assert_called_once()
        mock_activities.get_extraction_summary.assert_called_once()
        
        # Verify other activities were not called
        mock_activities.extract_commit_metadata.assert_not_called()
        mock_activities.extract_issues_metadata.assert_not_called()
        mock_activities.extract_contributors.assert_not_called()

    @pytest.mark.asyncio
    async def test_workflow_with_derived_metrics(self, workflow, mock_activities):
        """Test workflow with derived metrics selected."""
        mock_activities.get_workflow_args.return_value = {
            "repo_url": "https://github.com/test/repo",
            "commit_limit": 50,
            "issues_limit": 30,
            "pr_limit": 20,
            "selections": {
                "repository": True,
                "commits": True,
                "issues": False,
                "pull_requests": True,
                "contributors": False,
                "dependencies": True,
                "fork_lineage": True,
                "commit_lineage": True,
                "bus_factor": True,
                "pr_metrics": True,
                "issue_metrics": False,
                "commit_activity": True,
                "release_cadence": True
            }
        }
        
        # Mock derived metrics activities
        mock_activities.extract_fork_lineage = AsyncMock(return_value={"is_fork": False})
        mock_activities.extract_commit_lineage = AsyncMock(return_value={"merge_commits": []})
        mock_activities.extract_bus_factor = AsyncMock(return_value={"top1_pct": 0.8})
        mock_activities.extract_pr_metrics = AsyncMock(return_value={"merge_rate": 0.9})
        mock_activities.extract_commit_activity = AsyncMock(return_value={"per_week": {}})
        mock_activities.extract_release_cadence = AsyncMock(return_value={"tag_count_100": 5})
        mock_activities.extract_pull_requests_metadata = AsyncMock(return_value=[
            {"number": 1, "title": "PR 1", "state": "merged"}
        ])
        mock_activities.extract_dependencies_from_repo = AsyncMock(return_value=[
            {"manifest": "package.json", "dependencies": [{"name": "react", "version": "^18.0.0"}]}
        ])
        
        workflow_config = {"repo_url": "https://github.com/test/repo"\}
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            await workflow.run(workflow_config)
        
        # Verify all selected activities were called
        mock_activities.extract_repository_metadata.assert_called_once()
        mock_activities.extract_commit_metadata.assert_called_once()
        mock_activities.extract_pull_requests_metadata.assert_called_once()
        mock_activities.extract_dependencies_from_repo.assert_called_once()
        mock_activities.extract_fork_lineage.assert_called_once()
        mock_activities.extract_commit_lineage.assert_called_once()
        mock_activities.extract_bus_factor.assert_called_once()
        mock_activities.extract_pr_metrics.assert_called_once()
        mock_activities.extract_commit_activity.assert_called_once()
        mock_activities.extract_release_cadence.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_activity_failure_graceful_degradation(self, workflow, mock_activities):
        """Test workflow continues when some activities fail."""
        # Make one activity fail
        mock_activities.extract_commit_metadata = AsyncMock(side_effect=Exception("API Error"))
        
        mock_activities.get_workflow_args.return_value = {
            "repo_url": "https://github.com/test/repo",
            "commit_limit": 50,
            "issues_limit": 30,
            "pr_limit": 20,
            "selections": {
                "repository": True,
                "commits": True,
                "issues": True,
                "pull_requests": False,
                "contributors": False,
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
        
        workflow_config = {"repo_url": "https://github.com/test/repo"\}
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            # Should not raise exception
            await workflow.run(workflow_config)
        
        # Verify other activities still executed
        mock_activities.extract_repository_metadata.assert_called_once()
        mock_activities.extract_issues_metadata.assert_called_once()
        mock_activities.save_metadata_to_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_workflow_parameter_validation(self, workflow, mock_activities):
        """Test workflow parameter validation."""
        # Test with no selections
        mock_activities.get_workflow_args.return_value = {
            "repo_url": "https://github.com/test/repo",
            "selections": {
                "repository": False,
                "commits": False,
                "issues": False,
                "pull_requests": False,
                "contributors": False,
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
        
        workflow_config = {"repo_url": "https://github.com/test/repo"\}
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            with pytest.raises(ValueError, match="At least one metadata type must be selected"):
                await workflow.run(workflow_config)

    @pytest.mark.asyncio
    async def test_workflow_missing_repo_url(self, workflow, mock_activities):
        """Test workflow with missing repository URL."""
        mock_activities.get_workflow_args.return_value = {
            "repo_url": "",
            "selections": {"repository": True}
        }
        
        workflow_config = {}
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            with pytest.raises(ValueError, match="Repository URL is required"):
                await workflow.run(workflow_config)

    @pytest.mark.asyncio
    async def test_workflow_save_metadata_integration(self, workflow, mock_activities):
        """Test workflow save metadata integration."""
        mock_activities.get_workflow_args.return_value = {
            "repo_url": "https://github.com/test/repo",
            "selections": {"repository": True}
        }
        
        # Mock save to return S3 path
        mock_activities.save_metadata_to_file = AsyncMock(return_value="s3://bucket/metadata.json")
        
        workflow_config = {"repo_url": "https://github.com/test/repo"\}
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            await workflow.run(workflow_config)
        
        # Verify save was called with correct metadata structure
        save_call_args = mock_activities.save_metadata_to_file.call_args[0][0]
        assert isinstance(save_call_args, list)
        assert len(save_call_args) == 3  # [metadata, repo_url, extraction_id]
        
        metadata = save_call_args[0]
        assert "repository" in metadata
        assert "extraction_provenance" in metadata

    @pytest.mark.asyncio
    async def test_workflow_summary_generation(self, workflow, mock_activities):
        """Test workflow summary generation integration."""
        mock_activities.get_workflow_args.return_value = {
            "repo_url": "https://github.com/test/repo",
            "selections": {
                "repository": True,
                "commits": True,
                "issues": True
            }
        }
        
        # Mock summary with metrics
        mock_activities.get_extraction_summary = AsyncMock(return_value={
            "repository": "test/repo",
            "commits_count": 10,
            "issues_count": 5,
            "prs_count": 0,
            "contributors_count": 3,
            "dependencies_count": 0,
            "stars": 100,
            "forks": 50,
            "pr_merge_rate": 0.8,
            "avg_issue_resolution_seconds": 86400
        })
        
        workflow_config = {"repo_url": "https://github.com/test/repo"\}
        
        with patch('app.workflow.generate_extraction_id', return_value="test123"):
            await workflow.run(workflow_config)
        
        # Verify summary was called with correct parameters
        summary_call_args = mock_activities.get_extraction_summary.call_args[0]
        assert len(summary_call_args) == 3  # [repo_url, metadata, extraction_id]
        assert summary_call_args[0] == "https://github.com/test/repo"
        assert summary_call_args[2] == "test123"
        
        metadata = summary_call_args[1]
        assert "repository" in metadata
        assert "commits" in metadata
        assert "issues" in metadata
