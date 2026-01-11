// Main entry for development tools
import rustOptimizer from "./rust-optimizer.js";
import testGenerator from "./test-generator.js";
import securityHardener from "./security-hardener.js";
import copilotKernelAgent from "./copilot-kernel-agent.js";

// Start tool servers (for local use or integration)
async function main() {
  console.log("Kernel development tools ready.");
  // Agents can be run via MCP or integrated into Copilot
}

main().catch(console.error);