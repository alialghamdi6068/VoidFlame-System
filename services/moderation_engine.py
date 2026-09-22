import re
import unicodedata
from dataclasses import dataclass

AR = {
    "تهديد":35,"تهديدك":40,"اقتل":45,"بقتل":50,"اذبح":55,"ابيد":55,
    "تفجير":60,"متفجر":60,"ابتزاز":50,"دوكس":45,"دكس":45,
}
EN = {
    "kill":45,"killing":50,"murder":55,"threat":35,"threaten":40,
    "bomb":60,"explosive":60,"blackmail":50,"dox":45,"doxxing":50,
}
INSULTS={"fuck","fucking","bitch","idiot","stupid","moron","كلب","غبي","تافه","حمار","قذر","وصخ"}
ZERO_WIDTH=re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
URL_RE=re.compile(r"(?:https?://|discord\.gg/|www\.)\S+",re.I)

@dataclass(frozen=True)
class Result:
    score:int
    confidence:float
    category:str
    matched:list
    reason:str

class ModerationEngine:
    def normalize(self,text):
        text=unicodedata.normalize("NFKC",text or "")
        text=ZERO_WIDTH.sub("",text).replace("ـ","").lower()
        text=re.sub(r"[\u064b-\u065f\u0670]","",text)
        text=text.translate(str.maketrans({"0":"o","1":"i","3":"e","4":"a","5":"s","7":"t","8":"b","@":"a","$":"s"}))
        text=text.replace("أ","ا").replace("إ","ا").replace("آ","ا")
        text=re.sub(r"(.)\1{2,}",r"\1\1",text)
        text=re.sub(r"[^\w\s\u0600-\u06ff]"," ",text,flags=re.UNICODE)
        return re.sub(r"\s+"," ",text).strip()

    def analyze(self,content):
        n=self.normalize(content)
        score=0; matched=[]
        for word,weight in {**AR,**EN}.items():
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)",n):
                score+=weight; matched.append(word)
        for word in INSULTS:
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)",n):
                score+=12; matched.append(word)
        if URL_RE.search(content) and any(x in n for x in ("free","gift","nitro","discord")):
            score+=12; matched.append("suspicious_link")
        if len(matched)>=2: score+=10
        score=min(100,score)
        category="high_risk" if score>=70 else "moderate" if score>=40 else "low_risk" if score else "clean"
        confidence=min(.99,.50+score/200+(0.08 if len(matched)>=2 else 0))
        return Result(score,confidence,category,matched[:8],"أنماط مرصودة: "+", ".join(matched[:8]) if matched else "لم يتم رصد نمط مخالف.")
