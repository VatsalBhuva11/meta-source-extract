import json
import os
from datetime import datetime
from typing import Any, Dict, List
from urllib.parse import urlparse

import aiofiles
from application_sdk.activities import ActivitiesInterface
from application_sdk.observability.logger_adaptor import get_logger
from github import Github
from temporalio import activity

logger = get_logger(__name__)
activity.logger = logger


class GitHubMetadataActivities(ActivitiesInterface):
    def __init__(self):
        github_token = os.getenv("GITHUB_TOKEN")
        self.github = Github(github_token) if github_token else Github()
        self.data_dir = "extracted_metadata"
        os.makedirs(self.data_dir, exist_ok=True)

    def _extract_repo_info_from_url(self, repo_url: str) -> tuple[str, str]:
        parsed = urlparse(repo_url)
        if parsed.netloc not in ["github.com", "www.github.com"]:
            raise ValueError("Invalid GitHub URL")
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise ValueError("Invalid GitHub repository URL format")
        return path_parts[0], path_parts[1]

    @activity.defn
    async def extract_repository_metadata(self, repo_url: str) -> Dict[str, Any]:
        """Extract essential repository metadata."""
        logger.info(f"Extracting metadata for repository: {repo_url}")
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")

            metadata = {
                "repository": repo.full_name,
                "url": repo.html_url,
                "description": repo.description,
                "primary_language": repo.language,
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "open_issues": repo.open_issues_count,
                "created_at": repo.created_at.isoformat() if repo.created_at else None,
                "last_updated": repo.updated_at.isoformat() if repo.updated_at else None,
                "default_branch": repo.default_branch,
                "extraction_timestamp": datetime.now().isoformat(),
            }
            return metadata
        except Exception as e:
            logger.error(f"Error extracting repository metadata: {str(e)}")
            raise

    @activity.defn
    async def extract_commit_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """Extract essential commit metadata (recent)."""
        repo_url, limit = args
        logger.info(f"Extracting commit metadata for {repo_url}")
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")

            commits: List[Dict[str, Any]] = []
            for commit in repo.get_commits().get_page(0)[:limit]:
                commits.append({
                    "sha": commit.sha,
                    "message": commit.commit.message,
                    "author": commit.commit.author.name if commit.commit.author else None,
                    "date": commit.commit.author.date.isoformat() if commit.commit.author and commit.commit.author.date else None,
                })
            return commits
        except Exception as e:
            logger.error(f"Error extracting commit metadata: {str(e)}")
            raise

    @activity.defn
    async def extract_issues_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """Extract essential issues metadata."""
        repo_url, limit = args
        logger.info(f"Extracting issues metadata for {repo_url}")
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")

            issues: List[Dict[str, Any]] = []
            for issue in repo.get_issues(state="all").get_page(0)[:limit]:
                issues.append({
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "author": issue.user.login if issue.user else None,
                    "labels": [label.name for label in issue.labels],
                    "created_at": issue.created_at.isoformat() if issue.created_at else None,
                    "closed_at": issue.closed_at.isoformat() if issue.closed_at else None,
                })
            return issues
        except Exception as e:
            logger.error(f"Error extracting issues metadata: {str(e)}")
            raise

    @activity.defn
    async def extract_pull_requests_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """Extract essential pull requests metadata."""
        repo_url, limit = args
        logger.info(f"Extracting pull requests metadata for {repo_url}")
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")

            prs: List[Dict[str, Any]] = []
            for pr in repo.get_pulls(state="all").get_page(0)[:limit]:
                prs.append({
                    "number": pr.number,
                    "title": pr.title,
                    "state": pr.state,
                    "author": pr.user.login if pr.user else None,
                    "created_at": pr.created_at.isoformat() if pr.created_at else None,
                    "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
                    "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                    "merged": pr.merged,
                })
            return prs
        except Exception as e:
            logger.error(f"Error extracting PR metadata: {str(e)}")
            raise

    @activity.defn
    async def get_extraction_summary(self, args: List[Any]) -> Dict[str, Any]:
        """Generate a clean summary."""
        repo_url, metadata = args
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            summary = {
                "repository": f"{owner}/{repo_name}",
                "url": repo_url,
                "extracted_at": datetime.now().isoformat(),
                "commits_count": len(metadata.get("commits", [])),
                "issues_count": len(metadata.get("issues", [])),
                "prs_count": len(metadata.get("pull_requests", [])),
                "stars": metadata.get("stars", 0),
                "forks": metadata.get("forks", 0),
                "open_issues": metadata.get("open_issues", 0),
            }
            return summary
        except Exception as e:
            logger.error(f"Error generating extraction summary: {str(e)}")
            raise

    @activity.defn
    async def save_metadata_to_file(self, args: List[Any]) -> str:
        """
        Save extracted metadata to a JSON file.

        Expects args == [metadata_dict, repo_url]
        Returns the full filepath of the saved JSON file.
        """
        metadata, repo_url = args
        logger.info(f"Saving metadata to file for repository: {repo_url}")

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            filename = f"{owner}_{repo_name}_metadata.json"
            filepath = os.path.join(self.data_dir, filename)

            async with aiofiles.open(filepath, "w") as f:
                # default=str for datetime serialization safety
                await f.write(json.dumps(metadata, indent=2, default=str))

            logger.info(f"Metadata saved to: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error saving metadata to file: {str(e)}")
            raise
