#!/usr/bin/env python3
"""
Generate project documentation from Ork conversations
"""
import json
from pathlib import Path

def generate_architecture_doc():
    """Generate architecture document from Ork sessions."""
    sessions_dir = Path("ork_sessions/distributed-filesystem-v2")
    
    all_decisions = []
    all_diagrams = []
    
    # Collect from all sessions
    for session in sessions_dir.glob("*/session.json"):
        with open(session) as f:
            data = json.load(f)
            all_decisions.extend(data.get("decisions", []))
    
    # Ask Ork to synthesize
    prompt = f"""
    Synthesize these file system design decisions into a coherent architecture document:
    
    {chr(10).join(f'- {d}' for d in set(all_decisions))}
    
    Include:
    1. System Overview
    2. Component Architecture
    3. Data Flow Diagrams
    4. API Specifications
    5. Deployment Considerations
    """
    
    # Call Ork
    import subprocess
    result = subprocess.run(
        ["ork", "call", prompt],
        capture_output=True,
        text=True
    )
    
    # Save to docs
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    
    with open(docs_dir / "ARCHITECTURE.md", "w") as f:
        f.write(result.stdout)
    
    print(f"📄 Architecture document generated: docs/ARCHITECTURE.md")

if __name__ == "__main__":
    generate_architecture_doc()
