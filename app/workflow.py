import asyncio
from datetime import timedelta
from typing import Any, Callable, Coroutine, Dict, List, Sequence

from app.activities import GitHubMetadataActivities
from application_sdk.activities import ActivitiesInterface
from application_sdk.observability.decorators.observability_decorator import (
    observability,
)
from application_sdk.observability.logger_adaptor import get_logger
from application_sdk.observability.metrics_adaptor import get_metrics
from application_sdk.observability.traces_adaptor import get_traces
from application_sdk.workflows import WorkflowInterface
from temporalio import workflow

from app.config import (
    WORKFLOW_DEFAULT_COMMIT_LIMIT,
    WORKFLOW_DEFAULT_ISSUES_LIMIT,
    WORKFLOW_DEFAULT_PR_LIMIT,
    WORKFLOW_ACTIVITY_TIMEOUT_SECONDS,
)
from app.utils import generate_extraction_id

logger = get_logger(__name__)
workflow.logger = logger
metrics = get_metrics()
traces = get_traces()


@workflow.defn
class GitHubMetadataWorkflow(WorkflowInterface):
    @observability(logger=logger, metrics=metrics, traces=traces)
    @workflow.run
    async def run(self, workflow_config: Dict[str, Any]) -> None:
        """
        production workflow to extract and enrich github metadata.
        """
        extraction_id = generate_extraction_id()
        workflow_config.setdefault("extraction_id", extraction_id)

        logger.info(f"Workflow start - Raw workflow_config: {workflow_config}", extra={"extraction_id": extraction_id})

        activities_instance = GitHubMetadataActivities()

        # get the workflow configuration from the state store
        workflow_args: Dict[str, Any] = await workflow.execute_activity_method(
            activities_instance.get_workflow_args,
            workflow_config,
            start_to_close_timeout=timedelta(seconds=10),
        )

        logger.info(f"Workflow args from activity: {workflow_args}", extra={"extraction_id": extraction_id})

        # extract and validate parameters
        repo_url, commit_limit, issues_limit, pr_limit, normalized_selections = self._extract_parameters(workflow_args, workflow_config)

        logger.info(f"Extracted parameters - repo_url: {repo_url}, commit_limit: {commit_limit}, issues_limit: {issues_limit}, pr_limit: {pr_limit}", extra={"extraction_id": extraction_id})
        logger.info(f"Selections: {normalized_selections}", extra={"extraction_id": extraction_id})

        # validate inputs
        self._validate_inputs(repo_url, normalized_selections, extraction_id)

        logger.info(f"Starting GitHub metadata extraction workflow for: {repo_url}", extra={"extraction_id": extraction_id})

        # extract repository metadata if selected
        repo_metadata = await self._extract_repository_metadata(activities_instance, repo_url, normalized_selections, extraction_id)

        # phase 1: Core data activities
        commits, issues, pull_requests, contributors, dependencies = await self._execute_core_activities(
            activities_instance, repo_url, commit_limit, issues_limit, pr_limit, normalized_selections, extraction_id
        )

        # phase 2: Derived metrics
        fork_lineage, commit_lineage, bus_factor, pr_metrics, issue_metrics, commit_activity, release_cadence = await self._execute_derived_activities(
            activities_instance, repo_url, commits, issues, pull_requests, normalized_selections, extraction_id
        )

        # build and save combined metadata
        combined_metadata = self._build_combined_metadata(
            repo_metadata, commits, issues, pull_requests, contributors, dependencies,
            fork_lineage, commit_lineage, bus_factor, pr_metrics, issue_metrics, 
            commit_activity, release_cadence, normalized_selections
        )

        await self._save_and_summarize(activities_instance, combined_metadata, repo_url, extraction_id)

        logger.info(f"GitHub metadata extraction workflow completed for: {repo_url}", extra={"extraction_id": extraction_id})

    def _extract_parameters(self, workflow_args: Dict[str, Any], workflow_config: Dict[str, Any]) -> tuple:
        """Extract and normalize workflow parameters."""
        repo_url: str = workflow_args.get("repo_url", workflow_config.get("repo_url", "https://github.com/VatsalBhuva11/EcoBloom"))
        commit_limit: int = workflow_args.get("commit_limit", workflow_config.get("commit_limit", WORKFLOW_DEFAULT_COMMIT_LIMIT))
        issues_limit: int = workflow_args.get("issues_limit", workflow_config.get("issues_limit", WORKFLOW_DEFAULT_ISSUES_LIMIT))
        pr_limit: int = workflow_args.get("pr_limit", workflow_config.get("pr_limit", WORKFLOW_DEFAULT_PR_LIMIT))
        selections: Dict[str, bool] = workflow_args.get("selections", {})

        # Normalize selections with defaults
        normalized_selections = {
            "repository": selections.get("repository", False),
            "commits": selections.get("commits", False),
            "issues": selections.get("issues", False),
            "pull_requests": selections.get("pull_requests", False),
            "contributors": selections.get("contributors", False),
            "dependencies": selections.get("dependencies", False),
            "fork_lineage": selections.get("fork_lineage", False),
            "commit_lineage": selections.get("commit_lineage", False),
            "bus_factor": selections.get("bus_factor", False),
            "pr_metrics": selections.get("pr_metrics", False),
            "issue_metrics": selections.get("issue_metrics", False),
            "commit_activity": selections.get("commit_activity", False),
            "release_cadence": selections.get("release_cadence", False),
        }

        return repo_url, commit_limit, issues_limit, pr_limit, normalized_selections

    def _validate_inputs(self, repo_url: str, normalized_selections: Dict[str, bool], extraction_id: str) -> None:
        """Validate workflow inputs."""
        if not repo_url:
            logger.error("No repo_url found in workflow_args", extra={"extraction_id": extraction_id})
            raise ValueError("Repository URL is required")

        if not any(normalized_selections.values()):
            logger.error("No metadata types selected for extraction", extra={"extraction_id": extraction_id})
            raise ValueError("At least one metadata type must be selected")

    async def _extract_repository_metadata(self, activities_instance: GitHubMetadataActivities, repo_url: str, 
                                         normalized_selections: Dict[str, bool], extraction_id: str) -> Dict[str, Any]:
        """Extract repository metadata if selected."""
        if not normalized_selections.get("repository", False):
            return None

        try:
            return await workflow.execute_activity_method(
                activities_instance.extract_repository_metadata,
                [repo_url, extraction_id],
                start_to_close_timeout=timedelta(seconds=120),
            )
        except Exception as e:
            logger.error("Failed to extract repository metadata", exc_info=e, extra={"extraction_id": extraction_id})
            raise

    async def _execute_core_activities(self, activities_instance: GitHubMetadataActivities, repo_url: str, 
                                     commit_limit: int, issues_limit: int, pr_limit: int, 
                                     normalized_selections: Dict[str, bool], extraction_id: str) -> tuple:
        """Execute core data extraction activities."""
        activities: List[Coroutine[Any, Any, Any]] = []
        
        # commits
        if normalized_selections.get("commits", False):
            activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_commit_metadata,
                    [repo_url, commit_limit, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            activities.append(asyncio.sleep(0, result=None))
            
        # issues
        if normalized_selections.get("issues", False):
            activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_issues_metadata,
                    [repo_url, issues_limit, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            activities.append(asyncio.sleep(0, result=None))
            
        # pull requests
        if normalized_selections.get("pull_requests", False):
            activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_pull_requests_metadata,
                    [repo_url, pr_limit, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            activities.append(asyncio.sleep(0, result=None))
            
        # contributors
        if normalized_selections.get("contributors", False):
            activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_contributors,
                    [repo_url, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            activities.append(asyncio.sleep(0, result=None))
            
        # dependencies
        if normalized_selections.get("dependencies", False):
            activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_dependencies_from_repo,
                    [repo_url, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            activities.append(asyncio.sleep(0, result=None))

        # execute all core activities
        results = await asyncio.gather(*activities, return_exceptions=True)
        commits, issues, pull_requests, contributors, dependencies = results

        # unwrap results
        def _unwrap(result, name):
            if isinstance(result, Exception):
                logger.error(f"Activity {name} failed", extra={"extraction_id": extraction_id, "error": str(result)})
                return None
            return result

        return (
            _unwrap(commits, "commits") if normalized_selections.get("commits", False) else None,
            _unwrap(issues, "issues") if normalized_selections.get("issues", False) else None,
            _unwrap(pull_requests, "pull_requests") if normalized_selections.get("pull_requests", False) else None,
            _unwrap(contributors, "contributors") if normalized_selections.get("contributors", False) else None,
            _unwrap(dependencies, "dependencies") if normalized_selections.get("dependencies", False) else None
        )

    async def _execute_derived_activities(self, activities_instance: GitHubMetadataActivities, repo_url: str,
                                        commits: List[Dict], issues: List[Dict], pull_requests: List[Dict],
                                        normalized_selections: Dict[str, bool], extraction_id: str) -> tuple:
        """Execute derived metrics activities."""
        derived_activities: List[Coroutine[Any, Any, Any]] = []
        
        # fork lineage
        if normalized_selections.get("fork_lineage", False):
            derived_activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_fork_lineage,
                    [repo_url, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            derived_activities.append(asyncio.sleep(0, result=None))
            
        # commit lineage
        if normalized_selections.get("commit_lineage", False):
            derived_activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_commit_lineage,
                    [repo_url, commits or [], extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            derived_activities.append(asyncio.sleep(0, result=None))
            
        # bus factor
        if normalized_selections.get("bus_factor", False):
            derived_activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_bus_factor,
                    [commits or [], extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            derived_activities.append(asyncio.sleep(0, result=None))
            
        # PR metrics
        if normalized_selections.get("pr_metrics", False):
            derived_activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_pr_metrics,
                    [pull_requests or [], extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            derived_activities.append(asyncio.sleep(0, result=None))
            
        # issue metrics
        if normalized_selections.get("issue_metrics", False):
            derived_activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_issue_metrics,
                    [issues or [], extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            derived_activities.append(asyncio.sleep(0, result=None))
            
        # commit activity
        if normalized_selections.get("commit_activity", False):
            derived_activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_commit_activity,
                    [commits or [], extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            derived_activities.append(asyncio.sleep(0, result=None))
            
        # release cadence
        if normalized_selections.get("release_cadence", False):
            derived_activities.append(
                workflow.execute_activity_method(
                    activities_instance.extract_release_cadence,
                    [repo_url, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                )
            )
        else:
            derived_activities.append(asyncio.sleep(0, result=None))

        # execute all derived activities
        derived_results = await asyncio.gather(*derived_activities, return_exceptions=True)
        fork_lineage, commit_lineage, bus_factor, pr_metrics, issue_metrics, commit_activity, release_cadence = derived_results

        # unwrap results
        def _unwrap(result, name):
            if isinstance(result, Exception):
                logger.error(f"Activity {name} failed", extra={"extraction_id": extraction_id, "error": str(result)})
                return None
            return result

        return (
            _unwrap(fork_lineage, "fork_lineage") if normalized_selections.get("fork_lineage", False) else None,
            _unwrap(commit_lineage, "commit_lineage") if normalized_selections.get("commit_lineage", False) else None,
            _unwrap(bus_factor, "bus_factor") if normalized_selections.get("bus_factor", False) else None,
            _unwrap(pr_metrics, "pr_metrics") if normalized_selections.get("pr_metrics", False) else None,
            _unwrap(issue_metrics, "issue_metrics") if normalized_selections.get("issue_metrics", False) else None,
            _unwrap(commit_activity, "commit_activity") if normalized_selections.get("commit_activity", False) else None,
            _unwrap(release_cadence, "release_cadence") if normalized_selections.get("release_cadence", False) else None
        )

    def _build_combined_metadata(self, repo_metadata: Dict[str, Any], commits: List[Dict], issues: List[Dict], 
                               pull_requests: List[Dict], contributors: List[Dict], dependencies: List[Dict],
                               fork_lineage: Dict[str, Any], commit_lineage: Dict[str, Any], bus_factor: Dict[str, Any],
                               pr_metrics: Dict[str, Any], issue_metrics: Dict[str, Any], commit_activity: Dict[str, Any],
                               release_cadence: Dict[str, Any], normalized_selections: Dict[str, bool]) -> Dict[str, Any]:
        """Build the final combined metadata dictionary with only selected items."""
        combined_metadata = {}
        
        # add repository metadata if available
        if repo_metadata is not None:
            combined_metadata.update(repo_metadata)
            
        # add core data if selected
        if normalized_selections.get("commits", False):
            combined_metadata["commits"] = commits or []
        if normalized_selections.get("issues", False):
            combined_metadata["issues"] = issues or []
        if normalized_selections.get("pull_requests", False):
            combined_metadata["pull_requests"] = pull_requests or []
        if normalized_selections.get("contributors", False):
            combined_metadata["contributors"] = contributors or []
        if normalized_selections.get("dependencies", False):
            combined_metadata["dependencies"] = dependencies or []
            
        # add derived metrics if selected
        if normalized_selections.get("fork_lineage", False):
            combined_metadata["fork_lineage"] = fork_lineage or {}
        if normalized_selections.get("commit_lineage", False):
            combined_metadata["commit_lineage"] = commit_lineage or {}
        if normalized_selections.get("bus_factor", False):
            combined_metadata["bus_factor"] = bus_factor or {}
        if normalized_selections.get("pr_metrics", False):
            combined_metadata["pr_metrics"] = pr_metrics or {}
        if normalized_selections.get("issue_metrics", False):
            combined_metadata["issue_metrics"] = issue_metrics or {}
        if normalized_selections.get("commit_activity", False):
            combined_metadata["commit_activity"] = commit_activity or {}
        if normalized_selections.get("release_cadence", False):
            combined_metadata["release_cadence"] = release_cadence or {}

        return combined_metadata

    async def _save_and_summarize(self, activities_instance: GitHubMetadataActivities, combined_metadata: Dict[str, Any], 
                                repo_url: str, extraction_id: str) -> None:
        """Save metadata to file and generate summary."""
        # save to file
        try:
            file_path = await workflow.execute_activity_method(
                activities_instance.save_metadata_to_file,
                [combined_metadata, repo_url, extraction_id],
                start_to_close_timeout=timedelta(seconds=120),
            )
            combined_metadata["file_path"] = file_path
        except Exception as e:
            logger.error("Failed saving metadata to file", extra={"extraction_id": extraction_id, "error": str(e)})


    @staticmethod
    def get_activities(activities: ActivitiesInterface) -> Sequence[Callable[..., Any]]:
        """return the sequence of activities for registration"""
        if not isinstance(activities, GitHubMetadataActivities):
            raise TypeError("Activities must be an instance of GitHubMetadataActivities")

        return [
            activities.get_workflow_args,
            activities.extract_repository_metadata,
            activities.extract_commit_metadata,
            activities.extract_issues_metadata,
            activities.extract_pull_requests_metadata,
            activities.extract_contributors,
            activities.extract_dependencies_from_repo,
            activities.extract_fork_lineage,
            activities.extract_commit_lineage,
            activities.extract_bus_factor,
            activities.extract_pr_metrics,
            activities.extract_issue_metrics,
            activities.extract_commit_activity,
            activities.extract_release_cadence,
            activities.save_metadata_to_file,
            activities.get_extraction_summary,
        ]
