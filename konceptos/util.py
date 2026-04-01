"""KonceptOS v2.1 — Shared utilities."""
import json,sys,re
from pathlib import Path

VALID_I = {'0','R','W','RW'}

def _ansi():
    if sys.platform!='win32': return True
    try:
        import ctypes;k=ctypes.windll.kernel32;h=k.GetStdHandle(-11)
        m=ctypes.c_ulong();k.GetConsoleMode(h,ctypes.byref(m));k.SetConsoleMode(h,m.value|0x0004);return True
    except: return False
ANSI=_ansi()

class C:
    if ANSI: RST='\033[0m';B='\033[1m';D='\033[2m';R='\033[31m';G='\033[32m';Y='\033[33m';BL='\033[34m';M='\033[35m';CN='\033[36m'
    else: RST=B=D=R=G=Y=BL=M=CN=''

def cc(t,*c): return (''.join(c)+str(t)+C.RST) if ANSI else str(t)

def extract_json(text):
    a,b=text.find('{'),text.rfind('}')
    if a==-1 or b<=a: return None,'No JSON'
    s=text[a:b+1]
    try: return json.loads(s),None
    except:
        s2=re.sub(r',\s*}','}',re.sub(r',\s*]',']',s))
        try: return json.loads(s2),None
        except json.JSONDecodeError as e: return None,'pos %d: %s'%(e.pos,e.msg)

def load_file(fp):
    p=Path(fp)
    if not p.exists():
        alt=Path('/mnt/user-data/uploads/'+fp)
        if alt.exists(): p=alt
        else: raise FileNotFoundError(fp)
    return p.read_text(encoding='utf-8',errors='replace')

def safe_name(name):
    """Convert any name to a valid JS/TS identifier."""
    # Keep alphanumeric and CJK characters, replace others with _
    s = ''
    for ch in name:
        if ch.isalnum() or ch == '_' or '\u4e00' <= ch <= '\u9fff':
            s += ch
        else:
            s += '_'
    s=s.strip('_')
    if not s: s='unnamed'
    if s[0].isdigit(): s='M_'+s
    return s

def safe_contract_name(name):
    """Convert module name to PascalCase contract name."""
    s=safe_name(name)
    # For pure CJK names, just append Contract
    if any('\u4e00' <= c <= '\u9fff' for c in s):
        return s+'Contract'
    return ''.join(w.capitalize() for w in s.split('_'))+'Contract'
