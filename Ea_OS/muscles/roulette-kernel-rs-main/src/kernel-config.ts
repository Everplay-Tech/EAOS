export const kernelAgent = {
  name: "Copilot Kernel Agent",
  description: "Assists with Rust kernel development: optimizes code, generates tests, hardens security.",
  tools: ["optimize-rust", "generate-tests", "harden-security"],
  model: "grok-beta",
  target: "github-copilot",
  mcpServers: ["kernel-agent"],
};