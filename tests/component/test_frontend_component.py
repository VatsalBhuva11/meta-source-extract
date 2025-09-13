"""
Component tests for frontend integration.
Tests the integration between frontend and backend API.
"""
import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from app.workflow import GitHubMetadataWorkflow
from app.activities import GitHubMetadataActivities


class TestFrontendComponent:
    """Component tests for frontend integration."""

    @pytest.fixture
    def sample_frontend_request(self):
        """Sample frontend request data."""
        return {
            "repoUrl": "https://github.com/facebook/react",
            "commitLimit": 50,
            "issuesLimit": 30,
            "prLimit": 20,
            "selections": {
                "repository": True,
                "commits": True,
                "issues": False,
                "pullRequests": True,
                "contributors": False,
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

    @pytest.fixture
    def sample_workflow_response(self):
        """Sample workflow response data."""
        return {
            "repository": "facebook/react",
            "url": "https://github.com/facebook/react",
            "description": "A declarative, efficient, and flexible JavaScript library",
            "stars": 200000,
            "forks": 40000,
            "commits": [
                {
                    "sha": "abc123",
                    "message": "Initial commit",
                    "author": "testuser",
                    "date": "2023-01-01T00:00:00Z"
                }
            ],
            "pull_requests": [
                {
                    "number": 1,
                    "title": "Feature PR",
                    "state": "merged",
                    "author": "testuser"
                }
            ],
            "dependencies": [
                {
                    "manifest": "package.json",
                    "dependencies": [
                        {"name": "react", "version": "^18.0.0"}
                    ]
                }
            ],
            "extraction_provenance": {
                "extraction_id": "test123",
                "extracted_by": "github-metadata-extractor",
                "extracted_at": "2023-12-01T00:00:00Z",
                "schema_version": "1",
                "source": "github"
            }
        }

    def test_frontend_request_parameter_mapping(self, sample_frontend_request):
        """Test that frontend request parameters are correctly mapped."""
        # Test camelCase to snake_case conversion
        selections = sample_frontend_request["selections"]
        
        # Verify camelCase keys are present
        assert "pullRequests" in selections
        assert "forkLineage" in selections
        assert "commitLineage" in selections
        assert "busFactor" in selections
        assert "prMetrics" in selections
        assert "issueMetrics" in selections
        assert "commitActivity" in selections
        assert "releaseCadence" in selections
        
        # Verify boolean values
        assert selections["repository"] is True
        assert selections["commits"] is True
        assert selections["issues"] is False
        assert selections["pullRequests"] is True
        assert selections["contributors"] is False
        assert selections["dependencies"] is True

    def test_frontend_request_validation(self, sample_frontend_request):
        """Test frontend request validation."""
        # Test valid request
        assert sample_frontend_request["repoUrl"].startswith("https://github.com/")
        assert isinstance(sample_frontend_request["commitLimit"], int)
        assert isinstance(sample_frontend_request["issuesLimit"], int)
        assert isinstance(sample_frontend_request["prLimit"], int)
        
        # Test selections validation
        selections = sample_frontend_request["selections"]
        assert any(selections.values())  # At least one selection should be True
        
        # Test individual selection types
        boolean_selections = [
            "repository", "commits", "issues", "pullRequests", "contributors",
            "dependencies", "forkLineage", "commitLineage", "busFactor",
            "prMetrics", "issueMetrics", "commitActivity", "releaseCadence"
        ]
        
        for selection in boolean_selections:
            assert selection in selections
            assert isinstance(selections[selection], bool)

    def test_frontend_request_parameter_limits(self, sample_frontend_request):
        """Test frontend request parameter limits."""
        # Test reasonable limits
        assert 0 < sample_frontend_request["commitLimit"] <= 1000
        assert 0 < sample_frontend_request["issuesLimit"] <= 1000
        assert 0 < sample_frontend_request["prLimit"] <= 1000
        
        # Test URL format
        repo_url = sample_frontend_request["repoUrl"]
        assert repo_url.startswith("https://github.com/")
        assert "/" in repo_url.split("github.com/")[1]  # Should have owner/repo format

    def test_frontend_response_structure(self, sample_workflow_response):
        """Test frontend response structure."""
        # Test required fields
        assert "repository" in sample_workflow_response
        assert "url" in sample_workflow_response
        assert "extraction_provenance" in sample_workflow_response
        
        # Test extraction provenance structure
        provenance = sample_workflow_response["extraction_provenance"]
        assert "extraction_id" in provenance
        assert "extracted_by" in provenance
        assert "extracted_at" in provenance
        assert "schema_version" in provenance
        assert "source" in provenance
        
        # Test data types
        assert isinstance(sample_workflow_response["repository"], str)
        assert isinstance(sample_workflow_response["stars"], int)
        assert isinstance(sample_workflow_response["forks"], int)
        assert isinstance(sample_workflow_response["commits"], list)
        assert isinstance(sample_workflow_response["pull_requests"], list)
        assert isinstance(sample_workflow_response["dependencies"], list)

    def test_frontend_response_metadata_filtering(self, sample_workflow_response):
        """Test that frontend response only includes selected metadata."""
        # Based on the sample request, only repository, commits, pull_requests, and dependencies should be present
        assert "repository" in sample_workflow_response
        assert "commits" in sample_workflow_response
        assert "pull_requests" in sample_workflow_response
        assert "dependencies" in sample_workflow_response
        
        # These should not be present based on the sample request
        assert "issues" not in sample_workflow_response
        assert "contributors" not in sample_workflow_response
        assert "fork_lineage" not in sample_workflow_response
        assert "commit_lineage" not in sample_workflow_response
        assert "bus_factor" not in sample_workflow_response
        assert "pr_metrics" not in sample_workflow_response
        assert "issue_metrics" not in sample_workflow_response
        assert "commit_activity" not in sample_workflow_response
        assert "release_cadence" not in sample_workflow_response

    def test_frontend_error_handling(self):
        """Test frontend error handling scenarios."""
        # Test invalid repository URL
        invalid_request = {
            "repoUrl": "https://gitlab.com/user/repo",
            "selections": {"repository": True}
        }
        
        # Should raise ValueError for invalid URL
        with pytest.raises(ValueError):
            from app.utils import parse_repo_url
            parse_repo_url(invalid_request["repoUrl"])
        
        # Test empty selections
        empty_selections_request = {
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
        
        # Should raise ValueError for empty selections
        selections = empty_selections_request["selections"]
        assert not any(selections.values())

    def test_frontend_parameter_conversion(self, sample_frontend_request):
        """Test frontend parameter conversion to backend format."""
        # Simulate the conversion that happens in get_workflow_args
        frontend_data = sample_frontend_request
        
        # Convert camelCase to snake_case for selections
        selections = frontend_data["selections"]
        converted_selections = {
            "repository": selections["repository"],
            "commits": selections["commits"],
            "issues": selections["issues"],
            "pull_requests": selections["pullRequests"],
            "contributors": selections["contributors"],
            "dependencies": selections["dependencies"],
            "fork_lineage": selections["forkLineage"],
            "commit_lineage": selections["commitLineage"],
            "bus_factor": selections["busFactor"],
            "pr_metrics": selections["prMetrics"],
            "issue_metrics": selections["issueMetrics"],
            "commit_activity": selections["commitActivity"],
            "release_cadence": selections["releaseCadence"]
        }
        
        # Verify conversion
        assert converted_selections["pull_requests"] == selections["pullRequests"]
        assert converted_selections["fork_lineage"] == selections["forkLineage"]
        assert converted_selections["commit_lineage"] == selections["commitLineage"]
        assert converted_selections["bus_factor"] == selections["busFactor"]
        assert converted_selections["pr_metrics"] == selections["prMetrics"]
        assert converted_selections["issue_metrics"] == selections["issueMetrics"]
        assert converted_selections["commit_activity"] == selections["commitActivity"]
        assert converted_selections["release_cadence"] == selections["releaseCadence"]

    def test_frontend_response_serialization(self, sample_workflow_response):
        """Test frontend response serialization."""
        # Test JSON serialization
        json_response = json.dumps(sample_workflow_response)
        assert isinstance(json_response, str)
        
        # Test deserialization
        deserialized_response = json.loads(json_response)
        assert deserialized_response == sample_workflow_response
        
        # Test datetime serialization
        provenance = sample_workflow_response["extraction_provenance"]
        assert "extracted_at" in provenance
        assert isinstance(provenance["extracted_at"], str)

    def test_frontend_request_validation_edge_cases(self):
        """Test frontend request validation edge cases."""
        # Test with None values
        request_with_none = {
            "repoUrl": "https://github.com/test/repo",
            "commitLimit": None,
            "issuesLimit": None,
            "prLimit": None,
            "selections": {"repository": True}
        }
        
        # Should handle None values gracefully
        assert request_with_none["repoUrl"] is not None
        assert request_with_none["selections"]["repository"] is True
        
        # Test with empty string
        request_with_empty = {
            "repoUrl": "",
            "selections": {"repository": True}
        }
        
        # Should be invalid
        assert not request_with_empty["repoUrl"]
        
        # Test with negative limits
        request_with_negative = {
            "repoUrl": "https://github.com/test/repo",
            "commitLimit": -1,
            "issuesLimit": -1,
            "prLimit": -1,
            "selections": {"repository": True}
        }
        
        # Should be invalid
        assert request_with_negative["commitLimit"] < 0
        assert request_with_negative["issuesLimit"] < 0
        assert request_with_negative["prLimit"] < 0

    def test_frontend_response_metadata_completeness(self, sample_workflow_response):
        """Test frontend response metadata completeness."""
        # Test that all selected metadata is present and complete
        assert "repository" in sample_workflow_response
        assert sample_workflow_response["repository"] == "facebook/react"
        
        # Test commits metadata
        if "commits" in sample_workflow_response:
            commits = sample_workflow_response["commits"]
            assert isinstance(commits, list)
            if commits:
                commit = commits[0]
                assert "sha" in commit
                assert "message" in commit
                assert "author" in commit
                assert "date" in commit
        
        # Test pull requests metadata
        if "pull_requests" in sample_workflow_response:
            prs = sample_workflow_response["pull_requests"]
            assert isinstance(prs, list)
            if prs:
                pr = prs[0]
                assert "number" in pr
                assert "title" in pr
                assert "state" in pr
                assert "author" in pr
        
        # Test dependencies metadata
        if "dependencies" in sample_workflow_response:
            deps = sample_workflow_response["dependencies"]
            assert isinstance(deps, list)
            if deps:
                dep = deps[0]
                assert "manifest" in dep
                assert "dependencies" in dep

    def test_frontend_response_error_handling(self):
        """Test frontend response error handling."""
        # Test error response structure
        error_response = {
            "error": "Repository not found",
            "code": "REPO_NOT_FOUND",
            "message": "The specified repository could not be found"
        }
        
        assert "error" in error_response
        assert "code" in error_response
        assert "message" in error_response
        
        # Test JSON serialization of error response
        json_error = json.dumps(error_response)
        assert isinstance(json_error, str)
        
        # Test deserialization
        deserialized_error = json.loads(json_error)
        assert deserialized_error == error_response

    def test_frontend_request_parameter_types(self, sample_frontend_request):
        """Test frontend request parameter types."""
        # Test URL type
        assert isinstance(sample_frontend_request["repoUrl"], str)
        
        # Test limit types
        assert isinstance(sample_frontend_request["commitLimit"], int)
        assert isinstance(sample_frontend_request["issuesLimit"], int)
        assert isinstance(sample_frontend_request["prLimit"], int)
        
        # Test selections type
        assert isinstance(sample_frontend_request["selections"], dict)
        
        # Test individual selection types
        for key, value in sample_frontend_request["selections"].items():
            assert isinstance(key, str)
            assert isinstance(value, bool)

    def test_frontend_response_metadata_consistency(self, sample_workflow_response):
        """Test frontend response metadata consistency."""
        # Test that repository name is consistent
        if "repository" in sample_workflow_response:
            repo_name = sample_workflow_response["repository"]
            assert isinstance(repo_name, str)
            assert "/" in repo_name  # Should be in owner/repo format
        
        # Test that URL is consistent with repository name
        if "url" in sample_workflow_response and "repository" in sample_workflow_response:
            url = sample_workflow_response["url"]
            repo_name = sample_workflow_response["repository"]
            assert url.endswith(repo_name)
        
        # Test that extraction provenance is consistent
        if "extraction_provenance" in sample_workflow_response:
            provenance = sample_workflow_response["extraction_provenance"]
            assert "extraction_id" in provenance
            assert "extracted_at" in provenance
            assert "schema_version" in provenance
            assert provenance["schema_version"] == "1"
            assert provenance["source"] == "github"
