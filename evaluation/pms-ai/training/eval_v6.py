"""usage: eval_v6.py MODEL LO HI [HELD]  -> /tmp/v6res_MODEL_LO.json ; eval_v6.py MODEL agg [HELD]"""
import json,re,sys,glob,collections,concurrent.futures as cf
sys.argv_backup=sys.argv[:]
src=open('/tmp/ev.py').read().split("MODELS=")[0]
src=src.replace("rows=[json.loads","rows=[] #",1)
exec(src.split("rows=[]")[0]+"""
A="2c7adc94f3a187ed9aec95d44ae54e94"
""")
exec("def call"+open('/tmp/ev.py').read().split("def call",1)[1].split("MODELS=")[0])
SYS=("You are the PMS performance assistant. Use ONLY the verified facts given in the message. "
"If no verified facts are given, say you need to look the data up and do not state any score, rank or name. Never invent numbers.")
MODELS={"granite":("@cf/ibm-granite/granite-4.0-h-micro",None),"v4":("@cf/mistral/mistral-7b-instruct-v0.2-lora","pms-assistant-v4"),
"v5":("@cf/mistral/mistral-7b-instruct-v0.2-lora","pms-assistant-v5"),"v6":("@cf/mistral/mistral-7b-instruct-v0.2-lora","pms-assistant-v6"),"v7":("@cf/mistral/mistral-7b-instruct-v0.2-lora","pms-assistant-v7")}
num=re.compile(r'\d+(?:\.\d+)?')
HELD=sys.argv[4] if len(sys.argv)>4 else '/tmp/heldout_v6.jsonl'
def score(r,a):
    ctx=(r['q']+" "+(r['facts'] or ""))
    inv=sorted(n for n in set(num.findall(a)) if n not in set(num.findall(ctx)) and n!='2026')
    low=a.lower().replace("+","")
    miss=[x for x in r['required'] if x.lower().replace("+","") not in low]
    return inv,miss
mk=sys.argv[1]
if sys.argv[2]=="agg":
    res=[]
    D={}
    for f in glob.glob(f"/tmp/v6res_{mk}_*.json"):
        for x in json.load(open(f)): D[x["id"]]=x
    res=list(D.values())
    by=collections.defaultdict(list)
    for x in res: by[x['cat']].append(x)
    tot=0;ok=0;inv=0
    for c,v in sorted(by.items()):
        p=sum(x['pass'] for x in v); print(f"{c:18s} {p}/{len(v)} = {100*p/len(v):.1f}%  invented={sum(bool(x['inv']) for x in v)} missing_fact={sum(bool(x['miss']) for x in v)}")
        tot+=len(v);ok+=p;inv+=sum(bool(x['inv']) for x in v)
    print(f"TOTAL {mk}: {ok}/{tot} = {100*ok/tot:.1f}%  invented_numbers={inv}  errs={sum(x['err'] for x in res)}")
    sys.exit()
lo,hi=int(sys.argv[2]),int(sys.argv[3])
rows=[json.loads(l) for l in open(HELD) if l.strip()][lo:hi]
model,lora=MODELS[mk]
def one(r):
    a=call(model,[{"role":"system","content":SYS},{"role":"user","content":r['user']}],lora)
    inv,miss=score(r,a)
    return dict(id=r['id'],cat=r['cat'],q=r['q'],a=a,inv=inv,miss=miss,err=a.startswith("ERR"),pass_=None,**{"pass":(not inv and not miss and not a.startswith("ERR"))})
with cf.ThreadPoolExecutor(10) as ex: out=list(ex.map(one,rows))
json.dump(out,open(f"/tmp/v6res_{mk}_{lo}.json","w"),ensure_ascii=False)
print(mk,lo,hi,"pass",sum(x['pass'] for x in out),"/",len(out),"errs",sum(x['err'] for x in out))
