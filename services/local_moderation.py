import re
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass

ARABIC_RISK = {"تهديد":35,"تهديدك":40,"اقتل":45,"بقتل":50,"انتحار":70,"اذبح":60,"ابيد":60,"تفجير":65,"متفجر":65,"ابتزاز":55,"دوكس":50,"دكس":50}
ENGLISH_RISK = {"kill":45,"killing":50,"murder":55,"threat":35,"threaten":40,"suicide":70,"bomb":65,"explosive":65,"blackmail":55,"dox":50,"doxxing":55,"rape":60}
INSULTS = {"fuck","fucking","bitch","idiot","stupid","moron","كلب","غبي","تافه","حمار","قذر","وصخ"}
ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
REPEATED = re.compile(r"(.)\1{3,}", re.UNICODE)
URL_RE = re.compile(r"(?:https?://|discord\.gg/|www\.)\S+", re.I)

@dataclass
class ModerationResult:
    score: int
    confidence: float
    category: str
    matched: list[str]
    reason: str

class LocalModerationEngine:
    def __init__(self):
        self.history = defaultdict(lambda: deque(maxlen=12))

    @staticmethod
    def normalize(text):
        text = unicodedata.normalize("NFKC", text or "")
        text = ZERO_WIDTH.sub("", text).replace("ـ","")
        text = re.sub(r"[\u064B-\u065F\u0670]","",text).lower()
        text = text.translate(str.maketrans({"0":"o","1":"i","3":"e","4":"a","5":"s","7":"t","8":"b","@":"a","$":"s"}))
        text = re.sub(r"[^\w\s\u0600-\u06ff]"," ",text,flags=re.UNICODE)
        text = REPEATED.sub(r"\1\1",text)
        return re.sub(r"\s+"," ",text).strip()

    def analyze(self, content):
        normalized=self.normalize(content)
        tokens=set(normalized.split())
        score=0
        matched=[]
        for word,weight in {**ARABIC_RISK,**ENGLISH_RISK}.items():
            if word in normalized:
                score += weight
                matched.append(word)
        hits=tokens.intersection(INSULTS)
        if hits:
            score += min(30,12*len(hits))
            matched.extend(sorted(hits))
        if URL_RE.search(content) and any(x in normalized for x in ("discord","nitro","free","gift")):
            score += 12
        if len(matched)>=2:
            score += 10
        score=max(0,min(100,score))
        category="high_risk" if score>=70 else ("moderate" if score>=40 else ("low_risk" if score else "clean"))
        confidence=min(.99,.50+score/200+(.08 if len(matched)>=2 else 0))
        reason="Matched: "+", ".join(matched[:8]) if matched else "No risky pattern detected."
        return ModerationResult(score,confidence,category,matched[:8],reason)

    def record(self,guild_id,user_id,score):
        now=time.time()
        q=self.history[(guild_id,user_id)]
        q.append((now,score))
        return len([s for t,s in q if now-t<=900])
