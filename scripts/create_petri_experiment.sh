#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
EXPERIMENT_NAME="${1:-$(date +%Y%m%d-%H%M%S)}"
BASE_DIR="${PETRI_EXPERIMENTS_DIR:-$HOME/lab/petri/$PROJECT_NAME}"
EXPERIMENT_DIR="$BASE_DIR/$EXPERIMENT_NAME"

mkdir -p "$EXPERIMENT_DIR"/{inputs,runs,artifacts,roles/smoke_reviewer/playbooks}

cat > "$EXPERIMENT_DIR/README.md" <<EOF
# Petri Experiment: $EXPERIMENT_NAME

This directory is intentionally outside the quantitative_trading Git worktree.

## Local Setup

\`\`\`bash
cd "$PROJECT_ROOT"
python -m pip install -e .

cd ~/dev/github/petri
python -m pip install -e .
\`\`\`

## Run

\`\`\`bash
cd "$EXPERIMENT_DIR"
petri run
\`\`\`

## Project Source

\`\`\`text
$PROJECT_ROOT
\`\`\`
EOF

cat > "$EXPERIMENT_DIR/petri.yaml" <<EOF
providers:
  default:
    type: claude_code

models:
  sonnet:
    provider: default
    model: sonnet

defaults:
  model: sonnet
  gate_strategy: all
  max_retries: 3
EOF

cat > "$EXPERIMENT_DIR/pipeline.yaml" <<EOF
name: quantitative-trading-experiment
description: External Petri experiment for quantitative_trading

goal: |
  Verify that Petri runs from this external experiment workspace and does not write runtime state into the project repository.

stages:
  - name: smoke_review
    roles: [smoke_reviewer]
    max_retries: 1
EOF

cat > "$EXPERIMENT_DIR/roles/smoke_reviewer/role.yaml" <<EOF
persona: soul.md
playbooks:
  - petri:shell_tools
  - smoke_review
EOF

cat > "$EXPERIMENT_DIR/roles/smoke_reviewer/gate.yaml" <<EOF
id: smoke-review-complete
description: Smoke review must complete successfully
evidence:
  path: "{stage}/{role}/result.json"
  check:
    field: passed
    equals: true
EOF

cat > "$EXPERIMENT_DIR/roles/smoke_reviewer/soul.md" <<EOF
You are a careful smoke-test reviewer. Verify the requested workspace boundary with minimal commands and do not modify the target project repository.
EOF

cat > "$EXPERIMENT_DIR/roles/smoke_reviewer/playbooks/smoke_review.md" <<EOF
Perform a minimal external workspace smoke review.

Requirements:

1. Confirm the current working directory is this Petri experiment workspace:

   \`\`\`text
   $EXPERIMENT_DIR
   \`\`\`

2. Confirm the target project source exists:

   \`\`\`text
   $PROJECT_ROOT
   \`\`\`

3. Do not edit files under the target project source.

4. Write the gate artifact exactly to result.json in the current working directory:

   \`\`\`json
   {
     "passed": true,
     "experiment_dir": "$EXPERIMENT_DIR",
     "project_root": "$PROJECT_ROOT",
     "summary": "Petri runtime state stayed in the external experiment workspace."
   }
   \`\`\`
EOF

printf '%s\n' "$EXPERIMENT_DIR"
