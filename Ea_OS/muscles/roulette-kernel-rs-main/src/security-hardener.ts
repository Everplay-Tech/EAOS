import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import OpenAI from "openai";
import { z } from 'zod';
import pRetry from 'p-retry';

const openai = new OpenAI({ apiKey: process.env.XAI_API_KEY, baseURL: "https://api.x.ai/v1" });

const server = new Server(
  {
    name: "Security Hardener Tool",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

server.setRequestHandler("tools/call", async (request) => {
  const { name, arguments: args } = request.params;
  if (name === "harden-code-security") {
    const schema = z.object({ code: z.string().min(1), language: z.string() });
    const validatedArgs = schema.parse(args);
    try {
      const response = await pRetry(() => openai.chat.completions.create({
        model: "grok-beta",
        messages: [{ role: "user", content: `Harden this ${validatedArgs.language} code for security: ${validatedArgs.code}. Identify vulnerabilities and provide secure alternatives.` }],
      }), { retries: 3 });
      return { content: [{ type: "text", text: response.choices[0].message.content }] };
    } catch (error) {
      console.error('Security hardening error:', error);
      throw new Error('Failed to harden code');
    }
  }
  throw new Error("Unknown tool");
});

export default server;