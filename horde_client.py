import asyncio
import time
import json
import os
import aiohttp
from typing import Dict, Any, List, Optional
from utils import (
    HORDE_API_KEY, HORDE_TIMEOUT, setup_logging,
    HORDE_ALLOW_NSFW, HORDE_DEFAULT_MODEL, HORDE_DEFAULT_SAMPLER, HORDE_DEFAULT_WIDTH,
    HORDE_DEFAULT_HEIGHT, HORDE_DEFAULT_STEPS, HORDE_DEFAULT_CFG_SCALE,
    HORDE_DEFAULT_HIRES_FIX, HORDE_DEFAULT_CLIP_SKIP
)

logger = setup_logging()

class HordeClient:
    """
    A client wrapper for the Stable Horde API (v2).
    Handles fetching models/styles, submitting jobs, and polling for results.
    """
    BASE_URL = "https://stablehorde.net/api/v2"
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self.timeout = HORDE_TIMEOUT
        self.models_cache = []
        self.styles_cache = {}

    def get_session(self) -> aiohttp.ClientSession:
        """Lazy initialization of the aiohttp session to ensure it binds to the correct async loop."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"apikey": HORDE_API_KEY, "Content-Type": "application/json"}
            )
        return self._session

    async def fetch_models(self) -> List[str]:
        """Fetches active Stable Diffusion models from the Horde API."""
        session = self.get_session()
        try:
            async with session.get(f"{self.BASE_URL}/models") as resp:
                data = await resp.json(content_type=None)
                self.models_cache = [m["name"] for m in data if m.get("type") == "stable-diffusion"]
                logger.info(f"Cached {len(self.models_cache)} models.")
        except Exception as e:
            logger.warning(f"Failed to fetch models: {e}. Using fallback defaults.")
            self.models_cache = ["AlbedoBase XL (SDXL)", "Dreamshaper", "Deliberate", "Anything Diffusion"]
        return self.models_cache

    async def fetch_styles(self) -> dict:
        """Fetches styles from GitHub and maintains a local backup in /data."""
        session = self.get_session()
        local_path = "/data/styles.json"
        
        try:
            url = "https://raw.githubusercontent.com/Haidra-Org/AI-Horde-Styles/main/styles.json"
            async with session.get(url) as resp:
                resp.raise_for_status()
                self.styles_cache = await resp.json(content_type=None)
                logger.info(f"Cached {len(self.styles_cache)} styles from GitHub.")
                
            # Update local backup
            try:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "w") as f:
                    json.dump(self.styles_cache, f)
            except Exception as e:
                logger.warning(f"Could not backup styles locally: {e}")
                
        except Exception as e:
            logger.warning(f"Failed to fetch styles from GitHub: {e}")
            if os.path.exists(local_path):
                try:
                    with open(local_path, "r") as f:
                        self.styles_cache = json.load(f)
                    logger.info(f"Loaded {len(self.styles_cache)} styles from local backup.")
                except Exception as backup_e:
                    logger.error(f"Failed to load local style backup: {backup_e}")
                    
        return self.styles_cache

    async def submit_job(self, payload: Dict[str, Any]) -> str:
        """Submits an async generation payload to the Horde."""
        session = self.get_session()
        async with session.post(f"{self.BASE_URL}/generate/async", json=payload) as resp:
            if resp.status != 202:
                text = await resp.text()
                raise RuntimeError(f"Horde submit failed ({resp.status}): {text}")
            data = await resp.json(content_type=None)
            return data["id"]

    async def poll_status(self, gen_id: str) -> Dict[str, Any]:
        """Checks the current status of an ongoing generation by ID."""
        session = self.get_session()
        async with session.get(f"{self.BASE_URL}/generate/status/{gen_id}") as resp:
            data = await resp.json(content_type=None)
            if not isinstance(data, dict):
                raise ValueError(f"Invalid status response format: {data}")
            return data

    async def generate(
        self, prompt: str, negative_prompt: Optional[str] = "", model: Optional[str] = None,
        sampler: Optional[str] = None, amount: int = 1, steps: Optional[int] = None, 
        cfg_scale: Optional[float] = None, width: Optional[int] = None, height: Optional[int] = None, 
        hires_fix: Optional[bool] = None, clip_skip: Optional[int] = None, tiling: bool = False, 
        shared: bool = False, style: str = "", nsfw: bool = True, progress_callback=None
    ) -> tuple[List[Dict[str, Any]], float, Dict[str, Any]]: 
        """
        Main orchestration function.
        Parses styles, applies overrides, submits the job, and handles the polling loop.
        """
        
        # 1. Initialize Base Defaults
        final_model = HORDE_DEFAULT_MODEL
        final_sampler = HORDE_DEFAULT_SAMPLER
        final_steps = HORDE_DEFAULT_STEPS
        final_cfg = HORDE_DEFAULT_CFG_SCALE
        final_width = HORDE_DEFAULT_WIDTH
        final_height = HORDE_DEFAULT_HEIGHT
        final_hires = HORDE_DEFAULT_HIRES_FIX
        final_clip_skip = HORDE_DEFAULT_CLIP_SKIP
        
        final_prompt = prompt
        user_neg = negative_prompt if negative_prompt else ""
        final_negative = user_neg

        # 2. Apply Style Modifications (If requested)
        if style and style in self.styles_cache:
            style_data = self.styles_cache[style]
            raw_style_prompt = style_data.get("prompt", "{p} ### {np}")
            
            # Split prompt strings
            if "###" in raw_style_prompt:
                parts = raw_style_prompt.split("###", 1)
                style_pos, style_neg = parts[0], parts[1]
            else:
                style_pos, style_neg = raw_style_prompt, "{np}"

            # Format Positive Prompt
            final_prompt = style_pos.replace("{p}", prompt).replace("{prompt}", prompt).strip()
            
            # Format Negative Prompt
            if "{np}" in style_neg or "{negative_prompt}" in style_neg:
                final_negative = style_neg.replace("{np}", user_neg).replace("{negative_prompt}", user_neg).strip()
            else:
                final_negative = f"{user_neg}, {style_neg}" if user_neg else style_neg.strip()

            # Clean up trailing/leading commas
            final_negative = final_negative.strip(" ,")

            # Apply style parameters
            style_model = style_data.get("model")
            if isinstance(style_model, list) and style_model:
                final_model = style_model[0]
            elif isinstance(style_model, str):
                final_model = style_model

            final_sampler = style_data.get("sampler_name", final_sampler)
            final_steps = style_data.get("steps", final_steps)
            final_cfg = style_data.get("cfg_scale", final_cfg)
            final_width = style_data.get("width", final_width)
            final_height = style_data.get("height", final_height)
            final_clip_skip = style_data.get("clip_skip", final_clip_skip)

        # Apply fallback quality tags if no negative is provided
        elif not final_negative:
            final_negative = "ugly, deformed, noisy, blurry, distorted, out of focus, bad anatomy, extra limbs, poorly drawn face, poorly drawn hands, missing fingers"
            final_prompt = f"{prompt}, masterpiece, best quality, ultra-detailed, highres"

        # 3. Apply Explicit User Overrides (Command Arguments)
        final_model = model or final_model
        final_sampler = sampler or final_sampler
        final_steps = steps or final_steps
        final_cfg = cfg_scale or final_cfg
        final_width = width or final_width
        final_height = height or final_height
        final_hires = hires_fix if hires_fix is not None else final_hires
        final_clip_skip = clip_skip if clip_skip is not None else final_clip_skip

        # 4. Construct Payload
        full_prompt = f"{final_prompt} ### {final_negative}" if final_negative else final_prompt

        payload = {
            "prompt": full_prompt,
            "models": [final_model],
            "params": {
                "sampler_name": final_sampler,
                "width": final_width, 
                "height": final_height, 
                "steps": final_steps, 
                "cfg_scale": final_cfg,
                "hires_fix": final_hires,
                "clip_skip": final_clip_skip,
                "tiling": tiling
            },
            "nsfw": HORDE_ALLOW_NSFW,
            "censor_nsfw": not HORDE_ALLOW_NSFW,
            "shared": shared,
            "amount": amount
        }

        # 5. Submit and Poll
        logger.info(f"Submitting job for prompt: {prompt[:50]}...")
        gen_id = await self.submit_job(payload)
        logger.info(f"Job submitted. ID: {gen_id}")

        start_time = time.monotonic()
        poll_count = 0
        
        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(f"Generation timed out after {self.timeout}s")

            status = await self.poll_status(gen_id)
            poll_count += 1

            # Update discord progress (skip every other poll to avoid rate limits)
            if progress_callback and (poll_count % 2 == 0 or status.get("done") or status.get("faulted")):
                await progress_callback(gen_id, status)

            # Handle completion states
            if status.get("done"):
                logger.info(f"Job {gen_id} completed.")
                used_settings = {
                    "model": final_model,
                    "style": style,
                    "negative_prompt": final_negative,
                    "sampler": final_sampler,
                    "steps": final_steps,
                    "cfg_scale": final_cfg,
                    "clip_skip": final_clip_skip,
                    "hires_fix": final_hires,
                    "tiling": tiling
                }
                return status.get("generations", []), status.get("kudos", 0.0), used_settings
            
            elif status.get("faulted"):
                reason = status.get("message", "Unknown error or censored")
                raise RuntimeError(f"Horde rejected/failed job: {reason}")
            
            # Wait and poll again
            await asyncio.sleep(5)

    async def close(self):
        """Cleanly close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()