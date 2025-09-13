# GitHub Metadata Extractor

A powerful application built with the Atlan SDK that extracts comprehensive metadata from GitHub repositories. This tool can extract repository information, commits, issues, and pull requests, saving the data locally for analysis.

## Features

-   **Repository Metadata**: Extracts basic repository information, including stars, forks, languages, and topics.
-   **Commit Analysis**: Retrieves detailed commit history with author information, statistics, and messages.
-   **Issue and Pull Request Tracking**: Extracts issues and pull requests with their labels, assignees, and statuses.
-   **Data Storage**: Saves all extracted metadata to JSON files for further analysis.
-   **Configurable Limits**: Allows you to set custom limits for the number of commits, issues, and pull requests to extract.
-   **Modern UI**: A clean and responsive web interface for easy interaction.
-   **Resilience**: Implements a circuit breaker to handle GitHub API rate limiting gracefully.

## Prerequisites

-   Python 3.11+
-   Temporal
-   Dapr
-   uv
-   A GitHub account (optional, for higher rate limits)

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd meta-source-extract
    ```

2.  **Install dependencies**:
    ```bash
    uv run poe download-components
    ```

3.  **Set up environment variables**:
    ```bash
    cp .env.example .env
    ```
    Edit the `.env` file to add your GitHub token if you have one.


## Demo Instructions

1.  **Start the application's dependencies**:
    ```bash
    uv run poe start-deps
    ```

2.  **Run the application**:
    ```bash
    uv run main.py
    ```

3.  **Access the web interface**:
    Open your browser and go to `http://localhost:8000`.

4.  **Use the application**:
    -   Enter a GitHub repository URL (e.g., `https://github.com/atlanhq/atlan`).
    -   Optionally, adjust the limits for commits, issues, and pull requests. You can even select which metadata to be extracted by selecting the required checkboxes.
    -   Click "Extract Metadata".
    -   Once the process is complete, you can view the results and download the generated JSON file.

5.  **To stop the dependencies**:
    ```bash
    uv run poe stop-deps
    ```
## Framework Notes

The Atlan SDK simplifies the development of this application by providing a robust framework for building data-driven apps. Some key takeaways from using it in this project:

-   **Workflow Orchestration**: The SDK's workflow management capabilities, powered by Temporal, make it easy to define and manage complex, long-running processes like metadata extraction. The `@workflow` and `@activity` decorators provide a clean and intuitive way to structure the code.
-   **Service Integration**: The SDK's integration with Dapr for service communication simplifies the interaction between the web server and the background workflow.
-   **Configuration Management**: The framework provides a straightforward way to manage configuration through environment variables, making it easy to switch between development and production settings.

## Architecture Notes

### High-Level Overview

This application is designed to be a resilient and scalable solution for extracting metadata from GitHub repositories. It is built on a microservices-based architecture, with distinct components for the user interface, API, and background processing.

### Component Breakdown

-   **FastAPI**: Provides the web interface and API endpoints for user interaction. It is responsible for accepting user requests and initiating the metadata extraction workflow.
-   **Temporal**: The core of the application's backend, used for orchestrating the metadata extraction workflow. It ensures that the extraction process is reliable and can recover from failures.
-   **Dapr**: Facilitates communication between the FastAPI server and the Temporal workflow, enabling a decoupled and scalable architecture.
-   **PyGithub**: A Python library used to interact with the GitHub API and retrieve the required metadata.

### Workflow

1.  A user submits a request through the web interface or API.
2.  The FastAPI server receives the request and starts a new Temporal workflow.
3.  The workflow orchestrates a series of activities to extract the requested metadata from the GitHub API.
4.  The extracted data is saved to a JSON file in the `extracted_metadata/` directory.

### Data Flow

The data flows from the GitHub API to the application, where it is processed and stored. The application does not store any user data beyond the extracted metadata, which is saved locally.

There is an optional configuration of saving the data to AWS S3, but that has not been tested yet because of lack of access to an AWS S3 environment. The function for that is ready and can be configured by setting up the appropriate environment variables
## AWS S3 Configuration (Optional)

To enable S3 upload of extracted metadata, set the following environment variables:

```bash
# Required for S3 upload
export METADATA_UPLOAD_TO_S3=true
export S3_BUCKET=your-bucket-name

# AWS Credentials (choose one method)
# Method 1: Environment variables
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_REGION=us-east-1

# Method 2: AWS CLI configuration
aws configure

# Method 3: IAM roles (if running on EC2)
# No additional configuration needed

# Method 4: Temporary credentials (for STS)
export AWS_SESSION_TOKEN=your-session-token
```

### AWS Credentials Priority

The application will use credentials in this order:
1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. AWS CLI configuration (`~/.aws/credentials`)
3. IAM roles (if running on EC2)
4. Default credential provider chain

If no credentials are found, S3 upload will be disabled and metadata will only be saved locally.

