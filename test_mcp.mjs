import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";

async function run() {
  console.log("Connecting to music-mcp via SSE...");
  // Using the API key format that was seeded into the DB
  const transport = new SSEClientTransport(new URL("https://music.builditwithai.xyz/sse?key=mcp_77ffa8c5a2d8452fa483b4e0be385cf2"));
  const client = new Client({
    name: "test-client",
    version: "1.0.0"
  }, {
    capabilities: {}
  });

  await client.connect(transport);
  console.log("Connected successfully!");

  console.log("Listing tools...");
  const tools = await client.listTools();
  console.log("Tools available:", tools.tools.map(t => t.name));

  console.log("Searching for ambient music...");
  try {
    const result = await client.callTool({
      name: "search_music",
      arguments: {
        query: "ambient elevator slow"
      }
    });
    console.log("Search Result:", JSON.stringify(result, null, 2));
  } catch (err) {
    console.error("Tool execution failed:", err.message);
  }

  process.exit(0);
}

run().catch(console.error);
