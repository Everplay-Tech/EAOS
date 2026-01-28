# EAOS Monorepo Split Guide

This guide explains how to use the automated monorepo split script to extract EAOS components into separate repositories under the E-TECH-PLAYTECH organization.

## Overview

The `split-monorepo.sh` script automates the process of:
1. Splitting each component from the monorepo while preserving full Git history
2. Creating new repositories in the E-TECH-PLAYTECH GitHub organization
3. Pushing the split history to the new repositories
4. Replacing the directories with Git submodules in the main repository

## Prerequisites

Before running the script, ensure you have:

1. **Git** - Version 2.0 or higher
2. **GitHub CLI (`gh`)** - Install from https://cli.github.com/
3. **GitHub Authentication** - Run `gh auth login` to authenticate
4. **Repository Permissions** - You must have permission to create repositories in the E-TECH-PLAYTECH organization
5. **Clean Working Directory** - Commit or stash any uncommitted changes

## Components to be Split

The following 11 components will be extracted:

| Component | Source Directory | Target Repo |
|-----------|------------------|-------------|
| Hyperbolic Chamber | `Ea_OS/muscles/hyperbolic-chamber` | `hyperbolic-chamber` |
| Referee Kernel | `Ea_OS/muscles/referee-kernel` | `referee-kernel` |
| Ledger | `Ea_OS/ledger` | `ledger` |
| IHP | `Ea_OS/IHP-main` | `ihp` |
| Dr. Lex | `Ea_OS/Intelligence/Dr-Lex` | `dr-lex` |
| Muscle Compiler | `Ea_OS/muscle-compiler` | `muscle-compiler` |
| Nucleus | `Ea_OS/nucleus` | `nucleus` |
| PermFS Bridge | `Ea_OS/muscles/permfs-bridge` | `permfs-bridge` |
| Roulette | `Ea_OS/muscles/roulette-kernel-rs-main` | `roulette` |
| Symbiote | `Ea_OS/muscles/symbiote` | `symbiote` |
| Net Stack | `Ea_OS/muscles/net-stack` | `net-stack` |

## Usage

### Basic Usage

```bash
# Run the script (will perform actual split)
./scripts/split-monorepo.sh
```

### Dry Run Mode (Recommended First)

To see what the script will do without making any changes:

```bash
# Dry run - no changes will be made
./scripts/split-monorepo.sh --dry-run
```

Or using environment variable:

```bash
DRY_RUN=true ./scripts/split-monorepo.sh
```

### Skip GitHub Repository Creation

If the repositories already exist in GitHub:

```bash
./scripts/split-monorepo.sh --skip-github-create
```

### Get Help

```bash
./scripts/split-monorepo.sh --help
```

## What the Script Does

For each component, the script performs the following steps:

1. **Create GitHub Repository**
   - Creates a new public repository in the E-TECH-PLAYTECH organization
   - Sets the repository description
   - Enables issues and disables wiki

2. **Split Git History**
   - Uses `git subtree split` to extract the component's history
   - Creates a temporary branch (e.g., `split/hyperbolic-chamber`)
   - Preserves all commits, authors, and timestamps

3. **Push to New Repository**
   - Adds a temporary remote for the new repository
   - Pushes the split branch to the new repository's `main` branch

4. **Convert to Submodule**
   - Removes the original directory from the monorepo
   - Adds the new repository as a Git submodule
   - Creates a commit documenting the migration

5. **Cleanup**
   - Removes temporary split branches
   - Cleans up temporary remotes

## Safety Features

- **Backup Branch**: Creates a backup branch before starting (e.g., `backup/pre-split-20260128-123456`)
- **Dry Run Mode**: Test the entire process without making changes
- **Existing Repository Detection**: Skips creation if a repository already exists
- **Directory Existence Check**: Verifies source directories exist before processing
- **Error Handling**: Uses `set -euo pipefail` for robust error handling

## After Running the Script

1. **Review Changes**
   ```bash
   git status
   git log --oneline -10
   ```

2. **Initialize Submodules**
   ```bash
   git submodule update --init --recursive
   ```

3. **Verify Each Submodule**
   ```bash
   # Check that each submodule is properly linked
   git submodule status
   ```

4. **Test Build/Functionality**
   - Ensure the project still builds correctly
   - Run tests if applicable

5. **Push Changes**
   ```bash
   git push origin <branch-name>
   ```

## Rollback Procedure

If something goes wrong, you can rollback using the backup branch:

```bash
# Find your backup branch
git branch --list 'backup/*'

# Rollback to the backup (replace with actual branch name)
git checkout backup/pre-split-20260128-123456

# Create a new branch from the backup
git checkout -b rollback-attempt

# Force push if needed (use with caution)
git push origin rollback-attempt --force
```

## Troubleshooting

### "Not authenticated with GitHub CLI"

Run:
```bash
gh auth login
```

### "Repository already exists"

The script will skip creation and continue. If you need to recreate:
```bash
gh repo delete E-TECH-PLAYTECH/repo-name
```

### "Source directory does not exist"

Check that the directory path in the script matches your repository structure. Update the `COMPONENTS` array in the script if needed.

### Git Subtree Split is Slow

`git subtree split` can be slow for large repositories with long history. This is normal. The script will show progress for each component.

### Submodule Not Showing Content

After the split, initialize submodules:
```bash
git submodule update --init --recursive
```

## Manual Split (Alternative)

If you prefer to split components manually:

```bash
# Example for hyperbolic-chamber
cd /path/to/EAOS

# Create split branch
git subtree split --prefix=Ea_OS/muscles/hyperbolic-chamber -b split/hyperbolic-chamber

# Create new repository (using gh CLI)
gh repo create E-TECH-PLAYTECH/hyperbolic-chamber --public

# Push to new repository
git remote add hyperbolic-origin https://github.com/E-TECH-PLAYTECH/hyperbolic-chamber.git
git push hyperbolic-origin split/hyperbolic-chamber:main

# Remove directory and add as submodule
git rm -r Ea_OS/muscles/hyperbolic-chamber
git submodule add https://github.com/E-TECH-PLAYTECH/hyperbolic-chamber.git Ea_OS/muscles/hyperbolic-chamber
git commit -m "refactor: migrate hyperbolic-chamber to submodule"

# Clean up
git branch -D split/hyperbolic-chamber
git remote remove hyperbolic-origin
```

## Important Notes

1. **One-Way Operation**: Once split, it's difficult to recombine. Make sure you want to proceed.
2. **Git History**: Full Git history is preserved in each new repository.
3. **Submodule Workflows**: Team members will need to learn submodule commands (`git submodule update`, etc.)
4. **CI/CD Updates**: Update CI/CD pipelines to handle submodules correctly.
5. **Dependencies**: Some components may have interdependencies that need to be resolved.

## Post-Split Considerations

After splitting the monorepo, consider:

1. **Update Documentation**
   - Update README files in each repository
   - Add links between related repositories
   - Document the new repository structure

2. **Configure CI/CD**
   - Set up GitHub Actions or other CI for each repository
   - Configure cross-repository dependencies

3. **Set Up Branch Protection**
   - Configure branch protection rules for each repository
   - Set up required reviews and status checks

4. **Update Issue Tracking**
   - Migrate or link issues to appropriate repositories
   - Update project boards

5. **Publish Packages**
   - Consider publishing stable components as packages
   - Update dependency references

## Getting Help

If you encounter issues:
- Check the script's log output for detailed error messages
- Review the backup branch to understand what changed
- Consult the Git documentation for `git subtree` and `git submodule`
- Open an issue in the EAOS repository

## References

- [Git Subtree Documentation](https://git-scm.com/docs/git-subtree)
- [Git Submodules Documentation](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
- [GitHub CLI Documentation](https://cli.github.com/manual/)
