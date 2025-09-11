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
        }),      
    });

    if (response.ok) {
      const result = await response.json();
      extractButton.textContent = "Extraction Started! 🎉";
      progressSection.style.display = "none";
      
      // Show success modal with basic info
      showSuccessModal(repoUrl, commitLimit, issuesLimit, prLimit);
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

function showSuccessModal(repoUrl, commitLimit, issuesLimit, prLimit) {
  const successModal = document.getElementById("successModal");
  const extractionResults = document.getElementById("extractionResults");
  
  // Extract repository name from URL
  const repoName = repoUrl.split("/").slice(-2).join("/");
  
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
