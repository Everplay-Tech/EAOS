#!/usr/bin/env python3
"""
Structured Design Session with Ork
Keeps context, manages sessions, generates documentation
"""
import subprocess
import json
import os
from datetime import datetime
from pathlib import Path

class OrkDesignSession:
    def __init__(self, project_name):
        self.project_name = project_name
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = Path(f"ork_sessions/{project_name}/{self.session_id}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        self.conversation_log = []
        self.decisions_made = []
        self.code_generated = []
        
        print(f"🦍 Ork Design Session: {project_name}")
        print(f"📁 Session directory: {self.session_dir}")
    
    def ask(self, question, context=None):
        """Ask Ork with context from previous questions."""
        # Build context-aware prompt
        prompt = self._build_prompt(question, context)
        
        # Call Ork
        print(f"\n💭 Asking: {question[:50]}...")
        response = self._call_ork(prompt)
        
        # Log everything
        entry = {
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "response": response,
            "context_used": context
        }
        self.conversation_log.append(entry)
        
        # Auto-save
        self._save_session()
        
        # Extract decisions and code
        self._extract_content(response)
        
        return response
    
    def _build_prompt(self, question, context):
        """Build prompt with conversation history."""
        prompt = f"Project: {self.project_name}\n"
        
        if context == "last_3":
            # Include last 3 Q/A pairs
            last_three = self.conversation_log[-3:] if len(self.conversation_log) >= 3 else self.conversation_log
            for entry in last_three:
                prompt += f"\nPrevious Q: {entry['question']}"
                prompt += f"\nPrevious A: {entry['response'][:200]}..."
        
        prompt += f"\n\nCurrent Question: {question}"
        prompt += "\n\nPlease provide specific, actionable advice."
        
        return prompt
    
    def _call_ork(self, prompt):
        """Call Ork CLI."""
        try:
            result = subprocess.run(
                ["ork", "call", prompt],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            return "Error: Ork timeout"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _extract_content(self, response):
        """Extract decisions and code from response."""
        # Simple extraction - in reality would use more sophisticated parsing
        if "DECISION:" in response:
            decision = response.split("DECISION:")[1].split("\n")[0].strip()
            self.decisions_made.append(decision)
        
        # Look for code blocks
        if "```python" in response:
            code = response.split("```python")[1].split("```")[0]
            self.code_generated.append({
                "timestamp": datetime.now().isoformat(),
                "code": code
            })
    
    def _save_session(self):
        """Save session state."""
        session_data = {
            "project": self.project_name,
            "start_time": self.session_id,
            "conversations": self.conversation_log,
            "decisions": self.decisions_made,
            "code": self.code_generated
        }
        
        with open(self.session_dir / "session.json", "w") as f:
            json.dump(session_data, f, indent=2)
        
        # Also save raw conversation
        with open(self.session_dir / "conversation.txt", "w") as f:
            for entry in self.conversation_log:
                f.write(f"\n{'='*60}\n")
                f.write(f"Q: {entry['question']}\n")
                f.write(f"A: {entry['response']}\n")
    
    def generate_summary(self):
        """Generate design session summary."""
        summary = f"""
# Design Session Summary: {self.project_name}
Session: {self.session_id}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Key Decisions Made
{chr(10).join(f'- {d}' for d in self.decisions_made)}

## Code Generated
{len(self.code_generated)} code snippets generated

## Full Conversation
See conversation.txt for details
"""
        
        summary_file = self.session_dir / "DESIGN_SUMMARY.md"
        summary_file.write_text(summary)
        
        return summary

# Example usage
if __name__ == "__main__":
    # Start a file system design session
    session = OrkDesignSession("distributed-filesystem-v2")
    
    # Structured design questions
    responses = []
    
    responses.append(session.ask(
        "What are the top 3 consensus algorithms for distributed file system metadata?",
        context=None
    ))
    
    responses.append(session.ask(
        "Compare RAFT vs Paxos for our 5-node metadata cluster",
        context="last_3"
    ))
    
    responses.append(session.ask(
        "Generate Python implementation of RAFT for metadata coordination",
        context="last_3"
    ))
    
    # Generate summary
    summary = session.generate_summary()
    print(f"\n📄 Session summary generated: {session.session_dir}/DESIGN_SUMMARY.md")
