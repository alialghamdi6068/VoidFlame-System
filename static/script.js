document.addEventListener('DOMContentLoaded',()=>{
const form=document.getElementById('system-form') || document.getElementById('settings-form');
const result=document.getElementById('result');
const saveButton=document.getElementById('save-settings');
const csrfToken=document.querySelector('meta[name="csrf-token"]')?.content || '';

function snapshot(){
  if(!form)return '';
  const data={};
  new FormData(form).forEach((v,k)=>data[k]=v);
  form.querySelectorAll('input[type=checkbox]').forEach(x=>data[x.name]=x.checked);
  return JSON.stringify(data);
}
let initialState=snapshot();
function markChanged(){const changed=snapshot()!==initialState;if(saveButton){saveButton.hidden=!changed;saveButton.disabled=!changed;}if(result&&changed)result.textContent='';}

async function save(payload){
  const guildId=String(window.FLAME_GUILD||'').trim();
  if(!/^[0-9]+$/.test(guildId))throw new Error('invalid guild');
  const r=await fetch(`/api/guild/${guildId}/settings`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},credentials:'same-origin',body:JSON.stringify(payload)});
  if(r.status===403)throw new Error('csrf');
  return await r.json();
}

function removeTicketEmojiFields(){if(!form)return;form.querySelectorAll('[name^="ticket_button_emoji_"]').forEach(input=>{const label=input.closest('label');if(label)label.remove();else input.remove();});}
function removeTicketFooterField(){if(!form)return;form.querySelectorAll('[name="ticket_panel_footer"]').forEach(input=>{const label=input.closest('label');if(label)label.remove();else input.remove();});}

const SYSTEM_TOGGLES={welcome:'welcome_enabled',tickets:'tickets_enabled',applications:'applications_enabled',levels:'levels_enabled',autoreply:'autoreply_enabled',giveaways:'giveaways_enabled',suggestions:'suggestions_enabled',logs:'logs_enabled',autorole:'autorole_enabled',announcements:'announcements_enabled',reminders:'reminders_enabled',scheduler:'scheduler_enabled',afk:'afk_enabled'};
const SYSTEM_NAMES={welcome:'الترحيب',tickets:'التذاكر',applications:'التقديمات',levels:'المستويات',autoreply:'الردود التلقائية',giveaways:'القيفاواي',suggestions:'الاقتراحات',logs:'اللوق',autorole:'الرتبة التلقائية',announcements:'الإعلانات',reminders:'التذكيرات',scheduler:'الجدولة',afk:'الغياب'};

async function addSystemToggle(){
  if(!form||!location.pathname.includes('/system/'))return;
  const system=location.pathname.split('/').pop();
  const field=SYSTEM_TOGGLES[system];
  if(!field||form.querySelector(`[name="${field}"]`))return;
  const wrap=document.createElement('section');
  wrap.className='panel system-toggle-panel';
  wrap.innerHTML=`<div class="form-grid"><label class="check"><input type="checkbox" name="${field}" checked> تفعيل نظام ${SYSTEM_NAMES[system]}</label></div>`;
  form.prepend(wrap);
  try{
    const guildId=String(window.FLAME_GUILD||'').trim();
    if(/^[0-9]+$/.test(guildId)){
      const r=await fetch(`/api/guild/${guildId}/settings`,{credentials:'same-origin'});
      const d=await r.json();
      if(d.ok&&d.settings&&Object.prototype.hasOwnProperty.call(d.settings,field))wrap.querySelector(`[name="${field}"]`).checked=Boolean(d.settings[field]);
    }
  }catch(e){}
  initialState=snapshot();
  markChanged();
}

function addProtectionSettings(){
  if(!form||!location.pathname.endsWith('/system/ai')||form.querySelector('.protection-advanced'))return;
  const panel=document.createElement('section');
  panel.className='panel protection-advanced';
  panel.innerHTML='<h3>🛡️ إعدادات الحماية المتقدمة</h3><div class="form-grid"><label>إجراء تغييرات الرومات والرتب<select name="mass_change_action"><option value="log">تسجيل فقط</option><option value="kick">طرد المنفذ</option></select></label><label>إجراء Anti-Raid<select name="raid_action"><option value="timeout">Timeout</option><option value="log">تسجيل فقط</option></select></label><label>إجراء Anti-Spam<select name="protection_action"><option value="timeout">Timeout</option><option value="kick">Kick</option></select></label><label class="check"><input type="checkbox" name="mass_change_lockdown"> قفل السيرفر تلقائياً عند التغيير الجماعي</label><label class="check"><input type="checkbox" name="webhook_protection"> حماية Webhooks</label><label class="check"><input type="checkbox" name="permission_change_protection"> حماية صلاحيات الرومات والرتب</label><label class="check"><input type="checkbox" name="guild_update_protection"> مراقبة تغييرات إعدادات السيرفر</label><label class="wide">المستخدمون الموثوقون (IDs مفصولة بفواصل)<input name="trusted_user_ids"></label><label class="wide">الرتب الموثوقة (IDs مفصولة بفواصل)<input name="trusted_role_ids"></label><label class="wide">رومات تجاهل الحماية (IDs مفصولة بفواصل)<input name="protection_ignore_channels"></label><label class="wide">رتب تجاهل الحماية (IDs مفصولة بفواصل)<input name="protection_ignore_roles"></label><label class="wide">رومات تجاهل AI (IDs مفصولة بفواصل)<input name="ai_ignore_channels"></label><label class="wide">رتب تجاهل AI (IDs مفصولة بفواصل)<input name="ai_ignore_roles"></label></div><p>اكتب IDs مفصولة بفواصل، مثال: 123,456,789.</p>';
  form.appendChild(panel);
  const csv=['trusted_user_ids','trusted_role_ids','protection_ignore_channels','protection_ignore_roles','ai_ignore_channels','ai_ignore_roles'];
  fetch('/api/guild/'+String(window.FLAME_GUILD)+'/settings',{credentials:'same-origin'}).then(r=>r.json()).then(d=>{
    if(!d.ok)return; const s=d.settings||{};
    ['mass_change_action','raid_action','protection_action'].forEach(k=>{const x=panel.querySelector('[name="'+k+'"]');if(x&&s[k])x.value=s[k];});
    ['mass_change_lockdown','webhook_protection','permission_change_protection','guild_update_protection'].forEach(k=>{const x=panel.querySelector('[name="'+k+'"]');if(x&&Object.prototype.hasOwnProperty.call(s,k))x.checked=Boolean(s[k]);});
    csv.forEach(k=>{const x=panel.querySelector('[name="'+k+'"]');if(x)x.value=Array.isArray(s[k])?s[k].join(','):'';});
    initialState=snapshot(); markChanged();
  }).catch(()=>{});
}
function buildSpecialPayload(p){
  ['trusted_user_ids','trusted_role_ids','protection_ignore_channels','protection_ignore_roles','ai_ignore_channels','ai_ignore_roles'].forEach(k=>{
    if(p[k]!==undefined)p[k]=String(p[k]).split(',').map(x=>x.trim()).filter(x=>/^\d+$/.test(x)).slice(0,100);
  });
  removeTicketEmojiFields();
  removeTicketFooterField();
  if(document.querySelector('[name="ticket_button_label_1"]')){const buttons=[];for(let i=1;i<=5;i++){const label=document.querySelector(`[name="ticket_button_label_${i}"]`)?.value.trim()||'';if(!label)continue;buttons.push({label,style:document.querySelector(`[name="ticket_button_style_${i}"]`)?.value||'success',category_id:document.querySelector(`[name="ticket_button_category_${i}"]`)?.value||'',support_role_id:document.querySelector(`[name="ticket_button_role_${i}"]`)?.value||'',title:document.querySelector(`[name="ticket_button_title_${i}"]`)?.value.trim()||'',description:document.querySelector(`[name="ticket_button_description_${i}"]`)?.value.trim()||''});}for(let i=1;i<=5;i++){delete p[`ticket_button_label_${i}`];delete p[`ticket_button_emoji_${i}`];delete p[`ticket_button_style_${i}`];delete p[`ticket_button_category_${i}`];delete p[`ticket_button_role_${i}`];delete p[`ticket_button_title_${i}`];delete p[`ticket_button_description_${i}`];}p.ticket_buttons=buttons;}
  if(document.querySelector('[name="level_reward_1"]')){const rewards={};for(let i=1;i<=20;i++){const value=document.querySelector(`[name="level_reward_${i}"]`)?.value||'';if(value)rewards[String(i)]=value;delete p[`level_reward_${i}`];}p.level_rewards=rewards;}return p;
}
function addVariablePanel(){if(!form||!location.pathname.includes('/system/'))return;const system=location.pathname.split('/').pop();const configs={welcome:{title:'المتغيرات المتاحة للترحيب',help:'انسخ المتغير وضعه داخل رسالة الترحيب، وسيتم استبداله تلقائياً عند دخول العضو.',items:[['{member}','منشن العضو'],['{username}','اسم العضو'],['{server}','اسم السيرفر'],['{members}','عدد أعضاء السيرفر'],['{inviter}','الشخص الذي دعا العضو'],['{count}','عدد الأعضاء (قديم ومتوافق)']]},tickets:{title:'المتغيرات المتاحة للتذاكر',help:'تقدر تستخدمها داخل عنوان أو رسالة التذكرة.',items:[['{member}','منشن صاحب التذكرة'],['{username}','اسم صاحب التذكرة'],['{server}','اسم السيرفر'],['{ticket}','رقم التذكرة مع #'],['{number}','رقم التذكرة بدون إضافات'],['{category}','قسم التذكرة'],['{support}','رتبة الدعم']]}};const config=configs[system];if(!config)return;const target=form.querySelector('textarea[name="welcome_message"]')||form.querySelector('textarea[name="ticket_button_description_1"]')||form.querySelector('textarea[name="ticket_panel_description"]');if(!target||form.querySelector('.flame-variables'))return;const panel=document.createElement('div');panel.className='panel flame-variables';panel.style.marginTop='12px';panel.innerHTML=`<h3>${config.title}</h3><p>${config.help}</p><div class="flame-variable-list"></div>`;const list=panel.querySelector('.flame-variable-list');config.items.forEach(([value,label])=>{const row=document.createElement('div');row.className='flame-variable-row';row.innerHTML=`<code>${value}</code><span>${label}</span><button type="button" class="purple-btn flame-copy">نسخ</button>`;row.querySelector('.flame-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(value);row.querySelector('.flame-copy').textContent='تم النسخ';setTimeout(()=>row.querySelector('.flame-copy').textContent='نسخ',1200);}catch(e){target.focus();document.execCommand('insertText',false,value);}});list.appendChild(row);});target.closest('label')?.insertAdjacentElement('afterend',panel);}

removeTicketEmojiFields();
removeTicketFooterField();
addSystemToggle();
addVariablePanel();
addProtectionSettings();
if(form){form.addEventListener('input',markChanged);form.addEventListener('change',markChanged);form.addEventListener('submit',async e=>{e.preventDefault();if(snapshot()===initialState)return;if(saveButton)saveButton.disabled=true;const p={};new FormData(form).forEach((v,k)=>p[k]=v);form.querySelectorAll('input[type=checkbox]').forEach(x=>p[x.name]=x.checked);['xp_min','xp_max','level_cooldown','log_rate_limit','spam_window_seconds','spam_message_limit','mention_limit','raid_window_seconds','raid_join_threshold','raid_timeout_minutes','mass_change_window_seconds','mass_change_threshold','protection_timeout_minutes'].forEach(k=>{if(p[k]!==undefined&&p[k]!=='')p[k]=Number(p[k]);});buildSpecialPayload(p);try{const d=await save(p);if(d.ok){initialState=snapshot();if(saveButton){saveButton.hidden=true;saveButton.disabled=true;}if(result)result.textContent='✓ تم الحفظ بنجاح.';}else{if(saveButton)saveButton.disabled=false;if(result)result.textContent='✕ '+(d.error||'تعذر الحفظ');}}catch(err){if(saveButton)saveButton.disabled=false;if(result)result.textContent=err.message==='csrf'?'✕ انتهت جلسة الأمان، حدّث الصفحة ثم حاول مرة أخرى.':'✕ تعذر الاتصال بالسيرفر.';}});}
markChanged();
const add=document.getElementById('add-reply');if(add)add.onclick=async()=>{const t=document.getElementById('reply-trigger'),r=document.getElementById('reply-response');if(!t.value.trim()||!r.value.trim())return alert('اكتب الكلمة والرد أولاً.');const d=await save({autoreply_action:'add',trigger:t.value.trim(),response:r.value.trim()});if(d.ok)location.reload();else alert(d.error||'تعذر الإضافة');};
document.querySelectorAll('.delete-reply').forEach(b=>b.onclick=async()=>{if(!confirm('حذف هذا الرد؟'))return;const d=await save({autoreply_action:'delete',trigger:b.dataset.trigger});if(d.ok)location.reload();else alert(d.error||'تعذر الحذف');});
});
