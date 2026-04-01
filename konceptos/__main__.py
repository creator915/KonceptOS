"""KonceptOS v2.1 — Entry point for python -m konceptos."""
import sys,json
from .engine import Engine
from .llm import LLM
from .cli import run_repl

def main():
    e=Engine();llm=LLM()
    if len(sys.argv)>2 and sys.argv[1]=='--load':
        fp=sys.argv[2]
        try:
            with open(fp,'r') as f: d=json.load(f)
            if 'dag' in d: e.load_dag(fp)
            else: e.load_v09(d)
            from .util import cc,C
            print(cc('  Loaded %s'%fp,C.G))
        except Exception as ex:
            from .util import cc,C
            print(cc('  %s'%ex,C.R))
    run_repl(e,llm)

if __name__=='__main__':
    main()
