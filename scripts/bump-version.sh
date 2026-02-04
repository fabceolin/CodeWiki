#!/bin/bash
# =============================================================================
# CodeWiki Version Bump Script
# =============================================================================
# Updates version number in all locations and optionally tags the release.
#
# Usage:
#   ./scripts/bump-version.sh <major|minor|patch>
#   ./scripts/bump-version.sh patch              # 1.0.2 -> 1.0.3
#   ./scripts/bump-version.sh minor              # 1.0.2 -> 1.1.0
#   ./scripts/bump-version.sh major              # 1.0.2 -> 2.0.0
#   ./scripts/bump-version.sh patch --push       # Bump, commit, tag, and push
#
# Options:
#   --commit    Automatically commit the version bump
#   --tag       Create a git tag (implies --commit)
#   --push      Commit, tag, and push to origin
#   --dry-run   Show what would be changed without making changes
#
# Files updated:
#   - pyproject.toml (version = "x.x.x")
#   - codewiki/__init__.py (__version__ = "x.x.x")
#   - codewiki/src/be/documentation_generator.py ("generator_version": "x.x.x")
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Files to update
FILES=(
    "pyproject.toml"
    "codewiki/__init__.py"
    "codewiki/src/be/documentation_generator.py"
)

# Patterns for each file
declare -A PATTERNS
PATTERNS["pyproject.toml"]='s/^version = "[0-9]+\.[0-9]+\.[0-9]+"/version = "NEW_VERSION"/'
PATTERNS["codewiki/__init__.py"]='s/__version__ = "[0-9]+\.[0-9]+\.[0-9]+"/__version__ = "NEW_VERSION"/'
PATTERNS["codewiki/src/be/documentation_generator.py"]='s/"generator_version": "[0-9]+\.[0-9]+\.[0-9]+"/"generator_version": "NEW_VERSION"/'

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

show_usage() {
    echo "Usage: $0 <major|minor|patch> [options]"
    echo ""
    echo "Arguments:"
    echo "  major    Bump major version (1.0.2 -> 2.0.0)"
    echo "  minor    Bump minor version (1.0.2 -> 1.1.0)"
    echo "  patch    Bump patch version (1.0.2 -> 1.0.3)"
    echo ""
    echo "Options:"
    echo "  --commit    Automatically commit the version bump"
    echo "  --tag       Create a git tag (implies --commit)"
    echo "  --push      Commit, tag, and push to origin"
    echo "  --dry-run   Show what would be changed without making changes"
    echo "  --help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 patch                  # Bump patch version"
    echo "  $0 minor --commit         # Bump minor and commit"
    echo "  $0 major --tag            # Bump major, commit, and tag"
    echo "  $0 patch --push           # Bump, commit, tag, and push"
    echo "  $0 minor --dry-run        # Preview changes"
}

get_current_version() {
    grep -E '^version = ' "$ROOT_DIR/pyproject.toml" | sed 's/version = "\(.*\)"/\1/'
}

calculate_new_version() {
    local current="$1"
    local bump_type="$2"

    # Parse current version
    local major minor patch
    IFS='.' read -r major minor patch <<< "$current"

    case "$bump_type" in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            log_error "Invalid bump type: $bump_type"
            exit 1
            ;;
    esac

    echo "$major.$minor.$patch"
}

validate_version() {
    local version="$1"
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        log_error "Invalid version format: $version"
        log_error "Version must be in semver format: MAJOR.MINOR.PATCH (e.g., 1.0.3)"
        exit 1
    fi
}

update_file() {
    local file="$1"
    local new_version="$2"
    local dry_run="$3"
    local filepath="$ROOT_DIR/$file"

    if [[ ! -f "$filepath" ]]; then
        log_warning "File not found: $filepath"
        return 1
    fi

    local pattern="${PATTERNS[$file]}"
    pattern="${pattern//NEW_VERSION/$new_version}"

    if [[ "$dry_run" == "true" ]]; then
        echo -e "  ${YELLOW}Would update:${NC} $file"
        grep -E "version|__version__|generator_version" "$filepath" | head -1 | sed 's/^/    /'
        echo -e "  ${GREEN}To:${NC}"
        sed -E "$pattern" "$filepath" | grep -E "version|__version__|generator_version" | head -1 | sed 's/^/    /'
    else
        # Use sed with -i for in-place editing (compatible with both macOS and Linux)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' -E "$pattern" "$filepath"
        else
            sed -i -E "$pattern" "$filepath"
        fi
        log_success "Updated: $file"
    fi
}

verify_update() {
    local new_version="$1"
    local errors=0

    log_info "Verifying version consistency..."

    for file in "${FILES[@]}"; do
        local filepath="$ROOT_DIR/$file"
        if grep -q "$new_version" "$filepath"; then
            echo -e "  ${GREEN}✓${NC} $file"
        else
            echo -e "  ${RED}✗${NC} $file - version not found"
            errors=$((errors + 1))
        fi
    done

    if [[ $errors -gt 0 ]]; then
        log_error "Version verification failed!"
        return 1
    fi

    log_success "All files updated to version $new_version"
}

# Parse arguments
BUMP_TYPE=""
DO_COMMIT=false
DO_TAG=false
DO_PUSH=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        major|minor|patch)
            if [[ -z "$BUMP_TYPE" ]]; then
                BUMP_TYPE="$1"
            else
                log_error "Bump type already specified: $BUMP_TYPE"
                exit 1
            fi
            shift
            ;;
        --commit)
            DO_COMMIT=true
            shift
            ;;
        --tag)
            DO_COMMIT=true
            DO_TAG=true
            shift
            ;;
        --push)
            DO_COMMIT=true
            DO_TAG=true
            DO_PUSH=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        -*)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
        *)
            log_error "Unexpected argument: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate input
if [[ -z "$BUMP_TYPE" ]]; then
    log_error "No bump type specified (major, minor, or patch)"
    show_usage
    exit 1
fi

# Change to root directory
cd "$ROOT_DIR"

# Get current and calculate new version
CURRENT_VERSION=$(get_current_version)
NEW_VERSION=$(calculate_new_version "$CURRENT_VERSION" "$BUMP_TYPE")

validate_version "$NEW_VERSION"

# Show current state
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║         CodeWiki Version Bump              ║"
echo "╠════════════════════════════════════════════╣"
printf "║  Current version: %-23s ║\n" "$CURRENT_VERSION"
printf "║  New version:     %-23s ║\n" "$NEW_VERSION"
printf "║  Bump type:       %-23s ║\n" "$BUMP_TYPE"
echo "╚════════════════════════════════════════════╝"
echo ""

# Update files
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Dry run - showing what would be changed:"
    echo ""
fi

for file in "${FILES[@]}"; do
    update_file "$file" "$NEW_VERSION" "$DRY_RUN"
done

echo ""

# Exit if dry run
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Would create git tag: v$NEW_VERSION"
    echo ""
    log_info "Dry run complete. No changes made."
    exit 0
fi

# Verify updates
verify_update "$NEW_VERSION"

# Commit if requested
if [[ "$DO_COMMIT" == "true" ]]; then
    echo ""
    log_info "Committing version bump..."

    git add "${FILES[@]}"
    git commit -m "chore(release): Bump version to $NEW_VERSION

Bump type: $BUMP_TYPE
Previous version: $CURRENT_VERSION

Updated version in:
- pyproject.toml
- codewiki/__init__.py
- codewiki/src/be/documentation_generator.py"

    log_success "Committed version bump"

    # Create tag if requested
    if [[ "$DO_TAG" == "true" ]]; then
        log_info "Creating git tag v$NEW_VERSION..."
        git tag -a "v$NEW_VERSION" -m "Release v$NEW_VERSION

Changes from v$CURRENT_VERSION to v$NEW_VERSION"
        log_success "Created tag: v$NEW_VERSION"
    fi

    # Push if requested
    if [[ "$DO_PUSH" == "true" ]]; then
        log_info "Pushing to origin..."
        git push origin HEAD
        if [[ "$DO_TAG" == "true" ]]; then
            log_info "Pushing tags..."
            git push origin "v$NEW_VERSION"
        fi
        log_success "Pushed to origin"
    fi
fi

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║              Summary                       ║"
echo "╠════════════════════════════════════════════╣"
printf "║  Version bumped:  %s -> %-14s ║\n" "$CURRENT_VERSION" "$NEW_VERSION"
printf "║  Committed:       %-23s ║\n" "$([[ "$DO_COMMIT" == "true" ]] && echo "Yes" || echo "No")"
printf "║  Tagged:          %-23s ║\n" "$([[ "$DO_TAG" == "true" ]] && echo "v$NEW_VERSION" || echo "No")"
printf "║  Pushed:          %-23s ║\n" "$([[ "$DO_PUSH" == "true" ]] && echo "Yes" || echo "No")"
echo "╚════════════════════════════════════════════╝"

if [[ "$DO_COMMIT" != "true" ]]; then
    echo ""
    log_info "To commit and tag this change, run:"
    echo "  git add ${FILES[*]}"
    echo "  git commit -m 'chore(release): Bump version to $NEW_VERSION'"
    echo "  git tag -a v$NEW_VERSION -m 'Release v$NEW_VERSION'"
fi
