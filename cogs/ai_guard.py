import asyncio
import json
import re
from datetime import timedelta

import aiohttp
import discord
from discord.ext import commands

from config import GEMINI_API_KEY, GEMINI_MODEL, AI_TIMEOUT, AI_HIGH_CONFIDENCE, AI_LOW_CONFIDENCE
from database import get_guild_data


class AIGuard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sem = asyncio.Semaphore(2)

    async def log(self, guild, title, description, actor=None, color=None):
        cog = self.bot.get_cog('Logs')
        if cog:
            await cog.send_log(guild, title, description, actor=actor, color=color)

    def parse_result(self, text):
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.I).strip()
        match = re.search(r'\{.*\}', text, flags=re.S)
        data = json.loads(match.group(0) if match else text)
        confidence = float(data.get('confidence', 0))
        if confidence > 1:
            confidence /= 100
        return bool(data.get('harmful', False)), max(0, min(1, confidence)), str(data.get('category', 'unknown'))[:80], str(data.get('reason', ''))[:500]

    async def classify(self, message):
        if not GEMINI_API_KEY:
            return None
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
        payload = {
            'contents': [{'parts': [{'text': 'Classify this Discord message for server safety. Return JSON only: harmful (boolean), confidence (0-1), category (short), reason (short). Do not flag normal chat. Message: ' + message.content[:3000]}]}],
            'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json'},
        }
        try:
            async with self.sem:
                timeout = aiohttp.ClientTimeout(total=AI_TIMEOUT)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, params={'key': GEMINI_API_KEY}, json=payload) as response:
                        raw = await response.text()
                        if response.status >= 400:
                            await self.log(message.guild, 'AI API Error', f'HTTP `{response.status}`\n`{raw[:800]}`', color=discord.Color.orange())
                            return None
                        body = json.loads(raw)
                        text = body['candidates'][0]['content']['parts'][0]['text']
                        return self.parse_result(text)
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
            await self.log(message.guild, 'AI Analysis Failed', f'`{type(exc).__name__}: {exc}`', color=discord.Color.orange())
            return None

    @staticmethod
    def duration(confidence):
        if confidence >= .99:
            return 30
        if confidence >= .97:
            return 20
        if confidence >= .95:
            return 15
        return 5

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or not message.content.strip():
            return
        if get_guild_data(message.guild.id).get('ai_enabled', True) is False:
            return
        result = await self.classify(message)
        if not result:
            return
        harmful, confidence, category, reason = result
        if harmful and confidence >= AI_HIGH_CONFIDENCE:
            minutes = self.duration(confidence)
            acted = False
            try:
                if message.guild.me and message.guild.me.guild_permissions.moderate_members:
                    await message.author.timeout(timedelta(minutes=minutes), reason=f'VoidFlame AI: {category} ({confidence:.0%})')
                    acted = True
            except (discord.Forbidden, discord.HTTPException):
                pass
            await self.log(message.guild, 'AI Moderation', f'Member: {message.author.mention}\nChannel: {message.channel.mention}\nCategory: `{category}`\nConfidence: **{confidence:.0%}**\nDuration: **{minutes}m**\nAction: **{"Timeout" if acted else "Failed"}**\nReason: {reason}\nContent: `{message.content[:1200]}`', actor=message.author, color=discord.Color.red())
        elif confidence < AI_LOW_CONFIDENCE:
            data = get_guild_data(message.guild.id)
            channel_id = data.get('staff_channel_id')
            channel = message.guild.get_channel(int(channel_id)) if channel_id else None
            if isinstance(channel, discord.TextChannel):
                embed = discord.Embed(title='AI Review Required', color=discord.Color.orange(), timestamp=discord.utils.utcnow())
                embed.add_field(name='Member', value=message.author.mention)
                embed.add_field(name='Confidence', value=f'{confidence:.0%}')
                embed.add_field(name='Category', value=category)
                embed.add_field(name='Reason', value=reason or 'No reason')
                embed.add_field(name='Content', value=message.content[:1000], inline=False)
                try:
                    await channel.send(embed=embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass


async def setup(bot):
    await bot.add_cog(AIGuard(bot))
