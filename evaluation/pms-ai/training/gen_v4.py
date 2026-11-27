"""Builds grounded_train_v4.jsonl = grounded_train.jsonl + extra synthetic rows.
Extras target v3 failures: invented numbers with no facts, 'rank #1 of 1', prompt echo,
ranking answers given as plain-text facts, and period mismatch. All data is synthetic."""
import json,random
random.seed(4)
SYS=json.loads(open('grounded_train.jsonl').readline())['messages'][0]['content']
FN=["Omar","Hala","Tarek","Salma","Walid","Mona","Adel","Heba","Ziad","Rana","Sami","Dalia","Hassan","Nour","Ibrahim","Farah","Majed","Laila","Yusuf","Amal","Khaled","Suha","Basil","Iman"]
LN=["Haddad","Rahman","Saleh","Nasser","Farouk","Mahmoud","Zaki","Khoury","Sabry","Anwar","Mostafa","Hamdan","Ghanem","Badawi","Othman"]
TEAMS=["Inbound","Outbound","Marketing","Billing","Retention","Support","Sales Ops"]
MON=["January","February","March","April","May","June","July","August","September","October"]
def nm(): return random.choice(FN)+" "+random.choice(LN)
def per(): return random.choice(MON)+" 2026"
def grade(s): return "A" if s>=90 else "B" if s>=80 else "C" if s>=70 else "D"
REF=["I need to look that up in the PMS data first, so I can't give a figure yet. Which period and team or employee should I use?",
"I don't have verified data for that in this message. Let me pull it from PMS before stating any score or ranking.",
"I can't answer that from memory. Give me the period and scope and I will check the verified PMS data."]
rows=[]
def add(u,a,t):
    rows.append({"messages":[{"role":"system","content":SYS},{"role":"user","content":u},{"role":"assistant","content":a}],"meta":{"id":f"v4_{len(rows):04d}","cat":t,"source":"synthetic","type":t}})
QS=["what is {n}'s score in {p}","how did {n} score in {p}?","show me {n}'s overall score for {p}","{n}'s overall PMS score, {p}","what did {n} get in {p}?","how is {n} doing in {p}","what was {n}'s PMS score in {p[0]}?","give me {n}'s rating for {p}","{n} score {p}"]
def q(n,p): 
    s=random.choice(QS); return s.replace("{p[0]}",p.split()[0]).format(n=n,p=p)
# 1 closed-book employee questions -> refuse (no numbers)
for _ in range(220):
    n,p=nm(),per(); a=random.choice(REF)
    add(random.choice(["Verified facts: none\n\nQuestion: ","Question: ",""])+q(n,p) if False else "Verified facts: none\n\nQuestion: "+q(n,p),a,"refusal")
for _ in range(60):  # bare question, no facts line
    add(q(nm(),per()),random.choice(REF),"refusal")
RQ=["who is the top employee in {t} in {p}","bottom agent in {t} for {p}","lowest scoring person in {t} {p}","best performer in {t} {p}","which team is lowest in {p}?","what is {t}'s average score in {p}","compare {t} and {u} in {p}","how did the company do in {p}"]
for _ in range(80):
    t,u=random.sample(TEAMS,2); add("Verified facts: none\n\nQuestion: "+random.choice(RQ).format(t=t,u=u,p=per()),random.choice(REF),"refusal")
# 2 grounded JSON facts; rank only when of>1
for _ in range(220):
    n,p=nm(),per(); s=round(random.uniform(52,99),1); f={"employee":n,"score_pct":str(s),"period":p}
    r=random.random(); txt=f"{n} scored {s}% in {p}."
    if r<.4: f["grade"]=grade(s); txt=f"{n} scored {s}% (Grade {grade(s)}) in {p}."
    if r<.25:
        of=random.choice([1,1,2,3,5,8]); f.update(grade=grade(s),rank=random.randint(1,of),of=of,scope=random.choice(TEAMS))
        txt=f"{n} scored {s}% (Grade {grade(s)}) in {p}."
        if of>1: txt+=f" That is rank #{f['rank']} of {of} in {f['scope']}."
    add("Verified facts: "+json.dumps(f)+"\n\nQuestion: "+q(n,p),txt,"grounded")
# 3 prose-format facts (as the eval harness sends them)
for _ in range(160):
    n,p=nm(),per(); s=round(random.uniform(52,99),1); qq=q(n,p)
    add(f"Verified facts: {n} scored {s} in {p} (Grade {grade(s)}).\n\nQuestion: {qq}",f"{n} scored {s}% in {p} (Grade {grade(s)}).","grounded")
    if _%2==0: add(f"Verified facts: {n} scored {s} in {p}.\n\nQuestion: {qq}",f"{n} scored {s}% in {p}.","grounded")
# 4 ranking questions with prose facts
TB=[("who is the top employee in {t} in {p}","the top employee in {t}"),("best performer in {t} {p}","the best performer in {t}"),("top agent in {t} for {p}","the top agent in {t}"),
    ("lowest scoring person in {t} {p}","the lowest scoring person in {t}"),("bottom agent in {t} for {p}","the bottom agent in {t}"),("weakest performer in {t} {p}","the weakest performer in {t}")]
for _ in range(120):
    n,p,t=nm(),per(),random.choice(TEAMS); qt,at=random.choice(TB); sc=random.random()<.5; s=round(random.uniform(52,99),1)
    if sc: f=f"Verified facts: {n} scored {s} in {p} (Grade {grade(s)}).\n\nQuestion: "; a=f"{n} is {at.format(t=t)} in {p}, with {s}% (Grade {grade(s)})."
    else: f=f"Verified facts: {n} is the answer to this ranking question (score not provided).\n\nQuestion: "; a=f"{n} is {at.format(t=t)} in {p}. The score was not provided."
    add(f+qt.format(t=t,p=p),a,"grounded")
# 5 period mismatch
for _ in range(60):
    n=nm(); p1,p2=random.sample([m+" 2026" for m in MON],2); s=round(random.uniform(52,99),1)
    add(f"Verified facts: {n} scored {s} in {p1}.\n\nQuestion: {q(n,p2)}",f"I only have verified data for {p1} ({n} scored {s}%). I don't have {p2}, so I can't give that score.","grounded")
base=open('grounded_train.jsonl').read().splitlines()
random.shuffle(rows)
with open('grounded_train_v4.jsonl','w') as o:
    for l in base: o.write(l+"\n")
    for r in rows: o.write(json.dumps(r,ensure_ascii=False)+"\n")
print(len(base),len(rows))
