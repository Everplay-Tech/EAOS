# EAOS Component Migration Prompt for Copilot

**Objective:**
Split the monolithic `EAOS` repository into modular, independent repositories under the GitHub organization `E-TECH-PLAYTECH`, and link them back to the main repository as submodules.

**Target Organization:** `https://github.com/E-TECH-PLAYTECH`

## Instructions for Agent/Copilot

For each component listed below, perform the following actions:

1.  **Create Repository:** Create a new public (or private, as appropriate) repository in the `E-TECH-PLAYTECH` organization matching the **Target Repo Name**.
2.  **Split History:** Use `git subtree split` or `git filter-repo` to extract the history of the **Source Directory** into a new branch (e.g., `split/<component-name>`).
3.  **Push Code:** Push this new branch to the `main` branch of the newly created remote repository.
4.  **Refactor Main Repo:**
    *   Remove the **Source Directory** from the `EAOS` repository (git rm).
    *   Add the new repository as a submodule at the same path: `git submodule add <new-repo-url> <source-directory>`.
5.  **Verification:** Ensure the submodule is initialized and the code is accessible.

## Component Inventory

| Component Name | Source Directory | Target Repo Name | Description |
| :--- | :--- | :--- | :--- |
| **Hyperbolic Chamber** | `muscles/hyperbolic-chamber` | `hyperbolic-chamber` | Task planner and deployment engine. (Already cleaned up locally). |
| **Referee Kernel** | `muscles/referee-kernel` | `referee-kernel` | The core microkernel and brain of EAOS. |
| **Ledger** | `ledger/` | `ledger` | Distributed ledger and transaction system. |
| **IHP** | `IHP-main/` | `ihp` | Industrial-grade IHP capsule implementation. |
| **Dr. Lex** | `Intelligence/Dr-Lex` | `dr-lex` | Governance engine and immune system. |
| **Muscle Compiler** | `muscle-compiler/` | `muscle-compiler` | Toolchain for compiling biological muscles. |
| **Nucleus** | `nucleus/` | `nucleus` | Core system runtime. |
| **PermFS Bridge** | `muscles/permfs-bridge` | `permfs-bridge` | Bridge between kernel and PermFS. |
| **Roulette** | `muscles/roulette-rs` | `roulette` | T9-Braid Compression engine. |
| **Symbiote** | `muscles/symbiote` | `symbiote` | Interface for organ/muscle interaction. |
| **Net Stack** | `muscles/net-stack` | `net-stack` | Networking stack implementation. |

## Special Notes

*   **PermFS:** `permfs/` is already initialized as a submodule pointing to `E-TECH-PLAYTECH/permfs`. Ensure it is clean.
*   **Hyperbolic Chamber:** This directory was recently converted from a broken submodule to tracked files to fix tests. It is now ready for a clean split.
*   **Dependencies:** Watch for relative path dependencies in `Cargo.toml` files. These may need to be updated to git dependencies or published crate versions after the split.

## Execution Command Example

```bash
# Example for Hyperbolic Chamber
git subtree split --prefix=muscles/hyperbolic-chamber -b split/hyperbolic-chamber
git remote add hyperbolic-origin https://github.com/E-TECH-PLAYTECH/hyperbolic-chamber.git
git push hyperbolic-origin split/hyperbolic-chamber:main
git rm -r muscles/hyperbolic-chamber
git submodule add https://github.com/E-TECH-PLAYTECH/hyperbolic-chamber.git muscles/hyperbolic-chamber
git commit -m "refactor: migrate hyperbolic-chamber to submodule"
```
