use std::collections::HashSet;
pub struct ModerationResult { pub score:u32, pub category:&'static str, pub matched:Vec<String> }
pub fn analyze(input:&str)->ModerationResult{
 let n=input.to_lowercase().replace('أ',"ا").replace('إ',"ا").replace('آ',"ا").replace('ـ',"");
 let risks=[("تهديد",35),("تهديدك",40),("اقتل",45),("بقتل",50),("اذبح",60),("ابيد",60),("تفجير",65),("متفجر",65),("ابتزاز",55),("دوكس",50),("dox",50),("doxxing",55),("kill",45),("murder",55),("threat",35),("bomb",65),("explosive",65),("blackmail",55)];
 let insults:HashSet<&str>=["fuck","fucking","bitch","idiot","stupid","moron","كلب","غبي","تافه","حمار","قذر","وصخ"].into_iter().collect();
 let mut score=0; let mut matched=Vec::new();
 for(w,s)in risks{if n.split_whitespace().any(|x|x==w){score+=s;matched.push(w.to_string());}}
 for w in n.split_whitespace(){if insults.contains(w){score+=12;matched.push(w.to_string());}}
 if matched.len()>=2{score+=10} score=score.min(100);
 let category=if score>=70{"high_risk"}else if score>=40{"moderate"}else if score>0{"low_risk"}else{"clean"};
 ModerationResult{score,category,matched}
}