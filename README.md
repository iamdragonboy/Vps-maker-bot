# VPS Deployer Bot

A powerful Discord bot for managing VPS instances with Docker containers.

## Features

- 🚀 Create and manage VPS instances
- 📊 Real-time resource monitoring
- 🔒 Secure SSH access via tmate
- ⚙️ Systemd support
- 🐳 Docker container management
- 🎮 User-friendly interface

## Developer

**DpWorld**
- Discord ID: dpworld
- GitHub: https://github.com/dpworld
- Discord Server: https://discord.gg/dpworld

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Commands

### Basic Commands
- `!list` - List your VPS instances
- `!manage_vps` - Manage your VPS
- `!commands` - Show all available commands

### Admin Commands
- `!create_vps <memory> <cpu> <disk>` - Create a new VPS
- `!vps_list` - List all VPS instances
- `!delete_vps <vps_id> <username>` - Delete a VPS
- `!delete_all` - Delete all VPS instances

## Requirements

- Python 3.8+
- Docker
- Discord.py
- Docker SDK for Python
- Systemd support
- tmate

## Installation

1. Clone the repository
2. Install required packages: `pip install -r requirements.txt`
3. Set up your Discord bot token in `.env` file
4. Run the bot: `python bot.py`

## Support

For support, join our Discord server: https://discord.gg/dpworld 