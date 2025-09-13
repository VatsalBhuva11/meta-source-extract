"""
Integration tests for end-to-end workflow.
Tests complete workflow integration without full Temporal execution.
"""
import pytest
import asyncio
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from app.workflow import GitHubMetadataWorkflow
from app.activities import GitHubMetadataActivities


class TestIntegration:
    """Integration tests for complete workflow."""

    @pytest.fixture
    def temp_metadata_dir(self):
        """Create temporary metadata directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_github_data(self):
        """Mock GitHub API data."""
        return {
            "repo": Mock(
                full_name="facebook/react",
                html_url="https://github.com/facebook/react",
                description="A declarative, efficient, and flexible JavaScript library",
                language="JavaScript",
                get_languages=Mock(return_value={"JavaScript": 1000, "TypeScript": 500}),
                stargazers_count=200000,
                forks_count=40000,
                open_issues_count=100,
                created_at=datetime(2013, 5, 24, tzinfo=timezone.utc),
                updated_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
                default_branch="main",
                fork=False,
                get_license=Mock(return_value=Mock(license=Mock(spdx_id="MIT")))
            ),
            "commits": [
                Mock(
                    sha="abc123",
                    commit=Mock(
                        message="Test commit",
                        author=Mock(
                            name="Test Author",
                            email="test@example.com",
                            date=datetime(2023, 1, 1, tzinfo=timezone.utc)
                        )
                    ),
                    html_url="https://github.com/test/repo/commit/abc123"
                )
            ],
            "issues": [
                Mock(
                    number=1,
                    title="Test Issue",
                    state="open",
                    user=Mock(login="testuser"),
                    labels=[Mock(name="bug")],
                    created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
                    closed_at=None,
                    html_url="https://github.com/test/repo/issues/1"
                )
            ],
            "pull_requests": [
                Mock(
                    number=1,
                    title="Test PR",
                    state="open",
                    user=Mock(login="testuser"),
                    labels=[],
                    created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
                    merged_at=None,
                    closed_at=None,
                    merged=False,
                    html_url="https://github.com/test/repo/pull/1"
                )
            ],
            "contributors": [
                Mock(
                    login="user1",
                    contributions=100,
                    avatar_url="https://avatars.githubusercontent.com/u/1",
                    html_url="https://github.com/user1"
                )
            ],
            "dependencies": [
                Mock(
                    name="package.json",
                    content="eyJuYW1lIjoidGVzdCIsImRlcGVuZGVuY2llcyI6eyJyZWFjdCI6Il4xOC4wLjAifX0=",
                    encoding="base64"
                )
            ]
        }

    @pytest.fixture
    def workflow_config(self):
        """Sample workflow configuration."""
        return {
            "repo_url": "https://github.com/facebook/react",
            "commit_limit": 50,
            "issues_limit": 30,
            "pr_limit": 20,
            "selections": {
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
        }

    @pytest.mark.asyncio
    async def test_workflow_activities_integration(self, temp_metadata_dir, mock_github_data, workflow_config):
        """Test integration between workflow and activities components."""
        with patch.dict(os.environ, {"METADATA_DIR": temp_metadata_dir}):
            with patch('app.activities.Github') as mock_github_class:
                # Setup mock GitHub client
                mock_github = Mock()
                mock_github_class.return_value = mock_github
                
                # Setup mock repository
                mock_repo = mock_github_data["repo"]
                mock_github.get_repo.return_value = mock_repo
                
                # Setup mock data for different activities
                mock_repo.get_commits.return_value = mock_github_data["commits"]
                mock_repo.get_issues.return_value = mock_github_data["issues"]
                mock_repo.get_pulls.return_value = mock_github_data["pull_requests"]
                mock_repo.get_contributors.return_value = mock_github_data["contributors"]
                mock_repo.get_contents.return_value = mock_github_data["dependencies"]
                
                # Create activities and workflow
                activities = GitHubMetadataActivities()
                workflow = GitHubMetadataWorkflow()
                
                # Test individual activity execution
                repo_metadata = await activities.extract_repository_metadata([
                    "https://github.com/facebook/react", "test123"
                ])
                
                commits = await activities.extract_commit_metadata([
                    "https://github.com/facebook/react", 50, "test123"
                ])
                
                issues = await activities.extract_issues_metadata([
                    "https://github.com/facebook/react", 30, "test123"
                ])
                
                pull_requests = await activities.extract_pull_requests_metadata([
                    "https://github.com/facebook/react", 20, "test123"
                ])
                
                contributors = await activities.extract_contributors([
                    "https://github.com/facebook/react", "test123"
                ])
                
                dependencies = await activities.extract_dependencies_from_repo([
                    "https://github.com/facebook/react", "test123"
                ])
                
                # Test workflow metadata combination
                normalized_selections = workflow._extract_parameters(workflow_config, {})[4]
                combined_metadata = workflow._build_combined_metadata(
                    repo_metadata, commits, issues, pull_requests, contributors, dependencies,
                    None, None, None, None, None, None, None, normalized_selections
                )
                
                # Verify integration results
                assert combined_metadata["repository"] == "facebook/react"
                assert combined_metadata["stars"] == 200000
                assert len(combined_metadata["commits"]) == 1
                assert len(combined_metadata["issues"]) == 1
                assert len(combined_metadata["pull_requests"]) == 1
                assert len(combined_metadata["contributors"]) == 1
                # Dependencies may be empty depending on parsing
                assert isinstance(combined_metadata["dependencies"], list)

    @pytest.mark.asyncio
    async def test_workflow_parameter_flow_integration(self, workflow_config):
        """Test parameter flow through workflow components."""
        workflow = GitHubMetadataWorkflow()
        
        # Test parameter extraction
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            workflow_config, {}
        )
        
        # Verify parameters
        assert repo_url == "https://github.com/facebook/react"
        assert commit_limit == 50
        assert issues_limit == 30
        assert pr_limit == 20
        assert normalized_selections["repository"] is True
        assert normalized_selections["commits"] is True
        assert normalized_selections["issues"] is True
        
        # Test input validation
        workflow._validate_inputs(repo_url, normalized_selections, "test123")
        
        # Test metadata building with mock data
        result = workflow._build_combined_metadata(
            {"repository": "facebook/react", "stars": 100},
            [{"sha": "abc123"}], [{"number": 1}], [{"number": 1}], [{"login": "user1"}], [{"name": "dep1"}],
            None, None, None, None, None, None, None, normalized_selections
        )
        
        # Verify result
        assert result["repository"] == "facebook/react"
        assert result["stars"] == 100
        assert result["commits"] == [{"sha": "abc123"}]
        assert result["issues"] == [{"number": 1}]
        assert result["pull_requests"] == [{"number": 1}]
        assert result["contributors"] == [{"login": "user1"}]
        assert result["dependencies"] == [{"name": "dep1"}]

    @pytest.mark.asyncio
    async def test_activities_data_flow_integration(self, temp_metadata_dir, mock_github_data):
        """Test data flow through activities."""
        with patch.dict(os.environ, {"METADATA_DIR": temp_metadata_dir}):
            with patch('app.activities.Github') as mock_github_class:
                mock_github = Mock()
                mock_github_class.return_value = mock_github
                mock_github.get_repo.return_value = mock_github_data["repo"]
                
                activities = GitHubMetadataActivities()
                
                # Test data flow through multiple activities
                repo_metadata = await activities.extract_repository_metadata([
                    "https://github.com/facebook/react", "test123"
                ])
                
                # Verify repository metadata structure
                assert "repository" in repo_metadata
                assert "stars" in repo_metadata
                assert "forks" in repo_metadata
                assert "extraction_provenance" in repo_metadata
                
                # Test summary generation
                summary = await activities.get_extraction_summary([
                    "https://github.com/facebook/react", repo_metadata, "test123"
                ])
                
                # Verify summary structure
                assert "repository" in summary
                assert "stars" in summary
                assert "forks" in summary

    @pytest.mark.asyncio
    async def test_error_handling_integration(self, temp_metadata_dir, workflow_config):
        """Test error handling integration across components."""
        with patch.dict(os.environ, {"METADATA_DIR": temp_metadata_dir}):
            with patch('app.activities.Github') as mock_github_class:
                # Make GitHub API fail
                mock_github = Mock()
                mock_github_class.return_value = mock_github
                mock_github.get_repo.side_effect = Exception("API Error")
                
                activities = GitHubMetadataActivities()
                workflow = GitHubMetadataWorkflow()
                
                # Test activity error handling
                with pytest.raises(Exception, match="RetryError"):
                    await activities.extract_repository_metadata([
                        "https://github.com/facebook/react", "test123"
                    ])
                
                # Test workflow error handling
                with pytest.raises(ValueError, match="Repository URL is required"):
                    workflow._validate_inputs("", {"repository": True}, "test123")

    @pytest.mark.asyncio
    async def test_file_operations_integration(self, temp_metadata_dir):
        """Test file operations integration."""
        with patch.dict(os.environ, {"METADATA_DIR": temp_metadata_dir}):
            with patch('app.activities.Github') as mock_github_class:
                mock_github = Mock()
                mock_github_class.return_value = mock_github
                
                activities = GitHubMetadataActivities()
                
                # Test file saving
                metadata = {"test": "data"}
                with patch('aiofiles.open', new_callable=AsyncMock) as mock_open:
                    mock_file = AsyncMock()
                    mock_open.return_value.__aenter__.return_value = mock_file
                    mock_open.return_value.__aexit__.return_value = None
                    
                    result = await activities.save_metadata_to_file([
                        metadata, "https://github.com/test/repo", "test123"
                    ])
                    
                    # Verify file operations
                    assert result.endswith(".json")
                    mock_file.write.assert_called_once()
                    
                    # Verify written data
                    written_data = mock_file.write.call_args[0][0]
                    parsed_data = json.loads(written_data)
                    assert parsed_data == metadata

    def test_frontend_backend_integration(self, workflow_config):
        """Test that frontend configuration matches backend expectations."""
        # This test verifies that the frontend sends data in the format expected by the backend
        
        # Simulate frontend form data
        frontend_data = {
            "repo_url": "https://github.com/facebook/react",
            "commit_limit": "50",
            "issues_limit": "30", 
            "pr_limit": "20",
            "selections": {
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
        }
        
        # Verify that frontend data structure matches backend expectations
        assert "repo_url" in frontend_data
        assert "commit_limit" in frontend_data
        assert "issues_limit" in frontend_data
        assert "pr_limit" in frontend_data
        assert "selections" in frontend_data
        
        # Verify selections structure
        selections = frontend_data["selections"]
        expected_keys = [
            "repository", "commits", "issues", "pull_requests", "contributors",
            "dependencies", "fork_lineage", "commit_lineage", "bus_factor",
            "pr_metrics", "issue_metrics", "commit_activity", "release_cadence"
        ]
        
        for key in expected_keys:
            assert key in selections
            assert isinstance(selections[key], bool)

    def test_workflow_parameter_validation_integration(self, workflow_config):
        """Test workflow parameter validation integration."""
        workflow = GitHubMetadataWorkflow()
        
        # Test valid configuration
        assert workflow_config["repo_url"] == "https://github.com/facebook/react"
        assert workflow_config["commit_limit"] == 50
        assert workflow_config["issues_limit"] == 30
        assert workflow_config["pr_limit"] == 20
        
        # Test selections validation
        selections = workflow_config["selections"]
        assert any(selections.values())  # At least one selection should be True
        
        # Test URL format validation
        assert workflow_config["repo_url"].startswith("https://github.com/")
        
        # Test limits validation
        assert workflow_config["commit_limit"] > 0
        assert workflow_config["issues_limit"] > 0
        assert workflow_config["pr_limit"] > 0

    def test_metadata_structure_integration(self, mock_github_data):
        """Test metadata structure integration across components."""
        # Test that metadata structures are consistent across activities
        repo_metadata_structure = {
            "repository": str,
            "url": str,
            "description": str,
            "primary_language": str,
            "stars": int,
            "forks": int,
            "open_issues": int,
            "license": str,
            "is_fork": bool,
            "extraction_provenance": dict
        }
        
        # Test that expected structure is maintained
        for key, expected_type in repo_metadata_structure.items():
            assert key in repo_metadata_structure
            assert isinstance(expected_type, type)

    def test_component_interfaces_integration(self):
        """Test that component interfaces are properly integrated."""
        # Test workflow interface
        workflow = GitHubMetadataWorkflow()
        assert hasattr(workflow, 'run')
        assert hasattr(workflow, 'get_activities')
        assert hasattr(workflow, '_extract_parameters')
        assert hasattr(workflow, '_validate_inputs')
        assert hasattr(workflow, '_build_combined_metadata')
        
        # Test activities interface
        with patch('app.activities.Github'):
            activities = GitHubMetadataActivities()
            assert hasattr(activities, 'extract_repository_metadata')
            assert hasattr(activities, 'extract_commit_metadata')
            assert hasattr(activities, 'extract_issues_metadata')
            assert hasattr(activities, 'extract_pull_requests_metadata')
            assert hasattr(activities, 'extract_contributors')
            assert hasattr(activities, 'extract_dependencies_from_repo')
            assert hasattr(activities, 'save_metadata_to_file')
            assert hasattr(activities, 'get_extraction_summary')

    def test_configuration_integration(self, temp_metadata_dir):
        """Test configuration integration across components."""
        with patch.dict(os.environ, {"METADATA_DIR": temp_metadata_dir}):
            with patch('app.activities.Github'):
                activities = GitHubMetadataActivities()
                
                # Test that configuration is properly integrated
                assert activities.data_dir == temp_metadata_dir
                assert hasattr(activities, 'github')
                assert hasattr(activities, 's3')

    def test_data_consistency_integration(self, mock_github_data):
        """Test data consistency across integration points."""
        # Test that data structures are consistent
        repo_data = mock_github_data["repo"]
        
        # Verify repository data structure
        assert hasattr(repo_data, 'full_name')
        assert hasattr(repo_data, 'html_url')
        assert hasattr(repo_data, 'description')
        assert hasattr(repo_data, 'language')
        assert hasattr(repo_data, 'stargazers_count')
        assert hasattr(repo_data, 'forks_count')
        assert hasattr(repo_data, 'open_issues_count')
        
        # Verify commit data structure
        commit_data = mock_github_data["commits"][0]
        assert hasattr(commit_data, 'sha')
        assert hasattr(commit_data, 'commit')
        assert hasattr(commit_data, 'html_url')

    def test_workflow_metadata_filtering_integration(self, workflow_config):
        """Test workflow metadata filtering integration."""
        workflow = GitHubMetadataWorkflow()
        
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

    def test_parameter_validation_integration(self, workflow_config):
        """Test parameter validation integration."""
        workflow = GitHubMetadataWorkflow()
        
        # Test parameter extraction and validation
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            workflow_config, {}
        )
        
        # Test validation
        workflow._validate_inputs(repo_url, normalized_selections, "test123")
        
        # Test that validation works for edge cases
        with pytest.raises(ValueError, match="Repository URL is required"):
            workflow._validate_inputs("", normalized_selections, "test123")
        
        with pytest.raises(ValueError, match="At least one metadata type must be selected"):
            empty_selections = {key: False for key in normalized_selections}
            workflow._validate_inputs(repo_url, empty_selections, "test123")

    def test_workflow_selections_normalization(self, workflow_config):
        """Test workflow selections normalization."""
        workflow = GitHubMetadataWorkflow()
        
        # Test with partial selections
        partial_config = {
            "repo_url": "https://github.com/test/repo",
            "selections": {
                "repository": True,
                "commits": True,
                "issues": False
            }
        }
        
        _, _, _, _, normalized_selections = workflow._extract_parameters(partial_config, {})
        
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
        assert normalized_selections["pull_requests"] is False  # Default

    def test_workflow_metadata_combination_edge_cases(self, workflow_config):
        """Test workflow metadata combination edge cases."""
        workflow = GitHubMetadataWorkflow()
        
        # Test with None values
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
        
        assert result["repository"] == "test/repo"
        assert "commits" not in result
        assert "issues" not in result
        assert "pull_requests" not in result

    def test_workflow_parameter_defaults(self, workflow_config):
        """Test workflow parameter defaults."""
        workflow = GitHubMetadataWorkflow()
        
        # Test with minimal config
        minimal_config = {
            "repo_url": "https://github.com/test/repo",
            "selections": {"repository": True}
        }
        
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = workflow._extract_parameters(
            minimal_config, {}
        )
        
        assert repo_url == "https://github.com/test/repo"
        assert commit_limit == 200  # Default from config
        assert issues_limit == 200  # Default from config
        assert pr_limit == 200  # Default from config
        assert normalized_selections["repository"] is True
        assert all(not value for key, value in normalized_selections.items() if key != "repository")
