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
- إعدادات Discord OAuth2 إذا كنت ستستخدم الـDashboard

## التثبيت

```bash
pip install -r requirements.txt
python bot.py
```

## متغيرات البيئة

انسخ `.env.example` إلى `.env` أو أضف المتغيرات نفسها في الاستضافة:

```text
DISCORD_TOKEN=
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DISCORD_REDIRECT_URI=
SESSION_SECRET=
PORT=10000
HOST=0.0.0.0
DATA_DIR=data
DATABASE_PATH=data/flame.db
```

لا تضع `DISCORD_TOKEN` أو `DISCORD_CLIENT_SECRET` داخل ملفات GitHub.

## Dashboard

بعد تشغيل البوت، افتح رابط الموقع ثم سجل الدخول بواسطة Discord. يجب أن يكون `DISCORD_REDIRECT_URI` مطابقًا تمامًا للرابط المسجل في Discord Developer Portal.

يتم حفظ إعدادات السيرفر وبيانات الأنظمة في SQLite عبر `DATABASE_PATH`.

## الاستضافة

المشروع يحتوي على `Procfile` و `railway.json` لتشغيله بأمر:

```bash
python bot.py
```

إذا كانت الاستضافة تستخدم نظام ملفات مؤقت، استخدم Volume/Persistent Storage لقاعدة البيانات حتى لا تضيع البيانات بعد إعادة التشغيل.

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

وتتوفر مجموعة من الأوامر نفسها كـ Slash Commands باللغة الإنجليزية، مثل `/level` و `/leaderboard` و `/giveaway` و `/ban`.

## ملاحظات

- يجب إعطاء البوت الصلاحيات التي تحتاجها الأنظمة، مثل Manage Channels للتذاكر.
- يجب أن يكون دور البوت أعلى من الرتب التي سيقوم بإعطائها.
- إعدادات كل سيرفر مستقلة عن السيرفرات الأخرى.
