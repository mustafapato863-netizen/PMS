"""usage: MS=adapter_v6 IN=/tmp/live2_results.jsonl OUT=/tmp/rf_v6.json python3 realfmt_eval.py"""
import json,re,sys,os,concurrent.futures as cf
os.environ.setdefault("HELD","/tmp/heldout_questions.jsonl")
sys.argv=["x","adapter_v4","0","0"]
exec(open('/tmp/ev.py').read().split("T=tasks()")[0])
MS=os.environ['MS'].split(',')
recs=[json.loads(l) for l in open(os.environ['IN'])]
use=[x for x in recs if x.get('headline') and x['outcome'] in('answer','unavailable_data')]
def facts(x):
    b=x.get('bul') or []
    b=[(y if isinstance(y,str) else (y.get('text') or json.dumps(y)) if isinstance(y,dict) else str(y)) for y in b]
    return (x['headline']+" "+" ".join(b))[:1200]
def one(a):
    x,mk=a; model,lora=MODELS[mk]; f=facts(x)
    ans=call(model,[{"role":"system","content":SYS},{"role":"user","content":"Verified facts: "+f+"\n\nQuestion: "+x['q']}],lora)
    allowed=nums(f)|nums(x['q'])
    inv=sorted(n for n in nums(ans) if n not in allowed and n!='2026')
    ALLOW=set("In The I A An It This That There No PMS Overall Score Monthly Review Employee Top Best Lowest Weakest Which What Who How Is Are Was Were And Or For Of To On At By With Yes You Let Try My Give Tell Please Egypt UAE KSA All Branches Root".split())
    cap=set(re.findall(r"\b[A-Z][a-zA-Z&\-]{2,}\b",ans)); known=set(re.findall(r"[A-Za-z&\-]+",f+" "+x['q']))
    inv_names=sorted(w for w in cap if w not in known and w not in ALLOW)
    hl=nums(x['headline']); hit=len(hl&nums(ans))
    ok=(not inv) and (not inv_names) and (not ans.startswith("ERR")) and (len(hl)==0 or hit>=0.9*len(hl))
    return dict(i=x['i'],mk=mk,src=x['src'],outcome=x['outcome'],q=x['q'],a=ans,inv=inv,inv_names=inv_names,hl=len(hl),hit=hit,ok=ok,words=len(ans.split()))
with cf.ThreadPoolExecutor(8) as ex: res=list(ex.map(one,[(x,m) for x in use for m in MS]))
json.dump(res,open(os.environ['OUT'],'w'),ensure_ascii=False)
for m in MS:
    s=[r for r in res if r['mk']==m]
    print(m,"n",len(s),"ok",sum(r['ok'] for r in s),f"{100*sum(r['ok'] for r in s)/len(s):.1f}%","invented_items",sum(bool(r['inv']) for r in s),"invented_name_items",sum(bool(r['inv_names']) for r in s),"recall",sum(r['hit'] for r in s),"/",sum(r['hl'] for r in s),"words",sum(r['words'] for r in s)//len(s))
    for k in sorted(set((r['src'],r['outcome']) for r in s),key=str):
        t=[r for r in s if (r['src'],r['outcome'])==k]; print("   ",k,sum(r['ok'] for r in t),"/",len(t))
