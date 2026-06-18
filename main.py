import asyncio
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from horde_client import HordeClient
from utils import (
    setup_logging, create_progress_embed, create_success_embed, create_error_embed,
    image_to_discord_file, DISCORD_TOKEN, DISCORD_GUILD_ID
)

logger = setup_logging()

# -------------------------------------------------------------
# Bot Setup & Initialization
# -------------------------------------------------------------
intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)
client: Optional[HordeClient] = None  

@bot.event
async def on_ready():
    """Triggered when the bot successfully connects to Discord."""
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Pre-fetch models and styles for autocomplete
    if client:
        await client.fetch_models()
        await client.fetch_styles()
    
    # Sync Slash Commands
    try:
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            synced = await bot.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} command(s) to guild {DISCORD_GUILD_ID}")
        else:
            raise discord.Forbidden("No GUILD_ID provided")
    except discord.Forbidden:
        logger.warning("Guild sync failed (403). Falling back to global sync...")
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s) globally")
    except Exception as e:
        logger.error(f"Command sync failed: {e}")

@bot.event
async def on_shutdown():
    """Ensures background client sessions are closed when the bot stops."""
    if client:
        await client.close()
        logger.info("Horde client session closed.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Global error handler for slash commands."""
    logger.error(f"Slash command error: {error}")
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.CommandInvokeError):
        await interaction.response.send_message(f"❌ Command failed: {error.original}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)

# -------------------------------------------------------------
# Autocomplete Handlers
# -------------------------------------------------------------

async def autocomplete_model(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Provides a dropdown list of available Horde models as the user types."""
    if not client or not client.models_cache:
        return [app_commands.Choice(name="AlbedoBase XL (SDXL)", value="AlbedoBase XL (SDXL)")]
    filtered = [m for m in client.models_cache if current.lower() in m.lower()]
    return [app_commands.Choice(name=m, value=m) for m in filtered[:25]]

SAMPLERS = [
    "k_dpmpp_2m", "k_dpmpp_sde", "k_dpmpp_2s_a", "k_euler_a", "k_euler", 
    "k_dpm_2", "k_dpm_2_a", "k_dpm_fast", "k_dpm_adaptive", "k_heun", 
    "k_lms", "dpmsolver", "DDIM", "lcm"
]

async def autocomplete_sampler(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Provides a dropdown list of valid samplers."""
    filtered = [s for s in SAMPLERS if current.lower() in s.lower()]
    return [app_commands.Choice(name=s, value=s) for s in filtered[:25]]

async def autocomplete_style(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Provides a dropdown list of curated visual styles."""
    if not client or not client.styles_cache:
        return [app_commands.Choice(name="None", value="")]
    styles = list(client.styles_cache.keys())
    filtered = [s for s in styles if current.lower() in s.lower()]
    return [app_commands.Choice(name=s, value=s) for s in filtered[:25]]

# -------------------------------------------------------------
# Discord Commands
# -------------------------------------------------------------

@bot.tree.command(name="styles", description="Search through available AI Horde styles")
@app_commands.describe(query="A word to search for in the style list (e.g., anime, nsfw, raw)")
async def styles(interaction: discord.Interaction, query: str):
    """A dedicated command to browse the massive styles list."""
    if not client or not client.styles_cache:
        await interaction.response.send_message("⏳ Styles are still loading from GitHub, please try again in a few seconds!", ephemeral=True)
        return
    
    matches = [s for s in client.styles_cache.keys() if query.lower() in s.lower()]
    
    if not matches:
        await interaction.response.send_message(f"❌ No styles found containing `{query}`.", ephemeral=True)
        return
    
    response = f"### 🎨 Found {len(matches)} styles matching `{query}`\n"
    for m in matches[:15]:
        response += f"- `{m}`\n"
        
    if len(matches) > 15:
        response += f"\n*...and {len(matches) - 15} more. Try a more specific search!*"
        
    await interaction.response.send_message(response, ephemeral=True)


@bot.tree.command(name="generate", description="Generates an image with AI Horde")
@app_commands.autocomplete(model=autocomplete_model, sampler=autocomplete_sampler, style=autocomplete_style)
@app_commands.describe(
    prompt="The main prompt for generation",
    negative_prompt="The negative prompt to generate an image with",
    style="The art style to apply (Start typing to search!)",
    model="Model to use (Overrides default)",
    sampler="The sampler to use (e.g., k_dpmpp_2m)",
    width="Image width (e.g., 1024)",
    height="Image height (e.g., 1024)",
    steps="Sampling steps (higher = more detail)",
    cfg_scale="CFG scale (how strictly to follow the prompt)",
    clip_skip="Skip CLIP layers (1-4, usually 2 for anime)",
    hires_fix="Enable high resolution fix (True/False)",
    amount="How many images to generate",
    tiling="Makes generated image have a seamless transition when stitched together",
    share_result="Whether to share your generation result for research"
)
@app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
async def generate(
    interaction: discord.Interaction,
    prompt: str,
    negative_prompt: Optional[str] = "",
    style: Optional[str] = "",
    model: Optional[str] = None,
    sampler: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    steps: Optional[int] = None,
    cfg_scale: Optional[float] = None,
    clip_skip: Optional[int] = None,
    hires_fix: Optional[bool] = None,
    amount: Optional[int] = 1,
    tiling: Optional[bool] = False,
    share_result: Optional[bool] = False
):
    """The main command for triggering AI image generation."""
    await interaction.response.defer()
    
    if client is None:
        await interaction.followup.send("❌ Bot is still initializing. Please try again in a few seconds.", ephemeral=True)
        return

    # Post initial waiting state
    initial_embed = create_progress_embed(prompt, "Pending...", "🟡 Submitting...")
    msg = await interaction.followup.send(embed=initial_embed)
    
    try:
        async def update_progress(gen_id: str, status: dict):
            """Callback function to update the Discord message as generation progresses."""
            if status.get("done"):
                state_text = "✅ Done"
            elif status.get("faulted"):
                state_text = "❌ Failed"
            elif status.get("processing"):
                state_text = "🔵 Processing"
            elif status.get("waiting"):
                state_text = "🟡 Queued"
            else:
                state_text = "⏳ Waiting..."

            embed = create_progress_embed(
                prompt, gen_id, state_text,
                position=status.get("queue_position"),
                workers=status.get("workers"),
                eta=status.get("eta"),
                kudos=status.get("kudos", 0)
            )
            try:
                await msg.edit(embed=embed)
            except discord.HTTPException as e:
                logger.warning(f"Failed to update progress embed: {e}")

        # Start the generation request
        generations, final_kudos, used_settings = await client.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            style=style,
            model=model,
            sampler=sampler,
            width=width,
            height=height,
            amount=amount,
            steps=steps,
            cfg_scale=cfg_scale,
            clip_skip=clip_skip,
            hires_fix=hires_fix,
            tiling=tiling,
            shared=share_result,
            progress_callback=update_progress
        )

        # Build final success message
        final_embed = create_success_embed(
            prompt=prompt, 
            gen_id=generations[0].get("id", "N/A") if generations else "N/A", 
            kudos=final_kudos,
            settings=used_settings
        )
        
        # Download images and attach to the Discord message
        files = []
        for i, gen in enumerate(generations):
            img_data = gen.get("img", "")
            if img_data:
                try:
                    file = await image_to_discord_file(img_data, f"gen_{i}.webp")
                    files.append(file)
                except Exception as e:
                    logger.warning(f"Failed to process image {i}: {e}")
                    continue

        await msg.edit(embed=final_embed, attachments=files)
        logger.info(f"Successfully generated {len(files)} image(s) for {interaction.user}")

    except TimeoutError:
        await msg.edit(embed=create_error_embed(prompt, "N/A", "⏱️ Generation timed out"))
    except RuntimeError as e:
        await msg.edit(embed=create_error_embed(prompt, "N/A", str(e)))
    except Exception as e:
        logger.error(f"Unhandled error in /generate: {e}", exc_info=True)
        await msg.edit(embed=create_error_embed(prompt, "N/A", f"Internal error: {e}"))

# -------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------
async def main():
    """Initializes clients and starts the Discord bot connection."""
    global client
    client = HordeClient()
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise