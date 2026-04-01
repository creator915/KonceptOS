"""KonceptOS v2.1 — Verify: impl cross-validation and K feedback.

This module implements the CODE → K feedback loop:
  1. Scan impl code for contract violations (accessing unauthorized channels)
  2. Detect multi-writer conflicts
  3. Detect inconsistent method signatures
  4. Detect duplicate channel initialization
  5. Suggest K modifications based on findings
"""
import re
from .util import cc, C

class Issue:
    """A detected issue in impl code or K structure."""
    def __init__(self, severity, module, message, suggestion=None):
        self.severity = severity  # 'error', 'warning', 'info'
        self.module = module      # module name or None for global
        self.message = message
        self.suggestion = suggestion  # suggested K change or None
    def __str__(self):
        s = '[%s] %s: %s' % (self.severity.upper(), self.module or 'GLOBAL', self.message)
        if self.suggestion: s += '\n  → %s' % self.suggestion
        return s


def verify_all(engine):
    """Run all verification checks. Returns list of Issues."""
    issues = []
    issues.extend(check_multi_writers(engine))
    issues.extend(check_contract_violations(engine))
    issues.extend(check_init_conflicts(engine))
    issues.extend(check_method_signatures(engine))
    return issues


def check_multi_writers(engine):
    """Detect channels with multiple writers — likely needs per-entity schema."""
    issues = []
    for aid in engine.attributes:
        ws = [o for o in engine.objects if engine.incidence.get((o, aid), 'RW') == 'W']
        if len(ws) > 1:
            an = engine.attributes[aid]['name']
            names = [engine.objects[o]['name'] for o in ws]
            sch = engine.schemas.get(aid, '')
            if 'Record<' in sch or 'Map<' in sch:
                # Already per-entity, just info
                issues.append(Issue('info', None,
                    '"%s" has %d writers (%s) with per-entity schema — OK' % (an, len(ws), ', '.join(names))))
            else:
                issues.append(Issue('error', None,
                    '"%s" has %d writers: %s' % (an, len(ws), ', '.join(names)),
                    'Change schema to Record<entityId, ...> or split into per-entity channels'))
    return issues


def check_contract_violations(engine):
    """Scan impl code for read/write of channels not in contract."""
    issues = []
    for oid in engine.objects:
        on = engine.objects[oid]['name']
        mod_impls = engine.impls.get(on, [])
        if not mod_impls: continue
        code = mod_impls[-1].get('code', '')
        contract = engine.contract_for(oid)
        allowed_read = set(contract['reads'] + contract['writes'] + contract.get('readwrites', []))
        allowed_write = set(contract['writes'] + contract.get('readwrites', []))
        
        # Find all state.read('xxx') calls
        for m in re.finditer(r"state\.read\s*\(\s*['\"]([^'\"]+)['\"]", code):
            ch = m.group(1)
            if ch not in allowed_read:
                issues.append(Issue('error', on,
                    "reads '%s' but contract only allows reads=[%s]" % (ch, ','.join(allowed_read)),
                    "Either add R for %s→%s in K, or change impl" % (on, ch)))
        
        # Find all state.write('xxx') calls
        for m in re.finditer(r"state\.write\s*\(\s*['\"]([^'\"]+)['\"]", code):
            ch = m.group(1)
            if ch not in allowed_write:
                issues.append(Issue('error', on,
                    "writes '%s' but contract only allows writes=[%s]" % (ch, ','.join(allowed_write)),
                    "Either add W for %s→%s in K, or change impl" % (on, ch)))
    return issues


def check_init_conflicts(engine):
    """Detect multiple modules initializing the same channel."""
    issues = []
    init_writers = {}  # {channel_name: [module_names]}
    
    for oid in engine.objects:
        on = engine.objects[oid]['name']
        mod_impls = engine.impls.get(on, [])
        if not mod_impls: continue
        code = mod_impls[-1].get('code', '')
        
        # Look for state.write in init-like functions
        # Heuristic: find writes inside init/setup/initialize methods
        in_init = False
        brace_depth = 0
        for line in code.split('\n'):
            stripped = line.strip()
            if re.match(r'(init|setup|initialize|onInit)\s*[\(\{]', stripped):
                in_init = True; brace_depth = 0
            if in_init:
                brace_depth += stripped.count('{') - stripped.count('}')
                if brace_depth < 0: in_init = False
                for m in re.finditer(r"state\.write\s*\(\s*['\"]([^'\"]+)['\"]", line):
                    ch = m.group(1)
                    init_writers.setdefault(ch, []).append(on)
    
    for ch, modules in init_writers.items():
        if len(modules) > 1:
            issues.append(Issue('warning', None,
                "Channel '%s' initialized by %d modules: %s — last one overwrites others" % (
                    ch, len(modules), ', '.join(modules)),
                "Designate one module as the initializer (usually the W module)"))
    return issues


def check_method_signatures(engine):
    """Detect inconsistent init/update/render method names across impls."""
    issues = []
    method_variants = {}  # {module_name: [method_names_found]}
    
    expected = {'init', 'update', 'render'}
    alternatives = {
        'init': ['setup', 'initialize', 'onInit', 'start'],
        'update': ['tick', 'onUpdate', 'step', 'process'],
        'render': ['draw', 'onRender', 'display'],
    }
    alt_to_expected = {}
    for exp, alts in alternatives.items():
        for a in alts: alt_to_expected[a] = exp
    
    for oid in engine.objects:
        on = engine.objects[oid]['name']
        mod_impls = engine.impls.get(on, [])
        if not mod_impls: continue
        code = mod_impls[-1].get('code', '')
        
        found = set()
        for m in re.finditer(r'(?:^|\s)(\w+)\s*[\(\{:]', code):
            name = m.group(1)
            if name in expected:
                found.add(name)
            elif name in alt_to_expected:
                found.add(name)
                issues.append(Issue('warning', on,
                    "Uses '%s()' instead of standard '%s()'" % (name, alt_to_expected[name]),
                    "Rename to '%s()' for framework compatibility" % alt_to_expected[name]))
        
        method_variants[on] = found
    
    return issues


def print_issues(issues):
    """Pretty-print issues to console."""
    if not issues:
        print(cc('  ✓ No issues found.', C.G))
        return
    
    errors = [i for i in issues if i.severity == 'error']
    warnings = [i for i in issues if i.severity == 'warning']
    infos = [i for i in issues if i.severity == 'info']
    
    if errors:
        print(cc('  ERRORS (%d):' % len(errors), C.R, C.B))
        for i in errors:
            print(cc('    ✗ %s' % i, C.R))
    if warnings:
        print(cc('  WARNINGS (%d):' % len(warnings), C.Y))
        for i in warnings:
            print(cc('    ! %s' % i, C.Y))
    if infos:
        print(cc('  INFO (%d):' % len(infos), C.D))
        for i in infos:
            print(cc('    · %s' % i, C.D))
    
    print()
    total = len(errors) + len(warnings)
    if errors:
        print(cc('  %d error(s) must be fixed before assemble.' % len(errors), C.R))
    elif warnings:
        print(cc('  %d warning(s). Assemble will proceed but output may have issues.' % len(warnings), C.Y))
