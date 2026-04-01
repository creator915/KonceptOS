"""KonceptOS v2.1 — Seed: pluggable prior knowledge at decision points."""
from .util import VALID_I

class Seed:
    """Base interface. Return None = 'I don't know'."""
    def suggest_direction(self,on,od,an,ad,ctx=None): return None
    def suggest_split(self,name,desc,kind,ctx=None): return None
    def suggest_schema(self,an,ad): return None

class JsonSeed(Seed):
    """Seed backed by JSON with vocab, trees, hints, conventions."""
    def __init__(self):
        self.domain="";self.obj_vocab=[];self.attr_vocab=[]
        self.obj_tree={};self.attr_tree={}
        self.incidence_hints={};self.conventions=[];self.reference_k=None

    def suggest_direction(self,on,od,an,ad,ctx=None):
        h=self.incidence_hints.get('%s|%s'%(on,an))
        if not h: h=self.incidence_hints.get('*|%s'%an)
        if not h: h=self.incidence_hints.get('%s|*'%on)
        return h.upper() if h and h.upper() in VALID_I else None

    def suggest_split(self,name,desc,kind,ctx=None):
        tree=self.obj_tree if kind=='obj' else self.attr_tree
        ch=tree.get(name)
        if not ch:
            for k,v in tree.items():
                if k in name or name in k: ch=v;break
        return [{'name':c,'desc':''} for c in ch] if ch else None

    def has_content(self):
        return bool(self.obj_tree or self.attr_tree or self.obj_vocab or self.conventions)

    def to_dict(self):
        return {'domain':self.domain,'obj_vocab':self.obj_vocab,'attr_vocab':self.attr_vocab,
                'obj_tree':self.obj_tree,'attr_tree':self.attr_tree,
                'incidence_hints':self.incidence_hints,'conventions':self.conventions,
                'reference_k':self.reference_k}

    def from_dict(self,d):
        self.domain=d.get('domain','');self.obj_vocab=d.get('obj_vocab',[])
        self.attr_vocab=d.get('attr_vocab',[]);self.obj_tree=d.get('obj_tree',{})
        self.attr_tree=d.get('attr_tree',{});self.incidence_hints=d.get('incidence_hints',{})
        self.conventions=d.get('conventions',[]);self.reference_k=d.get('reference_k')

    def summary(self):
        p=['  Seed: %s'%(self.domain or '(unnamed)')]
        if self.obj_vocab: p.append('    obj vocab: %d'%len(self.obj_vocab))
        if self.attr_vocab: p.append('    attr vocab: %d'%len(self.attr_vocab))
        if self.obj_tree: p.append('    obj tree: %d'%len(self.obj_tree))
        if self.attr_tree: p.append('    attr tree: %d'%len(self.attr_tree))
        if self.incidence_hints: p.append('    hints: %d'%len(self.incidence_hints))
        if self.conventions: p.append('    conventions: %d'%len(self.conventions))
        return '\n'.join(p)

class SeedChain(Seed):
    """Priority chain. First non-None answer wins."""
    def __init__(self,seeds=None): self.seeds=seeds or []
    def add(self,s): self.seeds.append(s)
    def suggest_direction(self,on,od,an,ad,ctx=None):
        for s in self.seeds:
            r=s.suggest_direction(on,od,an,ad,ctx)
            if r is not None: return r
        return None
    def suggest_split(self,name,desc,kind,ctx=None):
        for s in self.seeds:
            r=s.suggest_split(name,desc,kind,ctx)
            if r is not None: return r
        return None
