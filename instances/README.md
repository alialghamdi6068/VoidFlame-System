# VoidFlame System — Four Bot Instances

This repository runs four identical Discord bots from one shared codebase.

Each bot instance is isolated by token, primary guild, SQLite database, backups and system state. The source code and systems are shared, so changes are made once.

## Instances

- instances/bot-1/config.json
- instances/bot-2/config.json
- instances/bot-3/config.json
- instances/bot-4/config.json

Copy instances/config.json.example into each folder as config.json and fill in the token and guild ID.

Run all configured bots with:

    python run_all.py

## Discord system control

    /systems
    /system status
    /system enable <system>
    /system disable <system>
    /system reload <system>

Every feature module can be disabled. Disabling a module unloads its cog, which removes its commands/listeners and stops resources owned by that module.

## Resource policy

- No default message logging.
- No default presence or voice logging.
- No per-command logging.
- Minimal Gateway intents.
- Systems load only when enabled.
- SQLite is isolated per instance.
- Only useful moderation, ticket, security and error logs should be emitted by logging modules.

## Welcome embed

The default welcome is intentionally clean:

    Welcome {user} to {server}!
    You are member {count} 🎉

    📌 Please read the rules
    💬 Chat & have fun
    🚀 Enjoy!

The new member avatar is shown as the embed thumbnail. The channel, title, description, color and avatar setting can be changed from Discord with /welcome-config.
