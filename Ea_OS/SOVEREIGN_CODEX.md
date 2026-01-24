# The Sovereign Codex: EAOS v1.0

> "The Body must survive the Mind."

**EAOS (Eä Operating System)** is a biologically inspired, sovereign computing environment. It is designed to be a "Living Pod" that protects its user's logic and data from the hostile environment of the open web.

---

## 🧬 Anatomy of the Organism

The system is architected as a biological entity:

### 1. The Nucleus (The Will)
The userspace runtime. It contains your identity, your keys, and your intent.
- **Thalamus (Senses):** Filters input from the outside world (Keyboard, Network).
- **Visual Cortex (Sight):** Renders the interface.
- **Endocrine System (Feeling):** Circulates Pheromones to coordinate organs.

### 2. The Referee (The Autonomic Nervous System)
The kernel. It enforces the laws of physics and biology.
- **Arachnid (Vascular):** The Network Stack. Harvests HTTP data.
- **Scheduler (Cell Division):** Manages multitasking.
- **Sentry (Immune System):** Cryptographic verification.

### 3. Muscles (The Actuators)
Specialized, isolated WASM-like modules.
- **Broca:** Language Center (Parses text commands).
- **Myocyte:** Logic Engine (Executes Quenyan code).
- **Osteon:** Bone/Storage (Writes to PermFS).
- **Mirror:** Simulation (Predicts consequences of actions).

---

## ⌨️ How to Speak to the Nucleus

The Nucleus accepts commands via the **Somatic Nerve** (Keyboard/UART).

### Office Suite Commands
| Command | Description | Example |
| :--- | :--- | :--- |
| `write <filename> <content>` | Save a document to Osteon | `write notes.txt "Hello World"` |
| `logic <name> <formula>` | Compile and run Quenyan logic | `logic profit.qyn "revenue - cost"` |
| `read <filename>` | Read a document (Coming Soon) | `read notes.txt` |
| `list` | List all files in PermFS | `list` |
| `status` | Show system vital signs | `status` |

### Hive Mind Commands
| Command | Description | Example |
| :--- | :--- | :--- |
| `harvest <url>` | Fetch data from the web | `harvest example.com` |

---

## 🧠 Quenyan Logic

Quenyan is the language of thought in EAOS. It is a strict, typed logic language.

**Supported Operations:**
- Arithmetic: `+`, `-`, `*`, `/`
- Grouping: `(`, `)`
- Types: 64-bit Floating Point

**Example:**
```quenyan
(100 * 0.05) + 20
```
*Result: 25.0*

---

## 🛡️ Security Model

1.  **Sovereign Storage:** All data written to disk is encrypted and braided by **Roulette**.
2.  **Signed Intents:** The Nucleus cannot act without signing an Intent with the Master Key held by **Sentry**.
3.  **Resource Governance:** **Mitochondria** tracks energy usage. If a process loops infinitely, it is throttled.
4.  **Static Analysis:** **Mirror** simulates every command before execution. If it detects danger (e.g., deleting root), it warns the user.

---

## 🚀 Building and Running

**Prerequisites:**
- Rust Nightly
- QEMU
- UEFI Firmware (OVMF)

**Build:**
```bash
cargo build --workspace
```

**Run (Simulation):**
```bash
./run-eaos.sh
```

**Run (Tests):**
```bash
cargo test --workspace
```

---

*Verified 2026-01-20 by Gemini (Builder)*
