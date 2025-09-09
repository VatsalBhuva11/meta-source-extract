# GitHub Metadata Extractor

A powerful application built with Atlan's Application SDK that extracts comprehensive metadata from GitHub repositories. This tool can extract repository information, commits, issues, pull requests, and other valuable data, saving it locally for analysis.

## Features

- **Repository Metadata**: Extract basic repository information including stars, forks, languages, topics, and more
- **Commit Analysis**: Get detailed commit history with author information, statistics, and messages
- **Issues Tracking**: Extract issues and pull requests with labels, assignees, and status information
- **Data Storage**: Save all extracted metadata to JSON files for further analysis
- **Configurable Limits**: Set custom limits for commits, issues, and pull requests to extract
- **Modern UI**: Clean, responsive web interface for easy interaction
- **Rate Limiting**: Respects GitHub API rate limits with optional authentication

## Prerequisites

- Python 3.11+
- GitHub account (optional, for higher rate limits)
- Docker (for Dapr and Temporal)

## Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd hello_world
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env and add your GitHub token if desired
   ```

4. **Download required components**:
   ```bash
   poe download-components
   ```

## Configuration

### GitHub API Token (Optional but Recommended)

For unauthenticated requests, you're limited to 60 requests per hour. To increase this limit:

1. Go to [GitHub Settings > Personal Access Tokens](https://github.com/settings/tokens)
2. Generate a new token with appropriate permissions
3. Add it to your `.env` file:
   ```
   GITHUB_TOKEN=your_token_here
   ```

### Repository Limits

You can configure how much data to extract:
- **Commits**: 1-1000 (default: 50)
- **Issues**: 1-1000 (default: 50)  
- **Pull Requests**: 1-1000 (default: 50)

## Usage

### Start the Application

1. **Start dependencies**:
   ```bash
   poe start-deps
   ```

2. **Run the application**:
   ```bash
   python main.py
   ```

3. **Access the web interface**:
   Open your browser and go to `http://localhost:3000`

### Using the Web Interface

1. Enter a GitHub repository URL (e.g., `https://github.com/VatsalBhuva11/EcoBloom/`)
2. Configure extraction limits (optional)
3. Click "Extract Metadata"
4. Wait for the extraction to complete
5. View results and download the generated JSON file

### Using the API Directly

You can also trigger extractions programmatically:

```bash
curl -X POST http://localhost:3000/workflows/v1/start \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/VatsalBhuva11/EcoBloom/",
    "commit_limit": 100,
    "issues_limit": 50,
    "pr_limit": 50
  }'
```

## Extracted Data

The application extracts the following metadata:

### Repository Information
- Basic details (name, description, language, etc.)
- Statistics (stars, forks, watchers, issues)
- Topics and labels
- License information
- Creation and update timestamps

### Commits
- Commit SHA and message
- Author and committer information
- Timestamps
- File change statistics
- HTML URLs

### Issues
- Issue number, title, and body
- State (open/closed)
- Labels and assignees
- Milestone information
- Creation and update timestamps

### Pull Requests
- PR number, title, and body
- State (open/closed/merged)
- Head and base branch information
- Labels and assignees
- Merge information
- File change statistics

## Output

All extracted metadata is saved to the `extracted_metadata/` directory as JSON files with the format:
```
{owner}_{repository}_metadata.json
```

## Development

### Running Tests

```bash
poe test
```

### Code Quality

```bash
poe lint
```

## Troubleshooting

### Common Issues

1. **Rate Limit Exceeded**: 
   - Add a GitHub token to increase rate limits
   - Reduce extraction limits
   - Wait for rate limit reset

2. **Repository Not Found**:
   - Verify the repository URL is correct
   - Check if the repository is private (requires authentication)

3. **Permission Denied**:
   - Ensure your GitHub token has appropriate permissions
   - Check if the repository requires special access

### Logs

Check the application logs for detailed error information. The application uses structured logging with different levels.

## Architecture

This application is built using:
- **Atlan Application SDK**: For workflow orchestration
- **Temporal**: For reliable workflow execution
- **Dapr**: For service communication
- **PyGithub**: For GitHub API integration
- **FastAPI**: For the web interface

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the Apache-2.0 License - see the LICENSE file for details.

## Support

For issues and questions:
- Check the [GitHub Issues](https://github.com/your-repo/issues)
- Contact the development team
- Review the [Atlan Application SDK documentation](https://docs.atlan.com)
