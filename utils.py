import os
import io
import base64
import logging
import aiohttp
from logging.handlers import RotatingFileHandler
from typing import Optional
from discord import Embed, File
from dotenv import load_dotenv

load_dotenv()

# Environment Variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
HORDE_API_KEY = os.getenv("HORDE_API_KEY", "")

# AI Horde Defaults
HORDE_ALLOW_NSFW = os.getenv("HORDE_ALLOW_NSFW", "false").lower() == "true"
HORDE_DEFAULT_MODEL = os.getenv("HORDE_DEFAULT_MODEL", "AlbedoBase XL (SDXL)")
HORDE_DEFAULT_SAMPLER = os.getenv("HORDE_DEFAULT_SAMPLER", "k_dpmpp_2m")
HORDE_DEFAULT_WIDTH = int(os.getenv("HORDE_DEFAULT_WIDTH", "1024"))
HORDE_DEFAULT_HEIGHT = int(os.getenv("HORDE_DEFAULT_HEIGHT", "1024"))
HORDE_DEFAULT_STEPS = int(os.getenv("HORDE_DEFAULT_STEPS", "30"))
HORDE_DEFAULT_CFG_SCALE = float(os.getenv("HORDE_DEFAULT_CFG_SCALE", "7.0"))
HORDE_DEFAULT_HIRES_FIX = os.getenv("HORDE_DEFAULT_HIRES_FIX", "false").lower() == "true"
HORDE_DEFAULT_CLIP_SKIP = int(os.getenv("HORDE_DEFAULT_CLIP_SKIP", "1"))
HORDE_TIMEOUT = int(os.getenv("HORDE_TIMEOUT", "600"))
HORDE_SAFEGUARD_MODELS = [m.strip() for m in os.getenv("HORDE_SAFEGUARD_MODELS", "").split(",") if m.strip()]
HORDE_SAFEGUARD_NEGATIVES = os.getenv("HORDE_SAFEGUARD_NEGATIVES", "child, underage, loli")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

def setup_logging() -> logging.Logger:
    """Configures the logger to output to the console and a rotating file inside /data/logs."""
    logger = logging.getLogger("horde-bot")
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    
    # NEW: Check if handlers already exist to prevent double-logging
    if not logger.handlers:
        # Console output
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(console)
        
        # File output
        os.makedirs("/data/logs", exist_ok=True)
        file_handler = RotatingFileHandler("/data/logs/bot.log", maxBytes=5*1024*1024, backupCount=3)
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(file_handler)
    
    return logger

def format_eta(seconds: Optional[int]) -> str:
    """Formats raw seconds into a readable MM:SS string."""
    if not seconds: 
        return "Calculating..."
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"

async def image_to_discord_file(img_data: str, filename: str = "generation.webp") -> File:
    """Converts a URL or Base64 string into a Discord File object."""
    if img_data.startswith("http"):
        async with aiohttp.ClientSession() as session:
            async with session.get(img_data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                content = await resp.read()
        return File(fp=io.BytesIO(content), filename=filename)
    else:
        img_bytes = base64.b64decode(img_data)
        return File(fp=io.BytesIO(img_bytes), filename=filename)

# -------------------------------------------------------------
# Embed Generators
# -------------------------------------------------------------

def create_progress_embed(
    prompt: str, gen_id: str, status: str,
    position: Optional[int] = None, workers: Optional[int] = None,
    eta: Optional[int] = None, kudos: Optional[float] = None, color: int = 0x0099ff
) -> Embed:
    """Creates an embed to show the real-time status of a generation in the queue."""
    embed = Embed(title="🎨 AI Horde Generation", color=color)
    embed.add_field(name="Prompt", value=f"||{prompt[:100]}{'...' if len(prompt) > 100 else ''}||", inline=False)
    embed.add_field(name="Generation ID", value=f"`{gen_id}`", inline=False)
    embed.add_field(name="Status", value=status, inline=True)
    
    if position is not None:
        embed.add_field(name="Queue Position", value=str(position), inline=True)
    if workers is not None:
        embed.add_field(name="Workers", value=str(workers), inline=True)
    if eta is not None:
        embed.add_field(name="ETA", value=format_eta(eta), inline=True)
    if kudos is not None:
        embed.add_field(name="Kudos Spent", value=f"{kudos:.1f}", inline=True)
        
    embed.set_footer(text="Polling every 5s...")
    return embed

def create_success_embed(prompt: str, gen_id: str, kudos: float, settings: dict = None) -> Embed:
    """Creates the final embed containing generation details and parameter spoilers."""
    settings = settings or {}
    embed = Embed(title="✅ Generation Complete!", color=0x00ff00)
    
    embed.add_field(name="Prompt", value=f"||{prompt[:100]}{'...' if len(prompt) > 100 else ''}||", inline=False)
    embed.add_field(name="Model", value=settings.get("model", "Unknown"), inline=True)
    embed.add_field(name="Kudos Spent", value=f"{kudos:.1f}", inline=True)
    embed.add_field(name="Generation ID", value=f"`{gen_id}`", inline=False)

    # Compile the technical settings into a single, spoiler-tagged string
    details = []
    if settings.get("style"): details.append(f"Style: {settings['style']}")
    if settings.get("sampler"): details.append(f"Sampler: {settings['sampler']}")
    if settings.get("steps"): details.append(f"Steps: {settings['steps']}")
    if settings.get("cfg_scale"): details.append(f"CFG: {settings['cfg_scale']}")
    if settings.get("clip_skip"): details.append(f"Clip Skip: {settings['clip_skip']}")
    if settings.get("hires_fix"): details.append("Hires: Yes")
    if settings.get("tiling"): details.append("Tiling: Yes")

    neg = settings.get("negative_prompt", "")
    if neg:
        neg_short = (neg[:50] + '...') if len(neg) > 50 else neg
        details.append(f"Negative: {neg_short}")

    if details:
        details_str = " | ".join(details)
        embed.add_field(name="Parameters", value=f"||{details_str}||", inline=False)

    return embed

def create_error_embed(prompt: str, gen_id: str, reason: str) -> Embed:
    """Creates an embed to display an error message if generation fails."""
    embed = Embed(title="❌ Generation Failed", color=0xff0000)
    embed.add_field(name="Prompt", value=f"||{prompt[:100]}{'...' if len(prompt) > 100 else ''}||", inline=False)
    embed.add_field(name="Generation ID", value=f"`{gen_id}`", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    return embed