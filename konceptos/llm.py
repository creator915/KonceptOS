"""KonceptOS v2.1 — LLM: prompt templates and API calls."""
import json,os
from .util import VALID_I, extract_json, cc, C

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY","")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL","anthropic/claude-opus-4.6")
OPENROUTER_URL = os.environ.get("OPENROUTER_URL","https://openrouter.ai/api/v1/chat/completions")

class LLM:
    def __init__(self):
        self.ok=False
        try: import urllib.request; self.ok=bool(OPENROUTER_API_KEY)
        except: pass

    def ask(self,system,user,max_tokens=128000):
        import urllib.request,urllib.error
        body=json.dumps({"model":OPENROUTER_MODEL,"max_tokens":max_tokens,
            "messages":[{"role":"system","content":system},{"role":"user","content":user}]}).encode()
        req=urllib.request.Request(OPENROUTER_URL,data=body,headers={
            "Content-Type":"application/json","Authorization":"Bearer "+OPENROUTER_API_KEY,
            "HTTP-Referer":"https://konceptos.dev","X-Title":"KonceptOS"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=600) as resp:
                d=json.loads(resp.read().decode());ch=d.get("choices",[])
                if not ch:
                    err=d.get("error",{})
                    if err: return "(API error: %s)"%err.get("message",str(err))
                    return "(empty response)"
                return ch[0]["message"]["content"]
        except urllib.error.HTTPError as e:
            try: detail=e.read().decode()[:500]
            except: detail=''
            return "(HTTP %d: %s)"%(e.code,detail)
        except Exception as e: return "(err: %s)"%str(e)

    def is_error(self,r):
        return r.startswith('(HTTP') or r.startswith('(err') or r.startswith('(API')

    # ── K₀ extraction ──
    def extract_gm(self,text):
        return self.ask(
            "You are extracting a KonceptOS formal context K = (G, M, I) from a requirements document.\n\n"
            "OBJECTS (G) = modules, systems, entities — things that DO something.\n"
            "  Examples: physics_engine, renderer, player_character, collision_detector\n\n"
            "ATTRIBUTES (M) = DATA CHANNELS — concrete data that one module WRITES and another READS.\n"
            "  CORRECT: position, velocity, score, freeze_state, input_keys, sprite, map_data\n"
            "  WRONG: collision detection, rendering, physics (PROCESSES, not data)\n"
            "  WRONG: interaction, mechanism, condition (ABSTRACTIONS, not storable data)\n"
            "  Test: can you write a TypeScript type for it? position: {x:number,y:number} → YES ✓\n"
            "  Aim for 8-16 data channels. Each should be a NOUN representing storable data.\n\n"
            "INCIDENCE (I): For EVERY (object, attribute) pair:\n"
            "  0 = not involved, R = reads/observes, W = controls/produces, RW = both or unsure\n"
            "  W means CONTROLS (reads old value + writes new value). Use 0 generously.\n\n"
            "Pure JSON:\n"
            '{"objects":[{"id":"F01","name":"...","desc":"..."},...],\n'
            '"attributes":[{"id":"A","name":"...","desc":"..."},...],\n'
            '"incidence":{"F01":"R,0,W,RW,...","F02":"...",...}}',text,32000)

    # ── Direction judgment ──
    def judge_batch(self,pairs,context=''):
        """Judge multiple (obj,attr) pairs in batched LLM calls.
        pairs: [(obj_name, obj_desc, attr_name, attr_desc), ...]
        Returns: {index: '0'|'R'|'W'|'RW'}
        """
        if not pairs: return {}
        CHUNK=50
        result={}
        for start in range(0,len(pairs),CHUNK):
            chunk=pairs[start:start+CHUNK]
            lines=[]
            for i,(on,od,an,ad) in enumerate(chunk):
                lines.append('%d. %s (%s) × %s (%s)'%(start+i,on,od[:60],an,ad[:60]))
            prompt=("For each (object, attribute) pair, determine the direction:\n"
                "0 = not involved, R = reads/observes, W = controls/produces, RW = both/unsure\n"
                "W means CONTROLS (reads old value + writes new value).\n"
                "Use 0 generously — most modules don't interact with most channels.\n\n")
            if context: prompt+=context+"\n\n"
            prompt+="Pairs:\n"+'\n'.join(lines)
            prompt+="\n\nPure JSON: {\"%d\":\"R\",\"%d\":\"0\",...}"%(start,start+1)
            r=self.ask("Answer with ONLY the JSON mapping index to direction (0/R/W/RW).",prompt,4000)
            d,_=extract_json(r)
            if d:
                for k,v in d.items():
                    try:
                        idx=int(k);val=v.strip().upper()
                        if val in VALID_I: result[idx]=val
                    except: pass
            if len(pairs)>CHUNK:
                print(cc('    batch %d-%d/%d'%(start,min(start+CHUNK,len(pairs)),len(pairs)),C.D))
        return result

    # ── Expansion suggestion ──
    def ask_expansion(self,name,desc,kind,vocab_hint):
        vhint=("\nSeed vocabulary for reference: %s"%', '.join(vocab_hint)) if vocab_hint else ""
        if kind in ('attribute','attr'):
            system=("In KonceptOS, an ATTRIBUTE is a DATA CHANNEL — concrete data that one module writes and another reads.\n"
                "CORRECT: position, velocity, score, freeze_state, input_keys, sprite\n"
                "WRONG: collision detection, rendering, gravity (PROCESSES, not data)\n\n"
                "Test: can you say 'module A writes X, module B reads X'? If not, X is a process.\n"
                "Test: can you write a TypeScript type? e.g. position: {x: number, y: number}\n\n"
                "'%s' compresses multiple distinct data channels.\n"
                "What concrete data objects are being read/written under this name?\n"
                "List 2-5 data channels (nouns, not verbs).%s\n\n"
                "Pure JSON: {\"expansions\":[{\"name\":\"...\",\"desc\":\"...\"},...]}"
            )%(name,vhint)
        else:
            system=("'%s' compresses multiple distinct modules.\n"
                "List 2-5 conceptually different sub-modules (NOT R/W splits).%s\n\n"
                "Pure JSON: {\"expansions\":[{\"name\":\"...\",\"desc\":\"...\"},...]}"
            )%(name,vhint)
        return self.ask(system,"Name: %s\nDesc: %s"%(name,desc),2000)

    # ── Schema suggestion ──
    def suggest_schemas(self,attrs_info,conventions=''):
        """attrs_info: [(attr_name, attr_desc, writers, readers), ...]"""
        lines=[]
        for name,desc,writers,readers in attrs_info:
            lines.append('%s: %s (written by: %s; read by: %s)'%(name,desc or '-',writers or 'none',readers or 'none'))
        prompt=("For each data channel, suggest a TypeScript type definition.\n"
            "Use simple types: number, boolean, string, arrays, objects.\n"
            "Keep types minimal.\n\n")
        if conventions: prompt+="Constraints:\n%s\n\n"%conventions
        prompt+="Data channels:\n"+'\n'.join(lines)
        prompt+='\n\nPure JSON: {"channel_name":"TypeScript type",...}'
        r=self.ask("Answer with ONLY the JSON.",prompt,4000)
        d,_=extract_json(r)
        return d if d else {}

    # ── Module implementation ──
    def build_module(self,module_name,module_desc,contract_code,framework_excerpt,conventions='',upstream='',downstream='',prev_impls=None):
        """Generate a single module implementation.
        contract_code: the actual TypeScript contract interface for this module
        framework_excerpt: ChannelStore interface + ModuleImpl type + relevant Channel types
        """
        p="== FRAMEWORK (you MUST use these types exactly) ==\n"
        p+=framework_excerpt+"\n\n"
        p+="== YOUR MODULE ==\n"
        p+="Name: %s\nDescription: %s\n\n"%( module_name, module_desc)
        p+="== YOUR CONTRACT (generated from K, do NOT modify) ==\n"
        p+=contract_code+"\n\n"
        if conventions: p+="== CONSTRAINTS ==\n%s\n\n"%conventions
        if upstream: p+="== UPSTREAM (who writes your read channels) ==\n%s\n\n"%upstream
        if downstream: p+="== DOWNSTREAM (who reads your write channels) ==\n%s\n\n"%downstream
        if prev_impls:
            p+="== PREVIOUS ATTEMPTS ==\n"
            for pi in prev_impls[-2:]: p+="---\n%s\n// %s\n"%(pi.get('code','')[:1500],pi.get('comment',''))
        system=("You are implementing a single module for a KonceptOS project.\n"
            "You MUST:\n"
            "1. Import from the framework using the EXACT types shown\n"
            "2. Implement the ModuleImpl interface with init(), update(), render() methods\n"
            "3. Only access channels listed in your contract via state.read()/state.write()\n"
            "4. Use plain JavaScript (no TypeScript syntax, no type annotations)\n"
            "5. Export default your module object\n\n"
            "Output ONLY the module code. No markdown fences. No explanations.")
        return self.ask(system,p,8000)

    # ── Full build (legacy) ──
    def build_full(self,spec,conventions):
        s="Generate a COMPLETE RUNNABLE single-file HTML+JS webapp.\nOutput ONLY HTML. No markdown fences."
        p=("=== CONSTRAINTS ===\n"+conventions+"\n\n" if conventions else "")+spec
        return self.ask(s,p)

    # ── Full build with test hooks ──
    def build_full_with_hooks(self, spec, conventions, interface_info):
        """Generate HTML+JS webapp AND test hooks for Selenium verification.
        interface_info: {'inputs': [...], 'outputs': [...], 'schemas': {...}}
        Returns: (html_content, test_hooks_python_script)
        """
        # 构建接口边界说明
        ib_lines = ["\n\n== INTERFACE BOUNDARIES =="]
        ib_lines.append("\n--- INPUTS (W/RW attributes - user provides these) ---")
        for inp in interface_info.get('inputs', []):
            ib_lines.append(f"  {inp['name']}: {inp['desc']} (writers: {', '.join(inp['writers'])})")

        ib_lines.append("\n--- OUTPUTS (R/RW attributes - expected results) ---")
        for out in interface_info.get('outputs', []):
            ib_lines.append(f"  {out['name']}: {out['desc']} (readers: {', '.join(out['readers'])})")

        ib_lines.append("\n--- TYPES ---")
        for attr_id, schema in interface_info.get('schemas', {}).items():
            ib_lines.append(f"  {attr_id}: {schema}")

        ib_text = '\n'.join(ib_lines)

        prompt = f"""Generate TWO outputs:

1. A COMPLETE RUNNABLE single-file HTML+JS webapp with Canvas
2. A Python test hooks file (selenium_test_hooks.py) for Selenium testing

The test hooks should define:
- TEST_INPUTS: list of (input_name, element_selector_or_id, test_value) tuples
- TEST_OUTPUTS: list of (output_name, element_selector_or_id, check_type) tuples
  check_type can be: 'exists', 'text_contains', 'canvas_has_content'
- CANVAS_CHECK_JS: JavaScript code to check canvas state
- EXPECTED_BEHAVIOR: description of what should happen when inputs are triggered

=== CONSTRAINTS ===
{conventions if conventions else '(none)'}

{ib_text}

=== SPEC ===
{spec}

Output format (use EXACT delimiters):
---HTML---
[complete HTML content here]
---TEST---
[Python test hooks content here]
"""
        r = self.ask("Generate HTML+TEST_HOOKS. Use EXACT ---HTML--- and ---TEST--- delimiters.", prompt, 48000)

        # 解析 HTML 和 TEST 部分
        html_content = r
        test_hooks = ""

        if '---HTML---' in r and '---TEST---' in r:
            parts = r.split('---HTML---')
            if len(parts) > 1:
                html_and_test = parts[1]
                if '---TEST---' in html_and_test:
                    html_content = html_and_test.split('---TEST---')[0].strip()
                    test_hooks = html_and_test.split('---TEST---')[1].strip()
                else:
                    html_content = html_and_test.strip()

        return html_content, test_hooks

    # ── LLM judgment: should regenerate? ──
    def should_regenerate(self, spec, conventions, interface_info, test_feedback):
        """让 LLM 判断测试失败是否严重到需要重新生成"""
        prompt = f"""Test failures detected:
{test_feedback}

Interface boundaries:
  Inputs: {[inp['name'] for inp in interface_info.get('inputs', [])]}
  Outputs: {[out['name'] for out in interface_info.get('outputs', [])]}

Should we regenerate the HTML based on this feedback? Consider:
- Are the failures critical (page doesn't load, major interaction broken)?
- Or minor (cosmetic, edge case)?

Respond with ONLY one word: yes or no"""
        r = self.ask("Decision: should we regenerate?", prompt, 1000)
        return 'yes' in r.lower()

    # ── LLM analyze errors and suggest fix prompt ──
    def analyze_errors(self, spec, conventions, interface_info, test_feedback):
        """让 LLM 分析错误并给出修正建议（返回给下一轮生成）"""
        prompt = f"""Analyze these test failures and suggest corrections for regeneration:

Test failures:
{test_feedback}

Interface boundaries:
  Inputs: {interface_info.get('inputs', [])}
  Outputs: {interface_info.get('outputs', [])}

Provide a brief (2-3 sentences) correction suggestion to guide the next regeneration.
Focus on WHAT is wrong and HOW to fix it. Do not regenerate the full HTML.
"""
        return self.ask("Provide correction suggestions.", prompt, 2000)

    # ── Output format decision ──
    def decide_output_format(self, spec):
        """Ask LLM whether to output single HTML or multi-file directory.
        Returns: 'single' or 'multi'
        """
        prompt = (
            "A KonceptOS project has the following spec (up to 2000 chars):\n"
            f"{spec[:2000]}\n\n"
            "Should this be built as:\n"
            "1. single — a single self-contained HTML file (simpler, easier to share, less maintainable)\n"
            "2. multi — a multi-file project with separate HTML/JS/CSS (better for complex projects, easier to maintain)\n\n"
            "Consider: number of modules, project complexity, need for maintainability.\n"
            "Respond with ONLY the word: single\n"
            "or: multi"
        )
        r = self.ask(
            "Answer with ONLY 'single' or 'multi'.",
            prompt, 4000
        )
        r = r.strip().lower()
        if 'multi' in r:
            return 'multi'
        return 'single'
