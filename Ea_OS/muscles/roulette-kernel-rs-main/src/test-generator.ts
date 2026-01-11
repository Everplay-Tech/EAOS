import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import OpenAI from "openai";
import { z } from 'zod';
import pRetry from 'p-retry';

const openai = new OpenAI({ apiKey: process.env.XAI_API_KEY, baseURL: "https://api.x.ai/v1" });

const server = new Server(
  {
    name: "Test Generator Tool",
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
  if (name === "generate-rust-tests") {
    const schema = z.object({ code: z.string().min(1) });
    const validatedArgs = schema.parse(args);
    try {
      const response = await pRetry(() => openai.chat.completions.create({
        model: "grok-beta",
        messages: [{ role: "user", content: `Generate comprehensive unit and property-based tests for this Rust code: ${validatedArgs.code}. Use proptest where applicable.` }],
      }), { retries: 3 });
      return { content: [{ type: "text", text: response.choices[0].message.content }] };
    } catch (error) {
      console.error('Test generation error:', error);
      throw new Error('Failed to generate tests');
    }
  }
  throw new Error("Unknown tool");
});

export default server;