const VALID_I = new Set(['0', 'R', 'W', 'RW']);

export { VALID_I };

export function compute(objects, attributes, incidence) {
  const oids = Object.keys(objects);
  const aids = Object.keys(attributes);

  if (!oids.length || !aids.length) return { concepts: [], edges: [], layers: [] };

  const involved = (o, a) => {
    const v = incidence[`${o}|${a}`];
    return v === 'R' || v === 'W' || v === 'RW';
  };

  const _intent = (ext) => {
    if (!ext.size) return new Set(aids);
    let r = new Set(aids);
    for (const o of ext) {
      r = new Set([...r].filter(a => involved(o, a)));
    }
    return r;
  };

  const _extent = (intn) => {
    if (!intn.size) return new Set(oids);
    let r = new Set(oids);
    for (const a of intn) {
      r = new Set([...r].filter(o => involved(o, a)));
    }
    return r;
  };

  const seen = new Set();
  const concepts = [];

  // Generate candidates
  const cands = [new Set()];
  for (const o of oids) cands.push(new Set([o]));
  for (let i = 0; i < oids.length; i++) {
    for (let j = i + 1; j < Math.min(i + 10, oids.length); j++) {
      cands.push(new Set([oids[i], oids[j]]));
    }
  }
  for (const a of aids) {
    const ext = _extent(new Set([a]));
    if (ext.size) cands.push(ext);
  }
  for (let i = 0; i < aids.length; i++) {
    for (let j = i + 1; j < aids.length; j++) {
      const ext = _extent(new Set([aids[i], aids[j]]));
      if (ext.size) cands.push(ext);
    }
  }
  if (aids.length <= 14) {
    for (let i = 0; i < aids.length; i++) {
      for (let j = i + 1; j < aids.length; j++) {
        for (let k = j + 1; k < aids.length; k++) {
          const ext = _extent(new Set([aids[i], aids[j], aids[k]]));
          if (ext.size) cands.push(ext);
        }
      }
    }
  }

  for (const ext of cands) {
    const intn = _intent(ext);
    const closed = _extent(intn);
    const key = `${[...closed].sort().join(',')}|${[...intn].sort().join(',')}`;
    if (!seen.has(key)) {
      seen.add(key);
      concepts.push([closed, intn]);
    }
  }

  concepts.sort((a, b) => a[1].size - b[1].size);

  const edges = [];
  for (let i = 0; i < concepts.length; i++) {
    for (let j = i + 1; j < concepts.length; j++) {
      const [ai, bi] = [concepts[i][1], concepts[j][1]];
      if (isProperSubset(ai, bi)) {
        let ok = true;
        for (let k = 0; k < concepts.length; k++) {
          if (k === i || k === j) continue;
          const bk = concepts[k][1];
          if (isProperSubset(ai, bk) && isProperSubset(bk, bi)) { ok = false; break; }
        }
        if (ok) edges.push([i, j]);
      }
    }
  }

  const layers = new Array(concepts.length).fill(0);
  let changed = true;
  while (changed) {
    changed = false;
    for (const [p, c] of edges) {
      if (layers[c] <= layers[p]) { layers[c] = layers[p] + 1; changed = true; }
    }
  }

  return { concepts, edges, layers };
}

function isProperSubset(a, b) {
  if (a.size >= b.size) return false;
  for (const el of a) if (!b.has(el)) return false;
  return true;
}

function isSubsetOf(a, b) {
  if (a.size > b.size) return false;
  for (const el of a) if (!b.has(el)) return false;
  return true;
}
