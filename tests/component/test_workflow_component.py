"""
Component tests for GitHubMetadataWorkflow.
Tests workflow components and helper methods without full Temporal context.
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import timedelta

from app.workflow import GitHubMetadataWorkflow
from app.activities import GitHubMetadataActivities


class TestGitHubMetadataWorkflowComponent:
    """Component tests for GitHubMetadataWorkflow."""

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

    def test_extract_parameters_component(self, workflow, sample_workflow_args):
        """Test parameter extraction component."""
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            sample_workflow_args, {}
        )
        
        assert repo_url == "https://github.com/test/repo"
        assert commit_limit == 50
        assert issues_limit == 30
        assert pr_limit == 20
        assert normalized_selections["repository"] is True
        assert normalized_selections["commits"] is True
        assert normalized_selections["issues"] is False
        assert normalized_selections["pull_requests"] is True
        assert normalized_selections["dependencies"] is True

    def test_validate_inputs_component(self, workflow):
        """Test input validation component."""
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

    def test_build_combined_metadata_component(self, workflow):
        """Test metadata combination component."""
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

    def test_get_activities_registration(self, workflow):
        """Test that get_activities returns correct activity list."""
        mock_activities = Mock(spec=GitHubMetadataActivities)
        
        activities = workflow.get_activities(mock_activities)
        
        # Should return list of activity methods
        assert isinstance(activities, list)
        assert len(activities) > 0

    def test_get_activities_wrong_type(self, workflow):
        """Test get_activities with wrong activity type."""
        with pytest.raises(TypeError, match="Activities must be an instance of GitHubMetadataActivities"):
            workflow.get_activities("not_an_activities_instance")

    def test_workflow_configuration_validation(self, sample_workflow_args):
        """Test workflow configuration validation."""
        # Test valid configuration
        assert sample_workflow_args["repo_url"] == "https://github.com/test/repo"
        assert sample_workflow_args["commit_limit"] == 50
        assert sample_workflow_args["issues_limit"] == 30
        assert sample_workflow_args["pr_limit"] == 20
        
        # Test selections validation
        selections = sample_workflow_args["selections"]
        assert any(selections.values())  # At least one selection should be True
        
        # Test URL format validation
        assert sample_workflow_args["repo_url"].startswith("https://github.com/")
        
        # Test limits validation
        assert sample_workflow_args["commit_limit"] > 0
        assert sample_workflow_args["issues_limit"] > 0
        assert sample_workflow_args["pr_limit"] > 0

    def test_selections_normalization(self, workflow):
        """Test selections normalization logic."""
        workflow_args = {
            "repo_url": "https://github.com/test/repo",
            "selections": {
                "repository": True,
                "commits": True,
                "issues": False,
                "pull_requests": True
            }
        }
        
        _, _, _, _, normalized_selections = workflow._extract_parameters(workflow_args, {})
        
        # Check that all metadata types are present
        expected_keys = [
            "repository", "commits", "issues", "pull_requests", "contributors",
            "dependencies", "fork_lineage", "commit_lineage", "bus_factor",
            "pr_metrics", "issue_metrics", "commit_activity", "release_cadence"
        ]
        
        for key in expected_keys:
            assert key in normalized_selections
            assert isinstance(normalized_selections[key], bool)
        
        # Check specific values
        assert normalized_selections["repository"] is True
        assert normalized_selections["commits"] is True
        assert normalized_selections["issues"] is False
        assert normalized_selections["pull_requests"] is True
        
        # Check defaults for missing keys
        assert normalized_selections["contributors"] is False
        assert normalized_selections["dependencies"] is False

    def test_workflow_parameter_defaults(self, workflow):
        """Test workflow parameter defaults."""
        workflow_args = {
            "repo_url": "https://github.com/test/repo",
            "selections": {"repository": True}
        }
        
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            workflow_args, {}
        )
        
        assert repo_url == "https://github.com/test/repo"
        assert commit_limit == 200  # Default from config
        assert issues_limit == 200  # Default from config
        assert pr_limit == 200  # Default from config
        assert normalized_selections["repository"] is True
        assert all(not value for key, value in normalized_selections.items() if key != "repository")

    def test_workflow_metadata_filtering(self, workflow):
        """Test workflow metadata filtering based on selections."""
        # Test with only repository selected
        normalized_selections = {
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
        
        result = workflow._build_combined_metadata(
            {"repository": "test/repo"}, None, None, None, None, None,
            None, None, None, None, None, None, None, normalized_selections
        )
        
        assert "repository" in result
        assert "commits" not in result
        assert "issues" not in result
        assert "pull_requests" not in result

    def test_workflow_error_scenarios(self, workflow):
        """Test workflow error scenarios."""
        # Test empty repo URL
        with pytest.raises(ValueError, match="Repository URL is required"):
            workflow._validate_inputs("", {"repository": True}, "test123")
        
        # Test no selections
        with pytest.raises(ValueError, match="At least one metadata type must be selected"):
            workflow._validate_inputs("https://github.com/test/repo", {
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
            }, "test123")

    def test_workflow_component_integration(self, workflow, sample_workflow_args):
        """Test integration of workflow components."""
        # Test the flow of components working together
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            sample_workflow_args, {}
        )
        
        # Validate inputs
        workflow._validate_inputs(repo_url, normalized_selections, "test123")
        
        # Build metadata
        result = workflow._build_combined_metadata(
            {"repository": "test/repo", "stars": 100},
            [{"sha": "1"}], None, None, None, [{"name": "dep1"}],
            None, None, None, None, None, None, None, normalized_selections
        )
        
        # Verify result
        assert result["repository"] == "test/repo"
        assert result["stars"] == 100
        assert result["commits"] == [{"sha": "1"}]
        assert result["dependencies"] == [{"name": "dep1"}]
        # Note: pull_requests is selected in sample_workflow_args, so it should be included
        assert "pull_requests" in result

    def test_workflow_metadata_combination_edge_cases(self, workflow):
        """Test workflow metadata combination edge cases."""
        # Test with empty lists
        normalized_selections = {
            "repository": True,
            "commits": True,
            "issues": True,
            "pull_requests": True,
            "contributors": True,
            "dependencies": True,
            "fork_lineage": False,
            "commit_lineage": False,
            "bus_factor": False,
            "pr_metrics": False,
            "issue_metrics": False,
            "commit_activity": False,
            "release_cadence": False
        }
        
        result = workflow._build_combined_metadata(
            {"repository": "test/repo"}, [], [], [], [], [],
            None, None, None, None, None, None, None, normalized_selections
        )
        
        assert result["repository"] == "test/repo"
        assert result["commits"] == []
        assert result["issues"] == []
        assert result["pull_requests"] == []
        assert result["contributors"] == []
        assert result["dependencies"] == []

    def test_workflow_parameter_extraction_edge_cases(self, workflow):
        """Test workflow parameter extraction edge cases."""
        # Test with missing limits
        workflow_args = {
            "repo_url": "https://github.com/test/repo",
            "selections": {"repository": True}
        }
        
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            workflow_args, {}
        )
        
        assert repo_url == "https://github.com/test/repo"
        assert commit_limit == 200  # Default
        assert issues_limit == 200  # Default
        assert pr_limit == 200  # Default
        assert normalized_selections["repository"] is True

    def test_workflow_metadata_structure_validation(self, workflow):
        """Test workflow metadata structure validation."""
        # Test that metadata structure is maintained
        repo_metadata = {
            "repository": "test/repo",
            "stars": 100,
            "forks": 50,
            "description": "Test repository"
        }
        
        normalized_selections = {
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
        
        result = workflow._build_combined_metadata(
            repo_metadata, None, None, None, None, None,
            None, None, None, None, None, None, None, normalized_selections
        )
        
        # Verify structure is maintained
        assert result["repository"] == "test/repo"
        assert result["stars"] == 100
        assert result["forks"] == 50
        assert result["description"] == "Test repository"
        assert "commits" not in result
        assert "issues" not in result
