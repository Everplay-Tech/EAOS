
"""
Novelty Tracker - Detects repetition and suggests fresh perspectives.
Use to maintain creative momentum across iterations.
"""
from typing import List, Set
from collections import Counter
import re

class NoveltyTracker:
    def __init__(self, threshold: float = 0.2):
        self.history: List[str] = []
        self.threshold = threshold

    def tokenize(self, text: str) -> List[str]:
        """Extract meaningful tokens (skip stopwords)."""
       stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'to', 'of', 'and', 'in', 'that', 'it', 'for', 'on', 'with'}
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if w not in stopwords and len(w) > 2]

    def calculate_overlap(self, new_text: str) -> float:
        """Calculate semantic overlap with previous outputs."""
        if not self.history:
            return 0.0

        new_tokens = set(self.tokenize(new_text))
        if not new_tokens:
            return 0.0

        # Compare against last 3 outputs
        recent = self.history[-3:]
        all_prev_tokens: Set[str] = set()
        for prev in recent:
            all_prev_tokens.update(self.tokenize(prev))

        overlap = len(new_tokens & all_prev_tokens) / len(new_tokens)
        return overlap

    def check_and_record(self, text: str) -> dict:
        """Check novelty and record output. Returns analysis."""
        overlap = self.calculate_overlap(text)
        is_stale = overlap > self.threshold

        result = {
            'overlap_score': round(overlap, 3),
            'is_stale': is_stale,
            'suggestion': None
        }

        if is_stale:
            result['suggestion'] = self._suggest_reframe()

        self.history.append(text)
        return result

    def _suggest_reframe(self) -> str:
        suggestions = [
            "Try different abstraction level (zoom in/out)",
            "Introduce a constraint perturbation",
            "Query an adjacent domain for analogous solutions",
            "Invert the problem statement",
            "Start from the desired end state and work backward"
        ]
        # Rotate through suggestions based on history length
        return suggestions[len(self.history) % len(suggestions)]

    def reset(self):
        """Clear history for fresh start."""
        self.history = []


if __name__ == "__main__":
    # Demo
    tracker = NoveltyTracker(threshold=0.2)

    texts = [
        "We can solve this optimization problem using gradient descent.",
        "The optimization problem can be solved via gradient descent methods.",
        "Consider a completely different approach using genetic algorithms."
    ]

    for i, text in enumerate(texts, 1):
        result = tracker.check_and_record(text)
        print(f"Iteration {i}:")
        print(f"  Overlap: {result['overlap_score']}")
        print(f"  Stale: {result['is_stale']}")
        if result['suggestion']:
            print(f"  Suggestion: {result['suggestion']}")
        print()
