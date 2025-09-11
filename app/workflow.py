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

        workflow_args: Dict[str, Any] = await workflow.execute_activity_method(
            activities_instance.get_workflow_args,
            workflow_config,
            start_to_close_timeout=timedelta(seconds=10),
        )

        logger.info(f"Workflow args from activity: {workflow_args}", extra={"extraction_id": extraction_id})

        repo_url: str = workflow_args.get("repo_url", workflow_config.get("repo_url", "https://github.com/VatsalBhuva11/EcoBloom"))
        commit_limit: int = workflow_args.get("commit_limit", workflow_config.get("commit_limit", WORKFLOW_DEFAULT_COMMIT_LIMIT))
        issues_limit: int = workflow_args.get("issues_limit", workflow_config.get("issues_limit", WORKFLOW_DEFAULT_ISSUES_LIMIT))
        pr_limit: int = workflow_args.get("pr_limit", workflow_config.get("pr_limit", WORKFLOW_DEFAULT_PR_LIMIT))

        logger.info(f"Extracted parameters - repo_url: {repo_url}, commit_limit: {commit_limit}, issues_limit: {issues_limit}, pr_limit: {pr_limit}", extra={"extraction_id": extraction_id})

        if not repo_url:
            logger.error("No repo_url found in workflow_args", extra={"workflow_args": workflow_args})
            raise ValueError("Repository URL is required")

        logger.info(f"Starting GitHub metadata extraction workflow for: {repo_url}", extra={"extraction_id": extraction_id})

        try:
            repo_metadata = await workflow.execute_activity_method(
                activities_instance.extract_repository_metadata,
                [repo_url, extraction_id],
                start_to_close_timeout=timedelta(seconds=120),
            )
        except Exception as e:
            logger.error("Failed to extract repository metadata", exc_info=e, extra={"extraction_id": extraction_id})
            raise

        activities: List[Coroutine[Any, Any, Any]] = [
            workflow.execute_activity_method(
                activities_instance.extract_commit_metadata,
                [repo_url, commit_limit, extraction_id],
                start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
            ),
            workflow.execute_activity_method(
                activities_instance.extract_issues_metadata,
                [repo_url, issues_limit, extraction_id],
                start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
            ),
            workflow.execute_activity_method(
                activities_instance.extract_pull_requests_metadata,
                [repo_url, pr_limit, extraction_id],
                start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
            ),
            workflow.execute_activity_method(
                activities_instance.extract_contributors,
                [repo_url, extraction_id],
                start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
            ),
            workflow.execute_activity_method(
                activities_instance.extract_dependencies_from_repo,
                [repo_url, extraction_id],
                start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
            ),
        ]

        results = await asyncio.gather(*activities, return_exceptions=True)

        commits, issues, pull_requests, contributors, dependencies = results

        def _unwrap(result, name):
            if isinstance(result, Exception):
                logger.error(f"Activity {name} failed", extra={"extraction_id": extraction_id, "error": str(result)})
                return None
            return result

        commits = _unwrap(commits, "commits")
        issues = _unwrap(issues, "issues")
        pull_requests = _unwrap(pull_requests, "pull_requests")
        contributors = _unwrap(contributors, "contributors")
        dependencies = _unwrap(dependencies, "dependencies")

        # Now, run the new activities with the results from the previous ones
        if commits:
            lineage_and_quality_activities = [
                workflow.execute_activity_method(
                    activities_instance.calculate_code_lineage,
                    [repo_url, commits, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                ),
                workflow.execute_activity_method(
                    activities_instance.calculate_code_quality_metrics,
                    [repo_url, commits, issues, extraction_id],
                    start_to_close_timeout=timedelta(seconds=WORKFLOW_ACTIVITY_TIMEOUT_SECONDS),
                ),
            ]
            lineage_and_quality_results = await asyncio.gather(*lineage_and_quality_activities, return_exceptions=True)
            code_lineage, code_quality_metrics = lineage_and_quality_results
            code_lineage = _unwrap(code_lineage, "code_lineage")
            code_quality_metrics = _unwrap(code_quality_metrics, "code_quality_metrics")
        else:
            code_lineage, code_quality_metrics = None, None

        combined_metadata = {
            **repo_metadata,
            "commits": commits or [],
            "issues": issues or [],
            "pull_requests": pull_requests or [],
            "contributors": contributors or [],
            "dependencies": dependencies or [],
            "code_lineage": code_lineage or {},
            "code_quality_metrics": code_quality_metrics or {},
        }

        try:
            file_path = await workflow.execute_activity_method(
                activities_instance.save_metadata_to_file,
                [combined_metadata, repo_url, extraction_id],
                start_to_close_timeout=timedelta(seconds=120),
            )
            combined_metadata["file_path"] = file_path
        except Exception as e:
            logger.error("Failed saving metadata to file", extra={"extraction_id": extraction_id, "error": str(e)})

        try:
            summary = await workflow.execute_activity_method(
                activities_instance.get_extraction_summary,
                [repo_url, combined_metadata, extraction_id],
                start_to_close_timeout=timedelta(seconds=10),
            )
        except Exception as e:
            logger.error("Failed generating extraction summary", extra={"extraction_id": extraction_id, "error": str(e)})
            summary = {"error": str(e)}

        logger.info(f"GitHub metadata extraction workflow completed for: {repo_url}", extra={"extraction_id": extraction_id, "summary": summary})

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
            activities.save_metadata_to_file,
            activities.get_extraction_summary,
            activities.calculate_code_lineage,
            activities.calculate_code_quality_metrics,
        ]