"""v5 = v4 rows + synthetic multi-fact rows in the style of the app's real answer payloads.
Gap found in live questions: v4 never invents numbers but drops secondary facts (lowest team, followed-by list,
evaluated count). New rows teach it to restate every number in the verified facts. All values are synthetic."""
import json,random
random.seed(5)
SYS=json.loads(open('grounded_train.jsonl').readline())['messages'][0]['content']
MON=["January","February","March","April","May","June","July","August","September","October"]
TEAMS=["Finance","CSR","Inbound","Outbound","Marketing","Billing","Retention","Support","Sales Ops","Quality","Pre-Approvals IP","Collections"]
FN=["Omar","Hala","Tarek","Salma","Walid","Mona","Adel","Heba","Ziad","Rana","Sami","Dalia","Hassan","Nour","Farah","Laila","Yusuf","Amal","Khaled","Suha"]
LN=["Haddad","Rahman","Saleh","Nasser","Farouk","Mahmoud","Zaki","Khoury","Sabry","Anwar","Hamdan","Ghanem","Badawi"]
nm=lambda:random.choice(FN)+" "+random.choice(LN)
per=lambda:random.choice(MON)+" 2026"
sg=lambda d:("+" if d>=0 else "")+f"{d:.1f}"
rows=[]
def add(f,q,a):
    rows.append({"messages":[{"role":"system","content":SYS},{"role":"user","content":f"Verified facts: {f}\n\nQuestion: {q}"},{"role":"assistant","content":a}],"meta":{"id":f"v5_{len(rows):04d}","cat":"multi_fact","source":"synthetic","type":"grounded"}})
for _ in range(110):  # company overall
    p=per(); s=round(random.uniform(60,92),1); d=round(random.uniform(-9,9),1); n=random.randint(40,340); lo=random.choice(TEAMS); ls=round(random.uniform(35,80),1); ld=round(random.uniform(-8,8),1); k=random.randint(1,40); of=k+random.randint(0,20)
    f=f"Overall performance in {p} averages {s}% ({sg(d)} pts vs prior month) across {n} evaluated employees; {lo} has the lowest score at {ls}% ({sg(ld)} pts vs prior month), with {k} of {of} agents below target."
    a=f"Overall performance in {p} averages {s}% ({sg(d)} pts vs prior month) across {n} evaluated employees. {lo} has the lowest score at {ls}% ({sg(ld)} pts vs prior month), with {k} of {of} agents below target."
    add(f,random.choice([f"what is the overall company score for {p}",f"how did the company do in {p}",f"company summary {p}"]),a)
for _ in range(90):  # attention list
    p=per(); a1,a2,a3=random.sample(TEAMS,3); s=sorted([round(random.uniform(38,85),1) for _ in range(3)])
    f=f"{a1} needs the most attention in {p} with the lowest team score of {s[0]}% across All authorized departments, followed by {a2} at {s[1]}% and {a3} at {s[2]}%."
    a=f"{a1} needs the most attention in {p} with the lowest team score of {s[0]}%, followed by {a2} at {s[1]}% and {a3} at {s[2]}%."
    add(f,random.choice([f"which teams need attention in {p}",f"who needs attention in {p}",f"weakest teams {p}"]),a)
for _ in range(60):  # tied lowest
    p=per(); a1,a2=random.sample(TEAMS,2); s=round(random.uniform(50,88),1)
    f=f"{p} across All authorized departments, {a1} and {a2} need the most attention as the tied lowest-scoring teams at {s}% average team score."
    add(f,f"which teams need attention in {p}",f"{a1} and {a2} need the most attention in {p}. They are the tied lowest-scoring teams at {s}%.")
for _ in range(110):  # top / bottom employee with team and score
    p=per(); n=nm(); t=random.choice(TEAMS); s=round(random.uniform(50,99),2); top=random.random()<.5; of=random.randint(4,60)
    word="top" if top else "lowest scoring"
    f=f"{n} is the {word} employee in {t} in {p} with an average score of {s}% (rank {1 if top else of} of {of})."
    a=f"{n} is the {word} employee in {t} in {p}, with an average score of {s}% (rank {1 if top else of} of {of})."
    add(f,random.choice([f"who is the {'top' if top else 'lowest scoring'} employee in {t} for {p}",f"{'best' if top else 'weakest'} performer in {t} {p}"]),a)
for _ in range(110):  # team score with count and delta
    p=per(); t=random.choice(TEAMS); s=round(random.uniform(45,95),1); d=round(random.uniform(-10,10),1); n=random.randint(5,80); r=random.randint(1,14)
    f=f"{t} scored {s}% in {p} ({sg(d)} pts vs prior month) across {n} evaluated employees, ranking {r} of 14 teams."
    add(f,random.choice([f"how is {t} doing in {p}",f"what was the {t} team score in {p}",f"summary of {t} for {p}"]),f"{t} scored {s}% in {p} ({sg(d)} pts vs prior month) across {n} evaluated employees, ranking {r} of 14 teams.")
for _ in range(80):  # compare two teams
    p=per(); a1,a2=random.sample(TEAMS,2); s1,s2=round(random.uniform(45,95),1),round(random.uniform(45,95),1)
    hi,lo=(a1,a2) if s1>=s2 else (a2,a1)
    f=f"{a1} scored {s1}% and {a2} scored {s2}% in {p}."
    add(f,f"compare {a1} and {a2} in {p}",f"In {p}, {a1} scored {s1}% and {a2} scored {s2}%. {hi} is ahead by {abs(round(s1-s2,1))} points." if s1!=s2 else f"In {p}, {a1} and {a2} both scored {s1}%.")
for _ in range(60):  # change between months
    t=random.choice(TEAMS); m1,m2=random.sample(MON,2); s1,s2=round(random.uniform(45,95),1),round(random.uniform(45,95),1)
    f=f"{t} scored {s1}% in {m1} 2026 and {s2}% in {m2} 2026."
    add(f,f"how did {t} change from {m1} to {m2} 2026",f"{t} scored {s1}% in {m1} 2026 and {s2}% in {m2} 2026, a change of {sg(round(s2-s1,1))} points.")
random.shuffle(rows)
with open('grounded_train_v5.jsonl','w') as o:
    for l in open('grounded_train_v4.jsonl'): o.write(l)
    for r in rows: o.write(json.dumps(r,ensure_ascii=False)+"\n")
print(len(rows))
