# VoidFlame System

بوت Discord مع Dashboard لإدارة أنظمة السيرفر من مكان واحد.

## الأنظمة

- 🎫 التذاكر
- 📝 التقديمات
- 📈 المستويات و XP
- 💬 الردود التلقائية
- 🎉 القيفاواي
- 💡 الاقتراحات
- 📋 اللوق وتسجيل النشاطات
- 🏷️ الرتبة التلقائية
- 👋 الترحيب
- 📢 الإعلانات
- ⏰ التذكيرات
- 🗓️ الجدولة
- 💤 الغياب
- 🛡️ أدوات الإدارة: حظر، طرد، تايم، تحذيرات، مسح، قفل وفتح الرومات

## المتطلبات

- Python 3.11 أو أحدث
- Discord Bot مع `Message Content Intent` و `Server Members Intent`
- إعدادات Discord OAuth2 **فقط إذا كنت ستستخدم الـDashboard**

## التثبيت

```bash
pip install -r requirements.txt
python bot.py
```

## إعداد الاستضافة بدون Environment Variables

إذا كانت الاستضافة لا توفر Environment Variables، **ما تحتاج توقف المشروع**.

1. انسخ `config.json.example` إلى `config.json`.
2. ضع توكن البوت في `discord_token`.
3. شغّل البوت بالأمر:
   ```bash
   python bot.py
   ```

مثال:

```json
{
  "discord_token": "YOUR_DISCORD_BOT_TOKEN",
  "owner_id": "1293157778030071920",
  "data_dir": "data",
  "database_path": "data/flame.db"
}
```

`config.json` مستثنى من Git، لذلك لا ترفعه إلى GitHub.

## Environment Variables

الـEnvironment Variables أصبحت اختيارية. إذا كانت الاستضافة تدعمها، يكفي:

```text
DISCORD_TOKEN=
```

أي قيمة موجودة في Environment Variables لها أولوية على `config.json`.

## Dashboard

الـDashboard اختياري. البوت لا يحتاج إعدادات OAuth2 لكي يعمل.

إذا أردت Dashboard، أضف داخل `config.json`:

```json
{
  "discord_token": "YOUR_DISCORD_BOT_TOKEN",
  "discord_client_id": "YOUR_CLIENT_ID",
  "discord_client_secret": "YOUR_CLIENT_SECRET",
  "discord_redirect_uri": "https://YOUR-DOMAIN/callback"
}
```

يتم إنشاء `SESSION_SECRET` تلقائيًا داخل `data/session.secret`، لذلك لا تحتاج إلى متغير بيئة له.

يتم حفظ إعدادات السيرفر وبيانات الأنظمة في SQLite عبر `DATABASE_PATH`.

## الاستضافة

المشروع يحتوي على `Procfile` و `wispbyte.json` لتشغيله بأمر:

```bash
python bot.py
```

استخدم Persistent Storage/Volume إذا كانت الاستضافة تمسح الملفات بعد إعادة التشغيل، لأن قاعدة البيانات وملف جلسة الـDashboard موجودان داخل `data/`.

## الأوامر

الأوامر النصية العربية تستخدم البادئة الحالية `!`، مثل:

```text
!تكت
!تقديم
!قيفاواي 1h 1 Nitro
!لفل
!توب
!تحذير @member السبب
!باند @member السبب
```

وتتوفر مجموعة من الأوامر نفسها كـSlash Commands باللغة الإنجليزية، مثل `/level` و `/leaderboard` و `/giveaway` و `/ban`.

## ملاحظات

- يجب إعطاء البوت الصلاحيات التي تحتاجها الأنظمة، مثل Manage Channels للتذاكر.
- يجب أن يكون دور البوت أعلى من الرتب التي سيقوم بإعطائها.
- إعدادات كل سيرفر مستقلة عن السيرفرات الأخرى.
- لا تضع `DISCORD_TOKEN` أو `DISCORD_CLIENT_SECRET` داخل GitHub.


## Four-bot architecture

The same codebase can run four independent bot instances simultaneously. Each instance has its own token, primary server ID, SQLite database, backups and enabled-system state.

Configure instances/bot-1/config.json through instances/bot-4/config.json, then run:

    python run_all.py

Use /systems or /system enable|disable|status|reload inside each server to control systems independently.

The default welcome embed is clean and English:

    Welcome {user} to {server}!
    You are member {count} 🎉

    📌 Please read the rules
    💬 Chat & have fun
    🚀 Enjoy!

The new member's avatar is displayed inside the embed. Welcome channel, title, description, color and avatar display can be changed from Discord.
