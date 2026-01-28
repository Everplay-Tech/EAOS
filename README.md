# Eä OS (EAOS)

**A cryptographically-secured, muscle-based operating system for executing isolated neural network components with absolute security and verifiability.**

> "Security derived from mathematical proof, not procedural checks"

---

## 🚀 Quick Links

- **[Master System Summary](EAOS_MASTER_SUMMARY_20251230_CZA.md)** - Comprehensive overview of the Eä OS architecture
- **[Architecture Documentation](Ea_OS/ARCHITECTURE.md)** - Detailed architectural specifications
- **[Implementation Summary](IMPLEMENTATION_SUMMARY.md)** - Current implementation status

---

## 🤖 AI Agent Resources

### Custom Copilot Agent Design

Want to build a specialized AI assistant for your workflow? Check out our interactive guide:

📋 **[Custom Copilot Agent Design Prompt](CUSTOM_COPILOT_AGENT_DESIGN_PROMPT.md)**

This engaging, step-by-step guide helps you design custom Copilot agents through a collaborative dialogue. Perfect for:
- Creating domain-specific coding assistants
- Automating repetitive development tasks
- Building project-aware AI helpers
- Designing workflow-integrated agents

### Existing Agent Configurations

- **[GEMINI Agent Protocol](GEMINI.md)** - External cognitive assistant for EAOS development
- **[Agent Instructions](AGENTS.md)** - General agent configuration and skills
- **[Copilot Migration Prompt](Ea_OS/COPILOT_MIGRATION_PROMPT.md)** - Component migration guide

---

## 📚 Documentation

### Core System Components

- **Referee** - UEFI bootloader and initial secure environment (59.8 KiB TCB)
- **Nucleus** - Biological kernel with event-driven architecture (8 KiB target)
- **Muscle Contract** - Encrypted, authenticated program containers
- **Ledger** - Distributed lattice-based transaction system
- **Symbiote** - Organ/muscle interaction interface

### Deep Dives

- [Referee & Nucleus Deep Dive](DEEPDIVE_REFEREE_NUCLEUS_20251230_CZA.md)
- [Organelles Deep Dive](DEEPDIVE_ORGANELLES_20251230_CZA.md)
- [Ledger Deep Dive](DEEPDIVE_LEDGER_20251230_CZA.md)
- [Muscle Contract Deep Dive](DEEPDIVE_MUSCLE_CONTRACT_20251230_CZA.md)
- [Symbiote Deep Dive](DEEPDIVE_SYMBIOTE_20251230_CZA.md)

---

## 🏗️ Project Structure

```
EAOS/
├── Ea_OS/                      # Core operating system components
│   ├── ledger/                # Distributed ledger system
│   ├── muscles/               # Compiled muscle programs
│   ├── nucleus/               # Kernel implementation
│   └── referee/               # Secure bootloader
├── NN/                        # Neural network organelles
├── docs/                      # Additional documentation
├── scripts/                   # Build and utility scripts
└── CUSTOM_COPILOT_AGENT_DESIGN_PROMPT.md  # Interactive agent design guide
```

---

## 🔒 Core Principles

- **Minimal TCB**: Reduced trusted computing base (59.8 KiB + 8 KiB)
- **Zero Trusted Setup**: RSA-2048 modulus derived from π digits
- **Append-Only**: Immutable audit trail via lattice ledger
- **Capability-Based Security**: Declare before use, no ambient authority
- **Biological Constraints**: Event-driven architecture (neurons fire or die)

---

## 🛠️ Development

See individual component READMEs for specific build instructions:
- [Scripts README](scripts/README.md)
- [Ledger README](Ea_OS/ledger/README.md)

---

## 📖 Additional Resources

- **[Claude Explains EAOS](Claude_EXPLAINS_20251230_CZA.md)** - Simplified explanation of the system
- **[Migration Verification](MIGRATION_VERIFICATION_REPORT.md)** - Repository modularization status
- **[Monorepo Split Guide](MONOREPO_SPLIT_QUICKREF.md)** - Component separation reference

---

## 🤝 Contributing

Interested in contributing or building AI agents for EAOS development? Start with:

1. Read the [Master System Summary](EAOS_MASTER_SUMMARY_20251230_CZA.md)
2. Explore the [Custom Copilot Agent Design Prompt](CUSTOM_COPILOT_AGENT_DESIGN_PROMPT.md)
3. Review existing [Agent Configurations](GEMINI.md)

---

**Status**: ~85% Complete (as of 2025-12-30)

**Authors**: XZA and CZA (with GEMINI cognitive assistant)
