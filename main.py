import asyncio
import os
import uuid

from app.activities import GitHubMetadataActivities
from app.workflow import GitHubMetadataWorkflow
from application_sdk.application import BaseApplication
from application_sdk.observability.decorators.observability_decorator import (
    observability,
)
from application_sdk.observability.logger_adaptor import get_logger
from application_sdk.observability.metrics_adaptor import get_metrics
from application_sdk.observability.traces_adaptor import get_traces
from app.config import APP_NAME, DEFAULT_PORT

logger = get_logger(__name__)
metrics = get_metrics()
traces = get_traces()

APPLICATION_NAME = APP_NAME


@observability(logger=logger, metrics=metrics, traces=traces)
async def main():
    logger.info("Starting GitHub metadata extractor application", extra={"application": APPLICATION_NAME})
    # initialize application
    app = BaseApplication(name=APPLICATION_NAME)

    # setup workflow
    await app.setup_workflow(
        workflow_and_activities_classes=[(GitHubMetadataWorkflow, GitHubMetadataActivities)],
    )

    # start worker
    await app.start_worker()

    # Setup the application server (health endpoints + readiness)
    await app.setup_server(workflow_class=GitHubMetadataWorkflow)

    # start server
    await app.start_server()
    logger.info("Server started", extra={"port": int(os.getenv("PORT", DEFAULT_PORT))})


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error("Fatal error on startup", exc_info=True)
        raise
