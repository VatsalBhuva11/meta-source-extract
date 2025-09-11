import json
import os
import re
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

import aiofiles
from application_sdk.activities import ActivitiesInterface
from application_sdk.observability.logger_adaptor import get_logger
from application_sdk.activities.common.utils import auto_heartbeater

from temporalio import activity

# optional libraries
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
except Exception:
    # fallback no-op retry if tenacity isn't available
    def retry(*args, **kwargs):
        def deco(f):
            return f
        return deco

try:
    import boto3
    from botocore.exceptions import BotoCoreError
except Exception:
    boto3 = None
    BotoCoreError = Exception

try:
    from github import Github
except Exception:
    raise RuntimeError("PyGithub (github) library is required. Add `PyGithub` to requirements.")

from app.config import (
    METADATA_DIR,
    METADATA_UPLOAD_TO_S3,
    S3_BUCKET,
    SCHEMA_VERSION,
    GITHUB_API_PER_PAGE,
    DEFAULT_USER_AGENT,
)
from app.utils import (
    safe_isoformat,
    parse_repo_url,
)
from app.resilience import _get_from_cache, _set_cache, circuit_breaker

logger = get_logger(__name__)
activity.logger = logger


class GitHubMetadataActivities(ActivitiesInterface):
    def __init__(self):
        github_token = os.getenv("GITHUB_TOKEN")
        self.github = Github(login_or_token=github_token, per_page=GITHUB_API_PER_PAGE, user_agent=DEFAULT_USER_AGENT)
        self.data_dir = METADATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)
        # optional s3 client
        if METADATA_UPLOAD_TO_S3 and boto3:
            self.s3 = boto3.client("s3")
        else:
            self.s3 = None

    # helpers
    def _extract_repo_info_from_url(self, repo_url: str) -> Tuple[str, str]:
        owner, repo = parse_repo_url(repo_url)
        return owner, repo

    def _get_filepath(self, owner: str, repo_name: str, extraction_id: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{owner}_{repo_name}_schema{SCHEMA_VERSION}_{extraction_id}_{ts}.json"
        return os.path.join(self.data_dir, filename)

    # retry wrapper for github calls
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(Exception))
    def _get_repo(self, full_name: str):
        return self.github.get_repo(full_name)

    @activity.defn
    # critical path (no breaker)
    @auto_heartbeater
    async def extract_repository_metadata(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [repo_url, extraction_id]
        """
        repo_url, extraction_id = args
        logger.info("Extracting repository metadata", extra={"repo_url": repo_url, "extraction_id": extraction_id})
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            full_name = f"{owner}/{repo_name}"

            repo = await asyncio.to_thread(self._get_repo, full_name)

            metadata = {
                "repository": repo.full_name,
                "url": repo.html_url,
                "description": repo.description,
                "primary_language": repo.language,
                "languages": repo.get_languages(),
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "open_issues": repo.open_issues_count,
                "created_at": safe_isoformat(repo.created_at),
                "last_updated": safe_isoformat(repo.updated_at),
                "default_branch": repo.default_branch,
                "license": repo.get_license().license.spdx_id if self._safe_call(lambda: repo.get_license()) else None,
                "is_fork": repo.fork,
                "html_url": repo.html_url,
                "extraction_provenance": {
                    "extraction_id": extraction_id,
                    "extracted_by": "github-metadata-extractor",
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "schema_version": SCHEMA_VERSION,
                    "source": "github",
                },
            }
            return metadata
        except Exception as e:
            logger.error("Error extracting repository metadata", exc_info=e, extra={"repo_url": repo_url})
            raise

    def _safe_call(self, func):
        try:
            return func()
        except Exception:
            return None

    def _paginator(self, pager, limit: Optional[int] = None):
        items = []
        try:
            for page in pager:
                for item in page:
                    items.append(item)
                    if limit and len(items) >= limit:
                        return items
            return items
        except Exception as e:
            logger.error("Paginator error", exc_info=e)
            raise

    # caching + breaker
    @activity.defn(name="extract_commit_metadata")
    @auto_heartbeater
    @circuit_breaker
    #
    # rationale
    # - this can produce many calls; failures should open the breaker to avoid
    #   repeated pressure on the api; successful runs are cached by repo+limit
    #
    async def extract_commit_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """
        args: [repo_url, limit, extraction_id]
        """
        repo_url, limit, extraction_id = args
        logger.info("Extracting commit metadata", extra={"repo_url": repo_url, "limit": limit, "extraction_id": extraction_id})

        cached_result = _get_from_cache(repo_url, "commit_metadata", limit=limit)
        if cached_result is not None:
            return cached_result

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")

            commits = []
            for commit in repo.get_commits():
                if limit and len(commits) >= limit:
                    break
                author_name = None
                commit_author = getattr(commit.commit, "author", None)
                if commit_author:
                    author_name = commit_author.name
                commits.append({
                    "sha": commit.sha,
                    "message": commit.commit.message,
                    "author": author_name,
                    "date": safe_isoformat(commit.commit.author.date) if commit.commit.author and commit.commit.author.date else None,
                    "url": getattr(commit, "html_url", None),
                })

            _set_cache(repo_url, "commit_metadata", commits, ttl=900, limit=limit)
            return commits
        except Exception as e:
            logger.error("Error extracting commits", exc_info=e, extra={"repo_url": repo_url})
            raise

    # caching + breaker
    @activity.defn(name="extract_issues_metadata")
    @auto_heartbeater
    @circuit_breaker
    #
    # rationale
    # - non-critical to the core repo fetch; protects against transient api
    #   failures and benefits from caching per repo+limit
    #
    async def extract_issues_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """
        args: [repo_url, limit, extraction_id]
        """
        repo_url, limit, extraction_id = args
        logger.info("Extracting issues metadata", extra={"repo_url": repo_url, "limit": limit, "extraction_id": extraction_id})

        cached_result = _get_from_cache(repo_url, "issues_metadata", limit=limit)
        if cached_result is not None:
            return cached_result

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")

            issues = []
            for issue in repo.get_issues(state="all"):
                if limit and len(issues) >= limit:
                    break
                issues.append({
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "author": issue.user.login if issue.user else None,
                    "labels": [label.name for label in issue.labels],
                    "created_at": safe_isoformat(issue.created_at),
                    "closed_at": safe_isoformat(issue.closed_at),
                    "url": issue.html_url,
                })

            _set_cache(repo_url, "issues_metadata", issues, ttl=900, limit=limit)
            return issues
        except Exception as e:
            logger.error("Error extracting issues", exc_info=e, extra={"repo_url": repo_url})
            raise

    # caching + breaker
    @activity.defn(name="extract_pull_requests_metadata")
    @auto_heartbeater
    @circuit_breaker
    #
    # rationale
    # - similar to issues/commits; breaker limits repeated failures, cache
    #   prevents redundant work within ttl
    #
    async def extract_pull_requests_metadata(self, args: List[Any]) -> List[Dict[str, Any]]:
        """
        args: [repo_url, limit, extraction_id]
        """
        repo_url, limit, extraction_id = args
        logger.info("Extracting pull request metadata", extra={"repo_url": repo_url, "limit": limit, "extraction_id": extraction_id})

        cached_result = _get_from_cache(repo_url, "pull_requests_metadata", limit=limit)
        if cached_result is not None:
            return cached_result

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")

            prs = []
            for pr in repo.get_pulls(state="all"):
                if limit and len(prs) >= limit:
                    break
                prs.append({
                    "number": pr.number,
                    "title": pr.title,
                    "state": pr.state,
                    "author": pr.user.login if pr.user else None,
                    "created_at": safe_isoformat(pr.created_at),
                    "closed_at": safe_isoformat(pr.closed_at),
                    "merged_at": safe_isoformat(pr.merged_at),
                    "merged": pr.merged,
                    "url": pr.html_url,
                })

            _set_cache(repo_url, "pull_requests_metadata", prs, ttl=900, limit=limit)
            return prs
        except Exception as e:
            logger.error("Error extracting PRs", exc_info=e, extra={"repo_url": repo_url})
            raise

    # caching + breaker
    @activity.defn(name="extract_contributors")
    @auto_heartbeater
    @circuit_breaker
    #
    # rationale
    # - safe to gate behind breaker; cached to avoid repeated listing
    #
    async def extract_contributors(self, args: List[Any]) -> List[Dict[str, Any]]:
        """
        args: [repo_url, extraction_id]
        """
        repo_url, extraction_id = args
        logger.info("Extracting contributors", extra={"repo_url": repo_url, "extraction_id": extraction_id})

        cached_result = _get_from_cache(repo_url, "contributors")
        if cached_result is not None:
            return cached_result

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")
            contributors = []
            for contributor in repo.get_contributors()[:100]:
                contributors.append({
                    "login": contributor.login,
                    "contributions": contributor.contributions,
                    "url": getattr(contributor, "html_url", None),
                })

            _set_cache(repo_url, "contributors", contributors, ttl=1800)
            return contributors
        except Exception as e:
            logger.error("Error extracting contributors", exc_info=e, extra={"repo_url": repo_url})
            raise

    # caching + breaker
    @activity.defn(name="extract_dependencies_from_repo")
    @auto_heartbeater
    @circuit_breaker
    #
    # rationale
    # - best-effort enrichment; breaker prevents repeated failures on manifest
    #   endpoints; cached results reused during ttl
    #
    async def extract_dependencies_from_repo(self, args: List[Any]) -> List[Dict[str, Any]]:
        """
        args: [repo_url, extraction_id]
        """
        repo_url, extraction_id = args
        logger.info("Extracting dependencies", extra={"repo_url": repo_url, "extraction_id": extraction_id})

        cached_result = _get_from_cache(repo_url, "dependencies")
        if cached_result is not None:
            return cached_result

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")

            default_branch = repo.default_branch
            manifests = ["package.json", "requirements.txt", "pyproject.toml", "Pipfile", "pom.xml"]
            dependencies = []

            for manifest in manifests:
                try:
                    content_file = repo.get_contents(manifest, ref=default_branch)
                    if content_file and content_file.decoded_content:
                        text = content_file.decoded_content.decode("utf-8", errors="ignore")
                        deps = self._parse_manifest_text(manifest, text)
                        if deps:
                            dependencies.append({"manifest": manifest, "dependencies": deps})
                except Exception:
                    continue

            _set_cache(repo_url, "dependencies", dependencies, ttl=3600)
            return dependencies
        except Exception as e:
            logger.error("Error extracting dependencies", exc_info=e, extra={"repo_url": repo_url})
            raise

    def _parse_manifest_text(self, manifest_name: str, text: str) -> List[Dict[str, Any]]:
        deps = []
        try:
            if manifest_name == "package.json":
                j = json.loads(text)
                for section in ("dependencies", "devDependencies"):
                    sec = j.get(section, {})
                    for name, version in sec.items():
                        deps.append({"name": name, "version": version, "scope": section})
            elif manifest_name == "requirements.txt":
                for line in text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    m = re.match(r"([^=<>!~\s]+)(==|>=|<=|>|<|~=)?(.+)?", line)
                    if m:
                        deps.append({"name": m.group(1), "version": (m.group(3) or "").strip()})
            elif manifest_name == "pyproject.toml":
                for line in text.splitlines():
                    if "name =" in line or "version =" in line:
                        continue
            elif manifest_name == "pom.xml":
                for match in re.finditer(r"<dependency>.*?</dependency>", text, flags=re.S):
                    block = match.group(0)
                    group = re.search(r"<groupId>(.*?)</groupId>", block)
                    artifact = re.search(r"<artifactId>(.*?)</artifactId>", block)
                    version = re.search(r"<version>(.*?)</version>", block)
                    deps.append({
                        "group": group.group(1) if group else None,
                        "artifact": artifact.group(1) if artifact else None,
                        "version": version.group(1) if version else None
                    })
            return deps
        except Exception as e:
            logger.warning("Manifest parsing failed", exc_info=e)
            return deps

    @activity.defn
    async def get_extraction_summary(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [repo_url, metadata, extraction_id]
        """
        repo_url, metadata, extraction_id = args
        logger.info("Generating extraction summary", extra={"extraction_id": extraction_id})
        try:
            summary = {
                "repository": metadata.get("repository"),
                "url": repo_url,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "commits_count": len(metadata.get("commits", [])),
                "issues_count": len(metadata.get("issues", [])),
                "prs_count": len(metadata.get("pull_requests", [])),
                "contributors_count": len(metadata.get("contributors", [])),
                "dependencies_count": len(metadata.get("dependencies", [])),
                "stars": metadata.get("stars", 0),
                "forks": metadata.get("forks", 0),
            }
            try:
                prs = metadata.get("pull_requests", []) or []
                merged = [p for p in prs if p.get("merged")]
                summary["pr_merge_rate"] = len(merged) / len(prs) if prs else None

                issues = metadata.get("issues", []) or []
                closed_issues = [i for i in issues if i.get("closed_at")]
                total_days = 0.0
                for i in closed_issues:
                    c = i.get("closed_at")
                    o = i.get("created_at")
                    if c and o:
                        dt_c = datetime.fromisoformat(c)
                        dt_o = datetime.fromisoformat(o)
                        total_days += (dt_c - dt_o).total_seconds()
                summary["avg_issue_resolution_seconds"] = (total_days / len(closed_issues)) if closed_issues else None
            except Exception:
                logger.debug("Failed to compute some quality metrics", extra={"extraction_id": extraction_id})

            return summary
        except Exception as e:
            logger.error("Error generating summary", exc_info=e)
            raise

    @activity.defn
    @auto_heartbeater
    async def save_metadata_to_file(self, args: List[Any]) -> str:
        """
        save extracted metadata to a json file and optionally upload to s3.
        args: [metadata_dict, repo_url, extraction_id]
        returns the full filepath (local or s3://...) of the saved json file.
        """
        metadata, repo_url, extraction_id = args
        logger.info("Saving metadata to file", extra={"repo_url": repo_url, "extraction_id": extraction_id})

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            filepath = self._get_filepath(owner, repo_name, extraction_id)
            metadata.setdefault("extraction_provenance", {})
            metadata["extraction_provenance"].update({
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "file_path": filepath,
            })

            async with aiofiles.open(filepath, "w") as f:
                await f.write(json.dumps(metadata, indent=2, default=str))

            # optional s3 upload
            #
            # rationale
            # - controlled by env (METADATA_UPLOAD_TO_S3, S3_BUCKET) so local
            #   development remains filesystem-only without extra deps
            # - on success, the s3 path is recorded alongside the local path
            #
            if self.s3 and METADATA_UPLOAD_TO_S3 and S3_BUCKET:
                key = os.path.basename(filepath)
                try:
                    self.s3.upload_file(filepath, S3_BUCKET, key)
                    s3_path = f"s3://{S3_BUCKET}/{key}"
                    metadata["extraction_provenance"]["s3_path"] = s3_path
                    logger.info("Uploaded metadata to S3", extra={"s3_path": s3_path})
                    return s3_path
                except BotoCoreError as e:
                    logger.error("Failed to upload to S3", exc_info=e, extra={"extraction_id": extraction_id})
            return filepath
        except Exception as e:
            logger.error("Error saving metadata to file", exc_info=e, extra={"repo_url": repo_url})
            raise

    @activity.defn
    @auto_heartbeater
    async def calculate_code_lineage(self, args: List[Any]) -> str:
        """
        Calculate code lineage based on commit history and present it in a readable format.
        args: [repo_url, commits, extraction_id]
        """
        repo_url, commits, extraction_id = args
        logger.info("Calculating code lineage", extra={"repo_url": repo_url, "extraction_id": extraction_id})

        if not commits:
            return "No commit history available to generate lineage."

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")

            file_lineage = defaultdict(list)
            for c in commits:
                commit_sha = c.get("sha")
                if not commit_sha:
                    continue

                commit = await asyncio.to_thread(repo.get_commit, commit_sha)
                if commit and commit.files:
                    for file in commit.files:
                        file_lineage[file.filename].append({
                            "sha": commit.sha,
                            "author": c.get("author"),
                            "date": c.get("date"),
                            "additions": file.additions,
                            "deletions": file.deletions,
                            "message": commit.commit.message.split('\n')[0] # First line of commit message
                        })

            # Format the output
            lineage_str = ""
            for filename, history in file_lineage.items():
                lineage_str += f"--- File: {filename} ---\n"
                sorted_history = sorted(history, key=lambda x: x['date'], reverse=True)
                for entry in sorted_history:
                    date_str = entry['date']
                    if date_str:
                        try:
                            date = datetime.fromisoformat(date_str).strftime('%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError):
                            date = date_str # Keep original if parsing fails
                    else:
                        date = "Unknown date"

                    lineage_str += (
                        f"  - Commit: {entry['sha'][:7]} by {entry['author']} on {date}\n"
                        f"    Message: {entry['message']}\n"
                        f"    Changes: +{entry['additions']} / -{entry['deletions']}\n"
                    )
                lineage_str += "\n"

            return lineage_str if lineage_str else "Could not generate lineage information."
        except Exception as e:
            logger.error("Error calculating code lineage", exc_info=e, extra={"repo_url": repo_url})
            raise
        
    @activity.defn
    @auto_heartbeater
    async def calculate_code_quality_metrics(self, args: List[Any]) -> Dict[str, Any]:
        """
        Calculate code quality metrics.
        args: [repo_url, commits, issues, extraction_id]
        """
        repo_url, commits, issues, extraction_id = args
        logger.info("Calculating code quality metrics", extra={"repo_url": repo_url, "extraction_id": extraction_id})

        if not commits:
            return {}

        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")

            # 1. Code Churn
            file_churn = defaultdict(lambda: {"additions": 0, "deletions": 0, "changes": 0})
            for c in commits:
                commit_sha = c.get("sha")
                if not commit_sha:
                    continue
                
                commit = await asyncio.to_thread(repo.get_commit, commit_sha)
                if commit and commit.files:
                    for file in commit.files:
                        file_churn[file.filename]["additions"] += file.additions
                        file_churn[file.filename]["deletions"] += file.deletions
                        file_churn[file.filename]["changes"] += file.changes
            
            # 2. Bug Proneness (simple heuristic)
            bug_labels = {"bug", "fix", "error"}
            buggy_commits = set()
            if issues:
                for issue in issues:
                    if any(label in bug_labels for label in issue.get("labels", [])):
                        # This is a simplification. In a real-world scenario, you'd need to
                        # link issues to commits more reliably, e.g., via closing events.
                        pass
            
            metrics = {
                "file_churn": dict(file_churn),
            }
            return metrics
        except Exception as e:
            logger.error("Error calculating code quality metrics", exc_info=e, extra={"repo_url": repo_url})
            raise