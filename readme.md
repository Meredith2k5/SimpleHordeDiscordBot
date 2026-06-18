# 🎨 SimpleHordeDiscordBot

A streamlined, simple Discord bot which runs within Docker that allows users to generate images directly in Discord using the community-driven AI Horde(https://stablehorde.net/) network. 
It is recommended that you first get aquainted with AI Horde via https://aihorde.net - it runs on a volunteer basis through a 'kudos' system where you accumulate kudos for giving back, without this your generations will be slow and wont be prioritised.


## ✨ Features
* **Slash Commands:** Fully integrated `/generate` command with autocomplete for models, samplers, and styles.
* **Live Progress Tracking:** Updates the Discord embed with queue position, estimated wait time, and current processing status.
* **NSFW Controls:** Global toggle for server admins to allow or restrict NSFW generation requests.
* **Massive Style Library:** Automatically fetches and caches community styles from GitHub. Use `/styles` to search through hundreds of visual presets!
* **Parameter Hiding:** Clutters are hidden behind Discord spoilers so the chat stays clean while power-users can still view technical generation data.
* **Docker Ready:** Deploy easily and cleanly via Docker Compose.

---

## 🛠️ Prerequisites
Before running this bot, you will need:
1. **Docker and Docker Compose** installed on your host machine.
2. A **Discord Bot Token**. (You can get one from the Discord Developer Portal: https://discord.com/developers/applications . I may add a guide later for setting this up.
3. An **AI Horde API Key**. (Register at [AI Horde](https://stablehorde.net/) to get your key. Using an anonymous key will result in slower generation times. The bot is currently configured to use only your key with Discord users generating images from your kudo balance).

---

## 🚀 Setup & Installation

**1. Clone the repository**
```bash
git clone [https://github.com/Meredith2k5/SimpleHordeDiscordBot.git](https://github.com/Meredith2k5/SimpleHordeDiscordBot.git)
cd SimpleHordeDiscordBot
```
*Alternatively, you can download the repository as a `.zip` file from GitHub and extract it to a folder named `/simplehordediscordbot` on your machine.*

**2. Configure your Environment Variables**
Open `.env` in your text editor and fill in your actual credentials:
* `DISCORD_TOKEN`: Your bot's secret token.
* `DISCORD_GUILD_ID`: (Optional) The Server ID where you want the bot to primarily function and retreive commands.
* `HORDE_API_KEY`: Your personal Horde API key.
* `HORDE_ALLOW_NSFW`: Set to `true` or `false` to control allowed content.
Rename .env.example to .env once finished.

**3. Run the Bot**
Build and start the container in the background:
```bash
docker compose up -d --build
```

To view the bot's live logs, run:
```bash
docker-compose logs -f
```

---

## 📂 Data & Backups
This bot is entirely self-contained. When run via Docker Compose, it will create a `data/` folder directly alongside your code.
* **`/data/logs/`**: Contains rotational `.log` files for debugging.
* **`/data/styles.json`**: A local backup of the Horde styles, allowing the bot to boot even if GitHub is down.

---

## 🤝 Contributing
Contributions, issues, and feature requests are welcome. This is my first major project in awhile and Qwen 3.6 has been used to assist. 
Feel free to check the [issues page](https://github.com/Meredith2k5/SimpleHordeDiscordBot/issues).