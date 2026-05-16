#!/usr/bin/env bash
# setup-labels.sh — Run once after creating the GitHub repo
# Usage: GITHUB_TOKEN=ghp_xxx ./scripts/setup-labels.sh adityatawde9699/Leger

set -euo pipefail

REPO="${1:?Usage: $0 owner/repo}"
API="https://api.github.com/repos/${REPO}/labels"

create_label() {
  curl -s -X POST "$API" \
    -H "Authorization: token ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -d "{\"name\":\"$1\",\"color\":\"$2\",\"description\":\"$3\"}" > /dev/null
  echo "  ✓ $1"
}

echo "Creating labels for ${REPO}..."

# Type
create_label "bug"             "d73a4a" "Something isn't working"
create_label "enhancement"     "a2eeef" "New feature or request"
create_label "documentation"   "0075ca" "Improvements to documentation"
create_label "question"        "d876e3" "Further information requested"

# Priority
create_label "priority: critical"  "b60205" "Must fix immediately"
create_label "priority: high"      "ff9f1c" "Should be fixed soon"
create_label "priority: low"       "c5def5" "Nice to have"

# Area
create_label "area: frontend"    "1d76db" "React / UI changes"
create_label "area: backend"     "5319e7" "FastAPI / Python changes"
create_label "area: ai"          "f9d0c4" "AI services and LLM"
create_label "area: database"    "006b75" "Schema, migrations, queries"
create_label "area: devops"      "e4e669" "CI/CD, Docker, deployment"

# Status
create_label "triage"          "ededed" "Needs initial review"
create_label "stale"           "ffffff" "No recent activity"
create_label "pinned"          "006b75" "Important, do not auto-close"
create_label "good first issue" "7057ff" "Good for newcomers"
create_label "help wanted"     "008672" "Extra attention needed"

# Dependencies
create_label "dependencies"    "0366d6" "Dependency updates"
create_label "security"        "ee0701" "Security vulnerability"

echo "Done! ${REPO} labels configured."
