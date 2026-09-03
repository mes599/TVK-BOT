import asyncio
import os
from datetime import timedelta

import discord
from discord.ext import commands


# =========================================================
# SETTINGS
# =========================================================

TICKET_CHANNEL_NAME = "ticket🎫"
WELCOME_CHANNEL_NAME = "welcome👋"

COOLDOWN = timedelta(minutes=2)

# Payment links
REVOLUT_PAYMENT_URL = "https://revolut.me/ayberkqvg8"
PAYPAL_PAYMENT_URL = "https://paypal.me/aydmraybrk"


# =========================================================
# BOT TOKEN
# =========================================================

# IMPORTANT:
# Do NOT put your token directly into this file.
#
# 1.Windows PowerShell:
# 2.cd "C:\Users\user\Downloads\Dc Bot"
# 3.$env:DISCORD_BOT_TOKEN="DEIN_NEUES_TOKEN"
# 4.py bot.py

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")


# =========================================================
# GLOBALS
# =========================================================

ticket_cooldowns = {}


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()

# Required for message content
intents.message_content = True

# Required for on_member_join
intents.members = True


# =========================================================
# PAYMENT BUTTONS
# =========================================================

class PaymentButtons(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        # Revolut
        self.add_item(
            discord.ui.Button(
                label="💜 Pay with Revolut",
                style=discord.ButtonStyle.link,
                url=REVOLUT_PAYMENT_URL
            )
        )

        # PayPal
        self.add_item(
            discord.ui.Button(
                label="💙 Pay with PayPal",
                style=discord.ButtonStyle.link,
                url=PAYPAL_PAYMENT_URL
            )
        )


# =========================================================
# CLOSE TICKET BUTTON
# =========================================================

class TicketCloseButton(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

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

        if channel is None:
            return

        if not (
            channel.name.startswith("ticket-")
            or channel.name.startswith("order-")
        ):
            await interaction.response.send_message(
                "❌ This channel is not a ticket.",
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
                "❌ I don't have permission to delete this channel."
            )

        except discord.HTTPException as error:
            print(
                f"❌ Channel deletion error: {error}"
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
        placeholder="Commands, systems, features, etc.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500
    )

    requirements = discord.ui.TextInput(
        label="Special requirements",
        placeholder="Design, integrations, permissions, etc.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    extra = discord.ui.TextInput(
        label="Anything else?",
        placeholder="Anything else you want me to know?",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    def __init__(
        self,
        package_name,
        package_price
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

        if guild is None or channel is None:

            await interaction.response.send_message(
                "❌ This form can only be used inside a server.",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        # =================================================
        # GET BOT OWNER
        # =================================================

        owner = None

        try:

            application = (
                await interaction.client.application_info()
            )

            owner = application.owner

        except Exception as error:

            print(
                f"⚠️ Could not get bot owner: {error}"
            )

        # =================================================
        # ORDER EMBED
        # =================================================

        embed = discord.Embed(
            title="🤖 New Bot Order",
            description=f"New order from {user.mention}",
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
            value=self.requirements.value or "None",
            inline=False
        )

        embed.add_field(
            name="📝 Additional Information",
            value=self.extra.value or "None",
            inline=False
        )

        embed.set_footer(
            text=f"Customer: {user}"
        )

        # =================================================
        # ORDER MESSAGE
        # =================================================

        try:

            await channel.send(

                f"👋 Welcome {user.mention}!\n\n"

                "Thank you for your order! 🤖\n\n"

                "Your order has been received successfully.\n"

                "We will review your request and work on it "
                "within a maximum of **4 days**.\n\n"

                "💳 **Payment**\n"
                f"Please use one of the buttons below to pay "
                f"**{self.package_price}**.\n\n"

                "After payment, please let us know in this "
                "ticket so the payment can be checked.\n\n"

                "If you have any changes, questions, or "
                "additional requests, please contact "
                "the server owner: <@1137740302094966884> "
                "will contact you as soon as possible.",

                embed=embed,

                view=PaymentButtons()
            )

            # =================================================
            # CLOSE TICKET BUTTON
            # =================================================

            await channel.send(

                "🔒 **Finished with your order?**\n"
                "You can close this ticket using the button below.",

                view=TicketCloseButton()
            )

        except discord.HTTPException as error:

            print(
                f"❌ Could not send order message: {error}"
            )

        # =================================================
        # SEND ORDER TO OWNER
        # =================================================

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

        # =================================================
        # USER CONFIRMATION
        # =================================================

        await interaction.followup.send(

            "✅ **Thank you for your order!**\n\n"

            "Your information has been received.\n"

            f"Selected package: **{self.package_name}** "
            f"({self.package_price})\n\n"

            "Please complete the payment using one of the "
            "payment buttons in the ticket.",

            ephemeral=True
        )


# =========================================================
# PACKAGE BUTTONS
# =========================================================

class PackageButton(discord.ui.View):

    def __init__(self):

        # Package selection expires after 2 minutes.
        super().__init__(timeout=120)

    async def delete_package_message(
        self,
        interaction: discord.Interaction
    ):

        try:

            message = interaction.message

            if message is not None:
                await message.delete()

        except discord.NotFound:
            pass

        except discord.HTTPException as error:

            print(
                f"⚠️ Could not delete package message: {error}"
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

        await self.delete_package_message(
            interaction
        )

        await interaction.response.send_modal(
            BotOrderModal(
                "Starter",
                "€4.99"
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

        await self.delete_package_message(
            interaction
        )

        await interaction.response.send_modal(
            BotOrderModal(
                "Pro",
                "€9.99"
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

        await self.delete_package_message(
            interaction
        )

        await interaction.response.send_modal(
            BotOrderModal(
                "Advanced",
                "€14.99"
            )
        )


# =========================================================
# TICKET TYPE BUTTONS
# =========================================================

class TicketTypeButton(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

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

        await interaction.response.send_message(

            "🛠️ **Support**\n\n"

            "Please describe your problem here.\n"
            "A staff member will help you as soon as possible."

        )

        try:

            message = (
                await interaction.original_response()
            )

            await asyncio.sleep(15)

            await message.delete()

        except discord.NotFound:
            pass

        except discord.HTTPException as error:

            print(
                f"⚠️ Could not delete support message: {error}"
            )

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

        # =================================================
        # PACKAGE EMBED
        # =================================================

        embed = discord.Embed(

            title="🤖 Custom Discord Bots",

            description=(
                "Choose the package that fits your project.\n\n"
                "All packages are customized according to "
                "your requirements."
            ),

            color=discord.Color.blurple()
        )

        # =================================================
        # STARTER
        # =================================================

        embed.add_field(

            name="🟢 STARTER — €4.99",

            value=(
                "*Great for simple projects*\n\n"

                "👋 **Welcome System**\n"
                "Automatically welcomes new members.\n\n"

                "⚡ **Basic Commands**\n"
                "Simple commands like help, ping and "
                "server information.\n\n"

                "💬 **Custom Responses**\n"
                "Automatic replies to selected words "
                "or messages.\n\n"

                "🛠️ **Basic Configuration**\n"
                "Basic settings and customization."
            ),

            inline=False
        )

        # =================================================
        # PRO
        # =================================================

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
                "More control over roles, channels and "
                "bot behaviour."
            ),

            inline=False
        )

        # =================================================
        # ADVANCED
        # =================================================

        embed.add_field(

            name="🟣 ADVANCED — €14.99",

            value=(
                "*Great for advanced custom projects*\n\n"

                "✅ **Everything in Pro**\n"
                "Includes all Pro features.\n\n"

                "🗄️ **Database Features**\n"
                "Store data such as points, levels and "
                "statistics.\n\n"

                "🔄 **Advanced Automation**\n"
                "Automate multiple actions and systems.\n\n"

                "🔐 **Advanced Permissions**\n"
                "Detailed control over who can use features.\n\n"

                "📊 **Custom Server Systems**\n"
                "Systems designed specifically for your server.\n\n"

                "🧩 **Advanced Custom Features**\n"
                "Extra functionality based on your project."
            ),

            inline=False
        )

        # =================================================
        # CALL TO ACTION
        # =================================================

        embed.add_field(

            name="🚀 Ready to build your bot?",

            value=(
                "Choose the package you want below and "
                "tell us what your bot should do.\n\n"
                "We'll review your idea and get started!"
            ),

            inline=False
        )

        embed.set_footer(
            text="⏳ Package selection expires after 2 minutes."
        )

        # =================================================
        # SEND PACKAGE PAGE
        # =================================================

        await interaction.response.send_message(
            embed=embed,
            view=PackageButton()
        )


# =========================================================
# CREATE TICKET BUTTON
# =========================================================

class TicketButton(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

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
                "❌ This button can only be used in a server.",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        now = discord.utils.utcnow()

        # =================================================
        # CHECK EXISTING TICKET
        # =================================================

        existing_ticket = discord.utils.get(
            guild.text_channels,
            name=f"ticket-{user.id}"
        )

        if existing_ticket is not None:

            await interaction.followup.send(
                "❌ You already have an open ticket.",
                ephemeral=True
            )

            return

        # =================================================
        # COOLDOWN
        # =================================================

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

                    f"⏳ Please wait **{minutes} minutes "
                    f"and {seconds} seconds** before "
                    f"creating another ticket.",

                    ephemeral=True
                )

                return

        # =================================================
        # GET BOT OWNER
        # =================================================

        owner = None

        try:

            application = (
                await interaction.client.application_info()
            )

            owner = application.owner

        except Exception as error:

            print(
                f"⚠️ Could not get bot owner: {error}"
            )

        # =================================================
        # START COOLDOWN
        # =================================================

        ticket_cooldowns[user.id] = now

        # =================================================
        # PERMISSIONS
        # =================================================

        overwrites = {

            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        if owner is not None:

            overwrites[owner] = (
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
            )

        # =================================================
        # CREATE CHANNEL
        # =================================================

        try:

            channel = await guild.create_text_channel(

                name=f"ticket-{user.id}",

                overwrites=overwrites,

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

                "❌ I don't have permission to create "
                "or manage channels.",

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

                "❌ Something went wrong while creating "
                "your ticket.",

                ephemeral=True
            )

            return

        # =================================================
        # CONFIRMATION
        # =================================================

        await interaction.followup.send(

            f"✅ Your ticket has been created: "
            f"{channel.mention}",

            ephemeral=True
        )

        # =================================================
        # TICKET PANEL
        # =================================================

        try:

            await channel.send(

                "🎫 **What do you need help with?**\n\n"

                "Please choose an option below:",

                view=TicketTypeButton()
            )

            # =================================================
            # CLOSE TICKET BUTTON
            # =================================================

            await channel.send(

                "🔒 **Finished with your ticket?**\n"
                "You can close this ticket using the button below.",

                view=TicketCloseButton()
            )

        except discord.HTTPException as error:

            print(
                f"❌ Could not send ticket panel: {error}"
            )


# =========================================================
# BOT CLASS
# =========================================================

class TicketBot(commands.Bot):

    async def setup_hook(self):

        # Persistent views
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


# =========================================================
# BOT
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
            f"⚠️ Welcome channel '{WELCOME_CHANNEL_NAME}' "
            "was not found."
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
            "❌ I don't have permission to send messages "
            "in the welcome channel."
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

    import traceback

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

    print(
        f"🆔 Bot ID: {bot.user.id}"
    )

    print(
        "========================================"
    )

    # =====================================================
    # FIND TICKET CHANNEL
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

        return

    print(
        f"✅ Ticket channel found: #{channel.name}"
    )

    # =====================================================
    # CHECK EXISTING PANEL
    # =====================================================

    try:

        async for message in channel.history(
            limit=50
        ):

            if (
                message.author == bot.user
                and message.components
            ):

                print(
                    "✅ Ticket panel already exists."
                )

                return

    except discord.Forbidden:

        print(
            "❌ I cannot read the ticket channel history."
        )

        return

    except discord.HTTPException as error:

        print(
            f"❌ Could not check channel history: {error}"
        )

        return

    # =====================================================
    # CREATE PANEL
    # =====================================================

    try:

        embed = discord.Embed(

            title="🎫 Support & Orders",

            description=(
                "Need help or want to order a custom bot?\n\n"

                "Click **🎫 Create Ticket** to open a "
                "private ticket.\n\n"

                "💳 **Payment Methods**\n"
                "We currently accept **Revolut, PayPal "
                "and TWINT** only."
            ),

            color=discord.Color.blurple()
        )

        embed.set_footer(
            text=(
                "Please make sure you can use one of "
                "these payment methods."
            )
        )

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


# =========================================================
# START BOT
# =========================================================

if not BOT_TOKEN:

    print(
        "❌ ERROR: DISCORD_BOT_TOKEN is not set."
    )

else:

    bot.run(BOT_TOKEN)