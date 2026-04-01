"""KonceptOS v2.1 — CLI: REPL interface."""
import json,time
from .util import cc, C, extract_json, load_file, VALID_I, safe_name
from .engine import Engine
from .llm import LLM, OPENROUTER_MODEL
from .seed import JsonSeed, SeedChain
from . import codegen
from . import verify

HELP="""
  ═══════════════════════════════════════════════════
   KonceptOS v2.1
   K → K* by hypothesis refinement on immutable DAG
   I : G × M → {0, R, W, RW}  (all are hypotheses)
  ═══════════════════════════════════════════════════

  K editing:
    add obj <id> <n> [| desc]    add attr <id> <n> [| desc]
    set <obj> <attr> <0|R|W|RW>     row <obj> R,0,W,RW,...
    del obj|attr <id>
    schema <attr_id> <typedef>      schema auto [attr_id|all]
    convention [text]

  View:
    ctx    st    rw    flows    groups    lat    concept <n>
    order                  execution order
    conflicts              temporal conflicts
    ts                     TypeScript signatures
    framework              show generated framework.js

  DAG:
    commit [desc]    goto <hash>    undo    dag    path    diff <a> <b>

  Seed:
    seed    seed load <f>    seed save <f>    seed tree    seed conv

  Resolve:
    resolve obj|attr <id>    evolve [n|all]

  Impl & Verify:
    impl <module> [comment]    generate impl (with framework context)
    impls [module]             list impls
    impl show <module> <n>     show impl code
    ready                      impl coverage
    verify                     cross-validate all impls against K
    assemble [output.html]     K + framework + impls → runnable HTML

  LLM:
    llm analyze <file>    llm chat <msg>

  Build:
    build [output.html]   full build (legacy, one-shot LLM)

  Files:
    save <f>    open <f>    export <f.md>    compute    help    quit
"""

def show_ctx(e):
    if not e.objects or not e.attributes: print(cc('  Empty.',C.D));return
    oids=sorted(e.objects);aids=sorted(e.attributes)
    nw=max(18,max(len(e.objects[o]['name']) for o in oids)+6)
    hdr=' '*nw
    for a in aids: hdr+=cc(e.attributes[a]['name'][:5].center(6),C.CN)
    print(cc('  +'+ '-'*(nw+len(aids)*6)+'+',C.D))
    print('  |'+hdr+'|');print(cc('  +'+ '-'*(nw+len(aids)*6)+'+',C.D))
    for o in oids:
        ob=e.objects[o];lbl=' %s %s'%(cc(o,C.Y),ob['name']);vl=1+len(o)+1+len(ob['name'])
        row=lbl+' '*max(0,nw-vl)
        for a in aids:
            v=e.incidence.get((o,a),'RW')
            if v=='RW':  row+=cc(' RW  ',C.Y,C.B)+' '
            elif v=='R': row+=cc('  R   ',C.CN)
            elif v=='W': row+=cc('  W   ',C.M)
            else:        row+=cc('  .   ',C.D)
        print('  |'+row+'|')
    print(cc('  +'+ '-'*(nw+len(aids)*6)+'+',C.D))

def show_status(e):
    rw=e.rw_count();ce,ct=e.coverage()
    print(cc('  K: |G|=%d |M|=%d RW=%d |B|=%d'%(len(e.objects),len(e.attributes),rw,len(e.concepts)),C.B))
    if ct: print(cc('  Coverage: %d/%d (%.0f%%)'%(ce,ct,100*ce/ct),C.D))
    sc=sum(1 for a in e.attributes if a in e.schemas)
    sn=sum(1 for a in e.attributes if any(e.incidence.get((o,a),'RW')!='0' for o in e.objects))
    print(cc('  Schemas: %d/%d'%(sc,sn),C.G if sc>=sn else C.Y))
    if rw==0: print(cc('  ✓ No RW (cond 1)',C.G,C.B))
    else: print(cc('  %d RW to refine'%rw,C.Y))
    tc=e.detect_temporal_conflicts()
    if not tc: print(cc('  ✓ No temporal conflicts (cond 2)',C.G,C.B))
    else:
        for c in tc: print('  ✗ %s: early=[%s] late=[%s] %s'%(cc(c['name'],C.CN),','.join(c['early']),','.join(c['late']),c['splittable']))
    for c in e.check_consistency(): print('  ! %s'%cc(c,C.Y))
    if e.seed.has_content(): print(cc('  Seed: %s'%e.seed.domain,C.CN))
    if e.current_node: print(cc('  Node: %s%s'%(e.current_node,' *' if e.dirty else ''),C.D))

def run_repl(e=None, llm=None):
    if e is None: e=Engine()
    if llm is None: llm=LLM()

    print(cc("""
  ╔═══════════════════════════════════════════════════╗
  ║  KonceptOS v2.1                                  ║
  ║  K → code via framework generation + verification ║
  ║  impl uses generated contracts | verify checks K  ║
  ╚═══════════════════════════════════════════════════╝
    """,C.CN))
    print(cc('  LLM: %s'%('ready (%s)'%OPENROUTER_MODEL if llm.ok else 'N/A (set OPENROUTER_API_KEY)'),C.G if llm.ok else C.Y))

    while True:
        try:
            m='*' if e.dirty else ''
            raw=input(cc('  K[%d|%d]'%(len(e.objects),e.rw_count()),C.BL,C.B)+cc(m,C.Y)+cc('> ',C.D)).strip()
        except (EOFError,KeyboardInterrupt): print('\n  Bye.');break
        if not raw: continue
        parts=raw.split(maxsplit=3);cmd=parts[0].lower()
        try:
            if cmd=='help': print(HELP)
            elif cmd in('quit','exit'): break

            # ── seed ──
            elif cmd=='seed':
                if len(parts)==1: print(e.seed.summary() if e.seed.has_content() else cc('  No seed.',C.D))
                elif parts[1]=='load' and len(parts)>=3:
                    d=json.loads(load_file(' '.join(parts[2:])))
                    e.seed.from_dict(d);e.seed_chain=SeedChain([e.seed])
                    print(cc('  Loaded seed: %s'%e.seed.domain,C.G));print(e.seed.summary())
                elif parts[1]=='save' and len(parts)>=3:
                    with open(parts[2],'w',encoding='utf-8') as f: json.dump(e.seed.to_dict(),f,ensure_ascii=False,indent=2)
                    print(cc('  Saved.',C.G))
                elif parts[1]=='tree':
                    for t,lbl in [(e.seed.obj_tree,'Obj'),(e.seed.attr_tree,'Attr')]:
                        if t:
                            print(cc('  %s tree:'%lbl,C.CN))
                            for k,v in sorted(t.items()): print('    %s → %s'%(cc(k,C.Y),', '.join(v)))
                elif parts[1]=='conv':
                    if e.seed.conventions:
                        for c in e.seed.conventions: print('  - %s'%c)
                    else: print(cc('  None.',C.D))
                elif parts[1]=='set' and len(parts)>=4:
                    rest=raw.split(maxsplit=3);kind=rest[2].lower();tokens=rest[3].split() if len(rest)>3 else []
                    if len(tokens)<2: print(cc('  seed set obj|attr <parent> <c1> <c2>...',C.D))
                    else:
                        p,ch=tokens[0],tokens[1:]
                        if kind in('obj','object'): e.seed.obj_tree[p]=ch
                        elif kind in('attr','attribute'): e.seed.attr_tree[p]=ch
                        print(cc('  %s → %s'%(p,', '.join(ch)),C.G))

            # ── llm ──
            elif cmd=='llm' and len(parts)>=2:
                sub=parts[1].lower()
                if not llm.ok and sub in ('analyze','chat'):
                    print(cc('  LLM not available. Set OPENROUTER_API_KEY.',C.R));continue
                if sub=='analyze' and len(parts)>=3:
                    fp=' '.join(parts[2:])
                    try: content=load_file(fp)
                    except Exception as ex: print(cc('  %s'%ex,C.R));continue
                    print(cc('  Analyzing with %s ...'%OPENROUTER_MODEL,C.D))
                    r=llm.extract_gm(content)
                    if llm.is_error(r): print(cc('  LLM error: %s'%r,C.R));continue
                    d1,err=extract_json(r)
                    if not d1: print(cc('  Fail: %s'%err,C.R));print(r[:500]);continue
                    for obj in d1.get('objects',[]):
                        oid=obj.get('id','')
                        if oid: e.add_obj(oid,obj.get('name',oid),obj.get('desc',''));print('    +G %s %s'%(oid,obj.get('name','')))
                    for at in d1.get('attributes',[]):
                        aid=at.get('id','')
                        if aid: e.add_attr(aid,at.get('name',aid),at.get('desc',''));print('    +M %s %s'%(aid,at.get('name','')))
                    aids=sorted(e.attributes)
                    for key,val in d1.get('incidence',{}).items():
                        if isinstance(val,str) and key in e.objects:
                            for i,cell in enumerate(c.strip().upper() for c in val.split(',')):
                                if i<len(aids):
                                    cv=cell
                                    if cv in('1','YES'): cv='RW'
                                    if cv in VALID_I:
                                        try: e.set_i(key,aids[i],cv)
                                        except: pass
                    e.compute();nid=e.commit('llm analyze')
                    print(cc('  K: |G|=%d |M|=%d RW=%d |B|=%d  node=%s'%(len(e.objects),len(e.attributes),e.rw_count(),len(e.concepts),nid),C.G))
                    for c in e.check_consistency(): print('  ! %s'%cc(c,C.Y))
                elif sub=='chat' and len(parts)>=3:
                    msg=raw.split(maxsplit=2)[2]
                    print('  '+llm.ask("KonceptOS assistant.",msg).replace('\n','\n  '))
                else: print(cc('  llm analyze|chat',C.D))

            # ── resolve ──
            elif cmd=='resolve' and len(parts)>=3:
                kind=parts[1].lower();xid=parts[2]
                kk='obj' if kind in('obj','object') else 'attr'
                col=e.objects if kk=='obj' else e.attributes
                if xid not in col: print(cc('  Not found: %s'%xid,C.R));continue
                item=col[xid]
                ch_list=e.seed_chain.suggest_split(item['name'],item.get('desc',''),kk)
                if ch_list:
                    print(cc('  Seed: %s → %s'%(item['name'],', '.join(c['name'] for c in ch_list)),C.CN))
                else:
                    if not llm.ok: print(cc('  LLM not available.',C.R));continue
                    print(cc('  Asking LLM...',C.D))
                    vocab=(e.seed.obj_vocab if kk=='obj' else e.seed.attr_vocab) or None
                    r=llm.ask_expansion(item['name'],item.get('desc',''),kk.replace('obj','object'),vocab)
                    d,err=extract_json(r)
                    if not d or 'expansions' not in d: print(cc('  Failed: %s'%(err or r[:200]),C.R));continue
                    ch_list=d['expansions']
                    print(cc('  LLM: %s → %s'%(item['name'],', '.join(c['name'] for c in ch_list)),C.CN))
                ans=input(cc('  Proceed? (y/n/edit) ',C.Y)).strip().lower()
                if ans=='n': continue
                if ans=='edit':
                    names=input('  Names: ').strip().split()
                    ch_list=[{'name':n} for n in names]
                print(cc('  Resolving...',C.D))
                new_ids=e.resolve(xid,kk,ch_list,llm);e.compute()
                nid=e.commit('resolve %s %s → %s'%(kk,item['name'],', '.join(c['name'] for c in ch_list)))
                # Show new IDs (fixes problem #3)
                print(cc('  New IDs: %s'%', '.join('%s=%s'%(nid,e.attributes.get(nid,e.objects.get(nid,{})).get('name','?')) for nid in new_ids),C.CN))
                print(cc('  Done. RW=%d |G|=%d |M|=%d node=%s'%(e.rw_count(),len(e.objects),len(e.attributes),nid),C.G))

            # ── evolve ──
            elif cmd=='evolve':
                if not e.concepts: e.compute()
                rw=e.rw_count()
                if rw==0: print(cc('  RW=0',C.G));continue
                mx=rw*3 if len(parts)>1 and parts[1]=='all' else (int(parts[1]) if len(parts)>1 else 1)
                init_rw=rw
                for step in range(1,mx+1):
                    cells=e.rw_cells()
                    if not cells: print(cc('  RW=0!',C.G,C.B));break
                    obj_rw={};
                    for o,a in cells: obj_rw[o]=obj_rw.get(o,0)+1
                    worst=max(obj_rw,key=obj_rw.get);oname=e.objects[worst]['name']
                    ch=e.seed_chain.suggest_split(oname,e.objects[worst].get('desc',''),'obj')
                    if ch: print(cc('  [%d] %s → %s (seed)'%(step,oname,', '.join(c['name'] for c in ch)),C.CN))
                    else:
                        print(cc('  [%d] %s (LLM)...'%(step,oname),C.Y))
                        vocab=e.seed.obj_vocab or None
                        r=llm.ask_expansion(oname,e.objects[worst].get('desc',''),'object',vocab)
                        d,_=extract_json(r)
                        if not d or 'expansions' not in d: print(cc('    Failed',C.R));break
                        ch=d['expansions'];print(cc('    → %s'%', '.join(c['name'] for c in ch),C.CN))
                    e.resolve(worst,'obj',ch,llm);e.compute()
                    new_rw=e.rw_count()
                    print(cc('    RW: %d→%d |G|=%d'%(rw,new_rw,len(e.objects)),C.G if new_rw<rw else C.Y));rw=new_rw
                nid=e.commit('evolve %d steps RW %d→%d'%(step,init_rw,e.rw_count()))
                print(cc('  RW %d→%d  node=%s'%(init_rw,e.rw_count(),nid),C.G))

            # ── DAG ──
            elif cmd=='commit':
                e.compute();nid=e.commit(' '.join(parts[1:]) if len(parts)>1 else '')
                print(cc('  Committed: %s'%nid,C.G))
            elif cmd=='goto' and len(parts)>=2:
                t=parts[1];ms=[h for h in e.dag.nodes if h.startswith(t)]
                if len(ms)==1: e.goto_node(ms[0]);print(cc('  At %s |G|=%d RW=%d'%(ms[0],len(e.objects),e.rw_count()),C.G))
                elif not ms: print(cc('  No match.',C.R))
                else: print(cc('  Ambiguous: %s'%', '.join(ms),C.Y))
            elif cmd=='undo':
                if not e.current_node: print(cc('  No node.',C.R));continue
                ps=e.dag.parents(e.current_node)
                if not ps: print(cc('  At root.',C.Y));continue
                e.goto_node(ps[0]);print(cc('  Back to %s RW=%d'%(ps[0],e.rw_count()),C.G))
            elif cmd=='dag':
                if not e.dag.nodes: print(cc('  Empty.',C.D));continue
                print(cc('  DAG: %d nodes'%len(e.dag.nodes),C.B))
                for h,n in sorted(e.dag.nodes.items(),key=lambda x:x[1].ts):
                    m='→ ' if h==e.current_node else '  '
                    rw=sum(1 for v in n.incidence.values() if v=='RW')
                    ni=sum(len(v) for v in n.impls.values())
                    print('  %s%s |G|=%d |M|=%d RW=%d impl=%d %s'%(m,cc(h,C.CN if h==e.current_node else C.D),len(n.objects),len(n.attributes),rw,ni,n.ts))
            elif cmd=='path':
                if not e.current_node: print(cc('  No node.',C.D));continue
                path=e.dag.path_to_root(e.current_node)
                for i,h in enumerate(path):
                    n=e.dag.nodes[h];m='→ ' if h==e.current_node else '  '
                    desc=''
                    if i>0:
                        for p,c,d in e.dag.edges:
                            if p==path[i-1] and c==h: desc=d;break
                    rw=sum(1 for v in n.incidence.values() if v=='RW')
                    print('  %s%s RW=%d  %s'%(m,cc(h,C.CN),rw,cc(desc,C.D)))
            elif cmd=='diff' and len(parts)>=3:
                a,b=parts[1],parts[2]
                ma=[h for h in e.dag.nodes if h.startswith(a)];mb=[h for h in e.dag.nodes if h.startswith(b)]
                if len(ma)!=1 or len(mb)!=1: print(cc('  Need exact match.',C.R));continue
                na,nb=e.dag.nodes[ma[0]],e.dag.nodes[mb[0]]
                ia={('%s|%s'%(o,a)):v for (o,a),v in na.incidence.items()}
                ib={('%s|%s'%(o,a)):v for (o,a),v in nb.incidence.items()}
                changes=[(k,ia.get(k,'-'),ib.get(k,'-')) for k in sorted(set(list(ia)+list(ib))) if ia.get(k,'-')!=ib.get(k,'-')]
                bg=set(nb.objects)-set(na.objects);ag=set(na.objects)-set(nb.objects)
                if bg: print('  +G: %s'%', '.join(nb.objects[o]['name'] for o in bg if o in nb.objects))
                if ag: print('  -G: %s'%', '.join(na.objects[o]['name'] for o in ag if o in na.objects))
                rwa=sum(1 for v in na.incidence.values() if v=='RW')
                rwb=sum(1 for v in nb.incidence.values() if v=='RW')
                if rwa!=rwb: print('  RW: %d→%d'%(rwa,rwb))
                if changes:
                    print(cc('  %d I changes:'%len(changes),C.Y))
                    for k,va,vb in changes[:15]: print('    %s: %s→%s'%(k,va,vb))
                    if len(changes)>15: print('    +%d'%(len(changes)-15))
                if not changes and not ag and not bg: print(cc('  Identical.',C.D))

            # ── impl ──
            elif cmd=='impl':
                if len(parts)<2: print(cc('  impl <module> [comment]',C.D));continue
                if parts[1]=='show' and len(parts)>=4:
                    mod=parts[2];idx=int(parts[3]);imps=e.impls.get(mod,[])
                    if 0<=idx<len(imps): print(imps[idx].get('code',''));print(cc('  // %s'%imps[idx].get('comment',''),C.D))
                    else: print(cc('  No impl #%d'%idx,C.R))
                else:
                    if not llm.ok: print(cc('  LLM not available.',C.R));continue
                    mod=parts[1];comment=' '.join(parts[2:]) if len(parts)>2 else ''
                    oid=None
                    for o in e.objects:
                        if e.objects[o]['name']==mod or o==mod: oid=o;break
                    if not oid: print(cc('  Not found: %s'%mod,C.R));continue
                    ob=e.objects[oid]

                    # Generate framework context for this module
                    framework_excerpt=codegen.generate_impl_context(e,oid)
                    contract_code=codegen.generate_contract_code(e,oid)

                    # Build upstream/downstream info
                    up=[];dn=[]
                    for aid in sorted(e.attributes):
                        v=e.incidence.get((oid,aid),'RW');an=e.attributes[aid]['name']
                        if v in('R','RW'):
                            ws=[e.objects[o]['name'] for o in e.objects if o!=oid and e.incidence.get((o,aid),'RW') in ('W','RW')]
                            if ws: up.append('%s ← %s'%(an,', '.join(ws)))
                        if v in('W','RW'):
                            rs=[e.objects[o]['name'] for o in e.objects if o!=oid and e.incidence.get((o,aid),'RW')=='R']
                            if rs: dn.append('%s → %s'%(an,', '.join(rs)))

                    print(cc('  Generating impl for %s (with framework context)...'%ob['name'],C.D))
                    code=llm.build_module(ob['name'],ob.get('desc',''),contract_code,framework_excerpt,
                                         e.get_all_conventions(),'\n'.join(up),'\n'.join(dn),e.impls.get(ob['name'],[]))
                    if code.strip().startswith('```'):
                        ls=code.strip().split('\n')
                        if ls[0].startswith('```'):ls=ls[1:]
                        if ls and ls[-1].startswith('```'):ls=ls[:-1]
                        code='\n'.join(ls)
                    e.impls.setdefault(ob['name'],[]).append({'code':code,'comment':comment,'ts':time.strftime('%H:%M:%S')})
                    e.dirty=True
                    print(cc('  impl #%d (%d chars)'%(len(e.impls[ob['name']])-1,len(code)),C.G))
                    print(code[:400]+(('\n  ...(%d more)'%(len(code)-400)) if len(code)>400 else ''))

            elif cmd=='impls':
                mod=parts[1] if len(parts)>1 else None
                if mod:
                    for i,imp in enumerate(e.impls.get(mod,[])): print('  #%d %s %dch  %s'%(i,imp.get('ts',''),len(imp.get('code','')),cc(imp.get('comment',''),C.D)))
                else:
                    if not e.impls: print(cc('  No impls.',C.D))
                    for m,imps in sorted(e.impls.items()): print('  %s: %d impl(s)'%(cc(m,C.CN),len(imps)))

            elif cmd=='ready':
                status=[]
                for oid in sorted(e.objects):
                    on=e.objects[oid]['name'];n=len(e.impls.get(on,[]))
                    status.append((on,n))
                has=sum(1 for _,n in status if n>0);total=len(status)
                print(cc('  Impl coverage: %d/%d modules'%(has,total),C.G if has==total else C.Y))
                for on,n in status:
                    if n>0: print('  %s %s (%d impl%s)'%(cc('✓',C.G),on,n,'s' if n>1 else ''))
                    else: print('  %s %s'%(cc('✗',C.R),on))

            # ── verify ──
            elif cmd=='verify':
                print(cc('  Verifying K + impls...',C.D))
                issues=verify.verify_all(e)
                verify.print_issues(issues)

            # ── assemble ──
            elif cmd=='assemble':
                if not e.concepts: e.compute()
                # Run verify first
                issues=verify.verify_all(e)
                errors=[i for i in issues if i.severity=='error']
                if errors:
                    print(cc('  %d error(s) found. Fix before assemble:'%len(errors),C.R))
                    for i in errors: print(cc('    ✗ %s'%i,C.R))
                    ans=input(cc('  Assemble anyway? (y/n) ',C.Y)).strip().lower()
                    if ans!='y': continue
                out=parts[1] if len(parts)>1 else 'assembled.html'
                html,asm_issues=codegen.assemble_html(e)
                with open(out,'w',encoding='utf-8') as f: f.write(html)
                print(cc('  %s (%d chars)'%(out,len(html)),C.G))
                for iss in asm_issues: print(cc('  ! %s'%iss,C.Y))
                if not asm_issues: print(cc('  All %d modules assembled.'%len(e.objects),C.G))

            # ── framework ──
            elif cmd=='framework':
                print(codegen.generate_framework_js(e))

            # ── build (legacy) ──
            elif cmd=='build':
                if not llm.ok: print(cc('  LLM not available.',C.R));continue
                if not e.concepts: e.compute()
                spec=e.export_spec();conv=e.get_all_conventions()
                print(cc('  Building (legacy one-shot)...',C.D))
                r=llm.build_full(spec,conv)
                out=parts[1] if len(parts)>1 else 'build_output.html'
                if r.strip().startswith('```'):
                    ls=r.strip().split('\n')
                    if ls[0].startswith('```'):ls=ls[1:]
                    if ls and ls[-1].startswith('```'):ls=ls[:-1]
                    r='\n'.join(ls)
                with open(out,'w',encoding='utf-8') as f: f.write(r)
                print(cc('  %s (%d chars)'%(out,len(r)),C.G))

            # ── basics ──
            elif cmd=='add' and len(parts)>=3:
                kind=parts[1].lower();rest=raw.split(maxsplit=3)
                xid=rest[2];name=rest[3] if len(rest)>3 else xid;desc=''
                if '|' in name: name,desc=name.split('|',1);name=name.strip();desc=desc.strip()
                if kind in('obj','object'): e.add_obj(xid,name,desc)
                elif kind in('attr','attribute'): e.add_attr(xid,name,desc)
                print(cc('  +%s'%xid,C.G))
            elif cmd=='del' and len(parts)>=3:
                kind=parts[1].lower();xid=parts[2]
                if kind in('obj','object'): e.del_obj(xid)
                elif kind in('attr','attribute'): e.del_attr(xid)
                print(cc('  -%s'%xid,C.G))
            elif cmd=='set' and len(parts)>=4: e.set_i(parts[1],parts[2],parts[3]);print(cc('  OK',C.G))
            elif cmd=='row' and len(parts)>=3:
                oid=parts[1];vals=raw.split(maxsplit=2)[2].split(',');aids=sorted(e.attributes)
                for i,v in enumerate(vals):
                    if i<len(aids): e.set_i(oid,aids[i],v.strip())
                print(cc('  OK',C.G))
            elif cmd=='schema':
                if len(parts)>=2 and parts[1]=='auto':
                    if not llm.ok: print(cc('  LLM not available.',C.R));continue
                    target_aids=[parts[2]] if len(parts)>=3 and parts[2]!='all' else [a for a in e.attributes if a not in e.schemas]
                    if not target_aids: print(cc('  All set.',C.G));continue
                    attrs_info=[]
                    for aid in target_aids:
                        if aid not in e.attributes: continue
                        an=e.attributes[aid]['name'];ad=e.attributes[aid].get('desc','')
                        writers=', '.join(e.objects[o]['name'] for o in e.objects if e.incidence.get((o,aid),'RW')=='W')
                        readers=', '.join(e.objects[o]['name'] for o in e.objects if e.incidence.get((o,aid),'RW')=='R')
                        attrs_info.append((an,ad,writers,readers))
                    if not attrs_info: continue
                    print(cc('  Generating schemas for %d channels...'%len(attrs_info),C.D))
                    results=llm.suggest_schemas(attrs_info,e.get_all_conventions())
                    if not results: print(cc('  No schemas returned.',C.R));continue
                    name_to_aid={e.attributes[a]['name']:a for a in target_aids if a in e.attributes}
                    for ch_name,sch in results.items():
                        aid=name_to_aid.get(ch_name)
                        if aid: e.set_schema(aid,sch);print('  %s: %s'%(cc(ch_name,C.CN),cc(sch,C.G)))
                elif len(parts)>=3:
                    e.set_schema(parts[1],' '.join(parts[2:]));print(cc('  OK',C.G))
                else: print(cc('  schema <attr_id> <type> | schema auto [attr_id|all]',C.D))
            elif cmd=='convention':
                if len(parts)>1: e.conventions=' '.join(parts[1:]);e.dirty=True;print(cc('  Set.',C.G))
                else: print(e.get_all_conventions() or cc('  (empty)',C.D))

            # ── view ──
            elif cmd in('ctx','context'): show_ctx(e)
            elif cmd in('st','status'): show_status(e)
            elif cmd=='rw':
                cells=e.rw_cells()
                if not cells: print(cc('  RW=0',C.G))
                else:
                    by_obj={}
                    for o,a in cells: by_obj.setdefault(o,[]).append(a)
                    print(cc('  %d RW:'%len(cells),C.Y))
                    for o in sorted(by_obj,key=lambda x:-len(by_obj[x])):
                        print('    %s (%d): %s'%(cc(e.objects[o]['name'],C.CN),len(by_obj[o]),cc(', '.join(e.attributes[a]['name'] for a in by_obj[o]),C.M)))
            elif cmd=='flows':
                fl=e.dataflows()
                if not fl: print(cc('  None.',C.D))
                else:
                    for f,v,t in fl: print('  %s -[%s]→ %s'%(cc(f,C.CN),cc(v,C.M),cc(t,C.G)))
            elif cmd=='order':
                order,cyc=e.topo_sort()
                if cyc: print(cc('  Warning: cycle (all modules included, order approximate)',C.Y))
                for i,oid in enumerate(order): print('  %2d. %s'%(i+1,cc(e.objects[oid]['name'],C.CN)))
            elif cmd=='conflicts':
                tc=e.detect_temporal_conflicts()
                if not tc: print(cc('  None.',C.G))
                else:
                    for c in tc:
                        print('  %s (%s):'%(cc(c['name'],C.CN),c['splittable']))
                        print('    early: %s'%', '.join(c['early']));print('    late:  %s'%', '.join(c['late']))
            elif cmd=='groups':
                gr=e.coding_groups()
                if not gr: print(cc('  None.',C.D))
                else:
                    for ci in sorted(gr): print('  C%02d: %s'%(ci,cc(', '.join(e.objects[o]['name'] for o in gr[ci] if o in e.objects),C.CN)))
            elif cmd in('lat','lattice'):
                if not e.concepts: print(cc('  Empty.',C.D));continue
                ml=max(e.layers) if e.layers else 0
                print(cc('  B(K): %d concepts'%len(e.concepts),C.B))
                for layer in range(ml+1):
                    lc=[(i,e.concepts[i]) for i in range(len(e.concepts)) if e.layers[i]==layer]
                    if lc:
                        print(cc('  -- L%d --'%layer,C.BL))
                        for idx,(ext,intn) in lc:
                            en=[e.objects[o]['name'][:12] for o in sorted(ext) if o in e.objects]
                            an=[e.attributes[a]['name'][:8] for a in sorted(intn) if a in e.attributes]
                            print('    C%02d {%s} ← {%s}'%(idx,cc(','.join(an),C.M),cc(','.join(en[:5]),C.CN)))
            elif cmd=='concept' and len(parts)>=2:
                idx=int(parts[1])
                if 0<=idx<len(e.concepts):
                    ext,intn=e.concepts[idx]
                    print(cc('  C%02d L%d'%(idx,e.layers[idx]),C.B))
                    for a in sorted(intn): print('    %s  %s'%(e.attributes.get(a,{}).get('name',''),cc(e.schemas.get(a,''),C.D)))
                    for o in sorted(ext):
                        dirs=[e.attributes.get(a,{}).get('name','')[:4]+':'+e.incidence.get((o,a),'RW') for a in sorted(intn)]
                        print('    %s  %s'%(e.objects.get(o,{}).get('name',''),cc(' '.join(dirs),C.D)))
            elif cmd=='ts':
                from .util import safe_contract_name
                lines=['// KonceptOS v2.1 — TypeScript signatures','// Node: %s\n'%(e.current_node or '?')]
                lines.append('interface Channels {')
                for aid in sorted(e.attributes): lines.append('  %s: %s;'%(e.attributes[aid]['name'],e.schemas.get(aid,'any')))
                lines.append('}\n')
                for oid in sorted(e.objects):
                    on=e.objects[oid]['name'];cn=safe_contract_name(on)
                    c=e.contract_for(oid)
                    lines.append('// %s'%on)
                    lines.append('interface %s {'%cn)
                    if c['reads']: lines.append("  reads: %s;"%' | '.join("'%s'"%x for x in c['reads']))
                    if c['writes']: lines.append("  writes: %s;"%' | '.join("'%s'"%x for x in c['writes']))
                    if c['readwrites']: lines.append("  readwrites: %s;"%' | '.join("'%s'"%x for x in c['readwrites']))
                    lines.append('}\n')
                print('\n'.join(lines))

            # ── files ──
            elif cmd=='compute': e.compute();print(cc('  |B|=%d'%len(e.concepts),C.G))
            elif cmd=='save' and len(parts)>=2:
                if e.dirty: e.compute();e.commit('auto-save')
                e.save_dag(parts[1]);print(cc('  Saved: %d nodes'%len(e.dag.nodes),C.G))
            elif cmd=='open' and len(parts)>=2:
                try:
                    with open(parts[1],'r') as f: d=json.load(f)
                    if 'dag' in d: e.load_dag(parts[1]);print(cc('  DAG: %d nodes'%len(e.dag.nodes),C.G))
                    else: e.load_v09(d);print(cc('  v0.9 converted.',C.G))
                except Exception as ex: print(cc('  %s'%ex,C.R))
            elif cmd=='export' and len(parts)>=2:
                if not e.concepts: e.compute()
                e.export_spec(parts[1]);print(cc('  %s'%parts[1],C.G))
            elif cmd in('hist','history'):
                for h in e.history[-20:]: print(cc('  [%s] %s: %s'%(h['time'],h['act'],h['detail']),C.D))
            else: print(cc('  ? %s (try "help")'%raw,C.R))
        except Exception as ex:
            print(cc('  ERR: %s'%ex,C.R))
            import traceback;traceback.print_exc()
