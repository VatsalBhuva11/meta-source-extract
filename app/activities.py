import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
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
        # Initialize GitHub client with token if available
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            self.github = Github(github_token)
        else:
            self.github = Github()  # Unauthenticated requests (rate limited)
        
        # Create data directory if it doesn't exist
        self.data_dir = "extracted_metadata"
        os.makedirs(self.data_dir, exist_ok=True)

    def _extract_repo_info_from_url(self, repo_url: str) -> tuple[str, str]:
        """Extract owner and repo name from GitHub URL."""
        parsed = urlparse(repo_url)
        if parsed.netloc not in ["github.com", "www.github.com"]:
            raise ValueError("Invalid GitHub URL")
        
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 2:
            raise ValueError("Invalid GitHub repository URL format")
        
        owner = path_parts[0]
        repo_name = path_parts[1]
        return owner, repo_name

    @activity.defn
    async def get_workflow_args(self, workflow_config: Dict[str, Any]) -> Dict[str, Any]:
        """Get workflow arguments from configuration."""
        logger.info(f"Received workflow_config: {workflow_config}")
        
        if isinstance(workflow_config, dict):
            if "repo_url" in workflow_config:
                return workflow_config
            for key, value in workflow_config.items():
                if isinstance(value, dict) and "repo_url" in value:
                    return value
            
            logger.warning(f"No repo_url found in workflow_config. Available keys: {list(workflow_config.keys())}")
            logger.warning(f"Full workflow_config content: {json.dumps(workflow_config, indent=2)}")
        
        return workflow_config

    @activity.defn
    async def extract_repository_metadata(self, repo_url: str) -> Dict[str, Any]:
        """Extract basic repository metadata."""
        logger.info(f"Extracting metadata for repository: {repo_url}")
        
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")
            
            metadata = {
                "url": repo_url, "owner": owner, "name": repo_name, "full_name": repo.full_name,
                "description": repo.description, "language": repo.language, "languages": list(repo.get_languages().keys()),
                "stars": repo.stargazers_count, "forks": repo.forks_count, "watchers": repo.watchers_count,
                "open_issues": repo.open_issues_count, "created_at": repo.created_at.isoformat() if repo.created_at else None,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else None, "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
                "size": repo.size, "default_branch": repo.default_branch, "topics": repo.get_topics(),
                "license": repo.license.name if repo.license else None, "archived": repo.archived,
                "disabled": repo.disabled, "private": repo.private, "visibility": repo.visibility,
                "homepage": repo.homepage, "has_issues": repo.has_issues, "has_projects": repo.has_projects,
                "has_wiki": repo.has_wiki, "has_pages": repo.has_pages, "has_downloads": repo.has_downloads,
                "allow_squash_merge": repo.allow_squash_merge, "allow_merge_commit": repo.allow_merge_commit,
                "allow_rebase_merge": repo.allow_rebase_merge, "extraction_timestamp": datetime.now().isoformat(),
            }
            
            logger.info(f"Successfully extracted metadata for {repo.full_name}")
            return metadata
            
        except Exception as e:
            logger.error(f"Error extracting repository metadata: {str(e)}")
            raise

    @activity.defn
    async def extract_commit_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """Extract recent commit metadata."""
        repo_url, limit = args
        logger.info(f"Extracting commit metadata for repository: {repo_url}")
        
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")
            
            commits = []
            for commit in repo.get_commits()[:limit]:
                commit_data = {
                    "sha": commit.sha, "message": commit.commit.message,
                    "author": {"name": commit.commit.author.name, "email": commit.commit.author.email, "date": commit.commit.author.date.isoformat() if commit.commit.author.date else None},
                    "committer": {"name": commit.commit.committer.name, "email": commit.commit.committer.email, "date": commit.commit.committer.date.isoformat() if commit.commit.committer.date else None},
                    "url": commit.html_url,
                    "stats": {"additions": commit.stats.additions, "deletions": commit.stats.deletions, "total": commit.stats.total} if commit.stats else None,
                }
                commits.append(commit_data)
            
            logger.info(f"Successfully extracted {len(commits)} commits for {repo.full_name}")
            return commits
            
        except Exception as e:
            logger.error(f"Error extracting commit metadata: {str(e)}")
            raise

    @activity.defn
    async def extract_issues_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """Extract issues metadata."""
        repo_url, limit = args
        logger.info(f"Extracting issues metadata for repository: {repo_url}")
        
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")
            
            issues = []
            for issue in repo.get_issues(state="all")[:limit]:
                issue_data = {
                    "number": issue.number, "title": issue.title, "body": issue.body, "state": issue.state,
                    "user": {"login": issue.user.login, "id": issue.user.id, "type": issue.user.type} if issue.user else None,
                    "labels": [{"name": label.name, "color": label.color} for label in issue.labels],
                    "assignees": [{"login": assignee.login, "id": assignee.id} for assignee in issue.assignees],
                    "milestone": {"title": issue.milestone.title, "number": issue.milestone.number, "state": issue.milestone.state} if issue.milestone else None,
                    "created_at": issue.created_at.isoformat() if issue.created_at else None, "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
                    "closed_at": issue.closed_at.isoformat() if issue.closed_at else None, "url": issue.html_url,
                    "comments": issue.comments, "is_pull_request": issue.pull_request is not None,
                }
                issues.append(issue_data)
            
            logger.info(f"Successfully extracted {len(issues)} issues for {repo.full_name}")
            return issues
            
        except Exception as e:
            logger.error(f"Error extracting issues metadata: {str(e)}")
            raise

    @activity.defn
    async def extract_pull_requests_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """Extract pull requests metadata."""
        repo_url, limit = args
        logger.info(f"Extracting pull requests metadata for repository: {repo_url}")
        
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = self.github.get_repo(f"{owner}/{repo_name}")
            
            pull_requests = []
            for pr in repo.get_pulls(state="all")[:limit]:
                pr_data = {
                    "number": pr.number, "title": pr.title, "body": pr.body, "state": pr.state,
                    "user": {"login": pr.user.login, "id": pr.user.id, "type": pr.user.type} if pr.user else None,
                    "head": {"ref": pr.head.ref, "sha": pr.head.sha, "label": pr.head.label},
                    "base": {"ref": pr.base.ref, "sha": pr.base.sha, "label": pr.base.label},
                    "labels": [{"name": label.name, "color": label.color} for label in pr.labels],
                    "assignees": [{"login": assignee.login, "id": assignee.id} for assignee in pr.assignees],
                    "milestone": {"title": pr.milestone.title, "number": pr.milestone.number, "state": pr.milestone.state} if pr.milestone else None,
                    "created_at": pr.created_at.isoformat() if pr.created_at else None, "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                    "closed_at": pr.closed_at.isoformat() if pr.closed_at else None, "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                    "url": pr.html_url, "comments": pr.comments, "review_comments": pr.review_comments,
                    "commits": pr.commits, "additions": pr.additions, "deletions": pr.deletions,
                    "changed_files": pr.changed_files, "draft": pr.draft, "mergeable": pr.mergeable,
                    "mergeable_state": pr.mergeable_state, "merged": pr.merged,
                }
                pull_requests.append(pr_data)
            
            logger.info(f"Successfully extracted {len(pull_requests)} pull requests for {repo.full_name}")
            return pull_requests
            
        except Exception as e:
            logger.error(f"Error extracting pull requests metadata: {str(e)}")
            raise

    @activity.defn
    async def save_metadata_to_file(self, args: List[Any]) -> str:
        """Save extracted metadata to JSON file."""
        metadata, repo_url = args  # <-- FIXED: Unpack arguments from the list
        logger.info(f"Saving metadata to file for repository: {repo_url}")
        
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            filename = f"{owner}_{repo_name}_metadata.json"
            filepath = os.path.join(self.data_dir, filename)
            
            async with aiofiles.open(filepath, 'w') as f:
                await f.write(json.dumps(metadata, indent=2, default=str))
            
            logger.info(f"Metadata saved to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error saving metadata to file: {str(e)}")
            raise

    @activity.defn
    async def get_extraction_summary(self, args: List[Any]) -> Dict[str, Any]:
        """Generate a summary of the extraction process."""
        repo_url, metadata = args # <-- FIXED: Unpack arguments from the list
        logger.info(f"Generating extraction summary for repository: {repo_url}")
        
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            
            summary = {
                "repository": f"{owner}/{repo_name}", "url": repo_url, "extraction_timestamp": datetime.now().isoformat(),
                "total_commits_extracted": len(metadata.get("commits", [])),
                "total_issues_extracted": len(metadata.get("issues", [])),
                "total_pull_requests_extracted": len(metadata.get("pull_requests", [])),
                "repository_stats": {
                    "stars": metadata.get("stars", 0), "forks": metadata.get("forks", 0),
                    "watchers": metadata.get("watchers", 0), "open_issues": metadata.get("open_issues", 0),
                    "size": metadata.get("size", 0), "languages": metadata.get("languages", []),
                },
                "file_saved": metadata.get("file_path", "Not saved"),
            }
            
            logger.info(f"Extraction summary generated for {owner}/{repo_name}")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating extraction summary: {str(e)}")
            raise
