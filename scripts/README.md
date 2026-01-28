# EAOS Automation Scripts

This directory contains automation scripts for maintaining and managing the EAOS repository.

## Available Scripts

### `split-monorepo.sh`

Automates the process of splitting the EAOS monorepo into multiple independent repositories.

**Purpose:**
- Extract components from the monorepo while preserving Git history
- Create new repositories in the E-TECH-PLAYTECH organization
- Convert extracted directories to Git submodules

**Quick Start:**
```bash
# Test run (no changes made)
./scripts/split-monorepo.sh --dry-run

# Execute the split
./scripts/split-monorepo.sh
```

**Documentation:** See [docs/MONOREPO_SPLIT_GUIDE.md](../docs/MONOREPO_SPLIT_GUIDE.md) for detailed usage instructions.

---

### `verify-split.sh`

Verifies that the monorepo split completed successfully by checking submodule configuration, remote repositories, and more.

**Purpose:**
- Verify each component is properly configured as a submodule
- Check that remote repositories exist in E-TECH-PLAYTECH
- Ensure submodules are initialized correctly
- Validate .gitmodules configuration

**Quick Start:**
```bash
# Run verification after split
./scripts/verify-split.sh
```

**What it checks:**
- ✓ Directory is configured as submodule
- ✓ Remote repository exists
- ✓ Submodule is initialized
- ✓ Submodule URL is correct
- ✓ No leftover split branches
- ✓ .gitmodules file exists and is valid
- ✓ Working directory is clean

---

### `rollback-split.sh`

Interactive script to rollback a monorepo split if something goes wrong.

**Purpose:**
- Restore repository to pre-split state using backup branches
- Clean up failed split artifacts (branches, remotes)
- Create new branch from backup for safety

**Quick Start:**
```bash
# Interactive rollback
./scripts/rollback-split.sh
```

**Features:**
- Lists available backup branches
- Interactive branch selection
- Creates new rollback branch (preserves backup)
- Optionally cleans up split artifacts
- Confirmation prompts for safety

## General Usage Guidelines

1. **Always test with dry-run first**: Use `--dry-run` or `DRY_RUN=true` to preview changes
2. **Check prerequisites**: Ensure required tools are installed (see script documentation)
3. **Backup important data**: Scripts may create automatic backups, but manual backups are recommended
4. **Review output**: Check script output for errors or warnings before proceeding

## Script Development Guidelines

When adding new scripts to this directory:

1. **Use bash shebang**: Start with `#!/usr/bin/env bash`
2. **Enable strict mode**: Use `set -euo pipefail`
3. **Add help option**: Implement `--help` flag
4. **Support dry-run**: Add `--dry-run` mode for safety
5. **Use colors**: Implement colored output (INFO, SUCCESS, WARNING, ERROR)
6. **Add documentation**: Create or update documentation in `docs/`
7. **Make executable**: Run `chmod +x script-name.sh`

## Contributing

When contributing scripts:

1. Follow the existing code style
2. Add comprehensive error handling
3. Include usage examples in comments
4. Test thoroughly before committing
5. Update this README with new scripts
