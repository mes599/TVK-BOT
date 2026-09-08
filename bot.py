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

# SHOWCASE / DEMO
SHOWCASE_CHANNEL_NAME = "ticket-demo-bot🎫"
SHOWCASE_CATEGORY_NAME = "Bot Showcases🤖"

COOLDOWN = timedelta(minutes=2)

# Payment links
REVOLUT_PAYMENT_URL = "https://revolut.me/ayberkqvg8"
PAYPAL_PAYMENT_URL = "https://paypal.me/aydmraybrk"

# Your Discord user ID
OWNER_ID = 1137740302094966884


# =========================================================
# BOT TOKEN
# =========================================================

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")


# =========================================================
# GLOBALS
# =========================================================

ticket_cooldowns = {}


# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


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

    payment_note = discord.ui.TextInput(
        label="Payment information",
        placeholder="Add any information about your payment.",
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

        if channel is None:
            return

        # Only allow this inside tickets/orders
        if not (
            channel.name.startswith("ticket-")
            or channel.name.startswith("order-")
        ):
            await interaction.response.send_message(
                "❌ This button can only be used inside an order ticket.",
                ephemeral=True
            )
            return

        # Prevent duplicate confirmations
        if (
            "payment reported" in channel.topic.lower()
            if channel.topic
            else False
        ):
            await interaction.response.send_message(
                "⚠️ Payment information has already been submitted.",
                ephemeral=True
            )
            return

        # =================================================
        # GET BOT OWNER
        # =================================================

        owner = None

        try:
            application = await interaction.client.application_info()
            owner = application.owner

        except Exception as error:
            print(
                f"⚠️ Could not get bot owner: {error}"
            )

        # =================================================
        # MARK PAYMENT AS REPORTED
        # =================================================

        try:
            await channel.edit(
                topic=(
                    f"Payment reported by {user} "
                    f"(ID: {user.id})"
                )
            )

        except discord.HTTPException:
            pass

        # =================================================
        # CREATE PAYMENT NOTIFICATION
        # =================================================

        embed = discord.Embed(
            title="💰 Payment Confirmation",
            description=(
                f"{user.mention} has submitted "
                "payment information."
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="👤 Customer",
            value=f"{user.mention}\n`{user}`",
            inline=False
        )

        embed.add_field(
            name="🆔 Customer ID",
            value=str(user.id),
            inline=True
        )

        embed.add_field(
            name="🎫 Ticket",
            value=channel.mention,
            inline=True
        )

        embed.add_field(
            name="💳 Payment Method",
            value=self.payment_method.value,
            inline=False
        )

        embed.add_field(
            name="📝 Additional Information",
            value=self.payment_note.value or "None",
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
            text="Please manually verify the payment."
        )

        # =================================================
        # SEND INFORMATION TO OWNER
        # =================================================

        if owner is not None:

            try:
                await owner.send(
                    embed=embed
                )

                print(
                    f"✅ Payment information sent to owner "
                    f"for {user}."
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
        # CUSTOMER CONFIRMATION
        # =================================================

        await interaction.response.send_message(

            "✅ **Payment information submitted!**\n\n"

            f"💳 Payment method: "
            f"**{self.payment_method.value}**\n\n"

            "Your payment information has been sent "
            "to the server owner for manual verification.",

            ephemeral=True
        )

        # =================================================
        # MESSAGE INSIDE TICKET
        # =================================================

        try:

            await channel.send(

                f"💰 **Payment information submitted by "
                f"{user.mention}.**\n\n"

                "⏳ The server owner has been notified "
                "and will manually verify the payment."
            )

        except discord.HTTPException as error:

            print(
                f"⚠️ Could not send payment notification: {error}"
            )


# =========================================================
# PAYMENT CONFIRM BUTTON
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

        if channel is None:
            return

        # Only allow inside tickets/orders
        if not (
            channel.name.startswith("ticket-")
            or channel.name.startswith("order-")
        ):

            await interaction.response.send_message(

                "❌ This button can only be used "
                "inside an order ticket.",

                ephemeral=True
            )

            return

        # Prevent duplicate confirmations
        if (
            "payment reported" in channel.topic.lower()
            if channel.topic
            else False
        ):

            await interaction.response.send_message(

                "⚠️ Payment information has already "
                "been submitted.",

                ephemeral=True
            )

            return

        # Open confirmation form
        await interaction.response.send_modal(
            PaymentConfirmationModal()
        )


# =========================================================
# PAYMENT BUTTONS
# =========================================================

class PaymentButtons(discord.ui.View):

    def __init__(self):

        super().__init__(timeout=None)

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

            application = await interaction.client.application_info()
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

                f"💳 **Payment: {self.package_price}**\n\n"

                "Please choose one of the payment methods below.\n\n"

                "After completing the payment, click "
                "**✅ Confirm Payment**.\n\n"

                "⚠️ Payment completion is manually verified.",

                embed=embed,

                view=PaymentButtons()
            )

            # =================================================
            # CLOSE BUTTON
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

            "Please complete your payment and then "
            "click **✅ Confirm Payment**.",

            ephemeral=True
        )


# =========================================================
# PACKAGE BUTTONS
# =========================================================

class PackageButton(discord.ui.View):

    def __init__(self):
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

    # =====================================================
    # STARTER
    # =====================================================

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

        await self.delete_package_message(interaction)

        await interaction.response.send_modal(
            BotOrderModal(
                "Starter",
                "€4.99"
            )
        )

    # =====================================================
    # PRO
    # =====================================================

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

        await self.delete_package_message(interaction)

        await interaction.response.send_modal(
            BotOrderModal(
                "Pro",
                "€9.99"
            )
        )

    # =====================================================
    # ADVANCED
    # =====================================================

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

        await self.delete_package_message(interaction)

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

    # =====================================================
    # SUPPORT
    # =====================================================

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

    # =====================================================
    # ORDER
    # =====================================================

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
                "Help, ping and server information.\n\n"
                "💬 **Custom Responses**\n"
                "Automatic replies to selected messages.\n\n"
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
                "More control over roles, channels and bot behaviour."
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

        # =================================================
        # READY
        # =================================================

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

        existing_order = discord.utils.get(
            guild.text_channels,
            name=f"order-{user.id}"
        )

        if (
            existing_ticket is not None
            or existing_order is not None
        ):

            await interaction.followup.send(
                "❌ You already have an open ticket or order.",
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
        # GET OWNER
        # =================================================

        owner = None

        try:

            application = await interaction.client.application_info()
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

            overwrites[owner] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
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
# SHOWCASE DEMO - ACTION BUTTONS
# =========================================================

class DemoActionView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    # =====================================================
    # ORDER BOT
    # =====================================================

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

        embed = discord.Embed(
            title="🤖 Order Bot — Demo",
            description=(
                "🚀 **You just tested one possible feature!**\n\n"

                "This button could open an order system, "
                "display your services, show your packages, "
                "start a purchase process, open another menu, "
                "or perform a completely different action.\n\n"

                "💬 **And this message can be changed too.**\n\n"

                "Every part of your bot can be designed around "
                "your own idea. The text you are reading right now "
                "is only an example for this showcase.\n\n"

                "🎨 You can choose your own colors.\n"
                "📝 You can choose your own texts.\n"
                "🔘 You can choose your own buttons.\n"
                "⚙️ You can choose your own functions.\n"
                "✨ You can choose your own design.\n\n"

                "💡 **Your idea → Your design → Your bot.**"
            ),
            color=discord.Color.blue()
        )

        embed.add_field(
            name="🔧 Completely Customizable",
            value=(
                "Want this button to do something completely "
                "different? No problem. The function, message, "
                "name and appearance can all be changed."
            ),
            inline=False
        )

        embed.add_field(
            name="🚀 Unlimited Possibilities",
            value=(
                "A bot does not have to stop at two or three "
                "buttons. You can have several buttons, menus, "
                "different pages and many custom functions."
            ),
            inline=False
        )

        embed.set_footer(
            text="Demo feature • Everything can be customized"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # =====================================================
    # YOUR CHOICE
    # =====================================================

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

        embed = discord.Embed(
            title="✨ Your Choice — Demo",
            description=(
                "💡 **This button is an example of YOUR choice.**\n\n"

                "Imagine that this button does exactly what you "
                "want it to do.\n\n"

                "Maybe it opens a menu.\n"
                "Maybe it shows information.\n"
                "Maybe it starts an application.\n"
                "Maybe it opens another ticket.\n"
                "Maybe it connects to another system.\n"
                "Or maybe it does something completely unique.\n\n"

                "🎨 **You decide.**\n\n"

                "The name of the button, the emoji, the color, "
                "the message, the function and everything around "
                "it can be changed to match your vision.\n\n"

                "🔥 This showcase is only here to give you an idea "
                "of what your own custom Discord bot could look like."
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="🔘 More Than Just 2–3 Buttons",
            value=(
                "You are not limited to a small number of buttons. "
                "Your bot can have multiple buttons, menus and "
                "different interactive systems depending on what "
                "you need."
            ),
            inline=False
        )

        embed.add_field(
            name="🎯 Built Around Your Vision",
            value=(
                "Instead of changing your idea to fit a standard "
                "bot, the bot can be designed around your idea."
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
# SHOWCASE CLOSE BUTTON
# =========================================================

class ShowcaseCloseButton(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

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

        if channel is None:
            return

        # Only allow deletion of showcase demo tickets
        if (
            not channel.topic
            or "showcase-owner:" not in channel.topic
        ):

            await interaction.response.send_message(
                "❌ This is not a showcase demo ticket.",
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
                "❌ I don't have permission to delete "
                "the showcase demo ticket."
            )

        except discord.HTTPException as error:

            print(
                f"❌ Showcase ticket deletion error: {error}"
            )


# =========================================================
# SHOWCASE CREATE DEMO TICKET
# =========================================================

async def create_demo_ticket(
    interaction: discord.Interaction
):

    guild = interaction.guild
    user = interaction.user

    if guild is None:

        await interaction.response.send_message(
            "❌ This demo can only be used inside a server.",
            ephemeral=True
        )

        return

    await interaction.response.defer(
        ephemeral=True
    )

    # =====================================================
    # CHECK EXISTING DEMO
    # =====================================================

    existing_ticket = None

    for channel in guild.text_channels:

        if (
            channel.topic
            and f"showcase-owner:{user.id}"
            in channel.topic
        ):

            existing_ticket = channel
            break

    if existing_ticket:

        await interaction.followup.send(
            (
                "✨ **You already have a demo ticket!**\n\n"
                f"➡️ {existing_ticket.mention}"
            ),
            ephemeral=True
        )

        return

    # =====================================================
    # FIND / CREATE CATEGORY
    # =====================================================

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
                    "❌ I don't have permission to create "
                    "the showcase category."
                ),
                ephemeral=True
            )

            return

        except discord.HTTPException as error:

            await interaction.followup.send(
                f"❌ Could not create the showcase category: {error}",
                ephemeral=True
            )

            return

    # =====================================================
    # BOT MEMBER
    # =====================================================

    bot_member = guild.me

    if bot_member is None and bot.user is not None:

        bot_member = guild.get_member(
            bot.user.id
        )

    if bot_member is None:

        await interaction.followup.send(
            "❌ I could not find my bot member.",
            ephemeral=True
        )

        return

    # =====================================================
    # PERMISSIONS
    # =====================================================

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

    # =====================================================
    # CHANNEL NAME
    # =====================================================

    username = user.name.lower()

    channel_name = f"demo-{username}"

    channel_name = (
        channel_name
        .replace(" ", "-")
        .replace("_", "-")
    )

    channel_name = channel_name[:100]

    # =====================================================
    # CREATE PRIVATE DEMO CHANNEL
    # =====================================================

    try:

        ticket_channel = await guild.create_text_channel(

            name=channel_name,

            category=category,

            overwrites=overwrites,

            topic=(
                f"showcase-owner:{user.id} "
                f"| showcase-demo:true"
            ),

            reason=f"Showcase demo created for {user}"
        )

    except discord.Forbidden:

        await interaction.followup.send(
            (
                "❌ I don't have permission to create "
                "the demo ticket."
            ),
            ephemeral=True
        )

        return

    except discord.HTTPException as error:

        await interaction.followup.send(
            f"❌ Could not create the demo ticket: {error}",
            ephemeral=True
        )

        return

    # =====================================================
    # MAIN DEMO EMBED
    # =====================================================

    embed = discord.Embed(
        title="🚀 Welcome to Your Custom Bot Demo!",
        description=(
            "🎉 **Welcome! You are now inside a private "
            "demo ticket.**\n\n"

            "This is not just a normal ticket. This is a "
            "**small preview of what your own custom Discord "
            "bot could look like.**\n\n"

            "✨ Everything you see here can be changed.\n\n"

            "🎨 **Colors** can be changed.\n"
            "📝 **Texts** can be changed.\n"
            "🔘 **Button names** can be changed.\n"
            "😀 **Emojis** can be changed.\n"
            "📦 **Embeds** can be changed.\n"
            "⚙️ **Functions** can be changed.\n"
            "🔐 **Permissions** can be changed.\n"
            "📁 **Categories and channels** can be changed.\n"
            "💬 **Messages and responses** can be changed.\n\n"

            "🔥 **You are not limited to this design.**\n\n"

            "This demo is simply an example. Your final bot "
            "can look completely different and can be built "
            "around exactly what you want.\n\n"

            "💡 **Your idea. Your design. Your bot.**"
        ),
        color=discord.Color.blurple()
    )

    # =====================================================
    # CUSTOMIZATION FIELD
    # =====================================================

    embed.add_field(
        name="🎨 Make It Your Own",
        value=(
            "Imagine this bot with your own colors, your own "
            "branding, your own messages and your own style. "
            "Nothing here has to stay the way it is in this demo."
        ),
        inline=False
    )

    # =====================================================
    # BUTTON FIELD
    # =====================================================

    embed.add_field(
        name="🔘 Buttons? You Decide!",
        value=(
            "You don't have to use only two or three buttons. "
            "Depending on your project, you can have multiple "
            "buttons, menus and interactive options.\n\n"

            "🔹 2 buttons\n"
            "🔹 3 buttons\n"
            "🔹 5 buttons\n"
            "🔹 10 buttons\n"
            "🔹 Or a completely different system\n\n"

            "Each button can have its own name, emoji, color, "
            "message and function."
        ),
        inline=False
    )

    # =====================================================
    # FEATURES FIELD
    # =====================================================

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
            "⚙️ Automations\n"
            "🚀 And much more!"
        ),
        inline=False
    )

    # =====================================================
    # SALES / CALL TO ACTION
    # =====================================================

    embed.add_field(
        name="💎 Want Something Like This?",
        value=(
            "If you like the idea of having a custom Discord "
            "bot, this demo is only the beginning.\n\n"

            "🚀 Tell us what you have in mind and the bot can "
            "be designed around your vision.\n\n"

            "✨ Your server.\n"
            "✨ Your ideas.\n"
            "✨ Your design.\n"
            "✨ Your features.\n"
            "✨ Your bot.\n\n"

            "**Don't settle for a standard bot when your idea "
            "can be built around you.**"
        ),
        inline=False
    )

    embed.set_footer(
        text="🎫 Demo Ticket • Everything is customizable"
    )

    # =====================================================
    # SEND DEMO MESSAGE
    # =====================================================

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

                "🤖 **Order Bot** and ✨ **Your Choice** are "
                "example functions. Their names, messages and "
                "actions can all be replaced with your own ideas.\n\n"

                "🔒 Use **Close Ticket** whenever you are finished."
            ),

            view=ShowcaseCloseButton()
        )

    except discord.Forbidden:

        await interaction.followup.send(
            (
                "❌ The ticket was created, but I cannot "
                "send messages inside it."
            ),
            ephemeral=True
        )

        return

    except discord.HTTPException as error:

        await interaction.followup.send(
            f"❌ The ticket was created, but an error occurred: {error}",
            ephemeral=True
        )

        return

    # =====================================================
    # PRIVATE REDIRECT
    # =====================================================

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
# SHOWCASE BUTTON
# =========================================================

class ShowcaseView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

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

class TicketBot(commands.Bot):

    async def setup_hook(self):

        # NORMAL BOT VIEWS
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

        # SHOWCASE VIEWS
        self.add_view(
            ShowcaseView()
        )

        self.add_view(
            DemoActionView()
        )

        self.add_view(
            ShowcaseCloseButton()
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
    # FIND NORMAL TICKET CHANNEL
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

    else:

        print(
            f"✅ Ticket channel found: #{channel.name}"
        )

        # =================================================
        # CHECK EXISTING PANEL
        # =================================================

        panel_exists = False

        try:

            async for message in channel.history(
                limit=50
            ):

                if (
                    message.author == bot.user
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
                f"❌ Could not check channel history: {error}"
            )

        # =================================================
        # CREATE NORMAL PANEL
        # =================================================

        if not panel_exists:

            try:

                embed = discord.Embed(

                    title="🎫 Support & Orders",

                    description=(

                        "Need help or want to order a custom bot?\n\n"

                        "Click **🎫 Create Ticket** to open a "
                        "private ticket.\n\n"

                        "💳 **Payment Methods**\n"

                        "We currently accept **Revolut and PayPal**."
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

    # =====================================================
    # FIND SHOWCASE CHANNEL
    # =====================================================

    showcase_channel = discord.utils.get(
        bot.get_all_channels(),
        name=SHOWCASE_CHANNEL_NAME
    )

    if showcase_channel is None:

        print(
            f"❌ Showcase channel '{SHOWCASE_CHANNEL_NAME}' "
            "was not found."
        )

        return

    print(
        f"✅ Showcase channel found: #{showcase_channel.name}"
    )

    # =====================================================
    # CHECK EXISTING SHOWCASE PANEL
    # =====================================================

    showcase_exists = False

    try:

        async for message in showcase_channel.history(
            limit=50
        ):

            if (
                message.author == bot.user
                and message.components
            ):

                showcase_exists = True

                print(
                    "✅ Showcase panel already exists."
                )

                break

    except discord.Forbidden:

        print(
            "❌ I cannot read the showcase channel history."
        )

        return

    except discord.HTTPException as error:

        print(
            f"❌ Could not check showcase history: {error}"
        )

        return

    # =====================================================
    # CREATE SHOWCASE PANEL
    # =====================================================

    if not showcase_exists:

        embed = discord.Embed(
            title="🤖✨ CUSTOM DISCORD BOT SHOWCASE ✨🤖",
            description=(
                "🚀 **Want a Discord bot built around YOUR ideas?**\n\n"

                "Welcome to our interactive bot showcase! 🎉\n\n"

                "This is a live demonstration designed to show "
                "you just how flexible a custom Discord bot can be.\n\n"

                "🎨 **Your design.**\n"
                "💬 **Your messages.**\n"
                "🔘 **Your buttons.**\n"
                "⚙️ **Your functions.**\n"
                "✨ **Your vision.**\n\n"

                "Nothing in this demo has to stay the way it is. "
                "The layout, colors, text, buttons, embeds, "
                "permissions and functions can all be changed "
                "to match your requirements.\n\n"

                "🔥 **Ready to see it for yourself?**\n\n"

                "Click the button below and create your own "
                "private demo ticket!"
            ),
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🎫 Interactive Demo",
            value=(
                "Create a private demo ticket and explore how "
                "a custom ticket system can work."
            ),
            inline=False
        )

        embed.add_field(
            name="🎨 Completely Customizable",
            value=(
                "Colors, messages, emojis, buttons, embeds, "
                "permissions, channels and features can all "
                "be designed around your needs."
            ),
            inline=False
        )

        embed.add_field(
            name="🔘 Unlimited Button Ideas",
            value=(
                "You are not limited to just two or three "
                "buttons. Depending on the project, you can "
                "have multiple buttons, menus and interactive "
                "features."
            ),
            inline=False
        )

        embed.add_field(
            name="⚡ Built Around Your Vision",
            value=(
                "This showcase is only an example. Your own "
                "bot can be completely different and can be "
                "designed around exactly what you want."
            ),
            inline=False
        )

        embed.add_field(
            name="🚀 Experience The Demo",
            value=(
                "Click **🎫 Create Demo Ticket** below and "
                "see what a custom bot experience could look like!"
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
