#!/bin/bash

# Quantitative Trading Test Runner (UV Enhanced)
# Unified entry for unit / integration / web / all tests

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Defaults
TEST_TYPE=""
VERBOSE=false
COVERAGE=false
PARALLEL=false
FAIL_FAST=false
FILTER=""
SYNC=false
CLEAN=false
PYTHON_VERSION=""
HEADED=false
USE_UV=true  # Set to false to use plain python/pytest

print_usage() {
    cat <<EOF
Usage: $0 <test_type> [options]

Test Types:
  unit          Run unit tests           (tests/unit/)
  integration   Run integration tests    (tests/integration/)
  web           Run Playwright E2E tests (tests/web/)
  all           Run unit + integration + web

Common Options:
  -v, --verbose         Verbose output
  -f, --filter <pattern> pytest -k filter pattern
  --coverage            Generate coverage report (unit/integration only)
  --parallel            Run tests in parallel (requires pytest-xdist)
  --fail-fast           Stop on first failure

Web-specific Options:
  --headed              Run browser in headed mode (visible)

UV Options:
  --no-uv               Skip uv, use plain python/pytest directly
  --sync                Sync dependencies before running
  --clean               Remove .venv and recreate
  --python <version>    Use specific Python version (e.g. 3.12)

Examples:
  $0 unit                        # Run all unit tests
  $0 integration -v              # Run integration tests verbosely
  $0 web --headed                # Run E2E tests with visible browser
  $0 all --coverage              # Run everything with coverage
  $0 unit -f "test_exceptions"   # Run unit tests matching pattern
EOF
}

# Helpers
print_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[OK]${NC} $1"; }
print_error()   { echo -e "${RED}[FAIL]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_step()    { echo -e "${CYAN}[STEP]${NC} $1"; }
print_uv()      { echo -e "${PURPLE}[UV]${NC} $1"; }

calc_duration() {
    if command -v bc &> /dev/null; then
        echo "$1" | bc -l 2>/dev/null || echo "?"
    else
        uv run python -c "print(round($1, 1))" 2>/dev/null || echo "?"
    fi
}

check_uv() {
    if ! command -v uv &> /dev/null; then
        print_warning "uv not found, falling back to plain python/pytest"
        USE_UV=false
    fi
}

# Runner prefix: "uv run" or empty
run_prefix() {
    if [ "$USE_UV" = true ]; then
        echo "uv run"
    else
        echo ""
    fi
}

setup_env() {
    if [ "$USE_UV" = false ]; then
        return
    fi
    if [ ! -d ".venv" ]; then
        print_uv "Creating virtual environment..."
        uv venv
    fi
    if [ "$SYNC" = true ]; then
        print_uv "Syncing dependencies..."
        uv sync --all-extras --group dev --group test
    fi
}

# ---------- Test runners ----------

build_pytest_cmd() {
    # $1 = test path
    local test_path="$1"
    local prefix
    prefix=$(run_prefix)
    local cmd="${prefix} pytest ${test_path}"

    if [ "$COVERAGE" = true ]; then
        cmd="${prefix} pytest --cov=quant --cov-report=term-missing ${test_path}"
    fi
    [ "$VERBOSE" = true ]   && cmd="$cmd -v"
    [ "$PARALLEL" = true ]  && cmd="$cmd -n auto"
    [ "$FAIL_FAST" = true ] && cmd="$cmd -x --tb=short"
    [ -n "$FILTER" ]        && cmd="$cmd -k \"$FILTER\""
    cmd="$cmd --color=yes"
    echo "$cmd"
}

run_test_suite() {
    # $1 = label, $2 = test path, $3 = extra args (optional)
    local label="$1"
    local test_path="$2"
    local extra="$3"

    print_step "Running ${label}..."
    local cmd
    cmd=$(build_pytest_cmd "$test_path")
    [ -n "$extra" ] && cmd="$cmd $extra"

    print_info "Executing: $cmd"
    local start_time
    start_time=$(date +%s.%N)

    if eval "$cmd"; then
        local end_time
        end_time=$(date +%s.%N)
        local duration
        duration=$(calc_duration "$end_time - $start_time")
        print_success "${label} passed (${duration}s)"
        return 0
    else
        local end_time
        end_time=$(date +%s.%N)
        local duration
        duration=$(calc_duration "$end_time - $start_time")
        print_error "${label} failed (${duration}s)"
        return 1
    fi
}

run_unit_tests() {
    run_test_suite "Unit tests" "tests/unit/"
}

run_integration_tests() {
    run_test_suite "Integration tests" "tests/integration/"
}

run_web_tests() {
    local extra=""
    [ "$HEADED" = true ] && extra="--headed"
    # Web tests: no coverage (Playwright doesn't instrument Python)
    local save_coverage="$COVERAGE"
    COVERAGE=false
    run_test_suite "Web E2E tests" "tests/web/" "$extra"
    local result=$?
    COVERAGE="$save_coverage"
    return $result
}

# ---------- Argument parsing ----------

if [ $# -eq 0 ]; then
    print_error "No test type specified"
    print_usage
    exit 1
fi

if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    print_usage
    exit 0
fi

TEST_TYPE="$1"
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--verbose)   VERBOSE=true;         shift ;;
        -f|--filter)    FILTER="$2";          shift 2 ;;
        --coverage)     COVERAGE=true;        shift ;;
        --parallel)     PARALLEL=true;        shift ;;
        --fail-fast)    FAIL_FAST=true;       shift ;;
        --headed)       HEADED=true;          shift ;;
        --no-uv)        USE_UV=false;         shift ;;
        --sync)         SYNC=true;            shift ;;
        --clean)        CLEAN=true;           shift ;;
        --python)       PYTHON_VERSION="$2";  shift 2 ;;
        -h|--help)      print_usage; exit 0 ;;
        *)              print_error "Unknown option: $1"; print_usage; exit 1 ;;
    esac
done

# ---------- Setup ----------

# Ensure project root is on PYTHONPATH
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

check_uv
setup_env

if [ "$USE_UV" = true ] && [ -n "$PYTHON_VERSION" ]; then
    print_uv "Ensuring Python ${PYTHON_VERSION}..."
    uv python install "$PYTHON_VERSION"
fi

if [ "$CLEAN" = true ]; then
    print_step "Cleaning environment..."
    rm -rf .venv htmlcov/ .coverage .pytest_cache/
    [ "$USE_UV" = true ] && uv venv
    print_step "Clean environment created"
fi

# ---------- Main ----------

print_step "Quantitative Trading Test Runner"
print_info "Test type: $TEST_TYPE"
print_info "Python: $($(run_prefix) python --version 2>&1)"

case $TEST_TYPE in
    unit)
        run_unit_tests
        exit $?
        ;;
    integration)
        run_integration_tests
        exit $?
        ;;
    web)
        run_web_tests
        exit $?
        ;;
    all)
        unit_ok=0; integ_ok=0; web_ok=0
        all_start=$(date +%s.%N)

        run_unit_tests        || unit_ok=1;  echo ""
        run_integration_tests || integ_ok=1; echo ""
        run_web_tests         || web_ok=1;   echo ""

        all_end=$(date +%s.%N)
        all_dur=$(calc_duration "$all_end - $all_start")

        print_step "=== Summary ==="
        [ $unit_ok  -eq 0 ] && print_success "Unit:        PASSED" || print_error "Unit:        FAILED"
        [ $integ_ok -eq 0 ] && print_success "Integration: PASSED" || print_error "Integration: FAILED"
        [ $web_ok   -eq 0 ] && print_success "Web E2E:     PASSED" || print_error "Web E2E:     FAILED"
        print_info "Total: ${all_dur}s"

        [ $unit_ok -eq 0 ] && [ $integ_ok -eq 0 ] && [ $web_ok -eq 0 ] && exit 0 || exit 1
        ;;
    *)
        print_error "Invalid test type: $TEST_TYPE (expected: unit | integration | web | all)"
        print_usage
        exit 1
        ;;
esac
