window.env = {
  APP_HTTP_HOST: "{{ app_http_host }}",
  APP_HTTP_PORT: "{{ app_http_port }}",
  APP_DASHBOARD_HTTP_HOST: "{{ app_dashboard_http_host }}",
  APP_DASHBOARD_HTTP_PORT: "{{ app_dashboard_http_port }}",
};

async function handleSubmit(event) {
  event.preventDefault();
  
  const repoUrl = document.getElementById("repoUrl").value;
  const commitLimit = parseInt(document.getElementById("commitLimit").value) || 50;
  const issuesLimit = parseInt(document.getElementById("issuesLimit").value) || 50;
  const prLimit = parseInt(document.getElementById("prLimit").value) || 50;
  
  const selections = {
    repository: document.getElementById("optRepo").checked,
    commits: document.getElementById("optCommits").checked,
    issues: document.getElementById("optIssues").checked,
    pull_requests: document.getElementById("optPRs").checked,
    contributors: document.getElementById("optContributors").checked,
    dependencies: document.getElementById("optDependencies").checked,
    fork_lineage: document.getElementById("optForkLineage").checked,
    commit_lineage: document.getElementById("optCommitLineage").checked,
    bus_factor: document.getElementById("optBusFactor").checked,
    pr_metrics: document.getElementById("optPrMetrics").checked,
    issue_metrics: document.getElementById("optIssueMetrics").checked,
    commit_activity: document.getElementById("optCommitActivity").checked,
    release_cadence: document.getElementById("optReleaseCadence").checked,
  };
  
  const anySelected = Object.values(selections).some(Boolean);
  if (!anySelected) {
    showError("Please select at least one metadata category to extract.");
    return;
  }
  
  const extractButton = document.getElementById("extractButton");
  const progressSection = document.getElementById("progressSection");
  const successModal = document.getElementById("successModal");
  const errorModal = document.getElementById("errorModal");
  
  // Validate GitHub URL
  if (!isValidGitHubUrl(repoUrl)) {
    showError("Please enter a valid GitHub repository URL (e.g., https://github.com/owner/repo)");
    return;
  }
  
  // Show progress
  extractButton.textContent = "Extracting... 🔄";
  extractButton.disabled = true;
  progressSection.style.display = "block";
  
  try {
    const response = await fetch("/workflows/v1/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
          repo_url: repoUrl,
          commit_limit: commitLimit,
          issues_limit: issuesLimit,
          pr_limit: prLimit,
          selections: selections,
        }),      
    });

    if (response.ok) {
      const result = await response.json();
      extractButton.textContent = "Extraction Started! 🎉";
      progressSection.style.display = "none";
      
      // Show success modal with basic info
      showSuccessModal(repoUrl, commitLimit, issuesLimit, prLimit, selections);
    } else {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.message || "Extraction failed");
    }
  } catch (error) {
    console.error("Extraction error:", error);
    progressSection.style.display = "none";
    showError(error.message || "An error occurred during metadata extraction");
  } finally {
    setTimeout(() => {
      extractButton.disabled = false;
      extractButton.textContent = "Extract Metadata";
    }, 2000);
  }
}

function isValidGitHubUrl(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.hostname === "github.com" && urlObj.pathname.split("/").length >= 3;
  } catch {
    return false;
  }
}

function showSuccessModal(repoUrl, commitLimit, issuesLimit, prLimit, selections) {
  const successModal = document.getElementById("successModal");
  const extractionResults = document.getElementById("extractionResults");
  
  // Extract repository name from URL
  const repoName = repoUrl.split("/").slice(-2).join("/");
  
  const selectedBadges = [];
  if (selections.repository) selectedBadges.push("Repository");
  if (selections.commits) selectedBadges.push("Commits");
  if (selections.issues) selectedBadges.push("Issues");
  if (selections.pull_requests) selectedBadges.push("PRs");
  if (selections.contributors) selectedBadges.push("Contributors");
  if (selections.dependencies) selectedBadges.push("Dependencies");
  if (selections.fork_lineage) selectedBadges.push("Fork lineage");
  if (selections.commit_lineage) selectedBadges.push("Commit lineage");
  if (selections.bus_factor) selectedBadges.push("Bus factor");
  if (selections.pr_metrics) selectedBadges.push("PR metrics");
  if (selections.issue_metrics) selectedBadges.push("Issue metrics");
  if (selections.commit_activity) selectedBadges.push("Commit activity");
  if (selections.release_cadence) selectedBadges.push("Release cadence");
  
  const badgesHtml = selectedBadges.map(b => `<span class="badge">${b}</span>`).join(" ");
  
  extractionResults.innerHTML = `
    <div class="result-item">
      <h3>Repository: ${repoName}</h3>
      <p><strong>URL:</strong> <a href="${repoUrl}" target="_blank">${repoUrl}</a></p>
    </div>
    <div class="result-stats">
      <div class="stat-item">
        <span class="stat-label">Commits to extract:</span>
        <span class="stat-value">${commitLimit}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">Issues to extract:</span>
        <span class="stat-value">${issuesLimit}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">Pull Requests to extract:</span>
        <span class="stat-value">${prLimit}</span>
      </div>
    </div>
    <div class="result-note">
      <p>Selected: ${badgesHtml}</p>
      <p>📁 Metadata will be saved to the <code>extracted_metadata/</code> directory</p>
      <p>⏱️ The extraction process may take a few minutes depending on the repository size</p>
    </div>
  `;
  
  successModal.classList.add("show");
}

function showError(message) {
  const errorModal = document.getElementById("errorModal");
  const errorMessage = document.getElementById("errorMessage");
  
  errorMessage.textContent = message;
  errorModal.classList.add("show");
}

// Close modal functions
document.getElementById("closeModal").addEventListener("click", () => {
  document.getElementById("successModal").classList.remove("show");
});

document.getElementById("closeErrorModal").addEventListener("click", () => {
  document.getElementById("errorModal").classList.remove("show");
});

// Close modals when clicking outside
document.addEventListener("click", (event) => {
  const successModal = document.getElementById("successModal");
  const errorModal = document.getElementById("errorModal");
  
  if (event.target === successModal) {
    successModal.classList.remove("show");
  }
  if (event.target === errorModal) {
    errorModal.classList.remove("show");
  }
});
