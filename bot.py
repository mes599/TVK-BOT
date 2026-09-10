import asyncio
import os
import traceback
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands

from config import ConfigurationError, get_settings


# =========================================================
# SETTINGS
# =========================================================

TICKET_CHANNEL_NAME = "ticket🎫"
WELCOME_CHANNEL_NAME = "welcome👋"

SHOWCASE_CHANNEL_NAME = "ticket-demo-bot🎫"
SHOWCASE_CATEGORY_NAME = "Bot Showcases🤖"

COOLDOWN = timedelta(minutes=2)

# Payment links
REVOLUT_PAYMENT_URL = "https://revolut.me/ayberkqvg8"
PAYPAL_PAYMENT_URL = "https://paypal.me/aydmraybrk"

# Your Discord user ID
OWNER_ID = 1137740302094966884

# How many messages are checked for existing panels
MAX_PANEL_HISTORY = 50

# Discord channel-name limit
MAX_CHANNEL_NAME_LENGTH = 100


# =========================================================
# PACKAGE DATA
# =========================================================

PACKAGES = {
    "starter": {
        "name": "Starter",
        "price": "€4.99",
    },
    "pro": {
        "name": "Pro",
        "price": "€9.99",
    },
    "advanced": {
        "name": "Advanced",
        "price": "€14.99",
    },
}


# =========================================================
# BOT TOKEN / SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
settings = None

try:

    settings = get_settings()

except ConfigurationError as error:

    print(
        f"❌ Configuration error: {error}"
    )

    BOT_TOKEN = None

else:

    missing_secret = settings.missing_startup_secret

    if missing_secret:

        print(
            f"❌ Configuration error: "
            f"{missing_secret} is not set."
        )

        BOT_TOKEN = None

    else:

        BOT_TOKEN = settings.discord_bot_token


# =========================================================
# GLOBAL STATE
# =========================================================

ticket_cooldowns: dict[int, datetime] = {}

# Prevents two users from creating the same type of ticket
# at exactly the same time.
ticket_creation_lock = asyncio.Lock()

# Prevents Verify/Reject from being processed simultaneously
# for the same ticket during the current bot process.
payment_action_locks: dict[int, asyncio.Lock] = {}


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def is_ticket_channel(
    channel: discord.abc.GuildChannel
) -> bool:
    """
    Returns True for normal ticket/order channels.
    """

    return (
        channel.name.startswith("ticket-")
        or channel.name.startswith("order-")
    )


def is_showcase_channel(
    channel: discord.abc.GuildChannel
) -> bool:
    """
    Returns True for showcase demo channels.
    """

    return bool(
        channel.topic
        and "showcase-demo:true" in channel.topic
    )


def get_topic_value(
    topic: Optional[str],
    key: str
) -> Optional[str]:
    """
    Reads a structured value from a channel topic.

    Example:

    ticket-owner:123456 | ticket-type:order | payment-status:pending
    """

    if not topic:
        return None

    for part in topic.split("|"):

        part = part.strip()

        if ":" not in part:
            continue

        current_key, value = part.split(
            ":",
            1
        )

        if current_key.strip() == key:

            return value.strip()

    return None


def build_ticket_topic(
    owner_id: int,
    ticket_type: str = "support",
    payment_status: str = "pending"
) -> str:

    return (
        f"ticket-owner:{owner_id} | "
        f"ticket-type:{ticket_type} | "
        f"payment-status:{payment_status}"
    )


def build_showcase_topic(
    owner_id: int
) -> str:

    return (
        f"showcase-owner:{owner_id} | "
        "showcase-demo:true"
    )


def get_ticket_owner_id(
    channel: discord.TextChannel
) -> Optional[int]:

    raw_owner_id = get_topic_value(
        channel.topic,
        "ticket-owner"
    )

    if raw_owner_id is None:
        return None

    try:

        return int(
            raw_owner_id
        )

    except ValueError:

        return None


def get_payment_status(
    channel: discord.TextChannel
) -> str:

    return (
        get_topic_value(
            channel.topic,
            "payment-status"
        )
        or "pending"
    )


def is_owner(
    interaction: discord.Interaction
) -> bool:

    return interaction.user.id == OWNER_ID


def get_owner_member(
    guild: discord.Guild
) -> Optional[discord.Member]:

    return guild.get_member(
        OWNER_ID
    )


async def get_bot_owner(
    client: discord.Client
) -> Optional[discord.User]:

    try:

        application = await client.application_info()

        return application.owner

    except discord.HTTPException as error:

        print(
            f"⚠️ Could not retrieve application owner: {error}"
        )

        return None


async def send_owner_dm(
    client: discord.Client,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    view: Optional[discord.ui.View] = None
) -> bool:
    """
    Sends a DM to the configured OWNER_ID.

    The actual Discord token is NOT stored here.
    Railway supplies DISCORD_BOT_TOKEN through the environment.
    """

    try:

        owner = client.get_user(
            OWNER_ID
        )

        if owner is None:

            owner = await client.fetch_user(
                OWNER_ID
            )

        await owner.send(
            content=content,
            embed=embed,
            view=view
        )

        return True

    except discord.NotFound:

        print(
            "❌ The configured OWNER_ID could not be found."
        )

    except discord.Forbidden:

        print(
            "❌ The bot cannot DM the configured owner."
        )

    except discord.HTTPException as error:

        print(
            f"❌ Owner DM error: {error}"
        )

    return False


async def set_payment_status(
    channel: discord.TextChannel,
    status: str
) -> bool:

    owner_id = get_ticket_owner_id(
        channel
    )

    if owner_id is None:
        return False

    ticket_type = get_topic_value(
        channel.topic,
        "ticket-type"
    ) or "support"

    try:

        await channel.edit(
            topic=build_ticket_topic(
                owner_id=owner_id,
                ticket_type=ticket_type,
                payment_status=status
            ),
            reason=(
                f"Payment status changed to {status}"
            )
        )

        return True

    except discord.Forbidden:

        print(
            f"❌ Cannot edit topic of #{channel.name}."
        )

    except discord.HTTPException as error:

        print(
            f"❌ Could not update payment status: {error}"
        )

    return False


def get_payment_request_data(
    message: Optional[discord.Message]
) -> Optional[tuple[int, int, int]]:
    """
    Gets guild ID, channel ID and customer ID from the
    structured footer of the payment notification.

    Footer format:

    payment-request:GUILD_ID:CHANNEL_ID:CUSTOMER_ID
    """

    if message is None:
        return None

    if not message.embeds:
        return None

    embed = message.embeds[0]

    footer_text = embed.footer.text

    if not footer_text:
        return None

    prefix = "payment-request:"

    if not footer_text.startswith(prefix):
        return None

    raw_data = footer_text[len(prefix):]

    parts = raw_data.split(":")

    if len(parts) != 3:
        return None

    try:

        guild_id = int(parts[0])
        channel_id = int(parts[1])
        customer_id = int(parts[2])

    except ValueError:

        return None

    return (
        guild_id,
        channel_id,
        customer_id
    )


def get_payment_lock(
    channel_id: int
) -> asyncio.Lock:

    lock = payment_action_locks.get(
        channel_id
    )

    if lock is None:

        lock = asyncio.Lock()

        payment_action_locks[
            channel_id
        ] = lock

    return lock


def format_payment_method(
    method: str
) -> str:

    clean_method = method.strip()

    if not clean_method:

        return "Not provided"

    return clean_method


# =========================================================
# PAYMENT CONFIRMATION MODAL
# =========================================================

class PaymentConfirmationModal(
    discord.ui.Modal,
    title="Confirm Payment"
):

    payment_method = discord.ui.TextInput(
        label="Payment method",
        placeholder="Revolut or PayPal",
        style=discord.TextStyle.short,
        required=True,
        max_length=50
    )

    account_name = discord.ui.TextInput(
        label="Name of your Account",
        placeholder=(
            "Enter the name of your Revolut or PayPal account."
        ),
        style=discord.TextStyle.short,
        required=True,
        max_length=100
    )

    payment_note = discord.ui.TextInput(
        label="Payment information",
        placeholder=(
            "Add any additional information about your payment."
        ),
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        channel = interaction.channel
        user = interaction.user

        # -------------------------------------------------
        # CHANNEL TYPE
        # -------------------------------------------------

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ This can only be used inside a ticket.",
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # TICKET CHECK
        # -------------------------------------------------

        if not is_ticket_channel(channel):

            await interaction.response.send_message(
                (
                    "❌ This button can only be used "
                    "inside an order ticket."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # TICKET OWNER CHECK
        # -------------------------------------------------

        ticket_owner_id = get_ticket_owner_id(
            channel
        )

        if ticket_owner_id != user.id:

            await interaction.response.send_message(
                (
                    "❌ Only the person who created "
                    "this ticket can report payment."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # PAYMENT STATUS CHECK
        # -------------------------------------------------

        current_status = get_payment_status(
            channel
        )

        if current_status != "pending":

            await interaction.response.send_message(
                (
                    "⚠️ This payment is already marked as "
                    f"**{current_status}**."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # DEFER
        # -------------------------------------------------

        await interaction.response.defer(
            ephemeral=True
        )

        guild = interaction.guild

        if guild is None:

            await interaction.followup.send(
                "❌ The server could not be found.",
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # SAVE ACCOUNT INFORMATION
        # -------------------------------------------------

        payment_method_value = format_payment_method(
            self.payment_method.value
        )

        account_name_value = (
            self.account_name.value.strip()
        )

        payment_note_value = (
            self.payment_note.value.strip()
            if self.payment_note.value
            else ""
        )

        # -------------------------------------------------
        # MARK AS REPORTED
        # -------------------------------------------------

        status_updated = await set_payment_status(
            channel,
            "reported"
        )

        if not status_updated:

            await interaction.followup.send(
                (
                    "❌ I could not update the payment "
                    "status. Please contact the owner."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # PAYMENT EMBED FOR OWNER
        # -------------------------------------------------

        embed = discord.Embed(
            title="💰 Payment Confirmation",
            description=(
                f"{user.mention} has reported a payment."
            ),
            color=discord.Color.orange()
        )

        embed.add_field(
            name="👤 Customer",
            value=(
                f"{user.mention}\n"
                f"`{user}`"
            ),
            inline=False
        )

        embed.add_field(
            name="🆔 Customer ID",
            value=str(user.id),
            inline=True
        )

        embed.add_field(
            name="🌐 Server",
            value=(
                f"{guild.name}\n"
                f"`{guild.id}`"
            ),
            inline=True
        )

        embed.add_field(
            name="🎫 Ticket",
            value=channel.mention,
            inline=True
        )

        embed.add_field(
            name="🆔 Ticket ID",
            value=str(channel.id),
            inline=True
        )

        embed.add_field(
            name="💳 Payment Method",
            value=payment_method_value,
            inline=False
        )

        embed.add_field(
            name="👤 Name of your Account",
            value=account_name_value,
            inline=False
        )

        embed.add_field(
            name="📝 Additional Information",
            value=payment_note_value or "None",
            inline=False
        )

        embed.add_field(
            name="🔎 Status",
            value=(
                "⏳ Awaiting manual verification."
            ),
            inline=False
        )

        embed.set_footer(
            text=(
                f"payment-request:"
                f"{guild.id}:"
                f"{channel.id}:"
                f"{user.id}"
            )
        )

        # -------------------------------------------------
        # OWNER VERIFICATION BUTTONS
        # -------------------------------------------------

        verification_view = PaymentVerificationView()

        # -------------------------------------------------
        # SEND OWNER NOTIFICATION
        # -------------------------------------------------

        owner_notified = await send_owner_dm(
            interaction.client,
            content=(
                "📩 **Payment verification required.**\n"
                "Please check the account name and manually "
                "verify the payment."
            ),
            embed=embed,
            view=verification_view
        )

        # -------------------------------------------------
        # CUSTOMER RESPONSE
        # -------------------------------------------------

        if owner_notified:

            await interaction.followup.send(
                (
                    "✅ **Payment information submitted!**\n\n"
                    f"💳 Payment method: "
                    f"**{payment_method_value}**\n"
                    f"👤 Account name: "
                    f"**{account_name_value}**\n\n"
                    "⏳ Your payment is now waiting "
                    "for manual verification."
                ),
                ephemeral=True
            )

        else:

            await interaction.followup.send(
                (
                    "⚠️ Your payment report was recorded, "
                    "but I could not notify the owner.\n\n"
                    "Please contact the server owner directly."
                ),
                ephemeral=True
            )

        # -------------------------------------------------
        # MESSAGE INSIDE TICKET
        # -------------------------------------------------

        try:

            await channel.send(
                (
                    f"💰 **Payment reported by "
                    f"{user.mention}.**\n\n"
                    f"💳 Payment method: "
                    f"**{payment_method_value}**\n"
                    f"👤 Account name: "
                    f"**{account_name_value}**\n\n"
                    "⏳ The server owner has been notified "
                    "and must verify the payment manually."
                )
            )

        except discord.Forbidden:

            print(
                "⚠️ I cannot send the payment message "
                "inside the ticket."
            )

        except discord.HTTPException as error:

            print(
                f"⚠️ Payment ticket message error: {error}"
            )


# =========================================================
# PAYMENT REPORT BUTTON
# =========================================================

class PaymentCompletedButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="✅ Confirm Payment",
            style=discord.ButtonStyle.green,
            custom_id="payment_completed"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ This can only be used inside a ticket.",
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # CHANNEL CHECK
        # -------------------------------------------------

        if not is_ticket_channel(channel):

            await interaction.response.send_message(
                (
                    "❌ This button can only be used "
                    "inside an order ticket."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # CUSTOMER CHECK
        # -------------------------------------------------

        ticket_owner_id = get_ticket_owner_id(
            channel
        )

        if ticket_owner_id != interaction.user.id:

            await interaction.response.send_message(
                (
                    "❌ Only the customer who created "
                    "this ticket can report payment."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # STATUS CHECK
        # -------------------------------------------------

        if get_payment_status(channel) != "pending":

            await interaction.response.send_message(
                (
                    "⚠️ Payment information has already "
                    "been submitted or processed."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # OPEN MODAL
        # -------------------------------------------------

        await interaction.response.send_modal(
            PaymentConfirmationModal()
        )


# =========================================================
# PAYMENT BUTTONS
# =========================================================

class PaymentButtons(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            discord.ui.Button(
                label="💜 Pay with Revolut",
                style=discord.ButtonStyle.link,
                url=REVOLUT_PAYMENT_URL
            )
        )

        self.add_item(
            discord.ui.Button(
                label="💙 Pay with PayPal",
                style=discord.ButtonStyle.link,
                url=PAYPAL_PAYMENT_URL
            )
        )

        self.add_item(
            PaymentCompletedButton()
        )


# =========================================================
# PAYMENT VERIFICATION VIEW
# =========================================================
#
# IMPORTANT:
# The custom IDs are fixed.
#
# This makes this view persistent and allows the Verify /
# Reject buttons to continue working after a bot restart.
#
# The ticket information is read from the payment message.
# =========================================================

class PaymentVerificationView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            PaymentVerifyButton()
        )

        self.add_item(
            PaymentRejectButton()
        )


# =========================================================
# VERIFY PAYMENT BUTTON
# =========================================================

class PaymentVerifyButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="✅ Verify Payment",
            style=discord.ButtonStyle.green,
            custom_id="payment_verify"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        # -------------------------------------------------
        # OWNER ONLY
        # -------------------------------------------------

        if not is_owner(interaction):

            await interaction.response.send_message(
                (
                    "❌ You are not authorized "
                    "to verify payments."
                )
            )

            return

        # -------------------------------------------------
        # GET PAYMENT DATA FROM DM MESSAGE
        # -------------------------------------------------

        data = get_payment_request_data(
            interaction.message
        )

        if data is None:

            await interaction.response.send_message(
                (
                    "❌ I could not read the payment "
                    "request information."
                )
            )

            return

        (
            guild_id,
            channel_id,
            customer_id
        ) = data

        # -------------------------------------------------
        # GET SERVER
        # -------------------------------------------------

        guild = interaction.client.get_guild(
            guild_id
        )

        if guild is None:

            await interaction.response.send_message(
                (
                    "❌ The server could not be found."
                )
            )

            return

        # -------------------------------------------------
        # GET TICKET
        # -------------------------------------------------

        channel = guild.get_channel(
            channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                (
                    "❌ The ticket could not be found. "
                    "It may have already been deleted."
                )
            )

            return

        # -------------------------------------------------
        # LOCK
        # -------------------------------------------------

        lock = get_payment_lock(
            channel.id
        )

        async with lock:

            # -------------------------------------------------
            # SECURITY CHECK
            # -------------------------------------------------

            ticket_owner_id = get_ticket_owner_id(
                channel
            )

            if ticket_owner_id != customer_id:

                await interaction.response.send_message(
                    (
                        "❌ Ticket ownership information "
                        "does not match."
                    )
                )

                return

            # -------------------------------------------------
            # CURRENT STATUS
            # -------------------------------------------------

            current_status = get_payment_status(
                channel
            )

            if current_status == "verified":

                await interaction.response.send_message(
                    "⚠️ This payment is already verified."
                )

                return

            if current_status != "reported":

                await interaction.response.send_message(
                    (
                        "⚠️ This payment is not currently "
                        "waiting for verification."
                    )
                )

                return

            # -------------------------------------------------
            # UPDATE STATUS
            # -------------------------------------------------

            updated = await set_payment_status(
                channel,
                "verified"
            )

            if not updated:

                await interaction.response.send_message(
                    (
                        "❌ I could not update the payment "
                        "status in the ticket."
                    )
                )

                return

            # -------------------------------------------------
            # OWNER DM RESPONSE
            # -------------------------------------------------

            await interaction.response.send_message(
                (
                    "✅ **Payment verified successfully!**\n\n"
                    f"🎫 Ticket: **{channel.name}**\n"
                    f"👤 Customer ID: **{customer_id}**"
                )
            )

            # -------------------------------------------------
            # UPDATE ORIGINAL PAYMENT REQUEST
            # -------------------------------------------------

            try:

                if interaction.message is not None:

                    verified_embed = discord.Embed(
                        title="✅ Payment Verified",
                        description=(
                            "This payment has been manually "
                            "verified by the bot owner."
                        ),
                        color=discord.Color.green()
                    )

                    verified_embed.add_field(
                        name="👤 Customer",
                        value=(
                            f"<@{customer_id}>"
                        ),
                        inline=True
                    )

                    verified_embed.add_field(
                        name="🎫 Ticket",
                        value=channel.mention,
                        inline=True
                    )

                    verified_embed.add_field(
                        name="🌐 Server",
                        value=guild.name,
                        inline=False
                    )

                    verified_embed.set_footer(
                        text="Payment status: VERIFIED"
                    )

                    await interaction.message.edit(
                        content=(
                            "✅ **Payment verified.**"
                        ),
                        embed=verified_embed,
                        view=None
                    )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Could not update owner payment message: "
                    f"{error}"
                )

            # -------------------------------------------------
            # MESSAGE IN TICKET
            # -------------------------------------------------

            try:

                await channel.send(
                    (
                        "✅ **Payment verified by the "
                        "server owner.**\n\n"
                        "Your payment has been manually "
                        "verified and your order can continue."
                    )
                )

            except discord.Forbidden:

                print(
                    "⚠️ Cannot send verification message "
                    "inside ticket."
                )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Verification ticket message error: "
                    f"{error}"
                )

            # -------------------------------------------------
            # CUSTOMER DM
            # -------------------------------------------------

            try:

                customer = interaction.client.get_user(
                    customer_id
                )

                if customer is None:

                    customer = await interaction.client.fetch_user(
                        customer_id
                    )

                await customer.send(
                    (
                        "✅ **Your payment has been verified!**\n\n"
                        f"🌐 Server: **{guild.name}**\n"
                        f"🎫 Ticket: **{channel.name}**\n\n"
                        "Your order can now continue."
                    )
                )

            except discord.NotFound:

                print(
                    "⚠️ Customer could not be found."
                )

            except discord.Forbidden:

                print(
                    "⚠️ Customer DMs are disabled."
                )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Could not DM customer: {error}"
                )


# =========================================================
# REJECT PAYMENT BUTTON
# =========================================================

class PaymentRejectButton(
    discord.ui.Button
):

    def __init__(self):

        super().__init__(
            label="❌ Reject Payment",
            style=discord.ButtonStyle.red,
            custom_id="payment_reject"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        # -------------------------------------------------
        # OWNER ONLY
        # -------------------------------------------------

        if not is_owner(interaction):

            await interaction.response.send_message(
                (
                    "❌ You are not authorized "
                    "to reject payments."
                )
            )

            return

        # -------------------------------------------------
        # GET PAYMENT DATA
        # -------------------------------------------------

        data = get_payment_request_data(
            interaction.message
        )

        if data is None:

            await interaction.response.send_message(
                (
                    "❌ I could not read the payment "
                    "request information."
                )
            )

            return

        (
            guild_id,
            channel_id,
            customer_id
        ) = data

        # -------------------------------------------------
        # GET SERVER
        # -------------------------------------------------

        guild = interaction.client.get_guild(
            guild_id
        )

        if guild is None:

            await interaction.response.send_message(
                "❌ The server could not be found."
            )

            return

        # -------------------------------------------------
        # GET TICKET
        # -------------------------------------------------

        channel = guild.get_channel(
            channel_id
        )

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                (
                    "❌ The ticket could not be found. "
                    "It may have already been deleted."
                )
            )

            return

        # -------------------------------------------------
        # LOCK
        # -------------------------------------------------

        lock = get_payment_lock(
            channel.id
        )

        async with lock:

            # -------------------------------------------------
            # SECURITY CHECK
            # -------------------------------------------------

            ticket_owner_id = get_ticket_owner_id(
                channel
            )

            if ticket_owner_id != customer_id:

                await interaction.response.send_message(
                    (
                        "❌ Ticket ownership information "
                        "does not match."
                    )
                )

                return

            # -------------------------------------------------
            # CURRENT STATUS
            # -------------------------------------------------

            current_status = get_payment_status(
                channel
            )

            if current_status == "verified":

                await interaction.response.send_message(
                    (
                        "❌ A verified payment cannot "
                        "be rejected."
                    )
                )

                return

            if current_status != "reported":

                await interaction.response.send_message(
                    (
                        "⚠️ This payment is not currently "
                        "waiting for verification."
                    )
                )

                return

            # -------------------------------------------------
            # UPDATE STATUS
            # -------------------------------------------------

            updated = await set_payment_status(
                channel,
                "rejected"
            )

            if not updated:

                await interaction.response.send_message(
                    (
                        "❌ I could not update the payment "
                        "status in the ticket."
                    )
                )

                return

            # -------------------------------------------------
            # OWNER DM RESPONSE
            # -------------------------------------------------

            await interaction.response.send_message(
                (
                    "❌ **Payment rejected successfully.**\n\n"
                    f"🎫 Ticket: **{channel.name}**\n"
                    f"👤 Customer ID: **{customer_id}**"
                )
            )

            # -------------------------------------------------
            # UPDATE ORIGINAL PAYMENT REQUEST
            # -------------------------------------------------

            try:

                if interaction.message is not None:

                    rejected_embed = discord.Embed(
                        title="❌ Payment Rejected",
                        description=(
                            "This payment has been rejected "
                            "by the bot owner."
                        ),
                        color=discord.Color.red()
                    )

                    rejected_embed.add_field(
                        name="👤 Customer",
                        value=(
                            f"<@{customer_id}>"
                        ),
                        inline=True
                    )

                    rejected_embed.add_field(
                        name="🎫 Ticket",
                        value=channel.mention,
                        inline=True
                    )

                    rejected_embed.add_field(
                        name="🌐 Server",
                        value=guild.name,
                        inline=False
                    )

                    rejected_embed.set_footer(
                        text="Payment status: REJECTED"
                    )

                    await interaction.message.edit(
                        content=(
                            "❌ **Payment rejected.**"
                        ),
                        embed=rejected_embed,
                        view=None
                    )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Could not update owner payment message: "
                    f"{error}"
                )

            # -------------------------------------------------
            # MESSAGE IN TICKET
            # -------------------------------------------------

            try:

                await channel.send(
                    (
                        "❌ **The reported payment could "
                        "not be verified.**\n\n"
                        "Please contact the server owner "
                        "if you believe this is a mistake."
                    )
                )

            except discord.Forbidden:

                print(
                    "⚠️ Cannot send rejection message "
                    "inside ticket."
                )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Rejection ticket message error: "
                    f"{error}"
                )

            # -------------------------------------------------
            # CUSTOMER DM
            # -------------------------------------------------

            try:

                customer = interaction.client.get_user(
                    customer_id
                )

                if customer is None:

                    customer = await interaction.client.fetch_user(
                        customer_id
                    )

                await customer.send(
                    (
                        "❌ **Your payment could not "
                        "be verified.**\n\n"
                        f"🌐 Server: **{guild.name}**\n"
                        f"🎫 Ticket: **{channel.name}**\n\n"
                        "Please contact the server owner."
                    )
                )

            except discord.NotFound:

                print(
                    "⚠️ Customer could not be found."
                )

            except discord.Forbidden:

                print(
                    "⚠️ Customer DMs are disabled."
                )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Could not DM customer: {error}"
                )


# =========================================================
# NORMAL TICKET CLOSE VIEW
# =========================================================

class TicketCloseButton(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="🔒 Close Ticket",
        style=discord.ButtonStyle.red,
        custom_id="ticket_close"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ This is not a text ticket.",
                ephemeral=True
            )

            return

        if not is_ticket_channel(channel):

            await interaction.response.send_message(
                "❌ This channel is not a ticket.",
                ephemeral=True
            )

            return

        ticket_owner_id = get_ticket_owner_id(
            channel
        )

        # -------------------------------------------------
        # OWNER OR TICKET CREATOR
        # -------------------------------------------------

        if (
            interaction.user.id != OWNER_ID
            and interaction.user.id != ticket_owner_id
        ):

            await interaction.response.send_message(
                (
                    "❌ Only the ticket creator or "
                    "the bot owner can close this ticket."
                ),
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 This ticket will be closed in 15 seconds..."
        )

        await asyncio.sleep(15)

        try:

            await channel.delete(
                reason="Ticket closed"
            )

        except discord.NotFound:
            pass

        except discord.Forbidden:

            print(
                "❌ I don't have permission to delete "
                "this ticket."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Ticket deletion error: {error}"
            )


# =========================================================
# ORDER MODAL
# =========================================================

class BotOrderModal(
    discord.ui.Modal,
    title="Order a Bot"
):

    idea = discord.ui.TextInput(
        label="Describe your idea",
        placeholder="What kind of bot do you want?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000
    )

    features = discord.ui.TextInput(
        label="What should the bot be able to do?",
        placeholder=(
            "Commands, systems, features, etc."
        ),
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    requirements = discord.ui.TextInput(
        label="Special requirements",
        placeholder=(
            "Design, integrations, permissions, etc."
        ),
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    extra = discord.ui.TextInput(
        label="Anything else?",
        placeholder=(
            "Anything else you want me to know?"
        ),
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    def __init__(
        self,
        package_name: str,
        package_price: str
    ):

        super().__init__()

        self.package_name = package_name
        self.package_price = package_price

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        guild = interaction.guild
        user = interaction.user
        channel = interaction.channel

        if guild is None:

            await interaction.response.send_message(
                (
                    "❌ This form can only be used "
                    "inside a server."
                ),
                ephemeral=True
            )

            return

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ Invalid ticket channel.",
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # SECURITY CHECK
        # -------------------------------------------------

        if get_ticket_owner_id(channel) != user.id:

            await interaction.response.send_message(
                (
                    "❌ Only the ticket creator can "
                    "place this order."
                ),
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        owner = await get_bot_owner(
            interaction.client
        )

        # -------------------------------------------------
        # ORDER EMBED
        # -------------------------------------------------

        embed = discord.Embed(
            title="🤖 New Bot Order",
            description=(
                f"New order from {user.mention}"
            ),
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="💰 Package",
            value=(
                f"{self.package_name} — "
                f"{self.package_price}"
            ),
            inline=False
        )

        embed.add_field(
            name="💡 Bot Idea",
            value=self.idea.value,
            inline=False
        )

        embed.add_field(
            name="⚙️ Features",
            value=self.features.value,
            inline=False
        )

        embed.add_field(
            name="📋 Special Requirements",
            value=(
                self.requirements.value
                or "None"
            ),
            inline=False
        )

        embed.add_field(
            name="📝 Additional Information",
            value=(
                self.extra.value
                or "None"
            ),
            inline=False
        )

        embed.add_field(
            name="🎫 Ticket",
            value=channel.mention,
            inline=False
        )

        embed.set_footer(
            text=f"Customer: {user}"
        )

        # -------------------------------------------------
        # UPDATE TICKET
        # -------------------------------------------------

        try:

            await channel.edit(
                topic=build_ticket_topic(
                    owner_id=user.id,
                    ticket_type="order",
                    payment_status="pending"
                ),
                reason="Ticket converted to order"
            )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    "❌ I cannot update the ticket "
                    "information."
                ),
                ephemeral=True
            )

            return

        except discord.HTTPException as error:

            print(
                f"❌ Could not update order ticket: {error}"
            )

            await interaction.followup.send(
                (
                    "❌ Something went wrong while "
                    "preparing your order."
                ),
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # SEND ORDER MESSAGE
        # -------------------------------------------------

        try:

            await channel.send(
                content=(
                    f"👋 Welcome {user.mention}!\n\n"

                    "Thank you for your order! 🤖\n\n"

                    "Your order has been received successfully.\n\n"

                    "We will review your request and work "
                    "on it within a maximum of **5 days**.\n\n"

                    "The exact development time depends on "
                    "the complexity of your bot, the number "
                    "of requested features and the overall "
                    "requirements.\n\n"

                    f"💳 **Payment: {self.package_price}**\n\n"

                    "Please choose one of the payment "
                    "methods below.\n\n"

                    "After completing the payment, click "
                    "**✅ Confirm Payment**.\n\n"

                    "⚠️ Payment completion is manually verified."
                ),
                embed=embed,
                view=PaymentButtons()
            )

            await channel.send(
                (
                    "🔒 **Finished with your order?**\n"
                    "You can close this ticket using "
                    "the button below."
                ),
                view=TicketCloseButton()
            )

        except discord.Forbidden:

            print(
                "❌ I cannot send messages in the order ticket."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Could not send order messages: {error}"
            )

        # -------------------------------------------------
        # OWNER NOTIFICATION
        # -------------------------------------------------

        if owner is not None:

            try:

                await owner.send(
                    "📩 **New Bot Order Received**",
                    embed=embed
                )

            except discord.Forbidden:

                print(
                    "⚠️ Could not DM the bot owner."
                )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Owner DM error: {error}"
                )

        # -------------------------------------------------
        # CUSTOMER CONFIRMATION
        # -------------------------------------------------

        await interaction.followup.send(
            (
                "✅ **Thank you for your order!**\n\n"

                "Your information has been received.\n\n"

                f"Selected package: **{self.package_name}** "
                f"({self.package_price})\n\n"

                "Please complete your payment and then "
                "click **✅ Confirm Payment**."
            ),
            ephemeral=True
        )


# =========================================================
# PACKAGE VIEW
# =========================================================

class PackageButton(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=120
        )

    @discord.ui.button(
        label="🟢 Starter — €4.99",
        style=discord.ButtonStyle.green,
        custom_id="package_starter"
    )
    async def starter(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            BotOrderModal(
                PACKAGES["starter"]["name"],
                PACKAGES["starter"]["price"]
            )
        )

    @discord.ui.button(
        label="🔵 Pro — €9.99",
        style=discord.ButtonStyle.blurple,
        custom_id="package_pro"
    )
    async def pro(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            BotOrderModal(
                PACKAGES["pro"]["name"],
                PACKAGES["pro"]["price"]
            )
        )

    @discord.ui.button(
        label="🟣 Advanced — €14.99",
        style=discord.ButtonStyle.gray,
        custom_id="package_advanced"
    )
    async def advanced(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            BotOrderModal(
                PACKAGES["advanced"]["name"],
                PACKAGES["advanced"]["price"]
            )
        )


# =========================================================
# TICKET TYPE VIEW
# =========================================================

class TicketTypeButton(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    # -----------------------------------------------------
    # SUPPORT
    # -----------------------------------------------------

    @discord.ui.button(
        label="🛠️ Support",
        style=discord.ButtonStyle.green,
        custom_id="ticket_support"
    )
    async def support(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ Invalid ticket channel.",
                ephemeral=True
            )

            return

        if get_ticket_owner_id(channel) != interaction.user.id:

            await interaction.response.send_message(
                (
                    "❌ Only the ticket creator can "
                    "use this option."
                ),
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            (
                "🛠️ **Support**\n\n"
                "Please describe your problem here.\n"
                "A staff member will help you as soon as possible."
            )
        )

    # -----------------------------------------------------
    # ORDER
    # -----------------------------------------------------

    @discord.ui.button(
        label="🤖 Order Now",
        style=discord.ButtonStyle.green,
        custom_id="ticket_order_bot"
    )
    async def order_bot(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ Invalid ticket channel.",
                ephemeral=True
            )

            return

        if get_ticket_owner_id(channel) != interaction.user.id:

            await interaction.response.send_message(
                (
                    "❌ Only the ticket creator can "
                    "place the order."
                ),
                ephemeral=True
            )

            return

        embed = discord.Embed(
            title="🤖 Custom Discord Bots",
            description=(
                "Choose the package that fits your project.\n\n"
                "All packages are customized according "
                "to your requirements."
            ),
            color=discord.Color.blurple()
        )

        # -------------------------------------------------
        # STARTER
        # -------------------------------------------------

        embed.add_field(
            name="🟢 STARTER — €4.99",
            value=(
                "*Great for simple projects*\n\n"

                "👋 **Welcome System**\n"
                "Automatically welcomes new members.\n\n"

                "⚡ **Basic Commands**\n"
                "Help, ping and server information.\n\n"

                "💬 **Custom Responses**\n"
                "Automatic replies to selected messages.\n\n"

                "🛠️ **Basic Configuration**\n"
                "Basic settings and customization."
            ),
            inline=False
        )

        # -------------------------------------------------
        # PRO
        # -------------------------------------------------

        embed.add_field(
            name="🔵 PRO — €9.99",
            value=(
                "*Great for growing Discord servers*\n\n"

                "✅ **Everything in Starter**\n"
                "Includes all Starter features.\n\n"

                "🛡️ **Moderation Commands**\n"
                "Kick, ban, timeout and message management.\n\n"

                "🎯 **Custom Commands**\n"
                "Commands created specifically for your server.\n\n"

                "🎫 **Ticket System**\n"
                "Private support and order tickets.\n\n"

                "⚙️ **Advanced Configuration**\n"
                "More control over roles, channels "
                "and bot behaviour."
            ),
            inline=False
        )

        # -------------------------------------------------
        # ADVANCED
        # -------------------------------------------------

        embed.add_field(
            name="🟣 ADVANCED — €14.99",
            value=(
                "*Great for advanced custom projects*\n\n"

                "✅ **Everything in Pro**\n"
                "Includes all Pro features.\n\n"

                "🗄️ **Database Features**\n"
                "Store points, levels and statistics.\n\n"

                "🔄 **Advanced Automation**\n"
                "Automate multiple actions and systems.\n\n"

                "🔐 **Advanced Permissions**\n"
                "Detailed control over features.\n\n"

                "📊 **Custom Server Systems**\n"
                "Systems designed specifically for your server.\n\n"

                "🧩 **Advanced Custom Features**\n"
                "Extra functionality based on your project."
            ),
            inline=False
        )

        # -------------------------------------------------
        # READY
        # -------------------------------------------------

        embed.add_field(
            name="🚀 Ready to build your bot?",
            value=(
                "Choose your package below and tell us "
                "what your bot should do.\n\n"
                "We'll review your idea and get started!"
            ),
            inline=False
        )

        embed.set_footer(
            text="⏳ Package selection expires after 2 minutes."
        )

        await interaction.response.send_message(
            embed=embed,
            view=PackageButton(),
            ephemeral=True
        )


# =========================================================
# CREATE TICKET VIEW
# =========================================================

class TicketButton(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="🎫 Create Ticket",
        style=discord.ButtonStyle.green,
        custom_id="ticket_create"
    )
    async def create_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        guild = interaction.guild
        user = interaction.user

        if guild is None:

            await interaction.response.send_message(
                (
                    "❌ This button can only be used "
                    "inside a server."
                ),
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        # -------------------------------------------------
        # LOCK
        # -------------------------------------------------

        async with ticket_creation_lock:

            now = discord.utils.utcnow()

            # -------------------------------------------------
            # EXISTING TICKET
            # -------------------------------------------------

            existing_ticket = discord.utils.get(
                guild.text_channels,
                name=f"ticket-{user.id}"
            )

            existing_order = discord.utils.get(
                guild.text_channels,
                name=f"order-{user.id}"
            )

            if (
                existing_ticket is not None
                or existing_order is not None
            ):

                await interaction.followup.send(
                    (
                        "❌ You already have an "
                        "open ticket or order."
                    ),
                    ephemeral=True
                )

                return

            # -------------------------------------------------
            # COOLDOWN
            # -------------------------------------------------

            last_ticket = ticket_cooldowns.get(
                user.id
            )

            if last_ticket is not None:

                remaining = (
                    COOLDOWN
                    - (now - last_ticket)
                )

                if remaining.total_seconds() > 0:

                    total_seconds = int(
                        remaining.total_seconds()
                    )

                    minutes = total_seconds // 60
                    seconds = total_seconds % 60

                    await interaction.followup.send(
                        (
                            f"⏳ Please wait **{minutes} "
                            f"minutes and {seconds} seconds** "
                            "before creating another ticket."
                        ),
                        ephemeral=True
                    )

                    return

            # -------------------------------------------------
            # BOT MEMBER
            # -------------------------------------------------

            bot_member = guild.me

            if bot_member is None:

                await interaction.followup.send(
                    "❌ I could not find my bot member.",
                    ephemeral=True
                )

                return

            # -------------------------------------------------
            # SERVER OWNER
            # -------------------------------------------------

            owner_member = get_owner_member(
                guild
            )

            # -------------------------------------------------
            # PERMISSIONS
            # -------------------------------------------------

            overwrites = {

                guild.default_role:
                    discord.PermissionOverwrite(
                        view_channel=False
                    ),

                user:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        attach_files=True,
                        embed_links=True
                    ),

                bot_member:
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                        manage_channels=True,
                        manage_messages=True
                    )
            }

            if owner_member is not None:

                overwrites[
                    owner_member
                ] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

            # -------------------------------------------------
            # SAVE COOLDOWN
            # -------------------------------------------------

            ticket_cooldowns[user.id] = now

            # -------------------------------------------------
            # CREATE CHANNEL
            # -------------------------------------------------

            try:

                channel = await guild.create_text_channel(
                    name=f"ticket-{user.id}",
                    overwrites=overwrites,
                    topic=build_ticket_topic(
                        owner_id=user.id,
                        ticket_type="support",
                        payment_status="pending"
                    ),
                    reason=(
                        f"Support ticket created by {user}"
                    )
                )

            except discord.Forbidden:

                ticket_cooldowns.pop(
                    user.id,
                    None
                )

                await interaction.followup.send(
                    (
                        "❌ I don't have permission to "
                        "create or manage channels."
                    ),
                    ephemeral=True
                )

                return

            except discord.HTTPException as error:

                ticket_cooldowns.pop(
                    user.id,
                    None
                )

                print(
                    f"❌ Ticket creation error: {error}"
                )

                await interaction.followup.send(
                    (
                        "❌ Something went wrong while "
                        "creating your ticket."
                    ),
                    ephemeral=True
                )

                return

        # -------------------------------------------------
        # CONFIRM
        # -------------------------------------------------

        await interaction.followup.send(
            (
                "✅ Your ticket has been created: "
                f"{channel.mention}"
            ),
            ephemeral=True
        )

        # -------------------------------------------------
        # TICKET PANEL
        # -------------------------------------------------

        try:

            await channel.send(
                (
                    "🎫 **What do you need help with?**\n\n"
                    "Please choose an option below:"
                ),
                view=TicketTypeButton()
            )

            await channel.send(
                (
                    "🔒 **Finished with your ticket?**\n"
                    "You can close this ticket using "
                    "the button below."
                ),
                view=TicketCloseButton()
            )

        except discord.Forbidden:

            print(
                "❌ I cannot send messages in the new ticket."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Could not send ticket panel: {error}"
            )


# =========================================================
# SHOWCASE ACTION VIEW
# =========================================================

class DemoActionView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    # -----------------------------------------------------
    # ORDER BOT
    # -----------------------------------------------------

    @discord.ui.button(
        label="🤖 Order Bot",
        style=discord.ButtonStyle.blurple,
        custom_id="showcase_order_bot"
    )
    async def order_bot(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ Invalid showcase channel.",
                ephemeral=True
            )

            return

        if not is_showcase_channel(channel):

            await interaction.response.send_message(
                "❌ This is not a showcase demo.",
                ephemeral=True
            )

            return

        embed = discord.Embed(
            title="🤖 Order Bot — Demo",
            description=(
                "🚀 **You just tested one possible feature!**\n\n"

                "This button could open an order system, "
                "display your services, show your packages, "
                "start a purchase process, open another menu, "
                "or perform a completely different action.\n\n"

                "💬 **This message can be changed too.**\n\n"

                "🎨 Your colors.\n"
                "📝 Your texts.\n"
                "🔘 Your buttons.\n"
                "⚙️ Your functions.\n"
                "✨ Your design."
            ),
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🔧 Completely Customizable",
            value=(
                "The function, message, name and appearance "
                "can all be changed."
            ),
            inline=False
        )

        embed.add_field(
            name="🚀 Unlimited Possibilities",
            value=(
                "Your bot can contain buttons, menus, pages "
                "and many custom functions."
            ),
            inline=False
        )

        embed.set_footer(
            text=(
                "Demo feature • Everything can be customized"
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # -----------------------------------------------------
    # YOUR CHOICE
    # -----------------------------------------------------

    @discord.ui.button(
        label="✨ Your Choice",
        style=discord.ButtonStyle.green,
        custom_id="showcase_your_choice"
    )
    async def your_choice(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ Invalid showcase channel.",
                ephemeral=True
            )

            return

        if not is_showcase_channel(channel):

            await interaction.response.send_message(
                "❌ This is not a showcase demo.",
                ephemeral=True
            )

            return

        embed = discord.Embed(
            title="✨ Your Choice — Demo",
            description=(
                "💡 **This button is an example of "
                "your choice.**\n\n"

                "Imagine this button doing exactly "
                "what you want.\n\n"

                "Maybe it opens a menu.\n"
                "Maybe it shows information.\n"
                "Maybe it starts an application.\n"
                "Maybe it opens another ticket.\n"
                "Maybe it connects to another system.\n\n"

                "🎨 **You decide.**"
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="🔘 More Than Just 2–3 Buttons",
            value=(
                "You can have multiple buttons, menus and "
                "interactive systems."
            ),
            inline=False
        )

        embed.add_field(
            name="🎯 Built Around Your Vision",
            value=(
                "Instead of changing your idea to fit a "
                "standard bot, the bot can be designed "
                "around your idea."
            ),
            inline=False
        )

        embed.set_footer(
            text="Your choice • Your design • Your bot"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


# =========================================================
# SHOWCASE CLOSE VIEW
# =========================================================

class ShowcaseCloseButton(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="🔒 Close Ticket",
        style=discord.ButtonStyle.red,
        custom_id="showcase_close_ticket"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        channel = interaction.channel

        if not isinstance(
            channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ This is not a showcase ticket.",
                ephemeral=True
            )

            return

        if not is_showcase_channel(channel):

            await interaction.response.send_message(
                "❌ This is not a showcase demo ticket.",
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # GET DEMO OWNER
        # -------------------------------------------------

        raw_owner_id = get_topic_value(
            channel.topic,
            "showcase-owner"
        )

        try:

            showcase_owner_id = int(
                raw_owner_id
            )

        except (TypeError, ValueError):

            await interaction.response.send_message(
                "❌ Invalid showcase owner information.",
                ephemeral=True
            )

            return

        # -------------------------------------------------
        # SECURITY
        # -------------------------------------------------

        if (
            interaction.user.id != showcase_owner_id
            and interaction.user.id != OWNER_ID
        ):

            await interaction.response.send_message(
                (
                    "❌ Only the demo creator or "
                    "the bot owner can close this demo."
                ),
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            "🔒 **Closing this demo ticket...**"
        )

        await asyncio.sleep(2)

        try:

            await channel.delete(
                reason="Showcase demo ticket closed"
            )

        except discord.NotFound:
            pass

        except discord.Forbidden:

            print(
                "❌ I cannot delete the showcase ticket."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Showcase deletion error: {error}"
            )


# =========================================================
# CREATE DEMO TICKET
# =========================================================

async def create_demo_ticket(
    interaction: discord.Interaction
):

    guild = interaction.guild
    user = interaction.user

    if guild is None:

        await interaction.response.send_message(
            (
                "❌ This demo can only be used "
                "inside a server."
            ),
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    # -----------------------------------------------------
    # EXISTING DEMO
    # -----------------------------------------------------

    for channel in guild.text_channels:

        raw_owner = get_topic_value(
            channel.topic,
            "showcase-owner"
        )

        demo_value = get_topic_value(
            channel.topic,
            "showcase-demo"
        )

        if (
            raw_owner == str(user.id)
            and demo_value == "true"
        ):

            await interaction.followup.send(
                (
                    "✨ **You already have a demo ticket!**\n\n"
                    f"➡️ {channel.mention}"
                ),
                ephemeral=True
            )

            return

    # -----------------------------------------------------
    # CATEGORY
    # -----------------------------------------------------

    category = discord.utils.get(
        guild.categories,
        name=SHOWCASE_CATEGORY_NAME
    )

    if category is None:

        try:

            category = await guild.create_category(
                SHOWCASE_CATEGORY_NAME,
                reason="Create showcase demo category"
            )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    "❌ I don't have permission to "
                    "create the showcase category."
                ),
                ephemeral=True
            )

            return

        except discord.HTTPException as error:

            print(
                f"❌ Category creation error: {error}"
            )

            await interaction.followup.send(
                (
                    "❌ Could not create the "
                    "showcase category."
                ),
                ephemeral=True
            )

            return

    # -----------------------------------------------------
    # BOT MEMBER
    # -----------------------------------------------------

    bot_member = guild.me

    if (
        bot_member is None
        and bot.user is not None
    ):

        bot_member = guild.get_member(
            bot.user.id
        )

    if bot_member is None:

        await interaction.followup.send(
            "❌ I could not find my bot member.",
            ephemeral=True
        )

        return

    # -----------------------------------------------------
    # OWNER MEMBER
    # -----------------------------------------------------

    owner_member = get_owner_member(
        guild
    )

    # -----------------------------------------------------
    # PERMISSIONS
    # -----------------------------------------------------

    overwrites = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        user:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),

        bot_member:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True
            )
    }

    if owner_member is not None:

        overwrites[
            owner_member
        ] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

    # -----------------------------------------------------
    # SAFE CHANNEL NAME
    # -----------------------------------------------------

    username = user.name.lower()

    safe_username = "".join(
        char
        if (
            char.isalnum()
            or char in "-_"
        )
        else "-"
        for char in username
    )

    safe_username = (
        safe_username
        .replace("_", "-")
        .strip("-")
    )

    if not safe_username:

        safe_username = "user"

    channel_name = (
        f"demo-{safe_username}-{user.id}"
    )[:MAX_CHANNEL_NAME_LENGTH]

    # -----------------------------------------------------
    # CREATE CHANNEL
    # -----------------------------------------------------

    try:

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=build_showcase_topic(
                user.id
            ),
            reason=(
                f"Showcase demo created for {user}"
            )
        )

    except discord.Forbidden:

        await interaction.followup.send(
            (
                "❌ I don't have permission to "
                "create the demo ticket."
            ),
            ephemeral=True
        )

        return

    except discord.HTTPException as error:

        print(
            f"❌ Demo ticket creation error: {error}"
        )

        await interaction.followup.send(
            "❌ Could not create the demo ticket.",
            ephemeral=True
        )

        return

    # -----------------------------------------------------
    # DEMO EMBED
    # -----------------------------------------------------

    embed = discord.Embed(
        title="🚀 Welcome to Your Custom Bot Demo!",
        description=(
            "🎉 **Welcome! You are now inside a private "
            "demo ticket.**\n\n"

            "This is a preview of what your own custom "
            "Discord bot could look like.\n\n"

            "✨ Everything you see here can be changed.\n\n"

            "🎨 **Colors**\n"
            "📝 **Texts**\n"
            "🔘 **Buttons**\n"
            "😀 **Emojis**\n"
            "📦 **Embeds**\n"
            "⚙️ **Functions**\n"
            "🔐 **Permissions**\n"
            "📁 **Categories and channels**\n"
            "💬 **Messages and responses**\n\n"

            "🔥 **You are not limited to this design.**"
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🎨 Make It Your Own",
        value=(
            "Imagine this bot with your own colors, "
            "branding, messages and style."
        ),
        inline=False
    )

    embed.add_field(
        name="🔘 Buttons? You Decide!",
        value=(
            "You can use buttons, menus and many "
            "different interactive systems."
        ),
        inline=False
    )

    embed.add_field(
        name="⚡ What Can Be Customized?",
        value=(
            "💬 Messages\n"
            "🎨 Colors\n"
            "🔘 Buttons\n"
            "📋 Menus\n"
            "🤖 Bot functions\n"
            "🔐 Permissions\n"
            "📁 Channels\n"
            "📦 Embeds\n"
            "✨ Branding\n"
            "⚙️ Automations"
        ),
        inline=False
    )

    embed.add_field(
        name="💎 Want Something Like This?",
        value=(
            "This demo is only an example. "
            "A custom bot can be designed around "
            "your own project and requirements."
        ),
        inline=False
    )

    embed.set_footer(
        text=(
            "🎫 Demo Ticket • Everything is customizable"
        )
    )

    # -----------------------------------------------------
    # SEND DEMO
    # -----------------------------------------------------

    try:

        await ticket_channel.send(
            content=(
                f"👋 **Welcome {user.mention}!**\n\n"
                "🔥 Your private demo is ready!"
            ),
            embed=embed,
            view=DemoActionView()
        )

        await ticket_channel.send(
            (
                "👇 **Try the buttons below!**\n\n"
                "🤖 **Order Bot** and ✨ **Your Choice** "
                "are example functions.\n\n"
                "🔒 Use **Close Ticket** whenever "
                "you are finished."
            ),
            view=ShowcaseCloseButton()
        )

    except discord.Forbidden:

        try:

            await ticket_channel.delete(
                reason=(
                    "Cleanup after failed showcase setup"
                )
            )

        except discord.HTTPException:
            pass

        await interaction.followup.send(
            (
                "❌ The ticket was created, but "
                "I cannot send messages inside it."
            ),
            ephemeral=True
        )

        return

    except discord.HTTPException as error:

        print(
            f"❌ Demo message error: {error}"
        )

        await interaction.followup.send(
            (
                "❌ The ticket was created, but "
                "the demo could not be initialized."
            ),
            ephemeral=True
        )

        return

    # -----------------------------------------------------
    # REDIRECT
    # -----------------------------------------------------

    await interaction.followup.send(
        (
            "🎉 **Your Demo Ticket is Ready!**\n\n"
            "🚀 Click below to enter your private demo:\n\n"
            f"🎫 {ticket_channel.mention}\n\n"
            "✨ Enjoy exploring the demo!"
        ),
        ephemeral=True
    )


# =========================================================
# SHOWCASE VIEW
# =========================================================

class ShowcaseView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="🎫 Create Demo Ticket",
        style=discord.ButtonStyle.green,
        custom_id="create_showcase_demo"
    )
    async def create_demo(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await create_demo_ticket(
            interaction
        )


# =========================================================
# BOT CLASS
# =========================================================

class TicketBot(
    commands.Bot
):

    async def setup_hook(self):

        # -------------------------------------------------
        # AI
        # -------------------------------------------------

        if (
            settings is not None
            and settings.ai_enabled
        ):

            from ai_agent import AIAgentCog

            await self.add_cog(
                AIAgentCog(
                    self,
                    settings
                )
            )

        # -------------------------------------------------
        # PERSISTENT VIEWS
        # -------------------------------------------------

        self.add_view(
            TicketButton()
        )

        self.add_view(
            TicketTypeButton()
        )

        self.add_view(
            TicketCloseButton()
        )

        self.add_view(
            PaymentButtons()
        )

        self.add_view(
            PaymentVerificationView()
        )

        self.add_view(
            ShowcaseView()
        )

        self.add_view(
            DemoActionView()
        )

        self.add_view(
            ShowcaseCloseButton()
        )

        # -------------------------------------------------
        # SLASH COMMAND SYNC
        # -------------------------------------------------

        if (
            settings is not None
            and settings.ai_enabled
        ):

            try:

                await self.tree.sync()

                print(
                    "✅ Slash commands synced."
                )

            except discord.HTTPException as error:

                print(
                    f"⚠️ Slash command sync failed: {error}"
                )


# =========================================================
# BOT INSTANCE
# =========================================================

bot = TicketBot(
    command_prefix="!",
    intents=intents
)


# =========================================================
# WELCOME SYSTEM
# =========================================================

@bot.event
async def on_member_join(
    member: discord.Member
):

    channel = discord.utils.get(
        member.guild.text_channels,
        name=WELCOME_CHANNEL_NAME
    )

    if channel is None:

        print(
            f"⚠️ Welcome channel "
            f"'{WELCOME_CHANNEL_NAME}' was not found."
        )

        return

    try:

        embed = discord.Embed(
            title="👋 Welcome!",
            description=(
                f"Welcome {member.mention}!\n\n"
                "Thank you for joining! 🎉"
            ),
            color=discord.Color.blurple()
        )

        await channel.send(
            embed=embed
        )

        print(
            f"✅ Welcomed {member}."
        )

    except discord.Forbidden:

        print(
            "❌ I don't have permission to send "
            "messages in the welcome channel."
        )

    except discord.HTTPException as error:

        print(
            f"❌ Welcome message error: {error}"
        )


# =========================================================
# ERROR LOGGING
# =========================================================

@bot.event
async def on_error(
    event,
    *args,
    **kwargs
):

    print(
        f"\n❌ ERROR IN EVENT: {event}"
    )

    traceback.print_exc()


# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    print(
        "========================================"
    )

    print(
        f"✅ Bot is online as {bot.user}"
    )

    if bot.user is not None:

        print(
            f"🆔 Bot ID: {bot.user.id}"
        )

    print(
        "========================================"
    )

    # =====================================================
    # NORMAL TICKET CHANNEL
    # =====================================================

    channel = discord.utils.get(
        bot.get_all_channels(),
        name=TICKET_CHANNEL_NAME
    )

    if channel is None:

        print(
            f"❌ Channel '{TICKET_CHANNEL_NAME}' "
            "was not found."
        )

    elif not isinstance(
        channel,
        discord.TextChannel
    ):

        print(
            f"❌ '{TICKET_CHANNEL_NAME}' "
            "is not a text channel."
        )

    else:

        print(
            f"✅ Ticket channel found: "
            f"#{channel.name}"
        )

        panel_exists = False

        try:

            async for message in channel.history(
                limit=MAX_PANEL_HISTORY
            ):

                if (
                    bot.user is not None
                    and message.author.id == bot.user.id
                    and message.components
                ):

                    panel_exists = True

                    print(
                        "✅ Ticket panel already exists."
                    )

                    break

        except discord.Forbidden:

            print(
                "❌ I cannot read the ticket channel history."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Could not check ticket history: {error}"
            )

        # -------------------------------------------------
        # CREATE NORMAL PANEL
        # -------------------------------------------------

        if not panel_exists:

            embed = discord.Embed(
                title="🎫 Support & Orders",
                description=(
                    "Need help or want to order "
                    "a custom bot?\n\n"

                    "Click **🎫 Create Ticket** to open "
                    "a private ticket.\n\n"

                    "💳 **Payment Methods**\n"
                    "We currently accept **Revolut and PayPal**.\n\n"

                    "💻 **Development**\n"
                    "All custom bots are developed using **Python**.\n\n"

                    "⏳ **Development Time**\n"
                    "Depending on the complexity, features and "
                    "requirements of your bot, development can "
                    "take **up to 5 days**.\n\n"

                    "The exact development time depends on "
                    "how much work is required, how many "
                    "features you request and what the bot "
                    "needs to be able to do.\n\n"

                    "📋 **Requirements**\n"
                    "Your Discord server must already be set up before ordering.\n"
                    "You must add me to your server so I can set up and configure the bot.\n"
                    "Please make sure I have the necessary permissions to complete the setup."
                ),
                color=discord.Color.blurple()
            )

            embed.set_footer(
                text=(
                    "Payment completion is manually verified."
                )
            )

            try:

                await channel.send(
                    embed=embed,
                    view=TicketButton()
                )

                print(
                    "✅ Ticket panel created successfully."
                )

            except discord.Forbidden:

                print(
                    "❌ I don't have permission to send "
                    "messages in the ticket channel."
                )

            except discord.HTTPException as error:

                print(
                    f"❌ Could not create ticket panel: {error}"
                )

    # =====================================================
    # SHOWCASE CHANNEL
    # =====================================================

    showcase_channel = discord.utils.get(
        bot.get_all_channels(),
        name=SHOWCASE_CHANNEL_NAME
    )

    if showcase_channel is None:

        print(
            f"❌ Showcase channel "
            f"'{SHOWCASE_CHANNEL_NAME}' was not found."
        )

        return

    if not isinstance(
        showcase_channel,
        discord.TextChannel
    ):

        print(
            f"❌ Showcase channel "
            f"'{SHOWCASE_CHANNEL_NAME}' is not "
            "a text channel."
        )

        return

    print(
        f"✅ Showcase channel found: "
        f"#{showcase_channel.name}"
    )

    # -----------------------------------------------------
    # CHECK SHOWCASE PANEL
    # -----------------------------------------------------

    showcase_exists = False

    try:

        async for message in showcase_channel.history(
            limit=MAX_PANEL_HISTORY
        ):

            if (
                bot.user is not None
                and message.author.id == bot.user.id
                and message.components
            ):

                showcase_exists = True

                print(
                    "✅ Showcase panel already exists."
                )

                break

    except discord.Forbidden:

        print(
            "❌ I cannot read the showcase history."
        )

        return

    except discord.HTTPException as error:

        print(
            f"❌ Could not check showcase history: {error}"
        )

        return

    # -----------------------------------------------------
    # CREATE SHOWCASE PANEL
    # -----------------------------------------------------

    if not showcase_exists:

        embed = discord.Embed(
            title="🤖✨ CUSTOM DISCORD BOT SHOWCASE ✨🤖",
            description=(
                "🚀 **Want a Discord bot built around "
                "YOUR ideas?**\n\n"

                "Welcome to our interactive bot showcase! 🎉\n\n"

                "This is a live demonstration designed "
                "to show how flexible a custom Discord "
                "bot can be.\n\n"

                "🎨 **Your design.**\n"
                "💬 **Your messages.**\n"
                "🔘 **Your buttons.**\n"
                "⚙️ **Your functions.**\n"
                "✨ **Your vision.**\n\n"

                "Nothing in this demo has to stay the "
                "way it is. The layout, colors, text, "
                "buttons, embeds, permissions and "
                "functions can all be changed.\n\n"

                "🔥 **Ready to see it for yourself?**\n\n"

                "Click the button below and create your "
                "own private demo ticket!"
            ),
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🎫 Interactive Demo",
            value=(
                "Create a private demo ticket and explore "
                "how a custom ticket system can work."
            ),
            inline=False
        )

        embed.add_field(
            name="🎨 Completely Customizable",
            value=(
                "Colors, messages, emojis, buttons, embeds, "
                "permissions, channels and features can "
                "all be designed around your needs."
            ),
            inline=False
        )

        embed.add_field(
            name="🔘 Unlimited Button Ideas",
            value=(
                "You can have multiple buttons, menus and "
                "interactive features."
            ),
            inline=False
        )

        embed.add_field(
            name="⚡ Built Around Your Vision",
            value=(
                "This showcase is only an example. "
                "Your own bot can be completely different "
                "and designed around exactly what you want."
            ),
            inline=False
        )

        embed.add_field(
            name="🚀 Experience The Demo",
            value=(
                "Click **🎫 Create Demo Ticket** below "
                "and see what a custom bot experience "
                "could look like!"
            ),
            inline=False
        )

        embed.set_footer(
            text="💎 Your Idea • Your Design • Your Bot 💎"
        )

        try:

            await showcase_channel.send(
                embed=embed,
                view=ShowcaseView()
            )

            print(
                "✅ Showcase created successfully."
            )

        except discord.Forbidden:

            print(
                "❌ I don't have permission to send "
                "messages in the showcase channel."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Could not send showcase: {error}"
            )


# =========================================================
# START BOT
# =========================================================

if not BOT_TOKEN:

    print(
        "❌ ERROR: DISCORD_BOT_TOKEN is not set."
    )

else:

    bot.run(
        BOT_TOKEN
    )