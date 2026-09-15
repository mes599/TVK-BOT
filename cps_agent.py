"""Direct ChatGPT chat for the private TVK AI Discord channel."""

import os
from typing import Optional

import discord
from discord.ext import commands

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


CPS_CHANNEL_NAME = "tvk-ai-cps-channel🔒"
CPS_MODEL = os.getenv("CPS_MODEL", "gpt-4o-mini")

CPS_SYSTEM_PROMPT = (
    "You are ChatGPT for the TVK Discord server owner. "
    "Answer naturally, clearly and helpfully. "
    "Do not require slash commands or special prefixes. "
    "The user's Discord message is the prompt."
)


def get_openai_client() -> Optional["AsyncOpenAI"]:
    if AsyncOpenAI is None:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    return AsyncOpenAI(api_key=api_key)


class CPSCog(commands.Cog):
    """Lets the owner chat directly with ChatGPT in the CPS channel."""

    def __init__(self, bot: commands.Bot, owner_id: int):
        self.bot = bot
        self.owner_id = owner_id
        self.client = get_openai_client()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Never answer bots, DMs, or messages outside the AI channel.
        if message.author.bot:
            return

        if message.guild is None:
            return

        if message.channel.name != CPS_CHANNEL_NAME:
            return

        # Keep this private AI channel restricted to the configured owner.
        if message.author.id != self.owner_id:
            return

        prompt = message.content.strip()
        if not prompt:
            return

        if self.client is None:
            await message.reply(
                "❌ OPENAI_API_KEY ist nicht konfiguriert.",
                mention_author=False,
            )
            return

        async with message.channel.typing():
            try:
                response = await self.client.responses.create(
                    model=CPS_MODEL,
                    instructions=CPS_SYSTEM_PROMPT,
                    input=prompt,
                    store=False,
                )

                answer = (response.output_text or "").strip()

            except Exception as error:
                print(f"❌ ChatGPT error: {error}")
                await message.reply(
                    "❌ Beim Antworten ist ein Fehler aufgetreten. "
                    "Prüfe bitte die Railway-Logs.",
                    mention_author=False,
                )
                return

        if not answer:
            answer = "Ich konnte darauf gerade keine Antwort erzeugen."

        # Discord allows at most 2000 characters per message.
        if len(answer) <= 2000:
            await message.reply(answer, mention_author=False)
            return

        # Split longer ChatGPT answers into Discord-sized messages.
        chunks = [answer[i:i + 2000] for i in range(0, len(answer), 2000)]
        for chunk in chunks:
            await message.channel.send(chunk)


async def setup(bot: commands.Bot, owner_id: int):
    await bot.add_cog(CPSCog(bot, owner_id))
