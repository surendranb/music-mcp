// Native fetch is available in Node 18+

// The URL of our deployed worker
const WORKER_URL = 'https://music.builditwithai.xyz';
// We'll pass the RESEND_API_KEY from the environment to authenticate with the worker
const ADMIN_SECRET = process.env.RESEND_API_KEY;

if (!ADMIN_SECRET) {
  console.error("❌ RESEND_API_KEY environment variable is required.");
  process.exit(1);
}

const BATCH_SIZE = 50;
const TOTAL_PAGES = 20; // 50 * 20 = 1,000 tracks

async function fetchArchiveMetadata(identifier: string) {
  try {
    const res = await fetch(`https://archive.org/metadata/${identifier}`);
    const data: any = await res.json();
    const mp3File = data.files?.find((f: any) => f.name.endsWith('.mp3'));
    if (mp3File) {
      return `https://archive.org/download/${identifier}/${encodeURIComponent(mp3File.name)}`;
    }
  } catch (e) {
    // Ignore errors for individual tracks
  }
  return null;
}

async function runBulkIngest() {
  console.log("🚀 Starting Bulk Ingestion from Internet Archive (Netlabels)");
  
  let totalIngested = 0;

  for (let page = 1; page <= TOTAL_PAGES; page++) {
    console.log(`\nFetching page ${page}/${TOTAL_PAGES}...`);
    const searchUrl = `https://archive.org/advancedsearch.php?q=collection:(netlabels)+AND+mediatype:(audio)+AND+format:(VBR+MP3)&fl[]=identifier,title,creator,licenseurl,subject&sort[]=publicdate+desc&rows=${BATCH_SIZE}&page=${page}&output=json`;
    
    const searchRes = await fetch(searchUrl);
    const searchData: any = await searchRes.json();
    const docs = searchData.response?.docs || [];

    if (docs.length === 0) {
      console.log("No more documents found.");
      break;
    }

    const batch = [];
    console.log(`Resolving MP3 files for ${docs.length} tracks...`);
    
    // Resolve MP3 URLs concurrently in small chunks to avoid rate limits
    for (let i = 0; i < docs.length; i += 10) {
      const chunk = docs.slice(i, i + 10);
      const chunkResults = await Promise.all(chunk.map(async (doc: any) => {
        if (!doc.identifier || !doc.title) return null;
        
        const audioUrl = await fetchArchiveMetadata(doc.identifier);
        if (!audioUrl) return null;

        let tags = 'music, netlabels, archive';
        if (Array.isArray(doc.subject) && doc.subject.length > 0) {
          tags = doc.subject.join(', ');
        } else if (typeof doc.subject === 'string') {
          tags = doc.subject;
        }

        const artistRaw = doc.creator || 'Unknown Artist';
        const artist = Array.isArray(artistRaw) ? artistRaw.join(', ') : artistRaw;
        const license = doc.licenseurl || 'Creative Commons';
        const attribution = `"${doc.title}" by ${artist}. Licensed under ${license}. Hosted on Internet Archive.`;
        
        // Vectorize limits ID to 64 bytes
        const id = doc.identifier.length > 64 ? doc.identifier.substring(0, 64) : doc.identifier;

        return {
          id: id,
          title: doc.title,
          artist,
          license,
          attribution,
          audioUrl,
          tags
        };
      }));

      batch.push(...chunkResults.filter(Boolean));
    }

    if (batch.length === 0) {
      console.log("No valid MP3s found in this batch.");
      continue;
    }

    console.log(`Pushing batch of ${batch.length} tracks to Worker API...`);
    
    const pushRes = await fetch(`${WORKER_URL}/api/admin/ingest-batch`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${ADMIN_SECRET}`
      },
      body: JSON.stringify({ tracks: batch })
    });

    if (pushRes.ok) {
      const pushData: any = await pushRes.json();
      console.log(`✅ Successfully ingested ${pushData.ingested} tracks!`);
      totalIngested += pushData.ingested;
    } else {
      const errorText = await pushRes.text();
      console.error(`❌ Error pushing batch: ${errorText}`);
    }
  }

  console.log(`\n🎉 Bulk ingestion complete! Total tracks added: ${totalIngested}`);
}

runBulkIngest();
