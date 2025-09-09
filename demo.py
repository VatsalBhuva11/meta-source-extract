#!/usr/bin/env python3
"""
Demo script for GitHub Metadata Extractor
This script demonstrates how to use the GitHub metadata extraction activities directly.
"""

import asyncio
import json
from app.activities import GitHubMetadataActivities


async def demo_extraction():
    """Demonstrate GitHub metadata extraction."""
    print("🚀 GitHub Metadata Extractor Demo")
    print("=" * 50)
    
    # Initialize activities
    activities = GitHubMetadataActivities()
    
    # Demo repository (small, public repository)
    repo_url = "https://github.com/octocat/Hello-World"
    
    print(f"📁 Extracting metadata from: {repo_url}")
    print()
    
    try:
        # Extract repository metadata
        print("1️⃣ Extracting repository metadata...")
        repo_metadata = await activities.extract_repository_metadata(repo_url)
        print(f"   ✅ Repository: {repo_metadata['full_name']}")
        print(f"   📊 Stars: {repo_metadata['stars']}, Forks: {repo_metadata['forks']}")
        print(f"   🔤 Language: {repo_metadata['language']}")
        print()
        
        # Extract commits (limit to 5 for demo)
        print("2️⃣ Extracting recent commits...")
        commits = await activities.extract_commit_metadata(repo_url, limit=5)
        print(f"   ✅ Extracted {len(commits)} commits")
        if commits:
            latest_commit = commits[0]
            print(f"   📝 Latest: {latest_commit['message'][:50]}...")
        print()
        
        # Extract issues (limit to 3 for demo)
        print("3️⃣ Extracting issues...")
        issues = await activities.extract_issues_metadata(repo_url, limit=3)
        print(f"   ✅ Extracted {len(issues)} issues")
        if issues:
            open_issues = [i for i in issues if i['state'] == 'open']
            print(f"   🔓 Open issues: {len(open_issues)}")
        print()
        
        # Extract pull requests (limit to 3 for demo)
        print("4️⃣ Extracting pull requests...")
        prs = await activities.extract_pull_requests_metadata(repo_url, limit=3)
        print(f"   ✅ Extracted {len(prs)} pull requests")
        if prs:
            merged_prs = [pr for pr in prs if pr['merged']]
            print(f"   ✅ Merged PRs: {len(merged_prs)}")
        print()
        
        # Combine all metadata
        combined_metadata = {
            **repo_metadata,
            "commits": commits,
            "issues": issues,
            "pull_requests": prs,
        }
        
        # Save to file
        print("5️⃣ Saving metadata to file...")
        file_path = await activities.save_metadata_to_file(combined_metadata, repo_url)
        print(f"   💾 Saved to: {file_path}")
        print()
        
        # Generate summary
        print("6️⃣ Generating extraction summary...")
        summary = await activities.get_extraction_summary(repo_url, combined_metadata)
        print("   📋 Summary:")
        print(f"      - Repository: {summary['repository']}")
        print(f"      - Commits extracted: {summary['total_commits_extracted']}")
        print(f"      - Issues extracted: {summary['total_issues_extracted']}")
        print(f"      - PRs extracted: {summary['total_pull_requests_extracted']}")
        print(f"      - Stars: {summary['repository_stats']['stars']}")
        print(f"      - Languages: {', '.join(summary['repository_stats']['languages'])}")
        print()
        
        print("🎉 Demo completed successfully!")
        print(f"📁 Check the extracted_metadata/ directory for the full JSON file.")
        
    except Exception as e:
        print(f"❌ Error during extraction: {str(e)}")
        print("💡 Make sure you have a stable internet connection and the repository is accessible.")


if __name__ == "__main__":
    print("This demo will extract metadata from a small GitHub repository.")
    print("Note: This uses the GitHub API and may be rate-limited without authentication.")
    print()
    
    try:
        asyncio.run(demo_extraction())
    except KeyboardInterrupt:
        print("\n⏹️ Demo interrupted by user.")
    except Exception as e:
        print(f"\n❌ Demo failed: {str(e)}")
