"""KonceptOS v2.1 — Engine: K=(G,M,I), FCA computation, immutable DAG."""
import json,time,hashlib,copy
from .util import VALID_I
from .seed import JsonSeed, SeedChain

def k_hash(objects,attributes,incidence,schemas):
    canon=json.dumps({'G':sorted((k,v['name']) for k,v in objects.items()),
        'M':sorted((k,v['name']) for k,v in attributes.items()),
        'I':sorted(('%s|%s'%(o,a),v) for (o,a),v in incidence.items()),
        'S':sorted(schemas.items())},sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()[:12]

class DAGNode:
    __slots__=('nid','objects','attributes','incidence','schemas','conventions',
               'impls','comments','seed_dict','ts')
    def __init__(self,obj,attr,inc,sch,conv='',seed_d=None):
        self.objects=copy.deepcopy(obj);self.attributes=copy.deepcopy(attr)
        self.incidence=dict(inc);self.schemas=dict(sch)
        self.conventions=conv;self.seed_dict=seed_d or {}
        self.impls={};self.comments=[]
        self.nid=k_hash(obj,attr,inc,sch)
        self.ts=time.strftime('%Y-%m-%d %H:%M:%S')

class DAG:
    def __init__(self): self.nodes={};self.edges=[];self.root=None
    def add_node(self,node,parent=None,desc=''):
        ex=self.nodes.get(node.nid)
        if ex:
            for m,imps in node.impls.items(): ex.impls.setdefault(m,[]).extend(imps)
            ex.comments.extend(node.comments);node=ex
        else: self.nodes[node.nid]=node
        if parent and parent in self.nodes:
            edge=(parent,node.nid,desc)
            if edge not in self.edges: self.edges.append(edge)
        if self.root is None: self.root=node.nid
        return node.nid
    def parents(self,nid): return [p for p,c,d in self.edges if c==nid]
    def children(self,nid): return [(c,d) for p,c,d in self.edges if p==nid]
    def path_to_root(self,nid):
        path=[nid]
        while True:
            ps=self.parents(path[-1])
            if not ps: break
            path.append(ps[0])
        return list(reversed(path))
    def to_dict(self):
        nd={}
        for h,n in self.nodes.items():
            nd[h]={'objects':n.objects,'attributes':n.attributes,
                'incidence':{'%s|%s'%(o,a):v for (o,a),v in n.incidence.items()},
                'schemas':n.schemas,'conventions':n.conventions,'seed':n.seed_dict,
                'impls':n.impls,'comments':n.comments,'ts':n.ts}
        return {'nodes':nd,'edges':self.edges,'root':self.root}
    def from_dict(self,d):
        self.nodes={};self.edges=d.get('edges',[]);self.root=d.get('root')
        for h,nd in d.get('nodes',{}).items():
            inc={}
            for k,v in nd.get('incidence',{}).items():
                p=k.split('|')
                if len(p)==2: inc[(p[0],p[1])]=v
            n=DAGNode(nd['objects'],nd['attributes'],inc,nd.get('schemas',{}),
                      nd.get('conventions',''),nd.get('seed'))
            n.nid=h;n.impls=nd.get('impls',{});n.comments=nd.get('comments',[]);n.ts=nd.get('ts','')
            self.nodes[h]=n


class Engine:
    """Mutable working state + FCA + DAG integration."""
    def __init__(self):
        self.objects={};self.attributes={};self.incidence={};self.schemas={}
        self.conventions="";self.concepts=[];self.edges=[];self.layers=[]
        self.history=[];self.seed=JsonSeed();self.seed_chain=SeedChain()
        self.dag=DAG();self.current_node=None;self.impls={};self.dirty=False

    # ── K manipulation ──
    def add_obj(self,oid,name,desc=''):
        self.objects[oid]={'name':name,'desc':desc}
        for a in self.attributes:
            if (oid,a) not in self.incidence: self.incidence[(oid,a)]='RW'
        self._log('add_obj','%s: %s'%(oid,name));self.dirty=True

    def add_attr(self,aid,name,desc=''):
        self.attributes[aid]={'name':name,'desc':desc}
        for o in self.objects:
            if (o,aid) not in self.incidence: self.incidence[(o,aid)]='RW'
        self._log('add_attr','%s: %s'%(aid,name));self.dirty=True

    def set_i(self,oid,aid,val):
        val=val.upper().strip()
        if val in('1','YES','TRUE'):val='RW'
        if val in('NO','FALSE','NONE','N'):val='0'
        if val not in VALID_I: raise ValueError('Use 0/R/W/RW')
        if oid not in self.objects: raise ValueError('No obj: '+oid)
        if aid not in self.attributes: raise ValueError('No attr: '+aid)
        old=self.incidence.get((oid,aid),'RW')
        self.incidence[(oid,aid)]=val
        if old!=val: self.dirty=True

    def del_obj(self,oid):
        if oid in self.objects:
            del self.objects[oid]
            self.incidence={k:v for k,v in self.incidence.items() if k[0]!=oid};self.dirty=True

    def del_attr(self,aid):
        if aid in self.attributes:
            del self.attributes[aid]
            self.incidence={k:v for k,v in self.incidence.items() if k[1]!=aid}
            self.schemas.pop(aid,None);self.dirty=True

    def set_schema(self,aid,s):
        if aid not in self.attributes: raise ValueError('No attr: '+aid)
        self.schemas[aid]=s;self.dirty=True

    # ── Queries ──
    def involved(self,o,a): return self.incidence.get((o,a),'RW') in ('R','W','RW')
    def rw_count(self): return sum(1 for v in self.incidence.values() if v=='RW')
    def rw_cells(self): return [(o,a) for (o,a),v in self.incidence.items() if v=='RW']
    def coverage(self):
        t=len(self.objects)*len(self.attributes)
        e=sum(1 for v in self.incidence.values() if v!='RW')
        return (e,t) if t else (0,0)

    def get_row(self,oid):
        return {a:self.incidence.get((oid,a),'RW') for a in self.attributes}
    def get_col(self,aid):
        return {o:self.incidence.get((o,aid),'RW') for o in self.objects}
    def get_row_str(self,oid):
        return ', '.join('%s=%s'%(self.attributes[a]['name'],self.incidence.get((oid,a),'RW'))
                        for a in sorted(self.attributes) if self.incidence.get((oid,a),'RW')!='0')

    def writers_of(self,aid):
        return [o for o in self.objects if self.incidence.get((o,aid),'RW') in ('W','RW')]
    def readers_of(self,aid):
        return [o for o in self.objects if self.incidence.get((o,aid),'RW') in ('R',)]

    def contract_for(self,oid):
        """Return {reads:[names], writes:[names], readwrites:[names]} for a module."""
        r=[];w=[];rw=[]
        for aid in sorted(self.attributes):
            v=self.incidence.get((oid,aid),'RW');an=self.attributes[aid]['name']
            if v=='R': r.append(an)
            elif v=='W': w.append(an)
            elif v=='RW': rw.append(an)
        return {'reads':r,'writes':w,'readwrites':rw}

    # ── FCA ──
    def _intent(self,ext):
        if not ext: return set(self.attributes)
        r=set(self.attributes)
        for o in ext: r&={a for a in self.attributes if self.involved(o,a)}
        return r
    def _extent(self,intn):
        if not intn: return set(self.objects)
        r=set(self.objects)
        for a in intn: r&={o for o in self.objects if self.involved(o,a)}
        return r

    def compute(self):
        if not self.objects or not self.attributes:
            self.concepts,self.edges,self.layers=[],[],[];return
        seen=set();concepts=[];oids=list(self.objects);aids=list(self.attributes)
        cands=[set()]
        for o in oids: cands.append({o})
        for i in range(len(oids)):
            for j in range(i+1,min(i+10,len(oids))): cands.append({oids[i],oids[j]})
        for a in aids: cands.append(self._extent({a}))
        for i in range(len(aids)):
            for j in range(i+1,len(aids)): cands.append(self._extent({aids[i],aids[j]}))
        if len(aids)<=14:
            for i in range(len(aids)):
                for j in range(i+1,len(aids)):
                    for k2 in range(j+1,len(aids)): cands.append(self._extent({aids[i],aids[j],aids[k2]}))
        for ext in cands:
            intn=self._intent(ext);closed=self._extent(intn)
            key=(frozenset(closed),frozenset(intn))
            if key not in seen: seen.add(key);concepts.append((set(closed),set(intn)))
        concepts.sort(key=lambda c:len(c[1]));self.concepts=concepts
        self.edges=[]
        for i in range(len(concepts)):
            for j in range(i+1,len(concepts)):
                ai,bi=concepts[i][1],concepts[j][1]
                if ai<bi:
                    ok=True
                    for k2 in range(len(concepts)):
                        if k2==i or k2==j: continue
                        if ai<concepts[k2][1]<bi: ok=False;break
                    if ok: self.edges.append((i,j))
        self.layers=[0]*len(concepts);ch=True
        while ch:
            ch=False
            for p,c in self.edges:
                if self.layers[c]<=self.layers[p]: self.layers[c]=self.layers[p]+1;ch=True

    # ── Consistency ──
    def check_consistency(self):
        issues=[]
        for aid in self.attributes:
            rs=[o for o in self.objects if self.incidence.get((o,aid),'RW')=='R']
            ws=[o for o in self.objects if self.incidence.get((o,aid),'RW')=='W']
            rws=[o for o in self.objects if self.incidence.get((o,aid),'RW')=='RW']
            an=self.attributes[aid]['name']
            if rs and not ws and not rws: issues.append('R_no_W: "%s" %dR no W'%(an,len(rs)))
            if ws and not rs and not rws: issues.append('W_no_R: "%s" %dW no R'%(an,len(ws)))
            # Multi-writer detection
            if len(ws)>1:
                names=[self.objects[o]['name'] for o in ws]
                issues.append('MULTI_W: "%s" has %d writers: %s → consider per-entity schema or split'%(
                    an,len(ws),', '.join(names)))
        return issues

    # ── Temporal conflicts ──
    def build_order_graph(self):
        g={}
        for aid in self.attributes:
            ws=[o for o in self.objects if self.incidence.get((o,aid),'RW') in ('W','RW')]
            rs=[o for o in self.objects if self.incidence.get((o,aid),'RW')=='R']
            for w in ws:
                for r in rs:
                    if w!=r: g.setdefault(w,set()).add(r)
        return g

    def detect_temporal_conflicts(self):
        graph=self.build_order_graph();all_o=list(self.objects)
        reach={o:set() for o in all_o}
        for o in all_o:
            stk=[o];vis=set()
            while stk:
                cur=stk.pop()
                for nxt in graph.get(cur,[]):
                    if nxt not in vis: vis.add(nxt);reach[o].add(nxt);stk.append(nxt)
        conflicts=[]
        for o in all_o:
            if o not in reach.get(o,set()): continue
            before=set();after=set()
            for aid in self.attributes:
                v=self.incidence.get((o,aid),'RW')
                if v in ('W','RW'):
                    for r in self.objects:
                        if r!=o and self.incidence.get((r,aid),'RW')=='R' and o in reach.get(r,set()):
                            before.add(aid)
                if v=='R':
                    for w in self.objects:
                        if w!=o and self.incidence.get((w,aid),'RW') in ('W','RW'):
                            after.add(aid)
            if before and after:
                on=self.objects[o]['name']
                conflicts.append({'obj':o,'name':on,
                    'splittable':'splittable' if not (before&after) else 'entangled',
                    'early':[self.attributes[a]['name'] for a in before if a in self.attributes],
                    'late':[self.attributes[a]['name'] for a in after if a in self.attributes]})
        return conflicts

    def topo_sort(self):
        graph=self.build_order_graph()
        in_d={o:0 for o in self.objects}
        for o,deps in graph.items():
            for d in deps:
                if d in in_d: in_d[d]+=1
        q=[o for o in self.objects if in_d[o]==0];order=[]
        while q:
            q.sort(key=lambda o:self.objects[o]['name']);cur=q.pop(0);order.append(cur)
            for nxt in graph.get(cur,[]):
                if nxt in in_d:
                    in_d[nxt]-=1
                    if in_d[nxt]==0: q.append(nxt)
        # If cycle, append remaining in alphabetical order
        remaining=[o for o in self.objects if o not in order]
        remaining.sort(key=lambda o:self.objects[o]['name'])
        has_cycle=len(remaining)>0
        return order+remaining, has_cycle

    # ── Data flows ──
    def dataflows(self):
        flows=[]
        for aid in self.attributes:
            ws=[o for o in self.objects if self.incidence.get((o,aid),'RW') in ('W','RW')]
            rs=[o for o in self.objects if self.incidence.get((o,aid),'RW')=='R']
            for w in ws:
                for r in rs:
                    if w!=r: flows.append((self.objects[w]['name'],self.attributes[aid]['name'],self.objects[r]['name']))
        return flows

    def coding_groups(self):
        if not self.concepts: return {}
        groups={}
        for oid in self.objects:
            best=-1;bisz=-1
            for idx,(ext,intn) in enumerate(self.concepts):
                if oid in ext and len(intn)>bisz: best=idx;bisz=len(intn)
            if best>=0: groups.setdefault(best,[]).append(oid)
        return groups

    def get_all_conventions(self):
        parts=[]
        if self.seed.conventions: parts.append('\n'.join('- '+c for c in self.seed.conventions))
        if self.conventions: parts.append(self.conventions)
        return '\n'.join(parts)

    # ── Resolve ──
    def resolve(self,xid,kind,children,llm):
        """Split object or attribute. Returns list of new IDs."""
        new_ids=[]
        if kind=='obj':
            if xid not in self.objects: return []
            pinc={(xid,a):self.incidence.get((xid,a),'RW') for a in self.attributes}
            for i,ch in enumerate(children):
                nid=ch.get('id','%s_%d'%(xid,i+1))
                while nid in self.objects: nid+='_'
                self.add_obj(nid,ch['name'],ch.get('desc',''));new_ids.append(nid)
            pending=[];pairs=[]
            for nid in new_ids:
                nn=self.objects[nid]['name'];nd=self.objects[nid].get('desc','')
                for aid in list(self.attributes):
                    an=self.attributes[aid]['name'];ad=self.attributes[aid].get('desc','')
                    pv=pinc.get((xid,aid),'RW')
                    if pv=='0': self.set_i(nid,aid,'0');continue
                    h=self.seed_chain.suggest_direction(nn,nd,an,ad)
                    if h: self.set_i(nid,aid,h);continue
                    pending.append((nid,aid,len(pairs)));pairs.append((nn,nd,an,ad))
            if pairs and llm and llm.ok:
                ctx="Splitting '%s' into: %s"%(self.objects.get(xid,{}).get('name',xid),
                    ', '.join(self.objects[n]['name'] for n in new_ids))
                results=llm.judge_batch(pairs,ctx)
                for nid,aid,idx in pending: self.set_i(nid,aid,results.get(idx,'RW'))
            else:
                for nid,aid,idx in pending: self.set_i(nid,aid,'RW')
            self.del_obj(xid)
        elif kind=='attr':
            if xid not in self.attributes: return []
            pinc={(o,xid):self.incidence.get((o,xid),'RW') for o in self.objects}
            for i,ch in enumerate(children):
                nid=ch.get('id','%s_%d'%(xid,i+1))
                while nid in self.attributes: nid+='_'
                self.add_attr(nid,ch['name'],ch.get('desc',''));new_ids.append(nid)
            pending=[];pairs=[]
            for oid in list(self.objects):
                on=self.objects[oid]['name'];od=self.objects[oid].get('desc','')
                pv=pinc.get((oid,xid),'RW')
                if pv=='0':
                    for na in new_ids: self.set_i(oid,na,'0')
                    continue
                for na in new_ids:
                    nan=self.attributes[na]['name'];nad=self.attributes[na].get('desc','')
                    h=self.seed_chain.suggest_direction(on,od,nan,nad)
                    if h: self.set_i(oid,na,h);continue
                    pending.append((oid,na,len(pairs)));pairs.append((on,od,nan,nad))
            if pairs and llm and llm.ok:
                ctx="Splitting '%s' into: %s"%(self.attributes.get(xid,{}).get('name',xid),
                    ', '.join(self.attributes[n]['name'] for n in new_ids))
                results=llm.judge_batch(pairs,ctx)
                for oid,na,idx in pending: self.set_i(oid,na,results.get(idx,'RW'))
            else:
                for oid,na,idx in pending: self.set_i(oid,na,'RW')
            self.del_attr(xid)
        self.dirty=True
        return new_ids

    # ── DAG ops ──
    def commit(self,desc=''):
        node=DAGNode(self.objects,self.attributes,self.incidence,self.schemas,
                     self.conventions,self.seed.to_dict() if self.seed.has_content() else {})
        node.impls=copy.deepcopy(self.impls)
        nid=self.dag.add_node(node,self.current_node,desc)
        self.current_node=nid;self.dirty=False;return nid

    def goto_node(self,nid):
        if nid not in self.dag.nodes: raise ValueError('No node: '+nid)
        n=self.dag.nodes[nid]
        self.objects=copy.deepcopy(n.objects);self.attributes=copy.deepcopy(n.attributes)
        self.incidence=dict(n.incidence);self.schemas=dict(n.schemas)
        self.conventions=n.conventions;self.impls=copy.deepcopy(n.impls)
        if n.seed_dict: self.seed.from_dict(n.seed_dict);self.seed_chain=SeedChain([self.seed])
        self.current_node=nid;self.dirty=False;self.compute()

    # ── Serialization ──
    def export_spec(self,fp=None):
        L=['# KonceptOS Spec\n']
        conv=self.get_all_conventions()
        if conv: L.append('## Conventions\n```\n%s\n```\n'%conv)
        L.append('## Objects (%d)\n| ID | Name | Desc |'%len(self.objects))
        L.append('|----|------|------|')
        for o in sorted(self.objects):
            ob=self.objects[o];L.append('| %s | %s | %s |'%(o,ob['name'],ob.get('desc','')))
        L.append('\n## Attributes (%d)\n| ID | Name | Schema |'%len(self.attributes))
        L.append('|----|------|--------|')
        for a in sorted(self.attributes):
            L.append('| %s | %s | %s |'%(a,self.attributes[a]['name'],self.schemas.get(a,'-')))
        aids=sorted(self.attributes)
        L.append('\n## Incidence\n| |'+'|'.join(self.attributes[a]['name'][:6] for a in aids)+'|')
        L.append('|--'+'|--'*len(aids)+'|')
        for o in sorted(self.objects):
            row='| %s '%self.objects[o]['name'][:14]
            for a in aids: row+='| %s '%self.incidence.get((o,a),'RW')
            L.append(row+'|')
        txt='\n'.join(L)
        if fp:
            with open(fp,'w',encoding='utf-8') as f: f.write(txt)
        return txt

    def _log(self,a,d):
        self.history.append({'time':time.strftime('%H:%M:%S'),'act':a,'detail':d})

    def save_dag(self,fp):
        import json as j
        with open(fp,'w',encoding='utf-8') as f:
            j.dump({'dag':self.dag.to_dict(),'current':self.current_node},f,ensure_ascii=False,indent=2)

    def load_dag(self,fp):
        import json as j
        with open(fp,'r',encoding='utf-8') as f: d=j.load(f)
        self.dag.from_dict(d.get('dag',{}))
        cur=d.get('current',self.dag.root)
        if cur and cur in self.dag.nodes: self.goto_node(cur)

    def load_v09(self,d):
        self.objects=d.get('objects',{});self.attributes=d.get('attributes',{})
        self.conventions=d.get('conventions','');self.incidence={}
        for k,v in d.get('incidence',{}).items():
            p=k.split('|')
            if len(p)==2: self.incidence[(p[0],p[1])]=v if v in VALID_I else 'RW'
        if 'seed' in d: self.seed.from_dict(d['seed']);self.seed_chain=SeedChain([self.seed])
        self.compute();self.commit('imported from v0.9')
