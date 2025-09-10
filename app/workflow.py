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
        This workflow extracts metadata from GitHub repositories.

        Args:
            workflow_config (Dict[str, Any]): The workflow configuration containing:
                - repo_url: GitHub repository URL
                - commit_limit: Number of commits to extract (default: 50)
                - issues_limit: Number of issues to extract (default: 50)
                - pr_limit: Number of pull requests to extract (default: 50)

        Returns:
            None
        """
        activities_instance = GitHubMetadataActivities()

        # Get the workflow configuration from the state store
        workflow_args: Dict[str, Any] = await workflow.execute_activity_method(
            activities_instance.get_workflow_args,
            workflow_config,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Extract parameters from workflow_args
        repo_url: str = workflow_args.get("repo_url", "https://github.com/rtyley/small-test-repo")
        commit_limit: int = workflow_args.get("commit_limit", 50)
        issues_limit: int = workflow_args.get("issues_limit", 50)
        pr_limit: int = workflow_args.get("pr_limit", 50)

        if not repo_url:
            logger.error(f"No repo_url found in workflow_args: {workflow_args}")
            raise ValueError("Repository URL is required")

        logger.info(f"Starting GitHub metadata extraction workflow for: {repo_url}")

        # Extract repository basic metadata
        repo_metadata = await workflow.execute_activity_method(
            activities_instance.extract_repository_metadata,
            repo_url,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Extract commits, issues, and pull requests in parallel
        activities: List[Coroutine[Any, Any, Any]] = [
            workflow.execute_activity_method(
                activities_instance.extract_commit_metadata,
                [repo_url, commit_limit],
                start_to_close_timeout=timedelta(seconds=60),
            ),
            workflow.execute_activity_method(
                activities_instance.extract_issues_metadata,
                [repo_url, issues_limit],
                start_to_close_timeout=timedelta(seconds=60),
            ),
            workflow.execute_activity_method(
                activities_instance.extract_pull_requests_metadata,
                [repo_url, pr_limit],
                start_to_close_timeout=timedelta(seconds=60),
            ),
        ]

        # Wait for all parallel activities to complete
        results = await asyncio.gather(*activities)
        commits, issues, pull_requests = results

        # Combine all metadata
        combined_metadata = {
            **repo_metadata,
            "commits": commits,
            "issues": issues,
            "pull_requests": pull_requests,
        }

        # Save metadata to file
        file_path = await workflow.execute_activity_method(
            activities_instance.save_metadata_to_file,
            [combined_metadata, repo_url],  # <-- FIXED: Arguments are now in a list
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Add file path to metadata
        combined_metadata["file_path"] = file_path

        # Generate extraction summary
        summary = await workflow.execute_activity_method(
            activities_instance.get_extraction_summary,
            [repo_url, combined_metadata], # <-- FIXED: Arguments are now in a list
            start_to_close_timeout=timedelta(seconds=10),
        )

        logger.info(f"GitHub metadata extraction workflow completed for: {repo_url}")
        logger.info(f"Summary: {summary}")

    @staticmethod
    def get_activities(activities: ActivitiesInterface) -> Sequence[Callable[..., Any]]:
        """Get the sequence of activities to be executed by the workflow."""
        if not isinstance(activities, GitHubMetadataActivities):
            raise TypeError("Activities must be an instance of GitHubMetadataActivities")

        return [
            activities.get_workflow_args,
            activities.extract_repository_metadata,
            activities.extract_commit_metadata,
            activities.extract_issues_metadata,
            activities.extract_pull_requests_metadata,
            activities.save_metadata_to_file,
            activities.get_extraction_summary,
        ]
