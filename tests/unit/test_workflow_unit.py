"""
Unit tests for GitHubMetadataWorkflow class.
Tests individual workflow methods in isolation.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import timedelta

from app.workflow import GitHubMetadataWorkflow


class TestGitHubMetadataWorkflow:
    """Unit tests for GitHubMetadataWorkflow class."""

    @pytest.fixture
    def workflow(self):
        """Create workflow instance."""
        return GitHubMetadataWorkflow()

    @pytest.fixture
    def sample_workflow_args(self):
        """Sample workflow arguments."""
        return {
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
                "fork_lineage": False,
                "commit_lineage": False,
                "bus_factor": False,
                "pr_metrics": False,
                "issue_metrics": False,
                "commit_activity": False,
                "release_cadence": False
            }
        }

    def test_extract_parameters(self, workflow):
        """Test parameter extraction from workflow args."""
        workflow_args = {
            "repo_url": "https://github.com/test/repo",
            "commit_limit": 100,
            "issues_limit": 50,
            "pr_limit": 25,
            "selections": {
                "repository": True,
                "commits": True,
                "issues": True,
                "pull_requests": False,
                "contributors": True,
                "dependencies": False,
                "fork_lineage": True,
                "commit_lineage": False,
                "bus_factor": True,
                "pr_metrics": False,
                "issue_metrics": True,
                "commit_activity": False,
                "release_cadence": True
            }
        }
        
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            workflow_args, {}
        )
        
        assert repo_url == "https://github.com/test/repo"
        assert commit_limit == 100
        assert issues_limit == 50
        assert pr_limit == 25
        assert normalized_selections["repository"] is True
        assert normalized_selections["commits"] is True
        assert normalized_selections["issues"] is True
        assert normalized_selections["pull_requests"] is False
        assert normalized_selections["fork_lineage"] is True
        assert normalized_selections["bus_factor"] is True

    def test_extract_parameters_with_defaults(self, workflow):
        """Test parameter extraction with default values."""
        workflow_args = {
            "repo_url": "https://github.com/test/repo",
            "selections": {}
        }
        
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            workflow_args, {}
        )
        
        assert repo_url == "https://github.com/test/repo"
        assert commit_limit == 200  # Default from config
        assert issues_limit == 200  # Default from config
        assert pr_limit == 200  # Default from config
        # All selections should default to False
        assert all(not value for value in normalized_selections.values())

    def test_validate_inputs_valid(self, workflow):
        """Test input validation with valid inputs."""
        repo_url = "https://github.com/test/repo"
        normalized_selections = {
            "repository": True,
            "commits": False,
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
        
        # Should not raise exception
        workflow._validate_inputs(repo_url, normalized_selections, "test123")

    def test_validate_inputs_no_repo_url(self, workflow):
        """Test input validation with missing repo URL."""
        repo_url = ""
        normalized_selections = {"repository": True}
        
        with pytest.raises(ValueError, match="Repository URL is required"):
            workflow._validate_inputs(repo_url, normalized_selections, "test123")

    def test_validate_inputs_no_selections(self, workflow):
        """Test input validation with no selections."""
        repo_url = "https://github.com/test/repo"
        normalized_selections = {
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
        
        with pytest.raises(ValueError, match="At least one metadata type must be selected"):
            workflow._validate_inputs(repo_url, normalized_selections, "test123")

    def test_build_combined_metadata(self, workflow):
        """Test building combined metadata with selected items."""
        repo_metadata = {"repository": "test/repo", "stars": 100}
        commits = [{"sha": "1"}]
        issues = [{"number": 1}]
        pull_requests = [{"number": 1}]
        contributors = [{"login": "user1"}]
        dependencies = [{"name": "dep1"}]
        fork_lineage = {"is_fork": False}
        commit_lineage = {"merge_commits": []}
        bus_factor = {"top1_pct": 0.5}
        pr_metrics = {"merge_rate": 0.8}
        issue_metrics = {"closure_rate": 0.6}
        commit_activity = {"per_week": {}}
        release_cadence = {"tag_count_100": 10}
        
        normalized_selections = {
            "repository": True,
            "commits": True,
            "issues": False,
            "pull_requests": True,
            "contributors": False,
            "dependencies": True,
            "fork_lineage": True,
            "commit_lineage": False,
            "bus_factor": True,
            "pr_metrics": False,
            "issue_metrics": True,
            "commit_activity": False,
            "release_cadence": True
        }
        
        result = workflow._build_combined_metadata(
            repo_metadata, commits, issues, pull_requests, contributors, dependencies,
            fork_lineage, commit_lineage, bus_factor, pr_metrics, issue_metrics,
            commit_activity, release_cadence, normalized_selections
        )
        
        # Check selected items are included
        assert result["repository"] == "test/repo"
        assert result["stars"] == 100
        assert result["commits"] == [{"sha": "1"}]
        assert result["pull_requests"] == [{"number": 1}]
        assert result["dependencies"] == [{"name": "dep1"}]
        assert result["fork_lineage"] == {"is_fork": False}
        assert result["bus_factor"] == {"top1_pct": 0.5}
        assert result["issue_metrics"] == {"closure_rate": 0.6}
        assert result["release_cadence"] == {"tag_count_100": 10}
        
        # Check non-selected items are not included
        assert "issues" not in result
        assert "contributors" not in result
        assert "commit_lineage" not in result
        assert "pr_metrics" not in result
        assert "commit_activity" not in result

    def test_build_combined_metadata_no_repo_metadata(self, workflow):
        """Test building combined metadata without repository metadata."""
        normalized_selections = {
            "repository": False,
            "commits": True,
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
        
        result = workflow._build_combined_metadata(
            None, [{"sha": "1"}], None, None, None, None,
            None, None, None, None, None, None, None, normalized_selections
        )
        
        assert result["commits"] == [{"sha": "1"}]
        assert "repository" not in result
        assert "stars" not in result

    def test_get_activities_wrong_type(self, workflow):
        """Test get_activities with wrong activity type."""
        with pytest.raises(TypeError, match="Activities must be an instance of GitHubMetadataActivities"):
            workflow.get_activities("not_an_activities_instance")
