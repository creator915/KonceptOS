const KONCEPTOS_API_KEY = process.env.KONCEPTOS_API_KEY || '';
const KONCEPTOS_MODEL = process.env.KONCEPTOS_MODEL || 'glm-5';
const KONCEPTOS_URL = process.env.KONCEPTOS_URL || 'https://open.bigmodel.cn/api/paas/v4/chat/completions';

function extractJson(text) {
  const a = text.indexOf('{');
  const b = text.lastIndexOf('}');
  if (a === -1 || b <= a) return null;
  const s = text.substring(a, b + 1);
  try { return JSON.parse(s); } catch {
    const s2 = s.replace(/,\s*}/g, '}').replace(/,\s*]/g, ']');
    try { return JSON.parse(s2); } catch { return null; }
  }
}

async function ask(system, user, maxTokens = 4000) {
  if (!KONCEPTOS_API_KEY) return '(No API key: set KONCEPTOS_API_KEY env)';
  try {
    const { default: fetch } = await import('node-fetch');
    const body = JSON.stringify({
      model: KONCEPTOS_MODEL,
      max_tokens: maxTokens,
      messages: [
        { role: 'system', content: system },
        { role: 'user', content: user }
      ]
    });
    const resp = await fetch(KONCEPTOS_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${KONCEPTOS_API_KEY}`
      },
      body
    });
    const d = await resp.json();
    if (d?.error) return `(API error: ${d.error.message || JSON.stringify(d.error)})`;
    const ch = d?.choices || [];
    if (!ch.length) return `(no choices: ${JSON.stringify(d).substring(0, 300)})`;
    const content = ch[0]?.message?.content;
    if (!content) return `(empty response. usage: ${JSON.stringify(d.usage)?.substring(0, 100)})`;
    return content;
  } catch (e) {
    if (e?.cause?.code === 'ENOTFOUND') return '(Network error: cannot reach bigmodel.cn)';
    return `(${e.message})`;
  }
}

export async function extractGm(text) {
  return ask(
    'Extract OBJECTS and ATTRIBUTES.\nATTRIBUTES = high-level concern dimensions (~6-12).\nPure JSON:\n{"objects":[{"id":"F01","name":"...","desc":"..."},...],"attributes":[{"id":"A","name":"...","desc":"..."},...]}',
    text, 8192
  );
}

export async function fillDirected(text, ops, aps) {
  return ask(
    'For each (object,attribute) determine: 0/R/W/RW.\nPer object: comma-separated in attribute order.\nPure JSON: {"F01":"R,0,W,RW,...",...}',
    `Objects: ${ops.map(([id, n]) => `${id}(${n})`).join(', ')}\nAttributes: ${aps.map(([id, n]) => `${id}(${n})`).join(', ')}\nDoc:\n${text}`,
    16384
  );
}

export async function judgeOne(on, od, an, ad) {
  const r = (await ask('Answer ONLY: 0, R, W, or RW', `Feature: ${on} - ${od}\nConcern: ${an} - ${ad}`, 10)).trim().toUpperCase();
  for (const v of ['RW', 'R', 'W', '0']) { if (r.includes(v)) return v; }
  return '0';
}

export async function askExpansion(name, desc, kind, vocabHint) {
  const vhint = vocabHint?.length ? `\nChoose from or be inspired by: ${vocabHint.join(', ')}` : '';
  const s = `'${name}' compresses multiple distinct ${kind}s.\nList 2-5 conceptually different sub-${kind}s (NOT R/W splits).${vhint}\n\nPure JSON: {"expansions":[{"name":"...","desc":"..."},...]}`;
  return ask(s, `Name: ${name}\nDesc: ${desc}`, 1000);
}

export async function buildFull(spec, binds, conventions) {
  let s = 'Generate a COMPLETE RUNNABLE single-file HTML+JS webapp from this FCA spec.\nRW means both reads and writes. Follow the lattice structure.\nOutput ONLY the HTML. No markdown fences.\n';
  if (conventions) s += `=== CRITICAL CONSTRAINTS (must satisfy ALL) ===\n${conventions}\n\n`;
  s += spec;
  if (binds) s += '\n\nTech Bindings:\n' + binds;
  return ask(s, 'Generate the HTML app now.', 128000);
}

export async function chat(system, user) {
  return ask(system, user);
}

export { extractJson };
