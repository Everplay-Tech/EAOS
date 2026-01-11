class Agent:
    &quot;&quot;&quot;
    Basic agent with role-based thinking.
    Heavy: Role specialization for decomposition.
    &quot;&quot;&quot;
    def __init__(self, name, role):
        self.name = name
        self.role = role

    def think(self, task, context):
        # Basic algorithmic logic (expandable to LLM calls/tools)
        if self.role == &quot;planner&quot;:
            return f&quot;Plan for '{task}': 1. Decompose sub-tasks. 2. Assign agents. 3. Predict outcomes.&quot;
        elif self.role == &quot;critic&quot;:
            issues = [&quot;risk of hallucination&quot;, &quot;missing edge cases&quot;, &quot;inefficient path&quot;]
            return f&quot;Critique '{task}': Address {', '.join(issues[:len(task)//10 +1])}&quot;
        elif self.role == &quot;executor&quot;:
            return f&quot;Execute '{task}': Simulated result with 95% confidence.&quot;
        elif self.role == &quot;integrator&quot;:
            return f&quot;Integrate proposals for '{task}': Consensus action plan.&quot;

class Coordinator:
    &quot;&quot;&quot;
    Heavy multi-agent: Multi-round debate, voting, self-critique loop.
    &quot;&quot;&quot;
    def __init__(self):
        self.agents = [
            Agent(&quot;PlanBot&quot;, &quot;planner&quot;),
            Agent(&quot;CriticBot&quot;, &quot;critic&quot;),
            Agent(&quot;ExecBot&quot;, &quot;executor&quot;),
            Agent(&quot;IntegrateBot&quot;, &quot;integrator&quot;)
        ]

    def vote(self, proposals):
        # Simple majority vote (heavy: could be weighted/ML)
        from collections import Counter
        return Counter(proposals).most_common(1)[0][0]

    def reason(self, task, max_rounds=5, convergence_threshold=0.8):
        context = task
        history = []
        for round_num in range(max_rounds):
            proposals = [agent.think(context, history) for agent in self.agents]
            consensus = self.vote(proposals)
            history.append((proposals, consensus))
            print(f&quot;\\n🔄 Round {round_num+1}:&quot;)
            for p in proposals:
                print(f&quot;  {p[:100]}...&quot;)
            print(f&quot;  👥 Consensus: {consensus[:100]}&quot;)
            
            # Convergence check (heavy: sim agreement score)
            agreement = proposals.count(consensus) / len(proposals)
            if agreement >= convergence_threshold:
                print(f&quot;\\n✅ Converged after {round_num+1} rounds.&quot;)
                break
            context = consensus
        
        return consensus, history

# Demo heavy reasoning
if __name__ == &quot;__main__&quot;:
    coord = Coordinator()
    task = &quot;Optimize neural net for multi-agent coordination with ethical constraints&quot;
    final, hist = coord.reason(task)
    print(f&quot;\\n🏆 Final Output: {final}&quot;)