"""KonceptOS v2.1 — CodeGen: K → framework code → impl prompts → assembly.

This module is the BRIDGE between K structure and runnable code.
It generates:
  1. framework.js  — Channels types + ChannelStore runtime + ModuleImpl interface
  2. Per-module impl prompts with framework context injected
  3. Assembled HTML from framework + impls in topological order
"""
import re
from .util import safe_name, safe_contract_name

# ═══ Framework Generation ═══

def generate_framework_js(engine):
    """Generate framework.js from K. This is the SINGLE SOURCE OF TRUTH
    for channel types, contracts, and module interface.
    
    Every impl MUST reference this. Assemble includes it verbatim.
    """
    lines=[
        '// ═══ KonceptOS Framework (generated from K node: %s) ═══'%(engine.current_node or '?'),
        '// DO NOT EDIT — regenerated from K on every assemble',
        '',
        '// ── Channel Store Runtime ──',
        'const _channels = {};',
        'const state = {',
        '  read(ch) {',
        '    if (!(ch in _channels)) throw new Error("Channel not initialized: " + ch);',
        '    return _channels[ch];',
        '  },',
        '  write(ch, val) { _channels[ch] = val; },',
        '  has(ch) { return ch in _channels; }',
        '};',
        '',
    ]
    
    # ── Channel names as constants ──
    lines.append('// ── Channel Names ──')
    for aid in sorted(engine.attributes):
        an = engine.attributes[aid]['name']
        const_name = 'CH_' + safe_name(an).upper()
        lines.append("const %s = '%s';" % (const_name, an))
    lines.append('')
    
    # ── Channel schemas as JSDoc ──
    lines.append('// ── Channel Schemas ──')
    lines.append('// Each channel\'s expected data shape:')
    for aid in sorted(engine.attributes):
        an = engine.attributes[aid]['name']
        sch = engine.schemas.get(aid, 'any')
        lines.append('//   %s: %s' % (an, sch))
    lines.append('')
    
    # ── Contracts ──
    lines.append('// ── Module Contracts (from I matrix) ──')
    lines.append('// Each module can ONLY access the channels listed in its contract.')
    lines.append('const CONTRACTS = {')
    for oid in sorted(engine.objects):
        on = engine.objects[oid]['name']
        c = engine.contract_for(oid)
        lines.append("  '%s': { reads: %s, writes: %s }," % (
            on, _js_array(c['reads']), _js_array(c['writes'])))
    lines.append('};')
    lines.append('')
    
    # ── Tile encoding constants (from conventions) ──
    lines.append('// ── Tile Encoding (shared across all modules) ──')
    lines.append('const TILES = { EMPTY:0, WALL:1, LAVA:2, WATER:3, POISON:4,')
    lines.append('  RED_GEM:5, BLUE_GEM:6, FIRE_EXIT:7, WATER_EXIT:8, SWITCH:9 };')
    lines.append('')
    
    # ── Physics constants ──
    conv = engine.get_all_conventions()
    if conv:
        lines.append('// ── Conventions ──')
        for line in conv.strip().split('\n'):
            lines.append('// %s' % line)
        lines.append('')
    
    # ── ModuleImpl interface ──
    lines.append('// ── Module Interface ──')
    lines.append('// Every module MUST be: { name, init(state), update(state, dt), render(state, ctx) }')
    lines.append('// init: called once at level start. Write initial channel values.')
    lines.append('// update: called every frame. Read channels, compute, write channels.')
    lines.append('// render: called every frame after update. Read channels, draw to ctx.')
    lines.append('')
    
    # ── Channel initialization ──
    lines.append('// ── Channel Initialization ──')
    lines.append('function initChannels() {')
    for aid in sorted(engine.attributes):
        an = engine.attributes[aid]['name']
        sch = engine.schemas.get(aid, 'null')
        # Generate sensible defaults based on schema
        default = _default_for_schema(sch)
        lines.append("  _channels['%s'] = %s;" % (an, default))
    lines.append('}')
    lines.append('')
    
    return '\n'.join(lines)


def generate_impl_context(engine, oid):
    """Generate the framework excerpt that gets injected into an impl prompt.
    This ensures the LLM knows EXACTLY what interface to implement.
    """
    on = engine.objects[oid]['name']
    od = engine.objects[oid].get('desc', '')
    c = engine.contract_for(oid)
    
    lines = []
    lines.append('// ═══ FRAMEWORK CONTEXT (use these exactly) ═══')
    lines.append('')
    lines.append('// Channel store API:')
    lines.append('//   state.read(channelName)  → returns current value')
    lines.append('//   state.write(channelName, value)  → updates channel')
    lines.append('')
    
    # Show only relevant channel schemas
    lines.append('// Channels you can READ:')
    all_channels = c['reads'] + c['writes'] + c.get('readwrites', [])
    for ch in c['reads']:
        aid = _find_aid(engine, ch)
        sch = engine.schemas.get(aid, 'any') if aid else 'any'
        lines.append("//   '%s': %s" % (ch, sch))
    lines.append('// Channels you can READ + WRITE:')
    for ch in c['writes']:
        aid = _find_aid(engine, ch)
        sch = engine.schemas.get(aid, 'any') if aid else 'any'
        lines.append("//   '%s': %s" % (ch, sch))
    lines.append('')
    
    # Contract
    lines.append('// YOUR CONTRACT (do NOT access other channels):')
    lines.append("// reads: %s" % c['reads'])
    lines.append("// writes: %s" % c['writes'])
    lines.append('')
    
    # Required module shape
    lines.append('// YOUR MODULE MUST be this shape:')
    lines.append('const myModule = {')
    lines.append("  name: '%s'," % on)
    lines.append('  init(state) { /* called once, initialize your write channels */ },')
    lines.append('  update(state, dt) { /* called every frame */ },')
    lines.append('  render(state, ctx) { /* draw to canvas context */ }')
    lines.append('};')
    
    return '\n'.join(lines)


def generate_contract_code(engine, oid):
    """Generate the contract declaration for one module."""
    on = engine.objects[oid]['name']
    c = engine.contract_for(oid)
    lines = [
        "// Contract for '%s'" % on,
        "// reads: %s" % _js_array(c['reads']),
        "// writes: %s" % _js_array(c['writes']),
    ]
    if c.get('readwrites'):
        lines.append("// readwrites (pending): %s" % _js_array(c['readwrites']))
    return '\n'.join(lines)


def assemble_html(engine, impl_selection=None):
    """Assemble K + framework + impls → runnable single-file HTML.
    
    impl_selection: {module_name: impl_index} or None (use latest)
    Returns: (html_string, issues_list)
    """
    order, has_cycle = engine.topo_sort()
    issues = []
    
    # Generate framework
    framework = generate_framework_js(engine)
    
    # Collect impls
    impl_code_blocks = []
    missing = []
    for oid in order:
        on = engine.objects[oid]['name']
        mod_impls = engine.impls.get(on, [])
        if not mod_impls:
            missing.append(on)
            impl_code_blocks.append(
                '\n// ═══ %s — NO IMPL ═══\n'
                'const mod_%s = { name:"%s", init(){}, update(){}, render(){} };'
                % (on, safe_name(on), on))
            continue
        idx = (impl_selection or {}).get(on, -1)
        impl = mod_impls[idx] if 0 <= idx < len(mod_impls) else mod_impls[-1]
        code = impl.get('code', '')
        # Strip TypeScript / module syntax
        code = _strip_ts_syntax(code)
        impl_code_blocks.append(
            '\n// ═══ %s (impl #%d: %s) ═══\n%s'
            % (on, mod_impls.index(impl), impl.get('comment', ''), code))
    
    if missing:
        issues.append('Missing impls: %s' % ', '.join(missing))
    if has_cycle:
        issues.append('Dependency cycle detected. All modules included but order may be suboptimal.')
    
    # Game loop
    loop_lines = _build_game_loop_js(engine, order)

    # Bootstrap
    boot = [
        '\n// ═══ Bootstrap ═══',
        'const canvas = document.getElementById("c");',
        'const ctx = canvas.getContext("2d");',
        'gameInit();',
        'let lastTime = performance.now();',
        'function mainLoop(now) {',
        '  const dt = (now - lastTime) / 16.67; // normalize to ~60fps',
        '  lastTime = now;',
        '  gameUpdate(dt);',
        '  ctx.clearRect(0, 0, canvas.width, canvas.height);',
        '  gameRender(ctx);',
        '  requestAnimationFrame(mainLoop);',
        '}',
        'requestAnimationFrame(mainLoop);',
    ]
    
    # Assemble HTML
    html = '<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
    html += '<title>KonceptOS Assembly — %s</title>' % (engine.current_node or '?')
    html += '<style>body{margin:0;background:#111;display:flex;justify-content:center;align-items:center;height:100vh}'
    html += 'canvas{border:1px solid #333}</style>'
    html += '</head><body>\n'
    html += '<canvas id="c" width="800" height="600"></canvas>\n'
    html += '<script>\n'
    html += '// Assembled by KonceptOS v2.1\n'
    html += '// Node: %s | Modules: %d | Channels: %d\n\n' % (
        engine.current_node or '?', len(engine.objects), len(engine.attributes))
    html += framework + '\n'
    html += '\n'.join(impl_code_blocks) + '\n'
    html += '\n'.join(loop_lines) + '\n'
    html += '\n'.join(boot) + '\n'
    html += '</script></body></html>'
    
    return html, issues


# ═══ Helpers ═══

def _js_array(lst):
    return '[%s]' % ', '.join("'%s'" % x for x in lst)

def _find_aid(engine, channel_name):
    for aid in engine.attributes:
        if engine.attributes[aid]['name'] == channel_name:
            return aid
    return None

def _default_for_schema(schema):
    """Generate a JS default value from a TypeScript schema string."""
    s = schema.strip()
    if s in ('any', 'null', '-', ''): return 'null'
    if s == 'number': return '0'
    if s == 'boolean': return 'false'
    if s == 'string': return "''"
    if s.startswith('{'): return '{}'
    if s.startswith('['): return '[]'
    if 'Record<' in s: return '{}'
    if 'Set<' in s: return 'new Set()'
    if s.startswith("'"): return s.split("'")[1] if "'" in s else "''"
    return '{}'

def _strip_ts_syntax(code):
    """Remove TypeScript-specific syntax from impl code for browser compatibility."""
    lines = code.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        # Remove import statements
        if stripped.startswith('import ') and ' from ' in stripped: continue
        # Remove export default
        if stripped.startswith('export default '): 
            out.append(line.replace('export default ', '// exported: '))
            continue
        if stripped == 'export default': continue
        # Remove TypeScript type annotations (basic)
        line = re.sub(r':\s*(string|number|boolean|void|any|never)\b', '', line)
        line = re.sub(r':\s*\{[^}]*\}\s*(?=[,\)\{])', '', line)
        line = re.sub(r'<[A-Z]\w*(?:Contract|Type|State)>', '', line)
        line = re.sub(r' as \w+', '', line)
        line = re.sub(r'interface \w+ \{', '// interface {', line)
        # Remove module.exports
        if stripped.startswith('module.exports'): continue
        if stripped.startswith('return MODULE_IMPL'): continue
        out.append(line)
    return '\n'.join(out)


# ═══ Multi-File Assembly ═══

def generate_index_html(engine, module_names):
    """Generate index.html that references framework.js, style.css, and module files."""
    node_info = engine.current_node or '?'
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '  <meta charset="utf-8">',
        '  <title>KonceptOS — %s</title>' % node_info,
        '  <link rel="stylesheet" href="style.css">',
        '</head>',
        '<body>',
        '  <canvas id="c" width="800" height="600"></canvas>',
        '  <script src="framework.js"></script>',
    ]
    for mn in module_names:
        lines.append('  <script src="modules/%s.js"></script>' % safe_name(mn))
    boot = [
        '  <script>',
        '    const canvas = document.getElementById("c");',
        '    const ctx = canvas.getContext("2d");',
        '    gameInit();',
        '    let lastTime = performance.now();',
        '    function mainLoop(now) {',
        '      const dt = (now - lastTime) / 16.67;',
        '      lastTime = now;',
        '      gameUpdate(dt);',
        '      ctx.clearRect(0, 0, canvas.width, canvas.height);',
        '      gameRender(ctx);',
        '      requestAnimationFrame(mainLoop);',
        '    }',
        '    requestAnimationFrame(mainLoop);',
        '  </script>',
        '</body>',
        '</html>',
    ]
    lines.extend(boot)
    return '\n'.join(lines)


def generate_style_css(engine):
    """Generate style.css with basic layout."""
    return """/* KonceptOS Framework Styles */
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: #111;
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  overflow: hidden;
}

canvas {
  border: 1px solid #333;
  background: #000;
}

/* Channel debug panel (optional) */
#debug {
  position: fixed;
  top: 8px;
  left: 8px;
  color: #0f0;
  font-family: monospace;
  font-size: 11px;
  pointer-events: none;
  line-height: 1.4;
}
"""


def generate_module_js(engine, oid, impl):
    """Generate a .js file for one module from its impl.

    impl: dict with keys {code, comment, ts}
    Returns: string of JS code
    """
    on = engine.objects[oid]['name']
    sn = safe_name(on)
    code = impl.get('code', '')
    code = _strip_ts_syntax(code)
    header = (
        '// ═══ %s (impl #%d) ═══\n'
        '// %s\n\n'
    ) % (on, engine.impls.get(on, []).index(impl), impl.get('comment', ''))
    return header + code


def assemble_dir(engine, output_dir='./output', impl_selection=None):
    """Assemble K → multi-file project directory.

    Creates:
      output_dir/
        index.html
        framework.js
        style.css
        modules/
          ModuleA.js
          ModuleB.js

    Returns: (output_dir, issues_list)
    """
    import os

    order, has_cycle = engine.topo_sort()
    issues = []
    missing = []

    # Prepare modules directory
    modules_dir = os.path.join(output_dir, 'modules')
    os.makedirs(modules_dir, exist_ok=True)

    # Write framework.js
    framework = generate_framework_js(engine)
    game_loop = _build_game_loop_js(engine, order)
    with open(os.path.join(output_dir, 'framework.js'), 'w', encoding='utf-8') as f:
        f.write('// Assembled by KonceptOS v2.1 | Node: %s\n\n' % (engine.current_node or '?'))
        f.write(framework)
        f.write('\n\n')
        f.write(game_loop)

    # Write style.css
    with open(os.path.join(output_dir, 'style.css'), 'w', encoding='utf-8') as f:
        f.write(generate_style_css(engine))

    # Write module JS files
    module_names = []
    for oid in order:
        on = engine.objects[oid]['name']
        sn = safe_name(on)
        module_names.append(sn)
        mod_impls = engine.impls.get(on, [])
        if not mod_impls:
            missing.append(on)
            stub = (
                '// ═══ %s — NO IMPL ═══\n'
                'const mod_%s = { name:"%s", init(){}, update(){}, render(){} };\n'
            ) % (on, sn, on)
            with open(os.path.join(modules_dir, '%s.js' % sn), 'w', encoding='utf-8') as f:
                f.write(stub)
            continue
        idx = (impl_selection or {}).get(on, -1)
        impl = mod_impls[idx] if 0 <= idx < len(mod_impls) else mod_impls[-1]
        code = generate_module_js(engine, oid, impl)
        with open(os.path.join(modules_dir, '%s.js' % sn), 'w', encoding='utf-8') as f:
            f.write(code)

    # Write index.html
    html = generate_index_html(engine, module_names)
    with open(os.path.join(output_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)

    if missing:
        issues.append('Missing impls: %s' % ', '.join(missing))
    if has_cycle:
        issues.append('Dependency cycle detected. All modules included but order may be suboptimal.')

    return output_dir, issues


def _build_game_loop_js(engine, order):
    """Build the game loop JS string (shared between assemble_html and assemble_dir)."""
    loop_lines = ['// ═══ Game Loop (topological order) ═══']
    loop_lines.append('const ALL_MODULES = [')
    for oid in order:
        on = engine.objects[oid]['name']
        sn = safe_name(on)
        loop_lines.append(
            "  typeof mod_%s !== 'undefined' ? mod_%s : {name:'%s',init(){},update(){},render(){}},"
            % (sn, sn, on)
        )
    loop_lines.append('];')
    loop_lines.extend([
        '',
        'function gameInit() {',
        '  initChannels();',
        '  ALL_MODULES.forEach(m => { if(m.init) m.init(state); });',
        '}',
        '',
        'function gameUpdate(dt) {',
        '  ALL_MODULES.forEach(m => { if(m.update) m.update(state, dt); });',
        '}',
        '',
        'function gameRender(ctx) {',
        '  ALL_MODULES.forEach(m => { if(m.render) m.render(state, ctx); });',
        '}',
    ])
    return '\n'.join(loop_lines)
