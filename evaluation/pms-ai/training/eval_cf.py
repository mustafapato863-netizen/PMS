# Held-out eval against Cloudflare Workers AI. Usage: CF_TOKEN_FILE=... HELD=question_bank/heldout_questions.jsonl python3 eval_cf.py <model_key> <start> <end>
# model keys: current_granite, mistral_base, adapter_v2, adapter_v3, adapter_v4. Gate: 0 invented numbers closed-book and grounded, all required facts present.
import json,os,re,sys,time,urllib.request,concurrent.futures as cf
TOK=open(os.environ['CF_TOKEN_FILE']).read().strip()  # path to a file holding the Cloudflare Workers AI token; never commit it
A="2c7adc94f3a187ed9aec95d44ae54e94"
rows=[json.loads(l) for l in open(__import__('os').environ.get('HELD','heldout_questions.jsonl')) if l.strip()]
SYS=("You are the PMS performance assistant. Use ONLY the verified facts given in the message. "
"If no verified facts are given, say you need to look the data up and do not state any score, rank or name. Never invent numbers.")
def call(model,msgs,lora=None):
    body={"messages":msgs,"max_tokens":220,"temperature":0}
    if lora: body["lora"]=lora
    req=urllib.request.Request(f"https://api.cloudflare.com/client/v4/accounts/{A}/ai/run/{model}",json.dumps(body).encode(),{"Authorization":"Bearer "+TOK,"content-type":"application/json"})
    for i in range(3):
        try:
            r=json.load(urllib.request.urlopen(req,timeout=60))
            res=r.get("result",{})
            if "choices" in res: return res["choices"][0]["message"]["content"] or ""
            return res.get("response") or ""
        except Exception as e:
            err=str(e)
            if hasattr(e,'read'):
                try: err=e.read().decode()[:200]
                except: pass
            if '429' in err or 'neuron' in err.lower(): return "ERR_LIMIT "+err
            time.sleep(2)
    return "ERR "+err
MODELS={"current_granite":("@cf/ibm-granite/granite-4.0-h-micro",None),
        "mistral_base":("@cf/mistral/mistral-7b-instruct-v0.2-lora",None),
        "adapter_v2":("@cf/mistral/mistral-7b-instruct-v0.2-lora","pms-assistant-v2"),
        "adapter_v3":("@cf/mistral/mistral-7b-instruct-v0.2-lora","pms-assistant-v3"),
        "adapter_v4":("@cf/mistral/mistral-7b-instruct-v0.2-lora","pms-assistant-v4")}
num=re.compile(r'\d+(?:\.\d+)?')
def nums(s): return set(num.findall(s))
MONS="January February March April May June July August September October November December".split()
def PER(r):
    for m in MONS:
        if m.lower() in r['prompt'].lower(): return m+" 2026"
    return "September 2026"
def tasks():
    t=[]
    for r in rows:
        t.append(("closed",r,None))
        if r['cat'] in('employee_score','top_employee','bottom_employee'):
            names=[a[0] for a in r.get('all_of',[]) if a and not num.search(a[0])]
            sc=[a[0] for a in r.get('all_of',[]) if a and num.search(a[0])]
            ev="Verified facts: "+"; ".join(names)+(" scored "+sc[0]+" in "+PER(r)+" (Grade A)." if sc else " is the answer to this ranking question (score not provided).")
            t.append(("grounded",r,ev))
    return t
T=tasks()[int(sys.argv[2]):int(sys.argv[3])]
def run(mk):
    model,lora=MODELS[mk]; out=[]
    def one(t):
        kind,r,ev=t
        u=r['prompt'] if kind=="closed" else ev+"\n\nQuestion: "+r['prompt']
        a=call(model,[{"role":"system","content":SYS},{"role":"user","content":u}],lora)
        qn=nums(r['prompt'])|(nums(ev) if ev else set())
        inv=sorted(n for n in nums(a) if n not in qn and n not in('2026',))
        ok_all=all(any(x.lower() in a.lower() for x in alt) for alt in r.get('all_of',[]))
        bad=[x for x in r.get('none_of',[]) if x.lower() in a.lower()]
        return dict(model=mk,kind=kind,id=r['id'],cat=r['cat'],q=r['prompt'],a=a,invented=inv,has_required=ok_all,forbidden=bad,err=a.startswith("ERR"))
    with cf.ThreadPoolExecutor(10) as ex: out=list(ex.map(one,T))
    return out
mk=sys.argv[1]
res=run(mk)
json.dump(res,open(__import__("os").environ.get("PFX","")+f"res_{mk}_{sys.argv[2]}.json","w"),ensure_ascii=False)
for kind in("closed","grounded"):
    s=[x for x in res if x['kind']==kind]
    if not s: continue
    print(mk,kind,"n",len(s),"errs",sum(x['err'] for x in s),"invented_numbers",sum(bool(x['invented']) for x in s),"forbidden",sum(bool(x['forbidden']) for x in s),"required_present",sum(x['has_required'] for x in s))
