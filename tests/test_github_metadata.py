import pytest
from app.activities import GitHubMetadataActivities
import os

class TestGitHubMetadataActivities:
    def test_extract_repo_info_from_url(self):
        activities = GitHubMetadataActivities()
        
        # Test valid GitHub URL
        owner, repo = activities._extract_repo_info_from_url("https://github.com/VatsalBhuva11/EcoBloom/")
        assert owner == "VatsalBhuva11"
        assert repo == "EcoBloom"
        
        # Test URL with www
        owner, repo = activities._extract_repo_info_from_url("https://www.github.com/facebook/react")
        assert owner == "facebook"
        assert repo == "react"
        
        # Test invalid URL
        with pytest.raises(ValueError):
            activities._extract_repo_info_from_url("https://gitlab.com/user/repo")
        
        # Test malformed URL
        with pytest.raises(ValueError):
            activities._extract_repo_info_from_url("https://github.com/user")

    def test_data_directory_creation(self):
        activities = GitHubMetadataActivities()
        assert activities.data_dir == "extracted_metadata"
        # The directory should be created in __init__
        assert os.path.exists(activities.data_dir)