# Petri Experiments

Petri experiments should run outside this repository's Git worktree. This keeps generated roles, pipelines, inputs, runs, and artifacts separate from source code changes.

## Recommended Layout

```text
~/dev/github/petri
  Petri source, installed as a local command.

~/dev/github/quantitative_trading
  Project source, installed as an editable Python package.

~/lab/petri/quantitative_trading/<experiment>
  Petri configuration, roles, inputs, runs, and artifacts for one experiment.
```

## One-Time Local Setup

```bash
cd ~/dev/github/petri
python -m pip install -e .

cd $PROJECT_ROOT
python -m pip install -e .
```

## Create an Experiment

```bash
./scripts/create_petri_experiment.sh exp-001
```

By default, the script creates:

```text
~/lab/petri/quantitative_trading/exp-001
```

Set `PETRI_EXPERIMENTS_DIR` to use another base directory:

```bash
PETRI_EXPERIMENTS_DIR=~/tmp/petri ./scripts/create_petri_experiment.sh exp-001
```

## Isolating Source Changes

When an experiment may change project source files, use a Git worktree:

```bash
cd $PROJECT_ROOT
git worktree add ~/lab/worktrees/quantitative_trading-exp-001 -b exp/petri-001
cd ~/lab/worktrees/quantitative_trading-exp-001
python -m pip install -e .
```

Point the Petri experiment at the worktree instead of the main project checkout. If the experiment fails, remove the worktree without touching the main worktree.

## Repository Boundary

The following paths are treated as local experiment state and should not be committed from this project repository:

```text
.petri/
.petri-input/
petri.yaml
pipeline.yaml
roles/
```

Only reviewed source, configuration, documentation, and tests should be copied back into the project repository.
