import json
import os
import traceback
from typing import Optional

import discord
from discord.ext import commands

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


# =========================================================
# SETTINGS
# =========================================================

# The channel where the owner drops rough drafts.
CPS_CHANNEL_NAME = "tvk-ai-cps-channel🔒"

# Maps a short internal key to the exact Discord channel name
# it should be posted to. Add more entries here to support
# more target channels.
CPS_TARGET_CHANNELS = {
    "server-news": "server-news📢",
    "discounts": "discounts🏷️",
    "challenge-vote": "challenge-vote🗳️",
}

CPS_MODEL = "gpt-4o-mini"

CPS_SYSTEM_PROMPT = (
    "You help a Discord server owner turn a rough draft into a "
    "polished announcement.\n\n"
    "You will receive a raw message from the owner. It usually "
    "mentions which channel the announcement is for, followed by "
    "the rough text to post.\n\n"
    "The only valid channel keys are: "
    + ", ".join(CPS_TARGET_CHANNELS.keys()) + ".\n\n"
    "Rewrite the text so it reads like a short, friendly, well "
    "formatted Discord announcement, and add fitting emojis "
    "(tasteful, not excessive). Keep the original meaning and any "
    "concrete facts (prices, dates, links, codes, percentages) "
    "exactly as given - never invent details.\n\n"
    "Respond with ONLY a raw JSON object, no code fences, no extra "
    "text, in exactly this shape:\n"
    '{"channel": "<one of the valid channel keys, or null if unclear>", '
    '"text": "<the rewritten announcement>"}'
)

DISCORD_MESSAGE_LIMIT = 2000


def get_openai_client() -> Optional["AsyncOpenAI"]:

    if AsyncOpenAI is None:
        return None

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return None

    return AsyncOpenAI(api_key=api_key)


# =========================================================
# EDIT MODAL
# =========================================================

class CPSEditModal(
    discord.ui.Modal,
    title="Edit Announcement"
):

    channel_key = discord.ui.TextInput(
        label="Target channel",
        style=discord.TextStyle.short,
        required=True,
        max_length=50
    )

    text = discord.ui.TextInput(
        label="Announcement text",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1800
    )

    def __init__(
        self,
        view: "CPSPreviewView"
    ):

        super().__init__()

        self.view_ref = view

        self.channel_key.default = view.target_key
        self.text.default = view.text

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        new_key = self.channel_key.value.strip().lower()

        if new_key not in CPS_TARGET_CHANNELS:

            await interaction.response.send_message(
                (
                    "❌ Unknown target channel. Valid options: "
                    + ", ".join(
                        f"**{key}**" for key in CPS_TARGET_CHANNELS
                    )
                ),
                ephemeral=True
            )
            return

        self.view_ref.target_key = new_key
        self.view_ref.text = self.text.value.strip()

        new_embed = self.view_ref.cog.build_preview_embed(
            self.view_ref.target_key,
            self.view_ref.text
        )

        await interaction.response.edit_message(
            embed=new_embed,
            view=self.view_ref
        )


# =========================================================
# PREVIEW VIEW
# =========================================================

class CPSPreviewView(
    discord.ui.View
):

    def __init__(
        self,
        cog: "CPSCog",
        requester_id: int,
        target_key: str,
        text: str
    ):

        super().__init__(
            timeout=600
        )

        self.cog = cog
        self.requester_id = requester_id
        self.target_key = target_key
        self.text = text
        self.message: Optional[discord.Message] = None

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ) -> bool:

        if interaction.user.id != self.requester_id:

            await interaction.response.send_message(
                (
                    "❌ Only the person who requested this "
                    "can use these buttons."
                ),
                ephemeral=True
            )
            return False

        return True

    async def on_timeout(self):

        for item in self.children:
            item.disabled = True

        if self.message is not None:

            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    # -----------------------------------------------------
    # CONFIRM
    # -----------------------------------------------------

    @discord.ui.button(
        label="✅ Confirm",
        style=discord.ButtonStyle.green,
        custom_id="cps_confirm"
    )
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild

        if guild is None:

            await interaction.response.send_message(
                "❌ This can only be used inside a server.",
                ephemeral=True
            )
            return

        if len(self.text) > DISCORD_MESSAGE_LIMIT:

            await interaction.response.send_message(
                (
                    "❌ This text is too long to post "
                    f"({len(self.text)}/{DISCORD_MESSAGE_LIMIT} "
                    "characters). Use ✏️ Edit to shorten it."
                ),
                ephemeral=True
            )
            return

        channel_name = CPS_TARGET_CHANNELS[self.target_key]

        target_channel = discord.utils.get(
            guild.text_channels,
            name=channel_name
        )

        if target_channel is None:

            await interaction.response.send_message(
                f"❌ I could not find #{channel_name}.",
                ephemeral=True
            )
            return

        try:

            await target_channel.send(self.text)

        except discord.Forbidden:

            await interaction.response.send_message(
                f"❌ I don't have permission to post in #{channel_name}.",
                ephemeral=True
            )
            return

        except discord.HTTPException as error:

            await interaction.response.send_message(
                f"❌ Could not post the message: {error}",
                ephemeral=True
            )
            return

        for item in self.children:
            item.disabled = True

        posted_embed = self.cog.build_preview_embed(
            self.target_key,
            self.text
        )

        posted_embed.title = "✅ Posted"
        posted_embed.color = discord.Color.green()

        await interaction.response.edit_message(
            embed=posted_embed,
            view=self
        )

        self.stop()

    # -----------------------------------------------------
    # EDIT
    # -----------------------------------------------------

    @discord.ui.button(
        label="✏️ Edit",
        style=discord.ButtonStyle.blurple,
        custom_id="cps_edit"
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            CPSEditModal(self)
        )

    # -----------------------------------------------------
    # CANCEL
    # -----------------------------------------------------

    @discord.ui.button(
        label="❌ Cancel",
        style=discord.ButtonStyle.red,
        custom_id="cps_cancel"
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        for item in self.children:
            item.disabled = True

        cancelled_embed = self.cog.build_preview_embed(
            self.target_key,
            self.text
        )

        cancelled_embed.title = "❌ Cancelled"
        cancelled_embed.color = discord.Color.red()

        await interaction.response.edit_message(
            embed=cancelled_embed,
            view=self
        )

        self.stop()


# =========================================================
# COG
# =========================================================

class CPSCog(
    commands.Cog
):

    def __init__(
        self,
        bot: commands.Bot,
        owner_id: int
    ):

        self.bot = bot
        self.owner_id = owner_id
        self.client = get_openai_client()

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

        if message.author.bot:
            return

        if message.guild is None:
            return

        if message.channel.name != CPS_CHANNEL_NAME:
            return

        if message.author.id != self.owner_id:
            return

        if not message.content.strip():
            return

        if self.client is None:

            await message.reply(
                (
                    "❌ OPENAI_API_KEY is not configured, "
                    "I can't rewrite this text right now."
                ),
                mention_author=False
            )
            return

        async with message.channel.typing():

            try:

                target_key, text = await self.generate(
                    message.content
                )

            except Exception as error:

                print(f"❌ CPS generation error: {error}")
                traceback.print_exc()

                await message.reply(
                    (
                        "❌ Something went wrong while "
                        "generating the announcement."
                    ),
                    mention_author=False
                )
                return

        if target_key is None:

            await message.reply(
                (
                    "🤔 I couldn't tell which channel this is for.\n"
                    "Please mention one of: "
                    + ", ".join(
                        f"**{key}**" for key in CPS_TARGET_CHANNELS
                    )
                ),
                mention_author=False
            )
            return

        preview_embed = self.build_preview_embed(
            target_key,
            text
        )

        view = CPSPreviewView(
            cog=self,
            requester_id=message.author.id,
            target_key=target_key,
            text=text
        )

        sent_message = await message.reply(
            embed=preview_embed,
            view=view,
            mention_author=False
        )

        view.message = sent_message

    async def generate(
        self,
        raw_text: str
    ) -> tuple[Optional[str], str]:

        response = await self.client.chat.completions.create(
            model=CPS_MODEL,
            messages=[
                {"role": "system", "content": CPS_SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            temperature=0.7,
        )

        raw_reply = response.choices[0].message.content or "{}"

        cleaned = raw_reply.strip()

        if cleaned.startswith("```"):

            cleaned = cleaned.strip("`")

            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            data = {}

        channel_key = data.get("channel")
        text = (data.get("text") or "").strip()

        if channel_key not in CPS_TARGET_CHANNELS:
            channel_key = None

        if not text:
            text = raw_text

        return channel_key, text

    def build_preview_embed(
        self,
        target_key: str,
        text: str
    ) -> discord.Embed:

        embed = discord.Embed(
            title="📝 Announcement Preview",
            description=text,
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🎯 Target Channel",
            value=f"#{CPS_TARGET_CHANNELS[target_key]}",
            inline=False
        )

        embed.set_footer(
            text=(
                "✅ Confirm to post it • ✏️ Edit to change it "
                "• ❌ Cancel to discard it"
            )
        )

        return embed
