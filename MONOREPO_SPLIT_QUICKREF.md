# Monorepo Split Quick Reference

## Quick Start

### 1. Dry Run (Test First)
```bash
./scripts/split-monorepo.sh --dry-run --skip-github-create
```

### 2. Authenticate with GitHub
```bash
gh auth login
```

### 3. Run the Split
```bash
./scripts/split-monorepo.sh
```

### 4. Verify Results
```bash
./scripts/verify-split.sh
```

### 5. Initialize Submodules
```bash
git submodule update --init --recursive
```

### 6. Push Changes
```bash
git push origin <branch-name>
```

## If Something Goes Wrong

### Rollback to Backup
```bash
./scripts/rollback-split.sh
```

## Components Being Split

| Component | Path | New Repo |
|-----------|------|----------|
| Hyperbolic Chamber | `Ea_OS/muscles/hyperbolic-chamber` | `E-TECH-PLAYTECH/hyperbolic-chamber` |
| Referee Kernel | `Ea_OS/muscles/referee-kernel` | `E-TECH-PLAYTECH/referee-kernel` |
| Ledger | `Ea_OS/ledger` | `E-TECH-PLAYTECH/ledger` |
| IHP | `Ea_OS/IHP-main` | `E-TECH-PLAYTECH/ihp` |
| Dr. Lex | `Ea_OS/Intelligence/Dr-Lex` | `E-TECH-PLAYTECH/dr-lex` |
| Muscle Compiler | `Ea_OS/muscle-compiler` | `E-TECH-PLAYTECH/muscle-compiler` |
| Nucleus | `Ea_OS/nucleus` | `E-TECH-PLAYTECH/nucleus` |
| PermFS Bridge | `Ea_OS/muscles/permfs-bridge` | `E-TECH-PLAYTECH/permfs-bridge` |
| Roulette | `Ea_OS/muscles/roulette-kernel-rs-main` | `E-TECH-PLAYTECH/roulette` |
| Symbiote | `Ea_OS/muscles/symbiote` | `E-TECH-PLAYTECH/symbiote` |
| Net Stack | `Ea_OS/muscles/net-stack` | `E-TECH-PLAYTECH/net-stack` |

## Documentation

- **Detailed Guide**: [docs/MONOREPO_SPLIT_GUIDE.md](docs/MONOREPO_SPLIT_GUIDE.md)
- **Scripts README**: [scripts/README.md](scripts/README.md)

## Prerequisites

- Git 2.0+
- GitHub CLI (`gh`) - https://cli.github.com/
- Authenticated with GitHub (`gh auth login`)
- Permission to create repos in E-TECH-PLAYTECH organization

## Important Notes

⚠️ **Backup created automatically** - The script creates a backup branch before making changes

⚠️ **One-way operation** - Once split, it's difficult to recombine

⚠️ **Test first** - Always run with `--dry-run` before executing

✅ **History preserved** - Full Git history is maintained in each new repository

✅ **Rollback available** - Use `rollback-split.sh` if needed
