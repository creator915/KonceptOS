#!/usr/bin/env node
import { Command } from 'commander';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import * as llm from '../src/lib/llm.js';
import { compute, VALID_I } from '../src/lib/fca.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PKG = JSON.parse(fs.readFileSync(path.join(__dirname, '../package.json'), 'utf8'));

// ANSI colors
const C = { RST: '\x1b[0m', B: '\x1b[1m', D: '\x1b[2m', R: '\x1b[31m', G: '\x1b[32m', Y: '\x1b[33m', BL: '\x1b[34m', M: '\x1b[35m', CN: '\x1b[36m' };
const cc = (t, ...c) => c.join('') + t + C.RST;

// Storage
const DATA_DIR = '.konceptos';
const STATE_FILE = path.join(DATA_DIR, 'state.json');

function ensureDataDir() {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
}

function loadState() {
  ensureDataDir();
  if (fs.existsSync(STATE_FILE)) {
    try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); } catch {}
  }
  return null;
}

function saveState(state) {
  ensureDataDir();
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
}

function createState() {
  return {
    objects: {}, attributes: {}, bindings: {}, conventions: '',
    incidence: {}, round: 0, history: [], snapshots: [],
    seed: { domain: '', obj_vocab: [], attr_vocab: [], obj_tree: {}, attr_tree: {}, incidence_hints: {}, conventions: [], reference_k: null }
  };
}

// Helper: compute FCA concepts
function runCompute(state) {
  if (!Object.keys(state.objects).length || !Object.keys(state.attributes).length) {
    return { concepts: [], edges: [], layers: [] };
  }
  const result = compute(state.objects, state.attributes, state.incidence);
  return result;
}

// Helper: compute snapshot
function snap(state) {
  const result = runCompute(state);
  const rw = Object.values(state.incidence).filter(v => v === 'RW').length;
  const unk = Object.values(state.incidence).filter(v => v === '?').length;
  return {
    round: state.round, time: new Date().toLocaleTimeString(),
    no: Object.keys(state.objects).length, na: Object.keys(state.attributes).length,
    nc: result.concepts.length, rw, unk,
    concepts: result.concepts, edges: result.edges, layers: result.layers,
    inc: { ...state.incidence }
  };
}

// Helper: update snapshots
function updateSnap(state) {
  state.snapshots.push(snap(state));
  if (state.snapshots.length > 300) state.snapshots = state.snapshots.slice(-300);
}

// Helper: rw count
function rwCount(state) { return Object.values(state.incidence).filter(v => v === 'RW').length; }
function unknowns(state) { return Object.entries(state.incidence).filter(([, v]) => v === '?'); }
function rwCells(state) { return Object.entries(state.incidence).filter(([, v]) => v === 'RW'); }

// Helper: involved
function involved(state, o, a) {
  return ['R', 'W', 'RW'].includes(state.incidence[`${o}|${a}`] || '0');
}

// Helper: log
function log(state, act, detail) {
  state.history.push({ round: state.round, time: new Date().toLocaleTimeString(), act, detail });
  if (state.history.length > 300) state.history = state.history.slice(-300);
}

// Helper: check consistency
function checkConsistency(state) {
  const issues = [];
  for (const aid of Object.keys(state.attributes)) {
    const rs = Object.keys(state.objects).filter(o => involved(state, o, aid));
    const ws = Object.keys(state.objects).filter(o => ['W', 'RW'].includes(state.incidence[`${o}|${aid}`] || '0'));
    if (rs.length && !ws.length) issues.push(`"${state.attributes[aid].name}": ${rs.length} R, no W`);
    if (ws.length && !rs.length) issues.push(`"${state.attributes[aid].name}": ${ws.length} W, no R`);
  }
  return issues;
}

// Helper: coding groups
function codingGroups(state) {
  const result = runCompute(state);
  const groups = {};
  for (const [oid, ob] of Object.entries(state.objects)) {
    let best = -1, bestSize = -1;
    result.concepts.forEach(([ext, intn], idx) => {
      if (ext.has(oid) && intn.size > bestSize) { best = idx; bestSize = intn.size; }
    });
    if (best >= 0) { if (!groups[best]) groups[best] = []; groups[best].push(oid); }
  }
  return groups;
}

// Helper: dataflows
function dataflows(state) {
  const flows = [];
  for (const aid of Object.keys(state.attributes)) {
    const ws = Object.keys(state.objects).filter(o => ['W', 'RW'].includes(state.incidence[`${o}|${aid}`] || '0'));
    const rs = Object.keys(state.objects).filter(o => involved(state, o, aid));
    for (const w of ws) {
      for (const r of rs) {
        if (w !== r) flows.push([w, aid, r]);
      }
    }
  }
  return flows;
}

// Helper: get all conventions
function getAllConventions(state) {
  const parts = [];
  if (state.seed?.conventions?.length) parts.push(state.seed.conventions.map(c => `- ${c}`).join('\n'));
  if (state.conventions) parts.push(state.conventions);
  return parts.join('\n');
}

// Helper: seed lookup
function lookupObj(state, name) {
  const tree = state.seed?.obj_tree || {};
  if (tree[name]) return tree[name];
  for (const [k, v] of Object.entries(tree)) {
    if (k.includes(name) || name.includes(k)) return v;
  }
  return null;
}

function lookupAttr(state, name) {
  const tree = state.seed?.attr_tree || {};
  if (tree[name]) return tree[name];
  for (const [k, v] of Object.entries(tree)) {
    if (k.includes(name) || name.includes(k)) return v;
  }
  return null;
}

// Display functions
function showCtx(state) {
  const oids = Object.keys(state.objects).sort();
  const aids = Object.keys(state.attributes).sort();
  if (!oids.length || !aids.length) { console.log(cc('  Empty.', C.D)); return; }
  let nw = Math.max(18, ...oids.map(o => state.objects[o].name.length)) + 6;
  let hdr = ' '.repeat(nw);
  for (const a of aids) hdr += cc(state.attributes[a].name.substring(0, 5).padStart(6), C.CN);
  console.log(cc('  +' + '-'.repeat(nw + aids.length * 6) + '+', C.D));
  console.log('  |' + hdr + '|');
  console.log(cc('  +' + '-'.repeat(nw + aids.length * 6) + '+', C.D));
  for (const o of oids) {
    const ob = state.objects[o];
    const lbl = ` ${cc(o, C.Y)} ${ob.name}`;
    const row = lbl + ' '.repeat(Math.max(0, nw - lbl.length));
    let line = '  |' + row;
    for (const a of aids) {
      const v = state.incidence[`${o}|${a}`] || '?';
      if (v === 'RW') line += cc(' RW  ', C.G, C.B) + ' ';
      else if (v === 'R') line += cc('  R   ', C.CN);
      else if (v === 'W') line += cc('  W   ', C.M);
      else if (v === '0') line += cc('  .   ', C.D);
      else line += cc('  ?   ', C.R);
    }
    console.log(line + '|');
  }
  console.log(cc('  +' + '-'.repeat(nw + aids.length * 6) + '+', C.D));
}

function showStatus(state) {
  const rw = rwCount(state);
  const unk = unknowns(state).length;
  const result = runCompute(state);
  console.log(cc(`  K: |G|=${Object.keys(state.objects).length} |M|=${Object.keys(state.attributes).length} RW=${rw} ?=${unk} |B|=${result.concepts.length}`, C.B));
  if (rw === 0 && unk === 0) console.log(cc('  K* reached', C.G, C.B));
  else { if (rw) console.log(cc(`  ${rw} RW = ${rw} compressions to resolve`, C.Y)); if (unk) console.log(cc(`  ${unk} unknowns`, C.R)); }
  const issues = checkConsistency(state);
  for (const c of issues) console.log(`  ! ${cc(c, C.Y)}`);
  if (state.seed?.domain) console.log(cc(`  Seed: ${state.seed.domain}`, C.CN));
  else console.log(cc('  Seed: none', C.D));
  const conv = getAllConventions(state);
  if (conv) console.log(cc(`  Conventions: ${conv.split('\n').filter(l => l.trim()).length} rules`, C.CN));
}

function showHelp() {
  console.log(`
  ================================================================
   KonceptOS v${PKG.version} CLI
   K -> K* by vocabulary replacement + redescription
   Data: ${DATA_DIR}/ (in current working directory)
  ================================================================

  Basics:
    konceptos add obj <id> <name> [-d desc]   konceptos add attr <id> <name> [-d desc]
    konceptos set <oid> <aid> <0|R|W|RW>       konceptos row <oid> <vals>
    konceptos del obj|attr <id>                konceptos bind <aid> <tech>
    konceptos convention [text...]

  View:
    konceptos ctx        Context table
    konceptos st         Status
    konceptos rw         RW cells with counts
    konceptos flows      Dataflows
    konceptos groups     Coding groups
    konceptos lat        Concept lattice
    konceptos concept <n>  Concept detail
    konceptos snaps      Snapshots
    konceptos diff <a> <b>  Diff snapshots
    konceptos hist       History

  Seed:
    konceptos seed        Seed summary
    konceptos seed load <file>
    konceptos seed save <file>
    konceptos seed tree
    konceptos seed conv
    konceptos seed set obj <parent> <child1> <child2>...
    konceptos seed set attr <parent> <child1> <child2>...

  LLM:
    konceptos llm analyze <file>   Extract G,M,I from doc
    konceptos llm ask              Fill unknowns (interactive)
    konceptos llm chat <msg>

  Resolve:
    konceptos resolve obj <id>    Expand object
    konceptos resolve attr <id>   Expand attribute
    konceptos evolve [n|all]       Auto-resolve RW cells

  Build:
    konceptos build [out.html]     Generate HTML app

  System:
    konceptos compute   Recompute FCA lattice
    konceptos save <f>  konceptos open <f>  konceptos export <f>
    konceptos rollback <n>
  `);
}

// Wrapper: commands that modify state
function withState(fn) {
  return async (...args) => {
    let state = loadState() || createState();
    await fn(state, ...args);
    saveState(state);
  };
}

// Wrapper: read-only state commands
function withStateRO(fn) {
  return (...args) => {
    const state = loadState() || createState();
    fn(state, ...args);
  };
}

const program = new Command();
program.version(PKG.version);

// Default: show help
program.action(() => showHelp());

// ── Basics ──

program.command('add').argument('<type>', 'obj|attr').argument('<id>').argument('<name>')
  .option('-d, --desc <text>', 'description')
  .action(withState(async (state, type, id, name, opts) => {
    if (type === 'obj') {
      state.objects[id] = { name, desc: opts.desc || '', solidified: false };
      for (const a of Object.keys(state.attributes)) state.incidence[`${id}|${a}`] = state.incidence[`${id}|${a}`] || '?';
      log(state, 'add_obj', `${id}: ${name}`);
    } else {
      state.attributes[id] = { name, desc: opts.desc || '' };
      for (const o of Object.keys(state.objects)) state.incidence[`${o}|${id}`] = state.incidence[`${o}|${id}`] || '?';
      log(state, 'add_attr', `${id}: ${name}`);
    }
    console.log(cc(`  +${id}`, C.G));
  }));

program.command('del').argument('<type>', 'obj|attr').argument('<id>')
  .action(withState(async (state, type, id) => {
    if (type === 'obj') {
      delete state.objects[id];
      state.incidence = Object.fromEntries(Object.entries(state.incidence).filter(([k]) => !k.startsWith(id + '|')));
      log(state, 'del_obj', id);
    } else {
      delete state.attributes[id];
      delete state.bindings[id];
      state.incidence = Object.fromEntries(Object.entries(state.incidence).filter(([k]) => !k.endsWith('|' + id)));
      log(state, 'del_attr', id);
    }
    console.log(cc(`  -${id}`, C.G));
  }));

program.command('set').argument('<oid>').argument('<aid>').argument('<val>')
  .action(withState(async (state, oid, aid, val) => {
    val = val.toUpperCase();
    if (['1', 'YES', 'TRUE'].includes(val)) val = 'RW';
    if (['NO', 'FALSE', 'NONE'].includes(val)) val = '0';
    if (!VALID_I.has(val)) { console.log(cc('  Use 0/R/W/RW', C.R)); return; }
    if (!state.objects[oid] || !state.attributes[aid]) { console.log(cc('  Not found', C.R)); return; }
    state.incidence[`${oid}|${aid}`] = val;
    log(state, 'set', `${oid}|${aid}=${val}`);
    console.log(cc('  OK', C.G));
  }));

program.command('row').argument('<oid>').argument('<vals>')
  .action(withState(async (state, oid, vals) => {
    if (!state.objects[oid]) { console.log(cc('  No object', C.R)); return; }
    const aids = Object.keys(state.attributes).sort();
    let cnt = 0;
    vals.split(',').map(v => v.trim().toUpperCase()).forEach((v, i) => {
      if (i < aids.length) {
        if (['1', 'YES', 'TRUE'].includes(v)) v = 'RW';
        if (['NO', 'FALSE', 'NONE'].includes(v)) v = '0';
        if (VALID_I.has(v)) { state.incidence[`${oid}|${aids[i]}`] = v; cnt++; }
      }
    });
    log(state, 'row', `${oid}: ${cnt} cells`);
    console.log(cc(`  OK (${cnt})`, C.G));
  }));

program.command('bind').argument('<aid>').argument('<tech...>')
  .action(withState(async (state, aid, tech) => {
    if (!state.attributes[aid]) { console.log(cc('  ?', C.R)); return; }
    state.bindings[aid] = Array.isArray(tech) ? tech.join(' ') : tech;
    console.log(cc(`  ${aid}->${state.bindings[aid]}`, C.G));
  }));

program.command('convention').argument('[text...]', 'convention text')
  .action(withState((state, text) => {
    if (text.length) { state.conventions = text.join(' '); console.log(cc(`  Set (${state.conventions.length} chars)`, C.G)); }
    else { const c = getAllConventions(state); if (c) console.log(c); else console.log(cc('  (empty)', C.D)); }
  }));

// ── View ──

program.command('ctx').action(withStateRO((state) => showCtx(state)));
program.command('st').action(withStateRO((state) => showStatus(state)));

program.command('rw').action(withStateRO((state) => {
  const cells = rwCells(state);
  if (!cells.length) { console.log(cc('  RW=0 (K*)', C.G)); return; }
  const byObj = {};
  cells.forEach(([k]) => {
    const [o, a] = k.split('|');
    if (!byObj[o]) byObj[o] = [];
    byObj[o].push(a);
  });
  console.log(cc(`  ${cells.length} RW:`, C.Y));
  for (const [o, aids] of Object.entries(byObj)) {
    const attrs = aids.map(a => state.attributes[a]?.name || a).join(', ');
    console.log(`    ${cc(state.objects[o]?.name || o, C.CN)} (${aids.length}): ${cc(attrs, C.M)}`);
  }
}));

program.command('flows').action(withStateRO((state) => {
  const fl = dataflows(state);
  if (!fl.length) { console.log(cc('  None.', C.D)); return; }
  fl.forEach(([w, a, r]) => {
    console.log(`  ${cc(state.objects[w]?.name || w, C.CN)} -[${cc(state.attributes[a]?.name || a, C.M)}]-> ${cc(state.objects[r]?.name || r, C.G)}`);
  });
}));

program.command('groups').action(withStateRO((state) => {
  const groups = codingGroups(state);
  const result = runCompute(state);
  console.log(cc(`  ${Object.keys(groups).length} groups:`, C.B));
  for (const [cidx, oids] of Object.entries(groups)) {
    const names = oids.map(o => state.objects[o]?.name || o).join(', ');
    const ext = result.concepts[parseInt(cidx)]?.[0] || new Set();
    const intn = result.concepts[parseInt(cidx)]?.[1] || new Set();
    console.log(`  C${cidx.padStart(2, '0')} L${result.layers[parseInt(cidx)] || 0} [${[...intn].map(a => state.attributes[a]?.name || a).join(',')}]: ${cc(names, C.CN)}`);
  }
}));

program.command('lat').alias('lattice').action(withStateRO((state) => {
  const result = runCompute(state);
  if (!result.concepts.length) { console.log(cc('  Empty.', C.D)); return; }
  const ml = Math.max(...result.layers, 0);
  console.log(cc(`  B(K): ${result.concepts.length} concepts`, C.B));
  const tags = ['T', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6', 'L7'];
  for (let layer = 0; layer <= ml; layer++) {
    const lc = result.concepts.map((c, i) => [i, c]).filter(([, c], i) => result.layers[i] === layer);
    if (!lc.length) continue;
    console.log(cc(`  -- ${tags[layer] || 'L' + layer} --`, C.BL));
    for (const [idx, [ext, intn]] of lc) {
      const en = [...ext].map(o => (state.objects[o]?.name || o).substring(0, 12)).join(',');
      const an = [...intn].map(a => (state.attributes[a]?.name || a).substring(0, 8)).join(',');
      console.log(`    C${String(idx).padStart(2, '0')} {${cc(an, C.M)}} <- {${cc(en.substring(0, 30), C.CN)}}`);
    }
  }
}));

program.command('concept').argument('<n>', 'concept index').action(withStateRO((state, n) => {
  const result = runCompute(state);
  const idx = parseInt(n);
  if (isNaN(idx) || idx < 0 || idx >= result.concepts.length) { console.log(cc('  Bad index', C.R)); return; }
  const [ext, intn] = result.concepts[idx];
  const layer = result.layers[idx] || 0;
  console.log(cc(`  C${String(idx).padStart(2, '0')} L${layer}`, C.B));
  console.log(cc('  Intent:', C.M));
  for (const a of [...intn].sort()) console.log(`    ${state.attributes[a]?.name || a}`);
  console.log(cc('  Extent:', C.CN));
  for (const o of [...ext].sort()) {
    const dirs = [...intn].sort().map(a => `${(state.attributes[a]?.name || a).substring(0, 4)}:${state.incidence[`${o}|${a}`] || '?'}`);
    console.log(`    ${state.objects[o]?.name || o}  ${cc(dirs.join(' '), C.D)}`);
  }
}));

program.command('hist').action(withStateRO((state) => {
  if (!state.history.length) { console.log(cc('  None.', C.D)); return; }
  state.history.slice(-20).forEach(h => console.log(`  [${h.time}] ${cc(h.act, C.CN)}: ${h.detail}`));
}));

// ── Snapshots ──

program.command('snaps').action(withStateRO((state) => {
  if (!state.snapshots.length) { console.log(cc('  None.', C.D)); return; }
  state.snapshots.forEach((s, i) => {
    const m = s.rw === 0 && s.unk === 0 ? '*' : ' ';
    console.log(`  ${m}#${i} ${s.time} |G|=${s.no} |M|=${s.na} |B|=${s.nc} RW=${cc(s.rw, s.rw ? C.Y : C.G)} ?=${cc(s.unk, s.unk ? C.R : C.G)}`);
  });
}));

program.command('diff').argument('<a>').argument('<b>')
  .action(withStateRO((state, a, b) => {
    const sa = state.snapshots[+a], sb = state.snapshots[+b];
    if (!sa || !sb) { console.log(cc('  Bad idx', C.R)); return; }
    console.log(cc(`  #${a} -> #${b}`, C.B));
    for (const [k, lb] of [['no', '|G|'], ['na', '|M|'], ['nc', '|B|'], ['rw', 'RW'], ['unk', '?']]) {
      if (sa[k] !== sb[k]) console.log(`  ${lb}: ${sa[k]} -> ${sb[k]} (${sb[k] - sa[k] > 0 ? '+' : ''}${sb[k] - sa[k]})`);
    }
    const ka = sa.inc || {}, kb = sb.inc || {};
    const ch = [...new Set([...Object.keys(ka), ...Object.keys(kb)])].filter(k => ka[k] !== kb[k]);
    if (ch.length) {
      console.log(cc('  Changes:', C.Y));
      ch.slice(0, 20).forEach(k => console.log(`    ${k}: ${ka[k] || '-'} -> ${kb[k] || '-'}`));
      if (ch.length > 20) console.log(`    +${ch.length - 20}`);
    }
  }));

program.command('rollback').argument('<n>')
  .action(withState((state, n) => {
    const s = state.snapshots[+n];
    if (!s) { console.log(cc('  ?', C.R)); return; }
    state.incidence = {};
    for (const [k, v] of Object.entries(s.inc || {})) state.incidence[k] = v;
    console.log(cc(`  Rolled back to #${n}`, C.G));
  }));

// ── Seed ──

const seedCmd = program.command('seed').description('Seed management');

seedCmd.action(withStateRO((state) => {
  const s = state.seed || {};
  const parts = [`Seed: ${s.domain || '(unnamed)'}`];
  if (s.obj_vocab?.length) parts.push(`  L1 obj vocab: ${s.obj_vocab.length}`);
  if (s.attr_vocab?.length) parts.push(`  L1 attr vocab: ${s.attr_vocab.length}`);
  if (s.obj_tree && Object.keys(s.obj_tree).length) parts.push(`  L2 obj tree: ${Object.keys(s.obj_tree).length} entries`);
  if (s.attr_tree && Object.keys(s.attr_tree).length) parts.push(`  L2 attr tree: ${Object.keys(s.attr_tree).length} entries`);
  if (s.incidence_hints && Object.keys(s.incidence_hints).length) parts.push(`  L2 hints: ${Object.keys(s.incidence_hints).length}`);
  if (s.conventions?.length) parts.push(`  L2 conventions: ${s.conventions.length} rules`);
  if (s.reference_k) parts.push(`  L3 reference K*: yes`);
  console.log(parts.join('\n'));
}));

seedCmd.command('load').argument('<file>').action(withState(async (state, fp) => {
  try { state.seed = JSON.parse(fs.readFileSync(fp, 'utf8')); console.log(cc(`  Loaded: ${state.seed.domain || '(unnamed)'}`, C.G)); } catch (ex) { console.log(cc(`  ${ex}`, C.R)); }
}));

seedCmd.command('save').argument('<file>').action(withState((state, fp) => {
  fs.writeFileSync(fp, JSON.stringify(state.seed, null, 2)); console.log(cc(`  ${fp}`, C.G));
}));

seedCmd.command('tree').action(withStateRO((state) => {
  const ot = state.seed?.obj_tree || {};
  const at = state.seed?.attr_tree || {};
  if (Object.keys(ot).length) { console.log(cc('  Object tree:', C.CN)); for (const [k, v] of Object.entries(ot)) console.log(`    ${cc(k, C.Y)} -> ${v.join(', ')}`); }
  if (Object.keys(at).length) { console.log(cc('  Attribute tree:', C.M)); for (const [k, v] of Object.entries(at)) console.log(`    ${cc(k, C.Y)} -> ${v.join(', ')}`); }
  if (!Object.keys(ot).length && !Object.keys(at).length) console.log(cc('  Empty.', C.D));
}));

seedCmd.command('conv').action(withStateRO((state) => {
  const conv = state.seed?.conventions || [];
  if (conv.length) { console.log(cc(`  Seed conventions (${conv.length}):`, C.CN)); conv.forEach(c => console.log(`    - ${c}`)); }
  else console.log(cc('  No seed conventions.', C.D));
}));

seedCmd.command('set').argument('<type>', 'obj|attr').argument('<parent>').argument('<children...>')
  .action(withState((state, type, parent, children) => {
    if (!state.seed) state.seed = {};
    if (type === 'obj') { state.seed.obj_tree = state.seed.obj_tree || {}; state.seed.obj_tree[parent] = children; console.log(cc(`  ${parent} -> ${children.join(', ')}`, C.G)); }
    else { state.seed.attr_tree = state.seed.attr_tree || {}; state.seed.attr_tree[parent] = children; console.log(cc(`  ${parent} -> ${children.join(', ')}`, C.G)); }
  }));

// ── LLM ──

const llmCmd = program.command('llm').description('LLM operations');

llmCmd.command('analyze').argument('<file>').action(withState(async (state, fp) => {
  try {
    const content = fs.readFileSync(fp, 'utf8');
    console.log(cc('  [1/2] Extracting G,M...', C.D));
    const r1 = await llm.extractGm(content);
    const d1 = llm.extractJson(r1);
    if (!d1) { console.log(cc(`  Step 1 failed: ${r1.substring(0, 300)}`, C.R)); return; }
    for (const obj of (d1.objects || [])) {
      if (obj.id) {
        state.objects[obj.id] = { name: obj.name || obj.id, desc: obj.desc || '', solidified: false };
        for (const a of Object.keys(state.attributes)) state.incidence[`${obj.id}|${a}`] = state.incidence[`${obj.id}|${a}`] || '?';
        console.log(`    +${obj.id} ${obj.name || obj.id}`);
      }
    }
    for (const attr of (d1.attributes || [])) {
      if (attr.id) {
        state.attributes[attr.id] = { name: attr.name || attr.id, desc: attr.desc || '' };
        for (const o of Object.keys(state.objects)) state.incidence[`${o}|${attr.id}`] = state.incidence[`${o}|${attr.id}`] || '?';
        console.log(`    +${attr.id} ${attr.name || attr.id}`);
      }
    }
    const op = Object.entries(state.objects).map(([id, o]) => [id, o.name]);
    const ap = Object.entries(state.attributes).map(([id, a]) => [id, a.name]);
    if (op.length && ap.length) {
      console.log(cc(`  [2/2] ${op.length}x${ap.length} directed I...`, C.D));
      const r2 = await llm.fillDirected(content, op, ap);
      const d2 = llm.extractJson(r2);
      if (!d2) {
        console.log(cc(`  Step 2 failed: ${r2}`, C.Y));
        console.log(cc(`  Run 'konceptos llm ask' to fill manually`, C.Y));
      } else {
        const aids = Object.keys(state.attributes).sort();
        let cnt = 0;
        for (const [key, val] of Object.entries(d2)) {
          if (state.objects[key] && typeof val === 'string') {
            val.split(',').map(v => v.trim().toUpperCase()).forEach((v, i) => {
              if (i < aids.length && VALID_I.has(v)) { state.incidence[`${key}|${aids[i]}`] = v; cnt++; }
            });
          }
        }
        console.log(cc(`  Filled ${cnt} cells`, C.G));
      }
    }
    updateSnap(state);
    showStatus(state);
  } catch (ex) { console.log(cc(`  ${ex}`, C.R)); }
}));

llmCmd.command('ask').description('Fill unknowns (interactive)').action(withState(async (state) => {
  const unks = unknowns(state);
  if (!unks.length) { console.log(cc('  Complete!', C.G)); return; }
  console.log(cc(`  ${unks.length} unknowns. Options: 0/R/W/RW=set, s=skip(LLM), sa=skip-all(LLM), q=quit`, C.D));

  const readline = await import('readline');
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const question = (prompt) => new Promise(resolve => rl.question(prompt, resolve));

  let skipAll = false;
  for (const [k] of unks) {
    const [o, a] = k.split('|');
    const on = state.objects[o]?.name || o;
    const an = state.attributes[a]?.name || a;
    if (skipAll) {
      const v = await llm.judgeOne(on, state.objects[o]?.desc || '', an, state.attributes[a]?.desc || '');
      state.incidence[k] = v;
      console.log(`    ${cc(on, C.CN)} x ${cc(an, C.M)} = ${v}`);
      continue;
    }
    const ans = (await question(`    ${cc(on, C.CN)} x ${cc(an, C.M)} ? `)).trim().toUpperCase();
    if (ans === 'Q') break;
    if (ans === 'SA' || ans === 'SKIPALL') {
      skipAll = true;
      const v = await llm.judgeOne(on, state.objects[o]?.desc || '', an, state.attributes[a]?.desc || '');
      state.incidence[k] = v;
      console.log(`    = ${v}`);
    } else if (ans === 'S' || ans === 'SKIP') {
      const v = await llm.judgeOne(on, state.objects[o]?.desc || '', an, state.attributes[a]?.desc || '');
      state.incidence[k] = v;
      console.log(`    = ${v}`);
    } else if (VALID_I.has(ans)) {
      state.incidence[k] = ans;
    }
  }
  rl.close();
  updateSnap(state);
  console.log(cc(`  Done. ${unknowns(state).length} remaining`, C.D));
}));

llmCmd.command('chat').argument('<message...>', 'message').action(async (message) => {
  const r = await llm.chat('FCA assistant.', Array.isArray(message) ? message.join(' ') : message);
  console.log('  ' + r.replace(/\n/g, '\n  '));
});

// ── Resolve ──

const resolveCmd = program.command('resolve').description('Resolve concepts');

resolveCmd.command('obj').argument('<id>').action(withState(async (state, id) => {
  if (!state.objects[id]) { console.log(cc(`  No obj: ${id}`, C.R)); return; }
  const ob = state.objects[id];
  const children = lookupObj(state, ob.name);
  let chList;
  if (children) {
    console.log(cc(`  Seed: ${ob.name} -> ${children.join(', ')}`, C.CN));
    chList = children.map(c => ({ name: c }));
  } else {
    console.log(cc('  No seed. Asking LLM...', C.D));
    const r = await llm.askExpansion(ob.name, ob.desc, 'object', state.seed?.obj_vocab);
    const d = llm.extractJson(r);
    if (!d?.expansions) { console.log(cc(`  Failed: ${r.substring(0, 200)}`, C.R)); return; }
    chList = d.expansions;
    console.log(cc(`  LLM: ${ob.name} -> ${chList.map(c => c.name).join(', ')}`, C.CN));
  }
  const newIds = chList.map((c, i) => {
    let nid = `${id}_${i + 1}`;
    while (state.objects[nid]) nid += '_';
    state.objects[nid] = { name: c.name, desc: c.desc || '', solidified: false };
    for (const a of Object.keys(state.attributes)) state.incidence[`${nid}|${a}`] = state.incidence[`${nid}|${a}`] || '?';
    return nid;
  });
  for (const nid of newIds) {
    for (const aid of Object.keys(state.attributes)) {
      const parentVal = state.incidence[`${id}|${aid}`] || '0';
      if (parentVal === '0') { state.incidence[`${nid}|${aid}`] = '0'; continue; }
      const hint = state.seed?.incidence_hints?.[`${state.objects[nid].name}|${state.attributes[aid].name}`] ||
                   state.seed?.incidence_hints?.[`*|${state.attributes[aid].name}`];
      if (hint && VALID_I.has(hint)) { state.incidence[`${nid}|${aid}`] = hint; continue; }
      const v = await llm.judgeOne(state.objects[nid].name, state.objects[nid].desc, state.attributes[aid].name, state.attributes[aid].desc);
      state.incidence[`${nid}|${aid}`] = v;
    }
  }
  delete state.objects[id];
  Object.keys(state.incidence).forEach(k => { if (k.startsWith(id + '|')) delete state.incidence[k]; });
  state.round++;
  updateSnap(state);
  log(state, 'resolve_obj', `${id} -> ${newIds.join(', ')}`);
  console.log(cc(`  Done. |G|=${Object.keys(state.objects).length} RW=${rwCount(state)}`, C.G));
}));

resolveCmd.command('attr').argument('<id>').action(withState(async (state, id) => {
  if (!state.attributes[id]) { console.log(cc(`  No attr: ${id}`, C.R)); return; }
  const at = state.attributes[id];
  const children = lookupAttr(state, at.name);
  let chList;
  if (children) {
    console.log(cc(`  Seed: ${at.name} -> ${children.join(', ')}`, C.CN));
    chList = children.map(c => ({ name: c }));
  } else {
    console.log(cc('  No seed. Asking LLM...', C.D));
    const r = await llm.askExpansion(at.name, at.desc, 'attribute', state.seed?.attr_vocab);
    const d = llm.extractJson(r);
    if (!d?.expansions) { console.log(cc(`  Failed: ${r.substring(0, 200)}`, C.R)); return; }
    chList = d.expansions;
    console.log(cc(`  LLM: ${at.name} -> ${chList.map(c => c.name).join(', ')}`, C.CN));
  }
  const oldBinding = state.bindings[id];
  const newIds = chList.map((c, i) => {
    let nid = `${id}_${i + 1}`;
    while (state.attributes[nid]) nid += '_';
    state.attributes[nid] = { name: c.name, desc: c.desc || '' };
    if (oldBinding) state.bindings[nid] = oldBinding;
    for (const o of Object.keys(state.objects)) state.incidence[`${o}|${nid}`] = state.incidence[`${o}|${nid}`] || '?';
    return nid;
  });
  for (const oid of Object.keys(state.objects)) {
    const parentVal = state.incidence[`${oid}|${id}`] || '0';
    if (parentVal === '0') { newIds.forEach(nid => { state.incidence[`${oid}|${nid}`] = '0'; }); continue; }
    for (const nid of newIds) {
      const hint = state.seed?.incidence_hints?.[`${state.objects[oid].name}|${state.attributes[nid].name}`] ||
                   state.seed?.incidence_hints?.[`*|${state.attributes[nid].name}`];
      if (hint && VALID_I.has(hint)) { state.incidence[`${oid}|${nid}`] = hint; continue; }
      const v = await llm.judgeOne(state.objects[oid].name, state.objects[oid].desc, state.attributes[nid].name, state.attributes[nid].desc);
      state.incidence[`${oid}|${nid}`] = v;
    }
  }
  delete state.attributes[id];
  delete state.bindings[id];
  Object.keys(state.incidence).forEach(k => { if (k.endsWith('|' + id)) delete state.incidence[k]; });
  state.round++;
  updateSnap(state);
  log(state, 'resolve_attr', `${id} -> ${newIds.join(', ')}`);
  console.log(cc(`  Done. |M|=${Object.keys(state.attributes).length} RW=${rwCount(state)}`, C.G));
}));

// ── Evolve ──

program.command('evolve').argument('[n]', 'number of cells (default 1, or "all")', '1')
  .action(withState(async (state, n) => {
    const initRw = rwCount(state);
    if (initRw === 0) { console.log(cc('  K* (RW=0)', C.G)); return; }
    const initSnap = state.snapshots.length;
    const mx = n === 'all' ? initRw * 3 : (parseInt(n) || 1);
    console.log(cc(`  === Evolve: ${initRw} RW ===`, C.B));
    for (let step = 1; step <= mx; step++) {
      const cells = rwCells(state);
      if (!cells.length) { console.log(cc('\n  K* reached!', C.G, C.B)); break; }
      const objRw = {};
      cells.forEach(([k]) => { const [o] = k.split('|'); objRw[o] = (objRw[o] || 0) + 1; });
      const worst = Object.entries(objRw).sort((a, b) => b[1] - a[1])[0][0];
      const oname = state.objects[worst]?.name;
      const children = lookupObj(state, oname);
      let chList;
      if (children) {
        console.log(cc(`\n  [${step}] ${oname} -> ${children.join(', ')} (seed)`, C.CN));
        chList = children.map(c => ({ name: c }));
      } else {
        console.log(cc(`\n  [${step}] ${oname} (LLM)...`, C.Y));
        const r = await llm.askExpansion(oname, state.objects[worst]?.desc || '', 'object', state.seed?.obj_vocab);
        const d = llm.extractJson(r);
        if (!d?.expansions) { console.log(cc('    Failed, stopping', C.R)); break; }
        chList = d.expansions;
        console.log(cc(`    -> ${chList.map(c => c.name).join(', ')}`, C.CN));
      }
      const newIds = chList.map((c, i) => {
        let nid = `${worst}_${i + 1}`;
        while (state.objects[nid]) nid += '_';
        state.objects[nid] = { name: c.name, desc: c.desc || '', solidified: false };
        for (const a of Object.keys(state.attributes)) state.incidence[`${nid}|${a}`] = state.incidence[`${nid}|${a}`] || '?';
        return nid;
      });
      for (const nid of newIds) {
        for (const aid of Object.keys(state.attributes)) {
          const parentVal = state.incidence[`${worst}|${aid}`] || '0';
          if (parentVal === '0') { state.incidence[`${nid}|${aid}`] = '0'; continue; }
          const v = await llm.judgeOne(state.objects[nid].name, state.objects[nid].desc, state.attributes[aid].name, state.attributes[aid].desc);
          state.incidence[`${nid}|${aid}`] = v;
        }
      }
      delete state.objects[worst];
      Object.keys(state.incidence).forEach(k => { if (k.startsWith(worst + '|')) delete state.incidence[k]; });
      state.round++;
      updateSnap(state);
      const newRw = rwCount(state);
      console.log(cc(`    RW: ${initRw} -> ${newRw}  |G|=${Object.keys(state.objects).length}`, newRw < initRw ? C.G : C.Y));
      if (newRw === 0) break;
    }
    const lastSnap = state.snapshots[initSnap];
    console.log(cc(`\n  RW ${initRw}->${rwCount(state)}  |G| ${lastSnap?.no}->${Object.keys(state.objects).length}  |M| ${lastSnap?.na}->${Object.keys(state.attributes).length}`, C.G));
  }));

// ── Build ──

program.command('build').argument('[out]', 'output file', 'index.html')
  .action(withState(async (state, out) => {
    const result = runCompute(state);
    if (!result.concepts.length) { console.log(cc('  Empty context. Nothing to build.', C.R)); return; }
    // Export spec
    const lines = ['# FCA Spec\n'];
    const conv = getAllConventions(state);
    if (conv) lines.push(`## Conventions\n\`\`\`\n${conv}\n\`\`\`\n`);
    lines.push(`## Objects (${Object.keys(state.objects).length})\n| ID | Name | Desc |\n|----|------|------|`);
    for (const [o, ob] of Object.entries(state.objects)) lines.push(`| ${o} | ${ob.name} | ${ob.desc || ''} |`);
    lines.push(`\n## Attributes (${Object.keys(state.attributes).length})\n| ID | Name | Binding |\n|----|------|---------|`);
    for (const [a, at] of Object.entries(state.attributes)) lines.push(`| ${a} | ${at.name} | ${state.bindings[a] || '-'} |`);
    const aids = Object.keys(state.attributes).sort();
    lines.push(`\n## Incidence\n| |${aids.map(a => state.attributes[a].name.substring(0, 6)).join('|')}|`);
    lines.push(`|--${'|--'.repeat(aids.length)}|`);
    for (const o of Object.keys(state.objects).sort()) {
      const row = `| ${state.objects[o].name.substring(0, 14)} `;
      lines.push(row + aids.map(a => ` ${state.incidence[`${o}|${a}`] || '?'}`).join(' ') + ' |');
    }
    lines.push(`\n## Concepts (${result.concepts.length})\n`);
    const ml = Math.max(...result.layers, 0);
    for (let layer = 0; layer <= ml; layer++) {
      const lc = result.concepts.map((c, i) => [i, c]).filter(([, c], i) => result.layers[i] === layer);
      if (!lc.length) continue;
      lines.push(`### L${layer}\n`);
      for (const [idx, [ext, intn]] of lc) {
        const en = [...ext].map(o => state.objects[o]?.name || o).join(', ') || 'empty';
        const an = [...intn].map(a => state.attributes[a]?.name || a).join(', ') || 'empty';
        lines.push(`C${String(idx).padStart(2, '0')} ({${an}}, {${en}})`);
      }
    }
    const spec = lines.join('\n');
    const binds = Object.entries(state.bindings).map(([a, t]) => `${state.attributes[a]?.name || a}:${t}`).join('\n');
    console.log(cc(`  Building... (conventions: ${conv ? conv.split('\n').filter(l => l.trim()).length : 0} rules)`, C.D));
    const r = await llm.buildFull(spec, binds, conv);
    // Strip markdown fences
    let html = r.trim();
    if (html.startsWith('```')) {
      const lines2 = html.split('\n');
      if (lines2[0].startsWith('```')) lines2.shift();
      if (lines2.length && lines2[lines2.length - 1].startsWith('```')) lines2.pop();
      html = lines2.join('\n');
    }
    fs.writeFileSync(out, html);
    console.log(cc(`  ${out} (${html.length} chars)`, C.G));
  }));

// ── System ──

program.command('compute').action(withState((state) => {
  updateSnap(state);
  const result = runCompute(state);
  console.log(cc(`  |B|=${result.concepts.length} (snap #${state.snapshots.length - 1})`, C.G));
}));

program.command('save').argument('<file>').action(withState((state, fp) => {
  saveState(state);
  fs.writeFileSync(fp, JSON.stringify(state, null, 2));
  console.log(cc(`  ${fp}`, C.G));
}));

program.command('open').argument('<file>').action(withState((state, fp) => {
  try {
    const loaded = JSON.parse(fs.readFileSync(fp, 'utf8'));
    Object.assign(state, loaded);
    updateSnap(state);
    console.log(cc(`  Loaded ${fp} (${state.snapshots?.length || 0} snaps)`, C.G));
  } catch (ex) { console.log(cc(`  ${ex}`, C.R)); }
}));

program.command('export').argument('<file>').action(withState((state, fp) => {
  const result = runCompute(state);
  const lines = ['# FCA Spec\n'];
  const conv = getAllConventions(state);
  if (conv) lines.push(`## Conventions\n\`\`\`\n${conv}\n\`\`\`\n`);
  lines.push(`## Objects (${Object.keys(state.objects).length})\n| ID | Name | Desc |\n|----|------|------|`);
  for (const [o, ob] of Object.entries(state.objects)) lines.push(`| ${o} | ${ob.name} | ${ob.desc || ''} |`);
  lines.push(`\n## Attributes (${Object.keys(state.attributes).length})\n| ID | Name | Binding |\n|----|------|---------|`);
  for (const [a, at] of Object.entries(state.attributes)) lines.push(`| ${a} | ${at.name} | ${state.bindings[a] || '-'} |`);
  const aids = Object.keys(state.attributes).sort();
  lines.push(`\n## Incidence\n| |${aids.map(a => state.attributes[a].name.substring(0, 6)).join('|')}|`);
  lines.push(`|--${'|--'.repeat(aids.length)}|`);
  for (const o of Object.keys(state.objects).sort()) {
    const row = `| ${state.objects[o].name.substring(0, 14)} `;
    lines.push(row + aids.map(a => ` ${state.incidence[`${o}|${a}`] || '?'}`).join(' ') + ' |');
  }
  lines.push(`\n## Concepts (${result.concepts.length})\n`);
  const ml = Math.max(...result.layers, 0);
  for (let layer = 0; layer <= ml; layer++) {
    const lc = result.concepts.map((c, i) => [i, c]).filter(([, c], i) => result.layers[i] === layer);
    if (!lc.length) continue;
    lines.push(`### L${layer}\n`);
    for (const [idx, [ext, intn]] of lc) {
      const en = [...ext].map(o => state.objects[o]?.name || o).join(', ') || 'empty';
      const an = [...intn].map(a => state.attributes[a]?.name || a).join(', ') || 'empty';
      lines.push(`C${String(idx).padStart(2, '0')} ({${an}}, {${en}})`);
    }
  }
  fs.writeFileSync(fp, lines.join('\n'));
  console.log(cc(`  ${fp}`, C.G));
}));

program.parse(process.argv);
