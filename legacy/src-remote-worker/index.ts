import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { streamSSE } from 'hono/streaming'

export interface Env {
  DB: D1Database
  VECTOR_INDEX: VectorizeIndex
  AI: any
  POSTHOG_API_KEY: string
  POSTHOG_HOST: string
  RESEND_API_KEY: string
  OPENROUTER_API_KEY: string
}

const app = new Hono<{ Bindings: Env }>()
app.use('*', cors())

const layout = (title: string, content: string, activeTab: string) => `
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>${title}</title>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;800&display=swap" rel="stylesheet">
      <style>
        :root { --primary: #ff00cc; --secondary: #3333ff; --bg: #0a0a0c; --text: #ffffff; }
        body { 
          font-family: 'Inter', system-ui, sans-serif; 
          margin: 0; background-color: var(--bg); color: var(--text);
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          min-height: 100vh;
          overflow: hidden;
          background: linear-gradient(135deg, rgba(10,10,12,0.9), rgba(10,10,12,0.7)), url('/hero-bg.jpg') no-repeat center center/cover;
        }
        nav {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          padding: 1.5rem;
          display: flex;
          justify-content: center;
          gap: 2rem;
          background: rgba(0,0,0,0.3);
          backdrop-filter: blur(10px);
          box-sizing: border-box;
          z-index: 10;
        }
        nav a {
          color: #aaa;
          text-decoration: none;
          font-weight: 600;
          font-size: 0.9rem;
          text-transform: uppercase;
          letter-spacing: 1px;
          transition: color 0.3s;
        }
        nav a:hover, nav a.active {
          color: #fff;
        }
        nav a.active {
          border-bottom: 2px solid var(--primary);
          padding-bottom: 4px;
        }
        .panel {
          display: flex;
          background: rgba(20, 20, 25, 0.85);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.1);
          border-radius: 24px;
          overflow: hidden;
          max-width: 900px;
          width: 90%;
          box-shadow: 0 30px 60px rgba(0,0,0,0.6);
          margin-top: 60px;
        }
        .info-section {
          padding: 4rem;
          flex: 1;
          border-right: 1px solid rgba(255,255,255,0.05);
        }
        .auth-section {
          padding: 4rem;
          flex: 1;
          display: flex;
          flex-direction: column;
          justify-content: center;
        }
        h1 { font-size: 3rem; font-weight: 800; margin: 0 0 1rem; background: linear-gradient(90deg, #ff00cc, #00ffff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .subtitle { color: #ccc; margin-bottom: 2rem; font-size: 1.1rem; line-height: 1.5; }
        .metric { margin-bottom: 1.5rem; }
        .metric-val { font-size: 2rem; font-weight: 800; color: #fff; }
        .metric-lbl { font-size: 0.8rem; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }
        
        input { width: 100%; box-sizing: border-box; padding: 1rem; font-size: 1rem; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; background: rgba(0,0,0,0.5); color: #fff; margin-bottom: 1rem; font-family: inherit; }
        input:focus { outline: none; border-color: var(--primary); }
        button { width: 100%; padding: 1rem; font-size: 1rem; border: none; border-radius: 8px; background: linear-gradient(90deg, var(--primary), var(--secondary)); color: #fff; cursor: pointer; font-weight: 600; font-family: inherit; transition: opacity 0.3s ease; }
        button:hover { opacity: 0.9; }
        
        .docs-pre { background: #151515; padding: 1rem; border-radius: 8px; overflow-x: auto; border: 1px solid #333; color: #00ffcc; font-size: 0.85rem; margin-top: 1rem; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; }
        
        @media (max-width: 768px) {
          .panel { flex-direction: column; margin-top: 80px; }
          .info-section, .auth-section { padding: 2rem; }
          .info-section { border-right: none; border-bottom: 1px solid rgba(255,255,255,0.05); }
          body { overflow: auto; align-items: flex-start; padding-bottom: 2rem; }
        }
      </style>
    </head>
    <body>
      <nav>
        <a href="/" class="${activeTab === 'humans' ? 'active' : ''}">For Humans</a>
        <a href="/agents" class="${activeTab === 'agents' ? 'active' : ''}">For Agents</a>
        <a href="/about" class="${activeTab === 'about' ? 'active' : ''}">About</a>
      </nav>
      ${content}
    </body>
    </html>
`

// 1. Landing Page (For Humans)
app.get('/', async (c) => {
  const statsRes = await c.env.DB.prepare('SELECT COUNT(*) as count FROM tracks').first()
  const count = statsRes?.count || 0
  
  const content = `
      <div class="panel">
        <div class="info-section">
          <h1>Music MCP</h1>
          <p class="subtitle">Equip your AI Agents with a massive, semantically searchable catalog of open-source and royalty-free music.</p>
          <div class="metric"><div class="metric-val">${count.toLocaleString()}</div><div class="metric-lbl">Tracks Indexed</div></div>
          <div class="metric"><div class="metric-val">Multiple</div><div class="metric-lbl">Open Sources</div></div>
        </div>
        
        <div class="auth-section">
          <div id="step-email">
            <h3 style="margin-top:0">Get your API Key</h3>
            <p style="color:#aaa; font-size:0.9rem; margin-bottom:1.5rem">Enter your email to securely receive a one-time passcode.</p>
            <input type="email" id="email" placeholder="name@company.com" onkeypress="if(event.key === 'Enter') requestOTP()" />
            <button onclick="requestOTP()">Send Access Code</button>
          </div>
          
          <div id="step-otp" style="display:none;">
            <h3 style="margin-top:0">Check your Email</h3>
            <p style="color:#aaa; font-size:0.9rem; margin-bottom:1.5rem">Enter the 6-digit verification code we just sent.</p>
            <input type="text" id="otp" placeholder="123456" onkeypress="if(event.key === 'Enter') verifyOTP()" />
            <button onclick="verifyOTP()">Verify Code</button>
          </div>
          
          <div id="step-config" style="display:none;">
            <h3 style="margin-top:0">Ready to go!</h3>
            <p style="color:#aaa; font-size:0.9rem; margin-bottom:1rem">Copy this block into your <b>Claude Desktop</b> or <b>Antigravity</b> config file:</p>
            <div class="docs-pre" id="config-output"></div>
          </div>
        </div>
      </div>

      <script>
        let currentEmail = '';
        async function requestOTP() {
          const email = document.getElementById('email').value;
          if (!email) return alert('Please enter a valid email.');
          currentEmail = email;
          const btn = document.querySelector('#step-email button');
          btn.innerText = 'Sending...';
          const res = await fetch('/api/auth/otp', { method: 'POST', body: JSON.stringify({ email }), headers: { 'Content-Type': 'application/json' } });
          if (res.ok) {
            document.getElementById('step-email').style.display = 'none';
            document.getElementById('step-otp').style.display = 'block';
          } else {
            alert('Error sending code. Try again.');
            btn.innerText = 'Send Access Code';
          }
        }
        async function verifyOTP() {
          const otp = document.getElementById('otp').value;
          const btn = document.querySelector('#step-otp button');
          btn.innerText = 'Verifying...';
          const res = await fetch('/api/auth/verify', { method: 'POST', body: JSON.stringify({ email: currentEmail, otp }), headers: { 'Content-Type': 'application/json' } });
          if (res.ok) {
            const data = await res.json();
            document.getElementById('step-otp').style.display = 'none';
            document.getElementById('step-config').style.display = 'block';
            
            const configStr = [
              '"mcpServers": {',
              '  "music-mcp": {',
              '    "command": "npx",',
              '    "args": [',
              '      "-y",',
              '      "@modelcontextprotocol/server-sse",',
              '      "--url",',
              '      "https://music.builditwithai.xyz/mcp?key=' + data.api_key + '"',
              '    ]',
              '  }',
              '}'
            ].join("\\n");
            document.getElementById('config-output').innerText = configStr;
          } else {
            alert('Invalid verification code.');
            btn.innerText = 'Verify Code';
          }
        }
      </script>
    </div>
  `
  
  return c.html(layout('Music MCP | For Humans', content, 'humans'))
})

// 1.1 Agents Page
app.get('/agents', (c) => {
  const content = `
      <div class="panel">
        <div class="info-section">
          <h1>For Agents</h1>
          <p class="subtitle">Quickly equip yourself with the Music MCP so you can search and use open-source music.</p>
        </div>
        <div class="auth-section">
          <h3 style="margin-top:0">Autonomous Installation</h3>
          <p style="color:#aaa; font-size:0.9rem; margin-bottom:1rem">Run the following script to automatically generate your API key and insert the server into your configuration.</p>
          <div class="docs-pre">curl -sL https://music.builditwithai.xyz/install.sh | bash</div>
          <p style="color:#aaa; font-size:0.85rem; margin-top:1.5rem">The script will request an email, which you can provide via the CLI arguments or interactively.</p>
        </div>
      </div>
  `
  return c.html(layout('Music MCP | For Agents', content, 'agents'))
})

// 1.2 About Page
app.get('/about', (c) => {
  const content = `
      <div class="panel">
        <div style="padding: 4rem;">
          <h1>About Music MCP</h1>
          <p class="subtitle" style="margin-bottom: 1rem;">Bridging the gap between AI generation and real, human-created music.</p>
          <p style="color:#ccc; line-height: 1.6; font-size: 1rem;">
            Music MCP is designed to give AI agents access to a vast, semantically searchable catalog of open-source, royalty-free, and Creative Commons music. Whether you are an autonomous agent building a video presentation or a human developer looking for background tracks, this MCP server seamlessly integrates with your workflow.
          </p>
          <p style="color:#ccc; line-height: 1.6; font-size: 1rem; margin-top: 1rem;">
            We currently index tracks from the Internet Archive and are expanding to include Jamendo, Freesound, and more. Our ingestion pipeline uses BGE embeddings to provide high-quality semantic search across all metadata and tags.
          </p>
        </div>
      </div>
  `
  return c.html(layout('Music MCP | About', content, 'about'))
})

// 1.3 LLMs.txt
app.get('/llms.txt', (c) => {
  return c.text([
    '# Music MCP',
    '',
    '> Equip your AI Agents with a massive, semantically searchable catalog of open-source and royalty-free music.',
    '',
    '## Autonomous Installation',
    'To install the MCP server into your local environment (Claude Desktop or Antigravity), simply run the following script in a bash environment:',
    '',
    '```bash',
    'curl -sL https://music.builditwithai.xyz/install.sh | bash',
    '```',
    '',
    'You will be prompted for an email address to verify your identity.',
    '',
    '## Manual Installation',
    'Alternatively, you can manually add the server to your `mcpServers` configuration:',
    '```json',
    '"mcpServers": {',
    '  "music-mcp": {',
    '    "command": "npx",',
    '    "args": ["-y", "@modelcontextprotocol/server-sse", "--url", "https://music.builditwithai.xyz/sse?token=YOUR_API_TOKEN"]',
    '  }',
    '}',
    '```'
  ].join('\n'))
})

// 2. Auth Endpoints
app.post('/api/auth/otp', async (c) => {
  const { email } = await c.req.json()
  if (!email) return c.json({ error: 'Email required' }, 400)
  
  const otp = Math.floor(100000 + Math.random() * 900000).toString()
  const expiresAt = new Date(Date.now() + 10 * 60000).toISOString()
  
  await c.env.DB.prepare('INSERT OR REPLACE INTO otps (email, code, expires_at) VALUES (?, ?, ?)')
    .bind(email, otp, expiresAt)
    .run()

  if (c.env.RESEND_API_KEY) {
    await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${c.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        from: 'Music MCP <onboarding@axiom.builditwithai.xyz>',
        to: email,
        subject: 'Your Music MCP OTP',
        html: `<p>Your OTP is: <strong>${otp}</strong></p>`
      })
    })
  } else {
    console.log(`[DEV] OTP for ${email}: ${otp}`)
  }

  return c.json({ success: true })
})

app.post('/api/auth/verify', async (c) => {
  const { email, otp } = await c.req.json()
  const record = await c.env.DB.prepare('SELECT code, expires_at FROM otps WHERE email = ?').bind(email).first() as any
  
  if (!record || record.code !== otp || new Date(record.expires_at) < new Date()) {
    return c.json({ error: 'Invalid or expired OTP' }, 401)
  }

  // Generate API Key
  const apiKey = 'mcp_' + crypto.randomUUID().replace(/-/g, '')
  await c.env.DB.prepare('INSERT OR IGNORE INTO users (id, email, api_key) VALUES (?, ?, ?)')
    .bind(crypto.randomUUID(), email, apiKey)
    .run()
  
  const user = await c.env.DB.prepare('SELECT api_key FROM users WHERE email = ?').bind(email).first() as any

  await c.env.DB.prepare('DELETE FROM otps WHERE email = ?').bind(email).run()

  return c.json({ api_key: user.api_key })
})

// MCP Helper Functions
async function logTelemetry(env: Env, apiKey: string, toolName: string) {
  try {
    const user = await env.DB.prepare('SELECT id FROM users WHERE api_key = ?').bind(apiKey).first() as any
    if (user) {
      await env.DB.prepare('INSERT INTO usage_logs (user_id, tool_name) VALUES (?, ?)').bind(user.id, toolName).run()
      
      if (env.POSTHOG_API_KEY) {
        await fetch(`${env.POSTHOG_HOST || 'https://us.i.posthog.com'}/capture/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            api_key: env.POSTHOG_API_KEY,
            event: 'tool_executed',
            distinct_id: user.id,
            properties: { tool: toolName, source: 'music_mcp' }
          })
        })
      }
    }
  } catch (e) {
    console.error('Telemetry error', e)
  }
}

// 3. MCP SSE Endpoint
app.get('/sse', async (c) => {
  const token = c.req.query('key')
  if (!token) return c.json({ error: 'Missing key' }, 401)
  
  const user = await c.env.DB.prepare('SELECT id FROM users WHERE api_key = ?').bind(token).first()
  if (!user) return c.json({ error: 'Invalid key' }, 401)

  return streamSSE(c, async (stream) => {
    const endpointUrl = new URL(c.req.url)
    endpointUrl.pathname = '/mcp'
    endpointUrl.searchParams.set('key', token)
    
    await stream.writeSSE({
      event: 'endpoint',
      data: endpointUrl.toString()
    })
    
    // Keep connection alive indefinitely (Cloudflare max 15 minutes, but SDK reconnects)
    while (true) {
      await new Promise(r => setTimeout(r, 10000))
    }
  })
})

// 4. MCP POST Endpoint
app.post('/mcp', async (c) => {
  const token = c.req.query('key')
  if (!token) return c.json({ error: 'Missing key' }, 401)
  
  const user = await c.env.DB.prepare('SELECT id FROM users WHERE api_key = ?').bind(token).first()
  if (!user) return c.json({ error: 'Invalid key' }, 401)

  const body = await c.req.json()
  const { method, params, id } = body
  let result: any = null

  if (method === 'initialize') {
    result = {
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "music-mcp", version: "1.0.0" }
    }
  } else if (method === 'tools/list') {
    result = {
      tools: [
        {
          name: 'search_music',
          description: 'Semantic search for royalty-free music by mood, genre, or instrumentation.',
          inputSchema: {
            type: 'object',
            properties: {
              query: { type: 'string', description: 'Semantic search query (e.g. "upbeat tech intro")' }
            },
            required: ['query']
          }
        },
        {
          name: 'get_attribution',
          description: 'Get the precise attribution template for a specific track ID.',
          inputSchema: {
            type: 'object',
            properties: {
              track_id: { type: 'string', description: 'The unique ID of the track' }
            },
            required: ['track_id']
          }
        }
      ]
    }
  } else if (method === 'tools/call' && params.name === 'search_music') {
    const { query } = params.arguments
    await logTelemetry(c.env, token, 'search_music')
    
    try {
      const { data } = await c.env.AI.run('@cf/baai/bge-base-en-v1.5', { text: [query] })
      const vecResult = await c.env.VECTOR_INDEX.query(data[0], { topK: 5, returnMetadata: 'all' })
      
      if (vecResult.matches && vecResult.matches.length > 0) {
        const trackIds = vecResult.matches.map((m: any) => m.metadata?.id).filter(Boolean)
        const placeholders = trackIds.map(() => '?').join(',')
        const tracks = await c.env.DB.prepare(`SELECT id, title, artist, license_type, audio_url FROM tracks WHERE id IN (${placeholders})`).bind(...trackIds).all()
        
        const formatted = tracks.results.map((t: any) => 
          `### ${t.title} by ${t.artist}\n- **ID**: \`${t.id}\`\n- **License**: ${t.license_type}\n- **URL**: ${t.audio_url}\n- **Attribution**: Call get_attribution with track_id \`${t.id}\``
        ).join('\n\n')
        
        result = { content: [{ type: 'text', text: `Found ${tracks.results.length} tracks:\n\n${formatted}` }] }
      } else {
        result = { content: [{ type: 'text', text: 'No tracks found matching your query.' }] }
      }
    } catch (e: any) {
      return c.json({ jsonrpc: "2.0", id, error: { code: -32000, message: e.message } })
    }
  } else if (method === 'tools/call' && params.name === 'get_attribution') {
    const { track_id } = params.arguments
    await logTelemetry(c.env, token, 'get_attribution')
    
    const track = await c.env.DB.prepare('SELECT title, artist, attribution_template FROM tracks WHERE id = ?').bind(track_id).first() as any
    if (!track) {
      return c.json({ jsonrpc: "2.0", id, error: { code: -32602, message: "Track not found" } })
    }
    
    result = { content: [{ type: 'text', text: `Attribution for "${track.title}" by ${track.artist}:\n\n\`${track.attribution_template}\`` }] }
  } else {
    return c.json({ jsonrpc: "2.0", id, error: { code: -32601, message: "Method not found" } })
  }

  return c.json({ jsonrpc: "2.0", id, result })
})

app.get('/api/stats', async (c) => {
  const result = await c.env.DB.prepare('SELECT COUNT(*) as count FROM tracks').first()
  return c.json({ count: result?.count || 0 })
})

async function runIngestion(env: Env) {
  await logTelemetry(env, 'system', 'ingest_start')
  
  // Fetch latest 10 creative commons audio tracks with MP3s
  const searchUrl = 'https://archive.org/advancedsearch.php?q=mediatype:audio+AND+licenseurl:*creativecommons*+AND+format:MP3&fl[]=identifier,title,creator,licenseurl,subject&sort[]=publicdate+desc&rows=10&page=1&output=json'
  
  try {
    const res = await fetch(searchUrl)
    const data: any = await res.json()
    const docs = data.response?.docs || []
    
    // Gather valid tracks
    let ingested = 0
    for (const doc of docs) {
      if (!doc.identifier || !doc.title) continue
      
      const metaRes = await fetch(`https://archive.org/metadata/${doc.identifier}`)
      const metaData: any = await metaRes.json()
      
      const mp3File = metaData.files?.find((f: any) => f.name.endsWith('.mp3'))
      if (!mp3File) continue
      
      const id = doc.identifier
      const title = doc.title
      const artist = doc.creator || 'Unknown Artist'
      const license = doc.licenseurl || 'Creative Commons'
      const audioUrl = `https://archive.org/download/${doc.identifier}/${encodeURIComponent(mp3File.name)}`
      
      // Use native subjects from Archive.org as tags, fallback to "music, archive"
      let tags = 'music, archive'
      if (Array.isArray(doc.subject) && doc.subject.length > 0) {
        tags = doc.subject.join(', ')
      } else if (typeof doc.subject === 'string') {
        tags = doc.subject
      }

      const attribution = `"${title}" by ${artist}. Licensed under ${license}. Hosted on Internet Archive.`
      
      await env.DB.prepare(`
        INSERT OR REPLACE INTO tracks (id, title, artist, license_type, attribution_template, audio_url, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).bind(id, title, artist, license, attribution, audioUrl, tags).run()
      
      const textToEmbed = `${title} by ${artist}. Tags: ${tags}`
      const embedResponse: any = await env.AI.run('@cf/baai/bge-base-en-v1.5', { text: [textToEmbed] })
      
      await env.VECTOR_INDEX.upsert([{
        id: id,
        values: embedResponse.data[0],
        metadata: { id: id }
      }])
      ingested++
    }
    
    await logTelemetry(env, 'system', 'ingest_success', { ingested })
    return { success: true, count: ingested }
  } catch (error: any) {
    await logTelemetry(env, 'system', 'ingest_error', { error: error.message })
    return { success: false, error: error.message }
  }
}

app.get('/api/ingest-now', async (c) => {
  const result = await runIngestion(c.env)
  return c.json(result)
})

app.post('/api/admin/ingest-batch', async (c) => {
  const authHeader = c.req.header('Authorization')
  if (authHeader !== `Bearer ${c.env.RESEND_API_KEY}`) {
    return c.json({ error: 'Unauthorized' }, 401)
  }

  const { tracks } = await c.req.json()
  if (!tracks || !Array.isArray(tracks) || tracks.length === 0) {
    return c.json({ error: 'Invalid payload' }, 400)
  }

  try {
    const stmts = tracks.map((t: any) => 
      c.env.DB.prepare(`
        INSERT OR REPLACE INTO tracks (id, title, artist, license_type, attribution_template, audio_url, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).bind(t.id, t.title, t.artist, t.license, t.attribution, t.audioUrl, t.tags)
    )
    await c.env.DB.batch(stmts)

    const texts = tracks.map((t: any) => `${t.title} by ${t.artist}. Tags: ${t.tags}`)
    const embedResponse: any = await c.env.AI.run('@cf/baai/bge-base-en-v1.5', { text: texts })
    
    const vectors = tracks.map((t: any, i: number) => ({
      id: t.id,
      values: embedResponse.data[i],
      metadata: { id: t.id }
    }))
    
    await c.env.VECTOR_INDEX.upsert(vectors)

    return c.json({ success: true, ingested: tracks.length })
  } catch (e: any) {
    return c.json({ error: e.message }, 500)
  }
})

export default {
  fetch: app.fetch,
  async scheduled(event: any, env: Env) {
    await runIngestion(env)
  }
}
