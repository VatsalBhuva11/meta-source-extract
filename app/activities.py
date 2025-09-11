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

    # lineage metrics
    @activity.defn(name="extract_fork_lineage")
    @auto_heartbeater
    @circuit_breaker
    async def extract_fork_lineage(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [repo_url, extraction_id]
        """
        repo_url, extraction_id = args
        logger.info("Extracting fork lineage", extra={"repo_url": repo_url, "extraction_id": extraction_id})
        cached = _get_from_cache(repo_url, "fork_lineage")
        if cached is not None:
            return cached
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")
            parent = None
            source = None
            try:
                if getattr(repo, "parent", None):
                    parent = getattr(repo.parent, "full_name", None)
                if getattr(repo, "source", None):
                    source = getattr(repo.source, "full_name", None)
            except Exception:
                pass
            result = {
                "is_fork": bool(getattr(repo, "fork", False)),
                "parent": parent,
                "source": source,
            }
            _set_cache(repo_url, "fork_lineage", result, ttl=1800)
            return result
        except Exception as e:
            logger.error("Error extracting fork lineage", exc_info=e, extra={"repo_url": repo_url})
            raise

    @activity.defn(name="extract_commit_lineage")
    @auto_heartbeater
    @circuit_breaker
    async def extract_commit_lineage(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [repo_url, commits, extraction_id]
        returns parent mapping and merge commit shas
        """
        repo_url, commits, extraction_id = args
        logger.info("Extracting commit lineage", extra={"repo_url": repo_url, "extraction_id": extraction_id})
        cached = _get_from_cache(repo_url, "commit_lineage")
        if cached is not None:
            return cached
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")
            parents_map: Dict[str, List[str]] = {}
            merge_commits: List[str] = []
            # cap to reasonable number to avoid rate overuse
            for c in (commits or [])[:300]:
                sha = c.get("sha")
                if not sha:
                    continue
                gh_commit = await asyncio.to_thread(repo.get_commit, sha)
                pshas = [p.sha for p in getattr(gh_commit, "parents", [])]
                parents_map[sha] = pshas
                if len(pshas) >= 2:
                    merge_commits.append(sha)
            result = {"parents": parents_map, "merge_commits": merge_commits}
            _set_cache(repo_url, "commit_lineage", result, ttl=1800)
            return result
        except Exception as e:
            logger.error("Error extracting commit lineage", exc_info=e, extra={"repo_url": repo_url})
            raise

    # quality metrics
    @activity.defn(name="extract_bus_factor")
    @auto_heartbeater
    @circuit_breaker
    async def extract_bus_factor(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [commits, extraction_id]
        """
        commits, extraction_id = args
        logger.info("Extracting bus factor", extra={"extraction_id": extraction_id})
        if not commits:
            return {"top1_pct": None, "top2_pct": None}
        author_counts: Dict[str, int] = {}
        total = 0
        for c in commits:
            author = c.get("author") or "unknown"
            author_counts[author] = author_counts.get(author, 0) + 1
            total += 1
        ranked = sorted(author_counts.values(), reverse=True)
        top1 = ranked[0] if ranked else 0
        top2 = (ranked[0] + ranked[1]) if len(ranked) > 1 else top1
        return {
            "top1_pct": (top1 / total) if total else None,
            "top2_pct": (top2 / total) if total else None,
        }

    @activity.defn(name="extract_pr_metrics")
    @auto_heartbeater
    @circuit_breaker
    async def extract_pr_metrics(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [pull_requests, extraction_id]
        """
        prs, extraction_id = args
        logger.info("Extracting PR metrics", extra={"extraction_id": extraction_id})
        if not prs:
            return {"merge_rate": None, "median_merge_days": None, "avg_merge_days": None}
        closed = [p for p in prs if p.get("state") == "closed"]
        merged = [p for p in prs if p.get("merged")]
        merge_durations = []
        for p in merged:
            opened = p.get("created_at")
            merged_at = p.get("merged_at")
            if opened and merged_at:
                try:
                    dt_o = datetime.fromisoformat(opened)
                    dt_m = datetime.fromisoformat(merged_at)
                    merge_durations.append((dt_m - dt_o).total_seconds() / 86400.0)
                except Exception:
                    pass
        med = None
        avg = None
        if merge_durations:
            s = sorted(merge_durations)
            n = len(s)
            med = s[n//2] if n % 2 == 1 else (s[n//2-1] + s[n//2]) / 2
            avg = sum(s) / n
        return {"merge_rate": (len(merged) / len(closed)) if closed else None, "median_merge_days": med, "avg_merge_days": avg}

    @activity.defn(name="extract_issue_metrics")
    @auto_heartbeater
    @circuit_breaker
    async def extract_issue_metrics(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [issues, extraction_id]
        """
        issues, extraction_id = args
        logger.info("Extracting issue metrics", extra={"extraction_id": extraction_id})
        if not issues:
            return {"closure_rate": None, "median_resolution_days": None, "avg_resolution_days": None}
        closed = [i for i in issues if i.get("closed_at")]
        durations = []
        for i in closed:
            c = i.get("closed_at")
            o = i.get("created_at")
            if c and o:
                try:
                    dt_c = datetime.fromisoformat(c)
                    dt_o = datetime.fromisoformat(o)
                    durations.append((dt_c - dt_o).total_seconds() / 86400.0)
                except Exception:
                    pass
        med = None
        avg = None
        if durations:
            s = sorted(durations)
            n = len(s)
            med = s[n//2] if n % 2 == 1 else (s[n//2-1] + s[n//2]) / 2
            avg = sum(s) / n
        return {"closure_rate": (len(closed) / len(issues)) if issues else None, "median_resolution_days": med, "avg_resolution_days": avg}

    @activity.defn(name="extract_commit_activity")
    @auto_heartbeater
    @circuit_breaker
    async def extract_commit_activity(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [commits, extraction_id]
        returns per-week and per-month counts
        """
        commits, extraction_id = args
        logger.info("Extracting commit activity", extra={"extraction_id": extraction_id})
        from collections import Counter
        by_week = Counter()
        by_month = Counter()
        for c in commits or []:
            d = c.get("date")
            if not d:
                continue
            try:
                dt = datetime.fromisoformat(d)
                by_week[dt.strftime("%Y-W%U")] += 1
                by_month[dt.strftime("%Y-%m")] += 1
            except Exception:
                pass
        return {"per_week": dict(by_week), "per_month": dict(by_month)}

    @activity.defn(name="extract_release_cadence")
    @auto_heartbeater
    @circuit_breaker
    async def extract_release_cadence(self, args: List[Any]) -> Dict[str, Any]:
        """
        args: [repo_url, extraction_id]
        """
        repo_url, extraction_id = args
        logger.info("Extracting release cadence", extra={"repo_url": repo_url, "extraction_id": extraction_id})
        cached = _get_from_cache(repo_url, "release_cadence")
        if cached is not None:
            return cached
        try:
            owner, repo_name = self._extract_repo_info_from_url(repo_url)
            repo = await asyncio.to_thread(self._get_repo, f"{owner}/{repo_name}")
            tags = []
            releases = []
            try:
                tags = [t.name for t in repo.get_tags()[:100]]
            except Exception:
                pass
            try:
                releases = [r.tag_name or r.name for r in repo.get_releases()[:100]]
            except Exception:
                pass
            result = {"tag_count_100": len(tags), "release_count_100": len(releases)}
            _set_cache(repo_url, "release_cadence", result, ttl=3600)
            return result
        except Exception as e:
            logger.error("Error extracting release cadence", exc_info=e, extra={"repo_url": repo_url})
            raise