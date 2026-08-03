const { execSync } = require('child_process');
try {
  console.log("Mocking D1 insertion...");
  execSync(`npx wrangler d1 execute music-mcp-d1 --remote --command "INSERT INTO tracks (id, title, artist, license_type, attribution_template, audio_url, tags) VALUES ('track_1', 'Tech Live', 'Kevin MacLeod', 'CC BY 4.0', 'Tech Live by Kevin...', 'http://example.com', 'upbeat, tech, electronic, fast');"`, {stdio: 'inherit'});
  console.log("Done. Please wait for the cron to generate the vector embeddings or trigger it locally.");
} catch(e) {}
