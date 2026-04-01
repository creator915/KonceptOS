"""KonceptOS v2.1 — Click CLI."""
import click, json, time
from .util import cc, C, extract_json, load_file, VALID_I, safe_name, safe_contract_name
from .engine import Engine, k_hash
from .llm import LLM, OPENROUTER_MODEL
from .seed import JsonSeed, SeedChain
from . import codegen
from . import verify
from .test_runner import SeleniumTestRunner

WORKSPACE_DIR = './.konceptos'

# ── helpers ────────────────────────────────────────────────────────────────────

def _engine():
    e = Engine()
    e.load_workspace(WORKSPACE_DIR)
    e.watch(_show_ctx)
    return e

def _ensure_dir():
    import os; os.makedirs(WORKSPACE_DIR, exist_ok=True)

def _warn(msg): click.echo(cc('  ' + msg, C.Y))
def _err(msg): click.echo(cc('  ' + msg, C.R))
def _ok(msg): click.echo(cc('  ' + msg, C.G))
def _info(msg): click.echo(cc('  ' + msg, C.D))
def _bold(msg): click.echo(cc('  ' + msg, C.B))
def _cyan(msg): click.echo(cc('  ' + msg, C.CN))

def _show_ctx(e):
    if not e.objects or not e.attributes: _info('Empty.'); return
    oids = sorted(e.objects); aids = sorted(e.attributes)
    nw = max(18, max(len(e.objects[o]['name']) for o in oids) + 6)
    hdr = ' ' * nw
    for a in aids: hdr += cc(e.attributes[a]['name'][:5].center(6), C.CN)
    click.echo(cc('  +' + '-' * (nw + len(aids) * 6) + '+', C.D))
    click.echo('  |' + hdr + '|'); click.echo(cc('  +' + '-' * (nw + len(aids) * 6) + '+', C.D))
    for o in oids:
        ob = e.objects[o]; lbl = ' %s %s' % (cc(o, C.Y), ob['name']); vl = 1 + len(o) + 1 + len(ob['name'])
        row = lbl + ' ' * max(0, nw - vl)
        for a in aids:
            v = e.incidence.get((o, a), 'RW')
            if v == 'RW': row += cc(' RW  ', C.Y, C.B) + ' '
            elif v == 'R': row += cc('  R   ', C.CN)
            elif v == 'W': row += cc('  W   ', C.M)
            else:         row += cc('  .   ', C.D)
        click.echo('  |' + row + '|')
    click.echo(cc('  +' + '-' * (nw + len(aids) * 6) + '+', C.D))

def _show_status(e):
    rw = e.rw_count(); ce, ct = e.coverage()
    _bold('K: |G|=%d |M|=%d RW=%d |B|=%d' % (len(e.objects), len(e.attributes), rw, len(e.concepts)))
    if ct: _info('Coverage: %d/%d (%.0f%%)' % (ce, ct, 100 * ce / ct))
    sc = sum(1 for a in e.attributes if a in e.schemas)
    sn = sum(1 for a in e.attributes if any(e.incidence.get((o, a), 'RW') != '0' for o in e.objects))
    _ok('Schemas: %d/%d' % (sc, sn)) if sc >= sn else _warn('Schemas: %d/%d' % (sc, sn))
    if rw == 0: _ok('No RW (cond 1)')
    else: _warn('%d RW to refine' % rw)
    tc = e.detect_temporal_conflicts()
    if not tc: _ok('No temporal conflicts (cond 2)')
    else:
        for c in tc: click.echo('  ✗ %s: early=[%s] late=[%s] %s' % (cc(c['name'], C.CN), ','.join(c['early']), ','.join(c['late']), c['splittable']))
    for c in e.check_consistency(): _warn(c)
    if e.seed.has_content(): _cyan('Seed: %s' % e.seed.domain)
    if e.current_node: _info('Node: %s' % e.current_node)


# ── CLI ───────────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """KonceptOS v2.1 — FCA-based AI code generation framework.

    K = (G, M, I) where G=objects/modules, M=attributes/channels, I=incidence.
    Workspace auto-saved to ./.konceptos/workspace.json after every edit.
    """
    pass


# ── K editing ─────────────────────────────────────────────────────────────────

@cli.command('add')
@click.argument('kind')  # obj | attr
@click.argument('id')
@click.argument('name')
@click.argument('desc', default='')
def add(kind, id, name, desc):
    """Add an object (module) or attribute (data channel)."""
    e = _engine()
    if kind == 'obj': e.add_obj(id, name, desc)
    elif kind == 'attr': e.add_attr(id, name, desc)
    else: _err('Use: add obj|attr <id> <name>'); return
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('+%s' % id)

@cli.command('set')
@click.argument('obj')
@click.argument('attr')
@click.argument('val')  # 0 | R | W | RW
def set_incidence(obj, attr, val):
    """Set incidence value for (obj, attr)."""
    e = _engine()
    try:
        e.set_i(obj, attr, val)
        _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
        _ok('OK')
    except Exception as ex: _err(str(ex))

@cli.command('row')
@click.argument('obj')
@click.argument('vals', nargs=-1)  # comma-separated or space-separated values
def row(obj, vals):
    """Set all incidence values for an object row. Values: 0,R,W,RW (comma or space sep)."""
    e = _engine()
    # Accept either 'R,0,W,RW' (single arg) or separate args
    if len(vals) == 1 and ',' in vals[0]:
        vals = vals[0].split(',')
    aids = sorted(e.attributes)
    for i, v in enumerate(vals):
        if i < len(aids):
            try: e.set_i(obj, aids[i], v.strip())
            except: pass
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('OK')

@cli.command('del')
@click.argument('kind')  # obj | attr
@click.argument('id')
def delete(kind, id):
    """Delete an object or attribute."""
    e = _engine()
    if kind == 'obj': e.del_obj(id)
    elif kind == 'attr': e.del_attr(id)
    else: _err('Use: del obj|attr <id>'); return
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('-%s' % id)

@cli.command('schema')
@click.argument('attr_id', required=False)
@click.argument('typedef', nargs=-1, required=False)
@click.option('--auto', 'is_auto', is_flag=True, help='Auto-generate schemas via LLM')
def schema(attr_id, typedef, is_auto):
    """Set schema for an attribute, or use --auto to generate all via LLM."""
    e = _engine()
    if is_auto:
        if not e.attributes: _info('Empty.'); return
        llm = LLM()
        if not llm.ok: _err('LLM not available. Set OPENROUTER_API_KEY.'); return
        e.compute()
        target_aids = [attr_id] if attr_id else [a for a in e.attributes if a not in e.schemas]
        if not target_aids: _ok('All set.'); return
        attrs_info = []
        for aid in target_aids:
            if aid not in e.attributes: continue
            an = e.attributes[aid]['name']; ad = e.attributes[aid].get('desc', '')
            ws = ', '.join(e.objects[o]['name'] for o in e.objects if e.incidence.get((o, aid), 'RW') == 'W')
            rs = ', '.join(e.objects[o]['name'] for o in e.objects if e.incidence.get((o, aid), 'RW') == 'R')
            attrs_info.append((an, ad, ws, rs))
        _info('Generating schemas for %d channels...' % len(attrs_info))
        results = llm.suggest_schemas(attrs_info, e.get_all_conventions())
        if not results: _err('No schemas returned.'); return
        name_to_aid = {e.attributes[a]['name']: a for a in target_aids if a in e.attributes}
        for ch_name, sch in results.items():
            aid = name_to_aid.get(ch_name)
            if aid: e.set_schema(aid, sch); _ok('%s: %s' % (ch_name, sch))
        _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
        return
    if not attr_id or not typedef: _err('Usage: schema <attr_id> <typedef>'); return
    t = ' '.join(typedef)
    try:
        e.set_schema(attr_id, t)
        _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
        _ok('OK')
    except Exception as ex: _err(str(ex))

@cli.command('convention')
@click.argument('text', nargs=-1)
def convention(text):
    """Set or view global conventions."""
    e = _engine()
    if text:
        e.conventions = ' '.join(text)
        _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
        _ok('Set.')
    else:
        conv = e.get_all_conventions()
        click.echo(conv if conv else cc('  (empty)', C.D))


# ── view ──────────────────────────────────────────────────────────────────────

@cli.command('ctx')
def ctx():
    """Show context matrix (K overview)."""
    _show_ctx(_engine())

@cli.command('st')
def st():
    """Show status."""
    _show_status(_engine())

@cli.command('rw')
def rw():
    """Show all RW (read-write) cells."""
    e = _engine()
    cells = e.rw_cells()
    if not cells: _ok('RW=0')
    else:
        by_obj = {}
        for o, a in cells: by_obj.setdefault(o, []).append(a)
        _warn('%d RW:' % len(cells))
        for o in sorted(by_obj, key=lambda x: -len(by_obj[x])):
            _warn('  %s (%d): %s' % (cc(e.objects[o]['name'], C.CN), len(by_obj[o]), cc(', '.join(e.attributes[a]['name'] for a in by_obj[o]), C.M)))

@cli.command('flows')
def flows():
    """Show data flows."""
    e = _engine()
    fl = e.dataflows()
    if not fl: _info('None.')
    else:
        for f, v, t in fl: click.echo('  %s -[%s]→ %s' % (cc(f, C.CN), cc(v, C.M), cc(t, C.G)))

@cli.command('order')
def order():
    """Show execution order (topological sort)."""
    e = _engine()
    o, cyc = e.topo_sort()
    if cyc: _warn('Warning: cycle detected')
    for i, oid in enumerate(o): click.echo('  %2d. %s' % (i + 1, cc(e.objects[oid]['name'], C.CN)))

@cli.command('conflicts')
def conflicts():
    """Show temporal conflicts."""
    e = _engine()
    tc = e.detect_temporal_conflicts()
    if not tc: _ok('None.')
    else:
        for c in tc:
            click.echo('  %s (%s):' % (cc(c['name'], C.CN), c['splittable']))
            click.echo('    early: %s' % ', '.join(c['early'])); click.echo('    late:  %s' % ', '.join(c['late']))

@cli.command('groups')
def groups():
    """Show coding groups."""
    e = _engine()
    gr = e.coding_groups()
    if not gr: _info('None.')
    else:
        for ci in sorted(gr): click.echo('  C%02d: %s' % (ci, cc(', '.join(e.objects[o]['name'] for o in gr[ci] if o in e.objects), C.CN)))

@cli.command('lat')
def lat():
    """Show concept lattice."""
    e = _engine()
    if not e.concepts: _info('Empty.'); return
    ml = max(e.layers) if e.layers else 0
    _bold('B(K): %d concepts' % len(e.concepts))
    for layer in range(ml + 1):
        lc = [(i, e.concepts[i]) for i in range(len(e.concepts)) if e.layers[i] == layer]
        if lc:
            click.echo(cc('  -- L%d --' % layer, C.BL))
            for idx, (ext, intn) in lc:
                en = [e.objects[o]['name'][:12] for o in sorted(ext) if o in e.objects]
                an = [e.attributes[a]['name'][:8] for a in sorted(intn) if a in e.attributes]
                click.echo('    C%02d {%s} ← {%s}' % (idx, cc(','.join(an), C.M), cc(','.join(en[:5]), C.CN)))

@cli.command('concept')
@click.argument('n', type=int)
def concept(n):
    """Show concept N details."""
    e = _engine()
    if not e.concepts or n < 0 or n >= len(e.concepts): _err('Out of range.'); return
    ext, intn = e.concepts[n]
    click.echo(cc('  C%02d L%d' % (n, e.layers[n]), C.B))
    for a in sorted(intn): click.echo('    %s  %s' % (e.attributes.get(a, {}).get('name', ''), cc(e.schemas.get(a, ''), C.D)))
    for o in sorted(ext):
        dirs = [e.attributes.get(a, {}).get('name', '')[:4] + ':' + e.incidence.get((o, a), 'RW') for a in sorted(intn)]
        click.echo('    %s  %s' % (e.objects.get(o, {}).get('name', ''), cc(' '.join(dirs), C.D)))

@cli.command('ts')
def ts():
    """Show TypeScript signatures."""
    e = _engine()
    lines = ['// KonceptOS v2.1 — TypeScript signatures', '// Node: %s\n' % (e.current_node or '?')]
    lines.append('interface Channels {')
    for aid in sorted(e.attributes): lines.append('  %s: %s;' % (e.attributes[aid]['name'], e.schemas.get(aid, 'any')))
    lines.append('}\n')
    for oid in sorted(e.objects):
        on = e.objects[oid]['name']; cn = safe_contract_name(on)
        c = e.contract_for(oid)
        lines.append('// %s' % on)
        lines.append('interface %s {' % cn)
        if c['reads']:       lines.append("  reads: %s;" % ' | '.join("'%s'" % x for x in c['reads']))
        if c['writes']:      lines.append("  writes: %s;" % ' | '.join("'%s'" % x for x in c['writes']))
        if c['readwrites']:  lines.append("  readwrites: %s;" % ' | '.join("'%s'" % x for x in c['readwrites']))
        lines.append('}\n')
    click.echo('\n'.join(lines))

@cli.command('framework')
def framework():
    """Show generated framework.js."""
    e = _engine()
    click.echo(codegen.generate_framework_js(e))


# ── DAG ───────────────────────────────────────────────────────────────────────

@cli.command('commit')
@click.argument('desc', default='')
def commit(desc):
    """Commit current state to DAG."""
    e = _engine()
    e.compute()
    nid = e.commit(desc)
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('Committed: %s' % nid)

@cli.command('goto')
@click.argument('hash_prefix')
def dag_goto(hash_prefix):
    """Jump to a DAG node by hash prefix."""
    e = _engine()
    ms = [h for h in e.dag.nodes if h.startswith(hash_prefix)]
    if len(ms) == 1:
        e.goto_node(ms[0])
        _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
        _ok('At %s |G|=%d RW=%d' % (ms[0], len(e.objects), e.rw_count()))
    elif not ms: _err('No match.')
    else: _warn('Ambiguous: %s' % ', '.join(ms))

@cli.command('undo')
def undo():
    """Go back to parent node."""
    e = _engine()
    if not e.current_node: _err('No node.'); return
    ps = e.dag.parents(e.current_node)
    if not ps: _warn('At root.'); return
    e.goto_node(ps[0])
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('Back to %s RW=%d' % (ps[0], e.rw_count()))

@cli.command('dag')
def dag():
    """List all DAG nodes."""
    e = _engine()
    if not e.dag.nodes: _info('Empty.'); return
    _bold('DAG: %d nodes' % len(e.dag.nodes))
    for h, n in sorted(e.dag.nodes.items(), key=lambda x: x[1].ts):
        m = '→ ' if h == e.current_node else '  '
        rw = sum(1 for v in n.incidence.values() if v == 'RW')
        ni = sum(len(v) for v in n.impls.values())
        click.echo('  %s%s |G|=%d |M|=%d RW=%d impl=%d %s' % (m, cc(h, C.CN if h == e.current_node else C.D), len(n.objects), len(n.attributes), rw, ni, n.ts))

@cli.command('path')
def path():
    """Show path from root to current node."""
    e = _engine()
    if not e.current_node: _info('No node.'); return
    p = e.dag.path_to_root(e.current_node)
    for i, h in enumerate(p):
        n = e.dag.nodes[h]; m = '→ ' if h == e.current_node else '  '
        desc = ''
        if i > 0:
            for pr, c, d in e.dag.edges:
                if pr == p[i - 1] and c == h: desc = d; break
        rw = sum(1 for v in n.incidence.values() if v == 'RW')
        click.echo('  %s%s RW=%d  %s' % (m, cc(h, C.CN), rw, cc(desc, C.D)))

@cli.command('diff')
@click.argument('a')
@click.argument('b')
def diff(a, b):
    """Compare two DAG nodes."""
    e = _engine()
    ma = [h for h in e.dag.nodes if h.startswith(a)]
    mb = [h for h in e.dag.nodes if h.startswith(b)]
    if len(ma) != 1 or len(mb) != 1: _err('Need exact hash match.'); return
    na, nb = e.dag.nodes[ma[0]], e.dag.nodes[mb[0]]
    ia = {'%s|%s' % (o, a2): v for (o, a2), v in na.incidence.items()}
    ib = {'%s|%s' % (o, a2): v for (o, a2), v in nb.incidence.items()}
    changes = [(k, ia.get(k, '-'), ib.get(k, '-')) for k in sorted(set(list(ia) + list(ib))) if ia.get(k, '-') != ib.get(k, '-')]
    bg = set(nb.objects) - set(na.objects); ag = set(na.objects) - set(nb.objects)
    if bg: click.echo('  +G: %s' % ', '.join(nb.objects[o]['name'] for o in bg if o in nb.objects))
    if ag: click.echo('  -G: %s' % ', '.join(na.objects[o]['name'] for o in ag if o in na.objects))
    rwa = sum(1 for v in na.incidence.values() if v == 'RW')
    rwb = sum(1 for v in nb.incidence.values() if v == 'RW')
    if rwa != rwb: click.echo('  RW: %d→%d' % (rwa, rwb))
    if changes:
        _warn('%d I changes:' % len(changes))
        for k, va, vb in changes[:15]: click.echo('    %s: %s→%s' % (k, va, vb))
        if len(changes) > 15: click.echo('    +%d' % (len(changes) - 15))
    if not changes and not ag and not bg: _info('Identical.')


# ── Seed ──────────────────────────────────────────────────────────────────────

@click.group('seed')
def seed_group():
    """Seed management commands."""
    pass

@seed_group.command('show')
def seed_show():
    """Show current seed summary."""
    e = _engine()
    if e.seed.has_content():
        _cyan('Seed: %s' % e.seed.domain); click.echo(e.seed.summary())
    else: _info('No seed.')

@seed_group.command('load')
@click.argument('filepath')
def seed_load(filepath):
    """Load seed from file."""
    e = _engine()
    d = json.loads(load_file(filepath))
    e.seed.from_dict(d); e.seed_chain = SeedChain([e.seed])
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('Loaded seed: %s' % e.seed.domain); click.echo(e.seed.summary())

@seed_group.command('save')
@click.argument('filepath')
def seed_save(filepath):
    """Save seed to file."""
    e = _engine()
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(e.seed.to_dict(), f, ensure_ascii=False, indent=2)
    _ok('Saved.')

@seed_group.command('tree')
def seed_tree():
    """Show object and attribute trees."""
    e = _engine()
    for t, lbl in [(e.seed.obj_tree, 'Obj'), (e.seed.attr_tree, 'Attr')]:
        if t:
            click.echo(cc('  %s tree:' % lbl, C.CN))
            for k, v in sorted(t.items()): click.echo('    %s → %s' % (cc(k, C.Y), ', '.join(v)))

@seed_group.command('conv')
def seed_conv():
    """Show seed conventions."""
    e = _engine()
    if e.seed.conventions:
        for c in e.seed.conventions: click.echo('  - %s' % c)
    else: _info('None.')

@seed_group.command('set')
@click.argument('kind')  # obj | attr
@click.argument('parent')
@click.argument('children', nargs=-1)
def seed_set(kind, parent, children):
    """Add split rule: seed set obj|attr <parent> <child1> <child2>..."""
    e = _engine()
    if not children: _err('seed set obj|attr <parent> <child1> <child2>...'); return
    if kind in ('obj', 'object'): e.seed.obj_tree[parent] = list(children)
    elif kind in ('attr', 'attribute'): e.seed.attr_tree[parent] = list(children)
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('%s → %s' % (parent, ', '.join(children)))

cli.add_command(seed_group)


# ── Resolve ───────────────────────────────────────────────────────────────────

@cli.command('resolve')
@click.argument('kind')  # obj | attr
@click.argument('id')
def resolve(kind, id):
    """Split an object or attribute into children (via seed or LLM)."""
    e = _engine()
    llm = LLM()
    col = e.objects if kind == 'obj' else e.attributes
    if id not in col: _err('Not found: %s' % id); return
    item = col[id]
    ch_list = e.seed_chain.suggest_split(item['name'], item.get('desc', ''), kind)
    if ch_list:
        _cyan('Seed: %s → %s' % (item['name'], ', '.join(c['name'] for c in ch_list)))
    else:
        if not llm.ok: _err('LLM not available.'); return
        _info('Asking LLM...')
        vocab = (e.seed.obj_vocab if kind == 'obj' else e.seed.attr_vocab) or None
        r = llm.ask_expansion(item['name'], item.get('desc', ''), kind.replace('obj', 'object'), vocab)
        d, err = extract_json(r)
        if not d or 'expansions' not in d: _err('Failed: %s' % (err or r[:200])); return
        ch_list = d['expansions']
        _cyan('LLM: %s → %s' % (item['name'], ', '.join(c['name'] for c in ch_list)))
    _info('Proceed? Edit or confirm...')
    new_ids = e.resolve(id, kind, ch_list, llm)
    e.compute()
    nid = e.commit('resolve %s %s' % (kind, item['name']))
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _cyan('New IDs: %s' % ', '.join('%s=%s' % (nid2, e.attributes.get(nid2, e.objects.get(nid2, {})).get('name', '?')) for nid2 in new_ids))
    _ok('Done. RW=%d |G|=%d |M|=%d node=%s' % (e.rw_count(), len(e.objects), len(e.attributes), nid))

@cli.command('evolve')
@click.argument('n', default=1)
@click.option('--all', 'is_all', is_flag=True, help='Evolve all RW cells')
def evolve(n, is_all):
    """Automatically evolve (split) RW cells. Default 1 step, or --all."""
    e = _engine()
    llm = LLM()
    if not e.concepts: e.compute()
    rw = e.rw_count()
    if rw == 0: _ok('RW=0'); return
    mx = rw * 3 if is_all else n
    init_rw = rw
    for step in range(1, mx + 1):
        cells = e.rw_cells()
        if not cells: _ok('RW=0!'); break
        obj_rw = {}
        for o, a in cells: obj_rw[o] = obj_rw.get(o, 0) + 1
        worst = max(obj_rw, key=obj_rw.get); oname = e.objects[worst]['name']
        ch = e.seed_chain.suggest_split(oname, e.objects[worst].get('desc', ''), 'obj')
        if ch:
            _cyan('[%d] %s → %s (seed)' % (step, oname, ', '.join(c['name'] for c in ch)))
        else:
            _info('[%d] %s (LLM)...' % (step, oname))
            vocab = e.seed.obj_vocab or None
            r = llm.ask_expansion(oname, e.objects[worst].get('desc', ''), 'object', vocab)
            d, _ = extract_json(r)
            if not d or 'expansions' not in d: _err('Failed'); break
            ch = d['expansions']
            _cyan('    → %s' % ', '.join(c['name'] for c in ch))
        e.resolve(worst, 'obj', ch, llm); e.compute()
        new_rw = e.rw_count()
        _ok('    RW: %d→%d |G|=%d' % (rw, new_rw, len(e.objects))) if new_rw < rw else _warn('    RW: %d→%d |G|=%d' % (rw, new_rw, len(e.objects)))
        rw = new_rw
    nid = e.commit('evolve %d steps RW %d→%d' % (step, init_rw, e.rw_count()))
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('RW %d→%d  node=%s' % (init_rw, e.rw_count(), nid))


# ── Impl & Verify ─────────────────────────────────────────────────────────────

@click.group('impl')
def impl_group():
    """Implementation commands."""
    pass

@impl_group.command('gen')
@click.argument('module')
@click.argument('comment', default='')
def impl_gen(module, comment):
    """Generate implementation for a module via LLM."""
    e = _engine()
    llm = LLM()
    if not llm.ok: _err('LLM not available. Set OPENROUTER_API_KEY.'); return
    oid = None
    for o in e.objects:
        if e.objects[o]['name'] == module or o == module: oid = o; break
    if not oid: _err('Not found: %s' % module); return
    ob = e.objects[oid]
    framework_excerpt = codegen.generate_impl_context(e, oid)
    contract_code = codegen.generate_contract_code(e, oid)
    up = []; dn = []
    for aid in sorted(e.attributes):
        v = e.incidence.get((oid, aid), 'RW'); an = e.attributes[aid]['name']
        if v in ('R', 'RW'):
            ws = [e.objects[o]['name'] for o in e.objects if o != oid and e.incidence.get((o, aid), 'RW') in ('W', 'RW')]
            if ws: up.append('%s ← %s' % (an, ', '.join(ws)))
        if v in ('W', 'RW'):
            rs = [e.objects[o]['name'] for o in e.objects if o != oid and e.incidence.get((o, aid), 'RW') == 'R']
            if rs: dn.append('%s → %s' % (an, ', '.join(rs)))
    _info('Generating impl for %s...' % ob['name'])
    code = llm.build_module(ob['name'], ob.get('desc', ''), contract_code, framework_excerpt,
                            e.get_all_conventions(), '\n'.join(up), '\n'.join(dn), e.impls.get(ob['name'], []))
    if code.strip().startswith('```'):
        ls = code.strip().split('\n')
        if ls[0].startswith('```'): ls = ls[1:]
        if ls and ls[-1].startswith('```'): ls = ls[:-1]
        code = '\n'.join(ls)
    e.impls.setdefault(ob['name'], []).append({'code': code, 'comment': comment, 'ts': time.strftime('%H:%M:%S')})
    e._mark_dirty()
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('impl #%d (%d chars)' % (len(e.impls[ob['name']]) - 1, len(code)))
    click.echo(code[:400] + (('\n  ...(%d more)' % (len(code) - 400)) if len(code) > 400 else ''))

@impl_group.command('list')
@click.argument('module', required=False)
def impl_list(module):
    """List all impls, or show impls for a specific module."""
    e = _engine()
    if module:
        for i, imp in enumerate(e.impls.get(module, [])):
            click.echo('  #%d %s %dch  %s' % (i, imp.get('ts', ''), len(imp.get('code', '')), cc(imp.get('comment', ''), C.D)))
    else:
        if not e.impls: _info('No impls.')
        for m, imps in sorted(e.impls.items()): click.echo('  %s: %d impl(s)' % (cc(m, C.CN), len(imps)))

@impl_group.command('show')
@click.argument('module')
@click.argument('n', type=int)
def impl_show(module, n):
    """Show impl code for module at index N."""
    e = _engine()
    imps = e.impls.get(module, [])
    if 0 <= n < len(imps):
        click.echo(imps[n].get('code', ''))
        _info('// %s' % imps[n].get('comment', ''))
    else: _err('No impl #%d' % n)

cli.add_command(impl_group)

@cli.command('ready')
def ready():
    """Show implementation coverage."""
    e = _engine()
    status = [(e.objects[oid]['name'], len(e.impls.get(e.objects[oid]['name'], []))) for oid in sorted(e.objects)]
    has = sum(1 for _, n in status if n > 0); total = len(status)
    _ok('Impl coverage: %d/%d modules' % (has, total)) if has == total else _warn('Impl coverage: %d/%d modules' % (has, total))
    for on, n in status:
        if n > 0: click.echo('  %s %s (%d impl%s)' % (cc('✓', C.G), on, n, 's' if n > 1 else ''))
        else: click.echo('  %s %s' % (cc('✗', C.R), on))

@cli.command('verify')
def verify_cmd():
    """Cross-validate all impls against K contracts."""
    e = _engine()
    _info('Verifying K + impls...')
    issues = verify.verify_all(e)
    verify.print_issues(issues)

@cli.command('assemble')
@click.argument('output', default='assembled')
def assemble(output):
    """Assemble K + framework + impls into runnable output.

    LLM decides output format (single HTML or multi-file directory).
    Output name format: {output}_{k_hash}.html or {output}_{k_hash}/
    """
    e = _engine()
    if not e.concepts: e.compute()
    issues = verify.verify_all(e)
    errors = [i for i in issues if i.severity == 'error']
    if errors:
        _err('%d error(s) found. Fix before assemble:' % len(errors))
        for i in errors: _err('  ✗ %s' % i)
        if not click.confirm('Assemble anyway?'): return

    # Compute hash from K content
    kh = k_hash(e.objects, e.attributes, e.incidence, e.schemas)

    # Ask LLM which format to use
    llm = LLM()
    spec = e.export_spec()
    if llm.ok:
        _info('Asking LLM for output format...')
        fmt = llm.decide_output_format(spec)
        _info('LLM chose: %s' % fmt)
    else:
        fmt = 'single'
        _warn('LLM not available, using single.')

    if fmt == 'multi':
        out_dir = '%s_%s' % (output.rstrip('/'), kh)
        _info('Assembling to directory: %s/' % out_dir)
        out_dir, asm_issues = codegen.assemble_dir(e, out_dir)
        _ok('%s/ (%d modules)' % (out_dir, len(e.objects)))
        for iss in asm_issues: _warn('! %s' % iss)
    else:
        out_file = '%s_%s.html' % (output.rstrip('/'), kh)
        html, asm_issues = codegen.assemble_html(e)
        with open(out_file, 'w', encoding='utf-8') as f: f.write(html)
        _ok('%s (%d chars)' % (out_file, len(html)))
        for iss in asm_issues: _warn('! %s' % iss)
        if not asm_issues: _ok('All %d modules assembled.' % len(e.objects))


# ── LLM ───────────────────────────────────────────────────────────────────────

@click.group('llm')
def llm_group():
    """LLM commands."""
    pass

@llm_group.command('analyze')
@click.argument('filepath')
def llm_analyze(filepath):
    """Extract K from a spec file using LLM."""
    e = _engine(); llm = LLM()
    if not llm.ok: _err('LLM not available. Set OPENROUTER_API_KEY.'); return
    try: content = load_file(filepath)
    except Exception as ex: _err(str(ex)); return
    _info('Analyzing with %s...' % OPENROUTER_MODEL)
    r = llm.extract_gm(content)
    if llm.is_error(r): _err('LLM error: %s' % r); return
    d1, err = extract_json(r)
    if not d1: _err('Fail: %s' % err); click.echo(r[:500]); return
    e._batch = True
    for obj in d1.get('objects', []):
        oid = obj.get('id', '')
        if oid: e.add_obj(oid, obj.get('name', oid), obj.get('desc', '')); click.echo('    +G %s %s' % (oid, obj.get('name', '')))
    for at in d1.get('attributes', []):
        aid = at.get('id', '')
        if aid: e.add_attr(aid, at.get('name', aid), at.get('desc', '')); click.echo('    +M %s %s' % (aid, at.get('name', '')))
    aids = sorted(e.attributes)
    for key, val in d1.get('incidence', {}).items():
        if isinstance(val, str) and key in e.objects:
            for i, cell in enumerate(c.strip().upper() for c in val.split(',')):
                if i < len(aids):
                    cv = cell
                    if cv in ('1', 'YES'): cv = 'RW'
                    if cv in VALID_I:
                        try: e.set_i(key, aids[i], cv)
                        except: pass
    e._batch = False
    e.compute(); nid = e.commit('llm analyze')
    _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    _ok('K: |G|=%d |M|=%d RW=%d |B|=%d  node=%s' % (len(e.objects), len(e.attributes), e.rw_count(), len(e.concepts), nid))
    for c in e.check_consistency(): _warn(c)

@llm_group.command('chat')
@click.argument('message')
def llm_chat(message):
    """Chat with LLM."""
    llm = LLM()
    if not llm.ok: _err('LLM not available. Set OPENROUTER_API_KEY.'); return
    click.echo('  ' + llm.ask('KonceptOS assistant.', message).replace('\n', '\n  '))

cli.add_command(llm_group)


# ── Build ─────────────────────────────────────────────────────────────────────

@cli.command('build')
@click.argument('output', default='build_output.html')
@click.option('--auto-test/--no-auto-test', default=True, help='Run Selenium tests after build')
@click.option('--max-iter', default=3, help='Max regeneration attempts')
@click.option('--test-hooks', default='selenium_test_hooks.py', help='Test hooks filename')
def build(output, auto_test, max_iter, test_hooks):
    """Full build with optional Selenium auto-verification loop."""
    e = _engine(); llm = LLM()
    if not llm.ok: _err('LLM not available. Set OPENROUTER_API_KEY.'); return
    if not e.concepts: e.compute()

    bounds = e.interface_boundaries()
    spec = e.export_spec(); conv = e.get_all_conventions()

    for i in range(max_iter):
        _info(f'Building (attempt {i+1}/{max_iter})...')

        if i == 0:
            # First attempt - use full build with hooks
            html, test_hooks_content = llm.build_full_with_hooks(spec, conv, bounds)
        else:
            # Subsequent attempts - incorporate feedback
            _info('Requesting regeneration with corrections...')
            correction = llm.analyze_errors(spec, conv, bounds, last_feedback)
            html, test_hooks_content = llm.build_full_with_hooks(spec, conv + f"\n\nCORRECTIONS:\n{correction}", bounds)

        # Parse code blocks if present
        if html.strip().startswith('```'):
            ls = html.strip().split('\n')
            if ls[0].startswith('```'): ls = ls[1:]
            if ls and ls[-1].startswith('```'): ls = ls[:-1]
            html = '\n'.join(ls)

        # Write output files
        with open(output, 'w', encoding='utf-8') as f: f.write(html)
        if test_hooks_content:
            with open(test_hooks, 'w', encoding='utf-8') as f: f.write(test_hooks_content)

        if not auto_test:
            _ok(f'{output} written ({len(html)} chars)'); break

        # Run Selenium tests
        _info('Running Selenium tests...')
        runner = SeleniumTestRunner(output, test_hooks)
        result = runner.run()

        if result.passed:
            _ok(f'{output} passed verification')
            break

        last_feedback = result.to_llm_feedback()
        _warn(f'Test failures: {last_feedback}')

        # Ask LLM if we should regenerate
        should_regen = llm.should_regenerate(spec, conv, bounds, last_feedback)
        if not should_regen:
            _info('LLM decided not to regenerate, keeping current output')
            break

        if i < max_iter - 1:
            _info('Regenerating based on feedback...')

    _ok('%s (%d chars)' % (output, len(html)))


# ── Files ─────────────────────────────────────────────────────────────────────

@cli.command('save')
@click.argument('filepath')
def save(filepath):
    """Save DAG to file."""
    e = _engine()
    if e.dirty: e.compute(); e.commit('auto-save')
    e.save_dag(filepath)
    _ok('Saved: %d nodes' % len(e.dag.nodes))

@cli.command('open')
@click.argument('filepath')
def open_dag(filepath):
    """Open DAG from file."""
    e = _engine()
    try:
        with open(filepath, 'r') as f: d = json.load(f)
        if 'dag' in d: e.load_dag(filepath); _ok('DAG: %d nodes' % len(e.dag.nodes))
        else: e.load_v09(d); _ok('v0.9 converted.')
        _ensure_dir(); e.save_workspace(WORKSPACE_DIR)
    except Exception as ex: _err(str(ex))

@cli.command('export')
@click.argument('filepath')
def export_md(filepath):
    """Export K to Markdown spec file."""
    e = _engine()
    if not e.concepts: e.compute()
    e.export_spec(filepath)
    _ok(filepath)

@cli.command('compute')
def compute():
    """Recompute FCA concept lattice."""
    e = _engine()
    e.compute()
    _ok('|B|=%d' % len(e.concepts))


# ── main ──────────────────────────────────────────────────────────────────────

@click.command('help')
def help_cmd():
    """Show this help message."""
    click.echo(cli.get_help(None))

def main():
    import sys
    # Handle bare 'help' command → show help
    if len(sys.argv) == 2 and sys.argv[1] == 'help':
        sys.argv[1] = '--help'
    # Handle legacy --load flag
    if '--load' in sys.argv:
        idx = sys.argv.index('--load')
        if idx + 1 < len(sys.argv):
            fp = sys.argv[idx + 1]
            e = _engine()
            try:
                import json as j
                with open(fp, 'r') as f: d = j.load(f)
                if 'dag' in d:
                    e.load_dag(fp)
                    click.echo(cc('  Loaded %s' % fp, C.G))
                else:
                    e.load_v09(d)
                    click.echo(cc('  v0.9 converted.', C.G))
                e.save_workspace(WORKSPACE_DIR)
            except Exception as ex:
                click.echo(cc('  %s' % ex, C.R))
            sys.argv = [sys.argv[0]] + sys.argv[idx + 2:]
            if not sys.argv[1:]:
                return
        else:
            sys.argv = [x for x in sys.argv if x != '--load']
    cli()

if __name__ == '__main__':
    main()
