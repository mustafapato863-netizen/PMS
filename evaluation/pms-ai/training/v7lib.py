"""Real-format shapes for stage 3 (10k). Synthetic values; shapes copied from the live Ask AI answer styles
(long ranked lists, single-person answers, no-records answers, top-N lists, scope suffixes)."""
import json, random
from v6lib import *

LONG_FN = ["Ahmed", "Mohamed", "Mahmoud", "Sherif", "Hesham", "Nourhan", "Mariam", "Rahab", "Sherry", "Ammar", "Bahy", "Yasser", "Sanio", "Valan", "Dafine", "Ayman", "Eslam", "Mostafa", "Hadeer", "Abdelrahman", "Marwa", "Salah", "Fatma", "Sayed", "Ghada", "Joseph", "Mol", "Thomas", "Priya", "Anil", "Deepak", "Sunil", "Reshma", "Lakshmi", "Noor", "Aisha", "Zainab", "Omar", "Hamza", "Bilal"]
LONG_MID = ["Mohamed", "Abdelrashed", "Abdelkahlek", "Chirakkal", "Hassan", "Abdul", "Kumar", "George", "Thomas", "Elfeky", "Abouzeid", "Mohssen", "Amer", "Ghareb", "Punnamoottil", "Nair", "Menon", "Varghese", "Ali", "Ibrahim", "Saad", "Gamal"]
REAL_TEAMS = ["Finance", "Pharmacy", "CSR", "RCM", "Re-Submission", "Coding", "Sales", "Inbound", "Outbound", "Marketing", "PMO", "Human Resources", "Qlty&Case-Mngt", "Support Positions",
              "Pre-Approvals IP", "Pre-Approvals OP", "Pre-Approvals IP Elective Dubai", "Pre-Approvals IP Offshore", "Pre-Approvals OP Final SHJAJM", "IT", "Legal", "Billing", "Retention", "Collections", "Claims", "Escalations"]
REAL_REG = ["Egypt", "UAE", "KSA", "Jordan", "Oman", "Qatar"]
SCOPE = ["", "", " (All Branches)", " (All Branches)", " across All authorized departments"]


class G7(G):
    def __init__(self, seed):
        super().__init__(seed, held=False)

    def lname(self):
        r = self.r
        k = r.choice([2, 3, 3, 4, 5])
        parts = [r.choice(LONG_FN)] + [r.choice(LONG_MID) for _ in range(k - 2)] + [r.choice(LONG_MID + TR_LN)]
        return " ".join(parts)

    def rteam(self): return self.r.choice(REAL_TEAMS)

    def no_records(self):
        r = self.r
        t, p = self.rteam(), self.per()
        qs = r.choice(["give me the {t} picture in {p}", "how is {t} doing in {p}", "top performers in {t} for {p}", "is {t} improving between {m} and {p}", "who is the best in {t} {p}",
                       "{t} results for {p}", "what was the {t} team score in {p}", "weakest person in {t} during {p}", "how did {t} score in {p}", "{t} {p} summary please",
                       "what happened to {t} in {p}", "show {t} for {p}"]).format(t=t, p=p, m=r.choice(MON))
        f = r.choice(["No published PMS evaluation records exist for {t} in {p}.", "No performance records matched the selected filters ({t} · {p}).", "No published PMS evaluation records exist for {t} in {p}."]).format(t=t, p=p)
        a = r.choice(["No published PMS evaluation records exist for {t} in {p}, so I have no score to report.", "There are no published PMS evaluation records for {t} in {p}, so I can't give a score or ranking for it.",
                      "I don't have any published PMS records for {t} in {p}, so there is no score to share. You could try another month."]).format(t=t, p=p)
        self.add("no_records", f, qs, a, [t, p])

    def _teams(self, k):
        r = self.r
        ts = r.sample(REAL_TEAMS, k)
        sc = sorted(self.f1(38, 92) for _ in range(k))
        return ts, sc

    def long_rank(self):
        r = self.r
        p = self.per(); k = r.randint(5, 16); ts, sc = self._teams(k)
        qs = r.choice(["which teams are struggling in {p}", "rank all teams for {p}", "where should we focus in {p}", "which teams need attention in {p}", "weakest teams {p}", "lowest scoring teams in {p}",
                       "how do the teams compare in {p}", "team ranking {p}", "teams from worst to best in {p}"]).format(p=p)
        scope = r.choice([" across all authorized departments", " across All authorized departments", ""])
        style = r.random()
        if style < .5:
            items = [f"{ts[i]} ({sc[i]}%)" for i in range(1, k)]
            f = f"In {p}{scope}, {ts[0]} had the lowest Monthly Review team score at {sc[0]}%, followed by " + ", ".join(items[:-1]) + f", and {items[-1]}."
            a = f"In {p}{scope}, {ts[0]} had the lowest Monthly Review team score at {sc[0]}%, followed by " + ", ".join(items[:-1]) + f", and {items[-1]}."
            req = [ts[0], str(sc[0])] + [x for i in range(1, k) for x in (ts[i], str(sc[i]))]
            if r.random() < .3 and k > 6:  # truncated facts: restate only complete items
                cut = r.randint(3, k - 2)
                f = f"In {p}{scope}, {ts[0]} had the lowest Monthly Review team score at {sc[0]}%, followed by " + ", ".join(items[:cut]) + f", {items[cut][:r.randint(3, len(items[cut]) - 3)]}"
                a = f"In {p}{scope}, {ts[0]} had the lowest Monthly Review team score at {sc[0]}%, followed by " + ", ".join(items[:cut]) + ". The list continues beyond what I have, so I can't give the remaining teams."
                req = [ts[0], str(sc[0])] + [x for i in range(1, cut + 1) for x in (ts[i], str(sc[i]))]
        else:
            ne = [r.randint(3, 60) for _ in range(k)]
            items = [f"{ts[i]} at {sc[i]}% (rank {i + 1}, {ne[i]} employees evaluated)" for i in range(k)]
            f = f"In {p}{scope}, the teams ranked from weakest to strongest by Monthly Review team score are: " + ", ".join(items[:-1]) + f", and {items[-1]}."
            a = f"In {p}{scope}, the teams ranked from weakest to strongest by Monthly Review team score are: " + ", ".join(items[:-1]) + f", and {items[-1]}."
            req = [x for i in range(k) for x in (ts[i], str(sc[i]), str(i + 1), str(ne[i]))]
            if r.random() < .3 and k > 6:
                cut = r.randint(3, k - 2)
                f = f"In {p}{scope}, the teams ranked from weakest to strongest by Monthly Review team score are: " + ", ".join(items[:cut]) + f", {items[cut][:r.randint(3, len(items[cut]) - 3)]}"
                a = f"In {p}{scope}, the teams ranked from weakest to strongest by Monthly Review team score start with: " + ", ".join(items[:cut]) + ". The list continues beyond what I have, so I can't give the later ranks."
                req = [x for i in range(cut) for x in (ts[i], str(sc[i]), str(i + 1), str(ne[i]))]
        self.add("long_rank", f, qs, a, req)

    def single_person(self):
        r = self.r
        n, t, p = self.lname(), self.rteam(), self.per(); s = round(r.uniform(45, 99), r.choice([1, 2])); top = r.random() < .5
        w = r.choice(["top employee", "best", "top"]) if top else r.choice(["weakest", "lowest scoring person", "lowest scoring employee"])
        qs = r.choice(["who is the {w} in {t} for {p}", "best employee in {t} {p}", "weakest person in {t} during {p}", "top performers in {t} for {p}", "who is the lowest scoring person in {t} in {p}",
                       "who leads {t} in {p}", "who is struggling most in {t} in {p}", "who is the star of {t} in {p}"]).format(w=w, t=t, p=p)
        if w in ("best", "weakest"): f = f"{n} is the {w} in {t} for {p} with an Overall Score of {s}%."
        else: f = f"{n} is the {w} in {t} for {p} with an Overall Score of {s}%."
        self.add("single_person", f, qs, f, [n, str(s), t])

    def emp_list(self):
        r = self.r
        t, p = self.rteam(), self.per(); k = r.randint(2, 6); ns = [self.lname() for _ in range(k)]
        sc = sorted(round(r.uniform(45, 99), 1) for _ in range(k)); asc = r.random() < .5
        if not asc: sc = sc[::-1]
        qs = r.choice(["weakest person in {t} during {p}", "who is the lowest scoring person in {t} in {p}", "best employee in {t} {p}", "top performers in {t} for {p}", "rank the people in {t} for {p}", "how are the employees in {t} doing in {p}"]).format(t=t, p=p)
        body = ", ".join(f"{ns[i]}: {sc[i]}%" for i in range(k))
        f = f"Employee performance rankings for {t} in {p}: {body}."
        self.add("emp_list", f, qs, f, [x for i in range(k) for x in (ns[i], str(sc[i]))])

    def top_n(self):
        r = self.r
        t, p = self.rteam(), self.per(); k = r.randint(2, 6); ns = [self.lname() for _ in range(k)]
        sc = sorted((round(r.uniform(60, 99), 1) for _ in range(k)), reverse=True)
        qs = r.choice(["top performers in {t} for {p}", "who are the best employees in {t} in {p}", "top {k} in {t} {p}", "best people in {t} {p}"]).format(t=t, p=p, k=k)
        body = ", ".join(f"{i + 1}. {ns[i]} ({sc[i]}%)" for i in range(k))
        f = f"Top {k} employees in {t} for {p}: {body}."
        self.add("top_n", f, qs, f, [str(k)] + [x for i in range(k) for x in (ns[i], str(sc[i]))])

    def team_scope(self):
        r = self.r
        t, p = self.rteam(), self.per(); s = self.f1(40, 98); n = r.randint(3, 80); d = self.f1(-9, 9)
        qs = r.choice(["how is {t} doing in {p}", "what was the {t} team score in {p}", "{t} results for {p}", "give me the {t} picture in {p}", "how did {t} score in {p}"]).format(t=t, p=p)
        k = r.random()
        if k < .3: f = f"{t} scored {s}% in {p} (average published employee scores; {n} evaluated employees)."; req = [t, str(s), str(n)]
        elif k < .5: f = f"{t}'s Overall Score in {p} is {s}%."; req = [t, str(s)]
        elif k < .7: f = f"{t} team Overall Score was {s}% in {p}."; req = [t, str(s)]
        elif k < .85: f = f"{t} scored {s}% in {p}{r.choice([' (All Branches)', ' (All Branches)'])} ({sg(d)} pp change vs prior month)."; req = [t, str(s), sg(d)]
        else: f = f"{t} recorded an Overall Score of {s}% in {p}."; req = [t, str(s)]
        self.add("team_scope", f, qs, f, req)

    def region_best(self):
        r = self.r
        p, g, t = self.per(), r.choice(REAL_REG), self.rteam(); s = self.f1(50, 98)
        qs = r.choice(["best team in {g} in {p}", "which team is best in {g} in {p}", "top team in {g} for {p}", "how is {g} doing in {p}"]).format(g=g, p=p)
        k = r.random()
        f = f"{t} is the best team in {g} in {p} with a Monthly Review team score of {s}%." if k < .6 else f"{t} ranks first with a score of {s}%."
        self.add("region_best", f, qs, f, [t, str(s)])

    def rootcause(self):
        r = self.r
        t, p = self.rteam(), self.per(); s = self.f1(40, 95); m = r.choice(["Onboarding & HR Orientation Completion Rate", "Attendance Rate", "Quality Audit Score", "Customer Satisfaction"])
        qs = r.choice(["why did {t} drop in {p}", "what caused the {t} decline in {p}", "why is {t} low in {p}", "explain the {t} score in {p}"]).format(t=t, p=p)
        f = f"Root causes for {t}'s {m} ({s}% in {p}) are not directly recorded in PMS scores."
        a = f"The root causes for {t}'s {m} ({s}% in {p}) are not directly recorded in PMS scores, so I can't say why it changed."
        self.add("root_cause", f, qs, a, [t, str(s)])
