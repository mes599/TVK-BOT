"""Direct ChatGPT chat with Discord actions for the private TVK AI channel."""

import os
import re
from typing import Optional

import discord
from discord.ext import commands

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


CPS_CHANNEL_NAME = "tvk-ai-cps-channel🔒"
CPS_MODEL = os.getenv("CPS_MODEL", "gpt-4o-mini")

# Channel names that the AI is allowed to target through a natural-language request.
DISCOUNT_CHANNEL_NAMES = {"discounts", "discount"}

CPS_SYSTEM_PROMPT = (
    "You are ChatGPT for the TVK Discord server owner. "
    "Answer naturally, clearly and helpfully. "
    "The owner can give you direct Discord actions in normal language. "
    "When an action is actually executed, confirm that it was done. "
    "Do not pretend an action was completed if it was not."
)


def get_openai_client() -> Optional["AsyncOpenAI"]:
    if AsyncOpenAI is None:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    return AsyncOpenAI(api_key=api_key)


def extract_channel_message_action(prompt: str) -> Optional[tuple[str, str]]:
    """Return (channel_name, text) for simple explicit post requests.

    Examples:
      'Schreibe in den discounts channel hello guys'
      'Schreib in #discounts: hello guys'
      'Poste hello guys in den discounts channel'
    """
    text = prompt.strip()

    patterns = [
        # German: Schreibe/Schreib/Poste/Veröffentliche ... in den ... channel ...
        re.compile(
            r"^(?:schreib(?:e)?|poste|veröffentliche|sende)\s+"
            r"(?:in\s+den\s+)?#?([\w-]+)\s*(?:channel)?\s*[:,-]?\s+(.+)$",
            re.IGNORECASE,
        ),
        # English: write/post ... in/to the ... channel
        re.compile(
            r"^(?:write|post|send)\s+(.+?)\s+(?:in|to)\s+(?:the\s+)?#?([\w-]+)\s*(?:channel)?$",
            re.IGNORECASE,
        ),
    ]

    match = patterns[0].match(text)
    if match:
        channel_name = match.group(1).lower()
        message_text = match.group(2).strip()
        if channel_name in DISCOUNT_CHANNEL_NAMES:
            return channel_name, message_text

    match = patterns[1].match(text)
    if match:
        message_text = match.group(1).strip()
        channel_name = match.group(2).lower()
        if channel_name in DISCOUNT_CHANNEL_NAMES:
            return channel_name, message_text

    # Specifically handle the wording the owner used.
    match = re.match(
        r"^schreib(?:e)?\s+in\s+(?:den\s+)?discounts\s+channel\s+(.+)$",
        text,
        re.IGNORECASE,
    )
    if match:
        return "discounts", match.group(1).strip()

    return None


class CPSCog(commands.Cog):
    """Lets the owner chat directly with ChatGPT and perform simple Discord actions."""

    def __init__(self, bot: commands.Bot, owner_id: int):
        self.bot = bot
        self.owner_id = owner_id
        self.client = get_openai_client()

    async def _execute_action(
        self,
        message: discord.Message,
        action: tuple[str, str],
    ) -> bool:
        channel_name, content = action

        target = discord.utils.find(
            lambda channel: (
                isinstance(channel, discord.TextChannel)
                and channel.name.lower() == channel_name.lower()
            ),
            message.guild.text_channels,
        )

        if target is None:
            await message.reply(
                f"❌ Ich finde den Channel `#{channel_name}` nicht.",
                mention_author=False,
            )
            return True

        if not target.permissions_for(message.guild.me).send_messages:
            await message.reply(
                f"❌ Ich habe keine Berechtigung, in #{target.name} zu schreiben.",
                mention_author=False,
            )
            return True

        try:
            await target.send(content)
        except discord.Forbidden:
            await message.reply(
                f"❌ Discord verweigert mir das Schreiben in #{target.name}.",
                mention_author=False,
            )
            return True
        except discord.HTTPException as error:
            print(f"❌ Discord send error in #{target.name}: {error}")
            await message.reply(
                f"❌ Die Nachricht konnte nicht in #{target.name} gesendet werden.",
                mention_author=False,
            )
            return True

        await message.reply(
            f"✅ Erledigt! Ich habe in #{target.name} geschrieben:\n> {content}",
            mention_author=False,
        )
        return True

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

        # IMPORTANT: execute explicit Discord actions instead of merely suggesting text.
        action = extract_channel_message_action(prompt)
        if action is not None:
            await self._execute_action(message, action)
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
