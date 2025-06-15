"""
**VPS Deployer Bot**
A powerful Discord bot for managing VPS instances with Docker containers.

**License:**
Copyright (c) 2024 DpWorld

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

**Developer Credits:**
Developed by DpWorld (Discord ID: dpworld)
GitHub: https://github.com/dpworld
Discord: https://discord.gg/dpworld

**Features:**
- Create and manage VPS instances
- Real-time resource monitoring
- Secure SSH access via tmate
- Systemd support
- Docker container management
- User-friendly interface
"""

import discord
from discord.ext import commands
from discord import ui
import os
import random
import string
import json
import subprocess
from dotenv import load_dotenv
import asyncio
import datetime
import docker
import time
import uuid
from datetime import datetime

# Load environment variables
load_dotenv()

# Bot configuration
TOKEN = os.getenv('DISCORD_TOKEN')
VPS_STORAGE_FILE = 'vps_data.json'
ADMIN_ROLE_ID = 1379417287093649488  # Your admin role ID

# Initialize bot with command prefix '!'
class CustomBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_command = None
        self._last_command_time = 0

    async def process_commands(self, message):
        if message.author.bot:
            return

        current_time = time.time()
        if (self._last_command == message.content and 
            current_time - self._last_command_time < 2):
            return

        self._last_command = message.content
        self._last_command_time = current_time
        await super().process_commands(message)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = CustomBot(command_prefix='!', intents=intents)

# Initialize Docker client
try:
    client = docker.from_env()
except Exception as e:
    print(f"Failed to initialize Docker client: {e}")
    client = None

# Store VPS data
vps_data = {}

def load_vps_data():
    global vps_data
    if os.path.exists(VPS_STORAGE_FILE):
        with open(VPS_STORAGE_FILE, 'r') as f:
            vps_data = json.load(f)
            # Fix missing created_at fields
            for vps_id, vps in vps_data.items():
                if 'created_at' not in vps:
                    vps['created_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_vps_data()

def save_vps_data():
    with open(VPS_STORAGE_FILE, 'w') as f:
        json.dump(vps_data, f)

def generate_vps_id():
    """Generate a unique VPS ID"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def has_required_role(ctx):
    """Check if user has required role to use bot commands"""
    # Allow all users to use basic commands
    return True

def has_admin_role(ctx):
    """Check if user has admin role"""
    return any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles)

async def capture_ssh_session_line(process):
    try:
        while True:
            output = await process.stdout.readline()
            if not output:
                break
            output = output.decode('utf-8').strip()
            if "ssh session:" in output:
                return output.split("ssh session:")[1].strip()
        return None
    except Exception as e:
        print(f"Error capturing SSH session: {e}")
        return None

async def send_tmate_session(interaction, container_id, vps_id):
    """Send new tmate session to user"""
    try:
        # Start tmate session
        exec_cmd = await asyncio.create_subprocess_exec(
            "docker", "exec", container_id, "tmate", "-F",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        ssh_session_line = await capture_ssh_session_line(exec_cmd)
        if not ssh_session_line:
            raise Exception("Failed to get tmate session")

        # Update stored session
        if vps_id in vps_data:
            vps_data[vps_id]['tmate_session'] = ssh_session_line
            save_vps_data()
            
            # Send new session to user
            try:
                user = await bot.fetch_user(int(vps_data[vps_id]["created_by"]))
                embed = discord.Embed(title="New VPS Session", color=discord.Color.blue())
                embed.add_field(name="VPS ID", value=vps_id, inline=True)
                embed.add_field(name="Tmate Session", value=f"```{ssh_session_line}```", inline=False)
                embed.add_field(name="Connection Instructions", value="1. Copy the Tmate session command\n2. Open your terminal\n3. Paste and run the command\n4. You will be connected to your VPS", inline=False)
                await user.send(embed=embed)
                await interaction.followup.send("✅ New session sent to your DMs!", ephemeral=True)
            except:
                await interaction.followup.send("Note: Could not send DM to the user.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Error getting new session: {str(e)}", ephemeral=True)

def count_user_servers(userid):
    count = 0
    for vps_id, data in vps_data.items():
        if data["created_by"] == userid:
            count += 1
    return count

async def run_docker_command(container_id, command, timeout=120):
    """Run a Docker command asynchronously with timeout"""
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", "exec", container_id, *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            if process.returncode != 0:
                raise Exception(f"Command failed: {stderr.decode()}")
            return True
        except asyncio.TimeoutError:
            process.kill()
            raise Exception(f"Command timed out after {timeout} seconds")
    except Exception as e:
        print(f"Error running Docker command: {e}")
        return False

async def kill_apt_processes(container_id):
    """Kill any running apt processes"""
    try:
        await run_docker_command(container_id, ["bash", "-c", "killall apt apt-get dpkg || true"])
        await asyncio.sleep(2)
        await run_docker_command(container_id, ["bash", "-c", "rm -f /var/lib/apt/lists/lock /var/cache/apt/archives/lock /var/lib/dpkg/lock*"])
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"Error killing apt processes: {e}")
        return False

async def wait_for_apt_lock(container_id, status_msg):
    """Wait for apt lock to be released"""
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            # First try to kill any running apt processes
            await kill_apt_processes(container_id)
            
            # Check if lock exists
            process = await asyncio.create_subprocess_exec(
                "docker", "exec", container_id, "bash", "-c", "lsof /var/lib/dpkg/lock-frontend",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:  # No lock found
                return True
                
            await status_msg.edit(content=f"🔄 Waiting for package manager to be ready... (Attempt {attempt + 1}/{max_attempts})")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error checking apt lock: {e}")
            await asyncio.sleep(5)
    
    return False

async def setup_container(container_id, vps_id):
    """Set up the container with required packages and configurations"""
    try:
        container = client.containers.get(container_id)
        if not container.status == "running":
            container.start()

        # Update package list and install required packages
        container.exec_run("apt-get update")
        container.exec_run("apt-get install -y tmate docker.io systemd-sysv dbus dbus-user-session", privileged=True)
        
        # Configure systemd
        container.exec_run("mkdir -p /etc/systemd/system/docker.service.d")
        container.exec_run("echo '[Service]\nExecStart=\nExecStart=/usr/bin/dockerd --containerd=/run/containerd/containerd.sock' > /etc/systemd/system/docker.service.d/override.conf")
        
        # Configure Docker
        container.exec_run("mkdir -p /etc/docker")
        container.exec_run("echo '{\"data-root\": \"/var/lib/docker\", \"exec-opts\": [\"native.cgroupdriver=systemd\"]}' > /etc/docker/daemon.json")
        
        # Set hostname and system information
        container.exec_run("hostnamectl set-hostname 'CatHosting Vps'")
        container.exec_run("echo 'CatHosting Vps' > /etc/hostname")
        container.exec_run("echo '127.0.0.1 CatHosting Vps' >> /etc/hosts")
        
        # Update system information files
        container.exec_run("""echo 'PRETTY_NAME="CatHosting Vps"
NAME="CatHosting Vps"
VERSION="1.0"
ID=cathosting
VERSION_ID="1.0"' > /etc/os-release""")
        
        container.exec_run("""echo 'DISTRIB_ID=CatHosting
DISTRIB_RELEASE=1.0
DISTRIB_CODENAME=vps
DISTRIB_DESCRIPTION="CatHosting Vps"' > /etc/lsb-release""")
        
        # Enable and start services
        container.exec_run("systemctl daemon-reload")
        container.exec_run("systemctl enable docker")
        container.exec_run("systemctl start docker")
        
        # Restart container to apply changes
        container.restart()
        
        return True
    except Exception as e:
        print(f"Error setting up container: {e}")
        return False

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║                     VPS Deployer Bot                        ║
    ║                                                            ║
    ║  Developed by: DpWorld (Discord ID: dpworld)               ║
    ║  GitHub: https://github.com/dpworld                        ║
    ║  Discord: https://discord.gg/dpworld                       ║
    ║                                                            ║
    ║  License: MIT License                                      ║
    ║  Copyright (c) 2024 DpWorld                                ║
    ║                                                            ║
    ║  Features:                                                 ║
    ║  • Create and manage VPS instances                         ║
    ║  • Real-time resource monitoring                           ║
    ║  • Secure SSH access via tmate                            ║
    ║  • Systemd support                                        ║
    ║  • Docker container management                            ║
    ║  • User-friendly interface                                ║
    ╚════════════════════════════════════════════════════════════╝
    """)
    load_vps_data()

@bot.command(name='commands')
@commands.check(has_required_role)
async def show_commands(ctx):
    """Show available commands"""
    embed = discord.Embed(title="Available Commands", color=discord.Color.blue())
    embed.add_field(name="Basic Commands", value="""
`!list` - List your VPS instances
`!connect_vps <vps_id>` - Connect to your VPS
`!check_ram <vps_id>` - Check RAM usage of your VPS
`!manage_vps <vps_id>` - Manage your VPS
`!node` - Show node information
""", inline=False)
    
    if has_admin_role(ctx):
        embed.add_field(name="Admin Commands", value="""
`!create_vps <memory> <cpu> <disk> <owner>` - Create a new VPS
`!vps_list` - List all VPS instances
`!delete_vps <vps_id> <username>` - Delete a VPS
""", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='list')
async def list_vps_command(ctx):
    """List VPS instances"""
    try:
        # Check if user has admin role
        is_admin = False
        if ctx.guild:  # Check if command is used in a server
            member = ctx.guild.get_member(ctx.author.id)
            if member:
                is_admin = any(role.id == ADMIN_ROLE_ID for role in member.roles)
        
        if is_admin:
            # Admin can see all VPSes
            if not vps_data:
                await ctx.send("No VPS instances found.")
                return

            embed = discord.Embed(
                title="📋 VPS List (Admin View)",
                description="Here are all the VPS instances:",
                color=discord.Color.blue()
            )

            for user_id, vps in vps_data.items():
                try:
                    user = await bot.fetch_user(int(user_id))
                    username = user.name
                except:
                    username = "Unknown User"

                status = "🟢 Running" if vps.get("status") == "running" else "🔴 Stopped"
                created_at = vps.get("created_at", "Unknown")
                
                embed.add_field(
                    name=f"VPS {vps['id']} ({username})",
                    value=f"Status: {status}\nCreated: {created_at}\nResources: {vps['ram']}MB RAM, {vps['cpu']} CPU, {vps['disk']}GB Disk",
                    inline=False
                )
        else:
            # Regular users can only see their own VPS
            user_id = str(ctx.author.id)
            if user_id not in vps_data:
                await ctx.send("❌ You don't have a VPS. Use !create_vps to create one.")
                return

            vps = vps_data[user_id]
            status = "🟢 Running" if vps.get("status") == "running" else "🔴 Stopped"
            created_at = vps.get("created_at", "Unknown")

            embed = discord.Embed(
                title="📋 Your VPS",
                description="Here are your VPS details:",
                color=discord.Color.blue()
            )
            embed.add_field(
                name=f"VPS {vps['id']}",
                value=f"Status: {status}\nCreated: {created_at}\nResources: {vps['ram']}MB RAM, {vps['cpu']} CPU, {vps['disk']}GB Disk",
                inline=False
            )

        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error listing VPS: {str(e)}")

@bot.command(name='vps_list')
@commands.check(has_admin_role)
async def admin_list_vps(ctx):
    """List all VPS instances (Admin only)"""
    try:
        if not vps_data:
            await ctx.send("No VPS instances found.")
            return

        embed = discord.Embed(title="All VPS Instances", color=discord.Color.blue())
        valid_vps_count = 0
        vps_to_remove = []  # Store VPS IDs to remove after iteration
        
        # Create a copy of the keys to iterate over
        for vps_id in list(vps_data.keys()):
            vps = vps_data[vps_id]
            try:
                # Get user information
                try:
                    user = await bot.fetch_user(int(vps.get("created_by", "0")))
                    username = user.name
                except:
                    username = "Unknown User"

                # Check container status
                try:
                    container = client.containers.get(vps.get("container_id", ""))
                    status = "🟢 Running" if container.status == "running" else "🔴 Stopped"
                except:
                    # Mark for removal after iteration
                    vps_to_remove.append(vps_id)
                    continue

                # Get VPS information with safe defaults
                vps_info = f"""
Owner: {username}
Status: {status}
Memory: {vps.get('ram', 'Unknown')}MB
CPU: {vps.get('cpu', 'Unknown')} cores
Disk: {vps.get('disk', 'Unknown')}GB
Username: {vps.get('username', 'Unknown')}
Created: {vps.get('created_at', 'Unknown')}
VPS ID: {vps_id}
"""

                embed.add_field(
                    name=f"VPS {vps_id}",
                    value=vps_info,
                    inline=False
                )
                valid_vps_count += 1
            except Exception as e:
                print(f"Error processing VPS {vps_id}: {e}")
                continue
        
        # Remove invalid VPS entries after iteration
        for vps_id in vps_to_remove:
            del vps_data[vps_id]
        if vps_to_remove:
            save_vps_data()

        if valid_vps_count == 0:
            await ctx.send("No valid VPS instances found.")
            return

        embed.set_footer(text=f"Total VPS instances: {valid_vps_count}")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error listing VPS instances: {str(e)}")

@bot.command(name='delete_vps')
@commands.check(has_admin_role)
async def delete_vps(ctx, vps_id: str, username: str):
    """Delete a VPS instance"""
    try:
        # Find VPS to delete
        vps_to_delete = None
        for vps_id_key, vps in vps_data.items():
            if vps_id_key == vps_id and vps["username"] == username:
                vps_to_delete = vps_id_key
                break

        if not vps_to_delete:
            await ctx.send("❌ VPS not found!")
            return

        # Stop and remove container
        try:
            container = client.containers.get(vps_data[vps_to_delete]["container_id"])
            container.stop()
            container.remove()
        except:
            pass  # Container might not exist

        # Remove VPS data
        del vps_data[vps_to_delete]
        save_vps_data()

        await ctx.send(f"✅ VPS {vps_id} has been deleted!")
    except Exception as e:
        await ctx.send(f"❌ Error deleting VPS: {str(e)}")

@bot.command(name='manage_vps')
async def manage_vps_command(ctx):
    """Manage your VPS"""
    try:
        user_id = str(ctx.author.id)
        if user_id not in vps_data:
            await ctx.send("❌ You don't have a VPS. Use !create_vps to create one.")
            return

        vps = vps_data[user_id]
        container = client.containers.get(vps["container_id"])
        status = "🟢 Running" if container.status == "running" else "🔴 Stopped"

        embed = discord.Embed(
            title="🎮 VPS Management",
            description=f"VPS ID: {vps['id']}\nStatus: {status}",
            color=discord.Color.blue()
        )

        view = VPSManagementView(ctx, vps)
        await ctx.send(embed=embed, view=view)
    except Exception as e:
        await ctx.send(f"❌ Error managing VPS: {str(e)}")

class OSSelectionView(ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.selected_os = None

    @discord.ui.select(
        placeholder="Select OS to install",
        options=[
            discord.SelectOption(label="Ubuntu 22.04", value="ubuntu:22.04", description="Latest LTS version"),
            discord.SelectOption(label="Ubuntu 20.04", value="ubuntu:20.04", description="Previous LTS version"),
            discord.SelectOption(label="Debian 12", value="debian:12", description="Latest Debian stable"),
            discord.SelectOption(label="Debian 11", value="debian:11", description="Previous Debian stable")
        ]
    )
    async def select_os(self, select_interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_os = select.values[0]
        await select_interaction.response.defer()
        self.stop()

class VPSManagementView(discord.ui.View):
    def __init__(self, ctx, vps):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.vps = vps

    @discord.ui.button(label="Start VPS", style=discord.ButtonStyle.green)
    async def start_vps(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.ctx.author.id):
            await interaction.response.send_message("❌ This is not your VPS!", ephemeral=True)
            return

        try:
            container = client.containers.get(self.vps["container_id"])
            if container.status == "running":
                await interaction.response.send_message("✅ VPS is already running!", ephemeral=True)
                return

            container.start()
            self.vps["status"] = "running"
            save_vps_data()

            # Install tmate if not installed
            container.exec_run("apt-get update && apt-get install -y tmate", privileged=True)
            
            # Kill any existing tmate sessions
            container.exec_run("pkill tmate || true")
            
            # Create new tmate session
            result = container.exec_run("tmate -S /tmp/tmate.sock new-session -d && tmate -S /tmp/tmate.sock wait tmate-ready && tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'", privileged=True)
            
            if result.exit_code != 0:
                await interaction.response.send_message("❌ Error getting new session: Failed to get tmate session", ephemeral=True)
                return

            ssh_url = result.output.decode().strip()
            
            embed = discord.Embed(
                title="🚀 VPS Started Successfully!",
                description="Your VPS is now running. Use the following command to connect:",
                color=discord.Color.green()
            )
            embed.add_field(name="SSH Command", value=f"```{ssh_url}```", inline=False)
            embed.add_field(name="Username", value=self.vps["username"], inline=False)
            embed.add_field(name="Password", value=self.vps["password"], inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error starting VPS: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Stop VPS", style=discord.ButtonStyle.red)
    async def stop_vps(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.ctx.author.id):
            await interaction.response.send_message("❌ This is not your VPS!", ephemeral=True)
            return

        try:
            container = client.containers.get(self.vps["container_id"])
            if container.status != "running":
                await interaction.response.send_message("✅ VPS is already stopped!", ephemeral=True)
                return

            container.stop()
            self.vps["status"] = "stopped"
            save_vps_data()
            await interaction.response.send_message("✅ VPS stopped successfully!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error stopping VPS: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Restart VPS", style=discord.ButtonStyle.blurple)
    async def restart_vps(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.ctx.author.id):
            await interaction.response.send_message("❌ This is not your VPS!", ephemeral=True)
            return

        try:
            container = client.containers.get(self.vps["container_id"])
            container.restart()
            self.vps["status"] = "running"
            save_vps_data()

            # Install tmate if not installed
            container.exec_run("apt-get update && apt-get install -y tmate", privileged=True)
            
            # Kill any existing tmate sessions
            container.exec_run("pkill tmate || true")
            
            # Create new tmate session
            result = container.exec_run("tmate -S /tmp/tmate.sock new-session -d && tmate -S /tmp/tmate.sock wait tmate-ready && tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'", privileged=True)
            
            if result.exit_code != 0:
                await interaction.response.send_message("❌ Error getting new session: Failed to get tmate session", ephemeral=True)
                return

            ssh_url = result.output.decode().strip()
            
            embed = discord.Embed(
                title="🔄 VPS Restarted Successfully!",
                description="Your VPS has been restarted. Use the following command to connect:",
                color=discord.Color.green()
            )
            embed.add_field(name="SSH Command", value=f"```{ssh_url}```", inline=False)
            embed.add_field(name="Username", value=self.vps["username"], inline=False)
            embed.add_field(name="Password", value=self.vps["password"], inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error restarting VPS: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Reinstall OS", style=discord.ButtonStyle.gray)
    async def reinstall_os(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.ctx.author.id):
            await interaction.response.send_message("❌ This is not your VPS!", ephemeral=True)
            return

        try:
            view = OSSelectionView(self.ctx, self.vps)
            await interaction.response.send_message("Select an operating system to reinstall:", view=view, ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error starting reinstallation: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Delete VPS", style=discord.ButtonStyle.danger)
    async def delete_vps(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.ctx.author.id):
            await interaction.response.send_message("❌ This is not your VPS!", ephemeral=True)
            return

        try:
            container = client.containers.get(self.vps["container_id"])
            container.stop()
            container.remove()
            del vps_data[str(self.ctx.author.id)]
            save_vps_data()
            await interaction.response.send_message("✅ VPS deleted successfully!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error deleting VPS: {str(e)}", ephemeral=True)

@bot.command(name='delete_all')
@commands.check(has_admin_role)
async def delete_all_vps(ctx):
    """Delete all VPS instances"""
    try:
        # Get confirmation
        await ctx.send("⚠️ Are you sure you want to delete ALL VPS instances? This action cannot be undone! Type 'yes' to confirm.")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'yes'
        
        try:
            await bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("❌ Operation cancelled - no confirmation received.")
            return

        # Delete all VPSes
        deleted_count = 0
        for vps_id, vps_data_item in list(vps_data.items()):
            try:
                # Stop and remove container
                try:
                    container = client.containers.get(vps_data_item["container_id"])
                    container.stop()
                    container.remove()
                except:
                    pass  # Container might not exist

                # Remove VPS data
                del vps_data[vps_id]
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting VPS {vps_id}: {e}")

        # Save updated VPS data
        save_vps_data()
        
        await ctx.send(f"✅ Successfully deleted {deleted_count} VPS instances!")
    except Exception as e:
        await ctx.send(f"❌ Error deleting VPSes: {str(e)}")

@bot.command(name='start_vps')
@commands.check(has_admin_role)
async def start_vps_command(ctx):
    """Start your VPS"""
    try:
        user_id = str(ctx.author.id)
        if user_id not in vps_data:
            await ctx.send("❌ You don't have a VPS. Use !create_vps to create one.")
            return

        vps = vps_data[user_id]
        container = client.containers.get(vps["container_id"])

        if container.status == "running":
            await ctx.send("✅ VPS is already running!")
            return

        # Start container
        container.start()
        vps["status"] = "running"
        save_vps_data()

        # Install tmate if not installed
        container.exec_run("apt-get update && apt-get install -y tmate", privileged=True)
        
        # Kill any existing tmate sessions
        container.exec_run("pkill tmate || true")
        
        # Create new tmate session
        result = container.exec_run("tmate -S /tmp/tmate.sock new-session -d && tmate -S /tmp/tmate.sock wait tmate-ready && tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'", privileged=True)
        
        if result.exit_code != 0:
            await ctx.send("❌ Error getting new session: Failed to get tmate session")
            return

        ssh_url = result.output.decode().strip()
        
        embed = discord.Embed(
            title="🚀 VPS Started Successfully!",
            description="Your VPS is now running. Use the following command to connect:",
            color=discord.Color.green()
        )
        embed.add_field(name="SSH Command", value=f"```{ssh_url}```", inline=False)
        embed.add_field(name="Username", value=vps["username"], inline=False)
        embed.add_field(name="Password", value=vps["password"], inline=False)
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error starting VPS: {str(e)}")

@bot.command(name='create_vps')
@commands.check(has_admin_role)
async def create_vps_command(ctx, ram: int, cpu: int, disk: int):
    """Create a new VPS with specified resources"""
    try:
        # Check minimum RAM requirement
        if ram < 6:
            await ctx.send("❌ Minimum RAM requirement is 6MB")
            return

        # Check if user already has a VPS
        user_id = str(ctx.author.id)
        if user_id in vps_data:
            await ctx.send("❌ You already have a VPS. Please delete your existing VPS first.")
            return

        status_msg = await ctx.send("🔄 Creating VPS... Please wait.")

        # Create Docker network if it doesn't exist
        try:
            client.networks.get("vps_network")
        except:
            await status_msg.edit(content="🔄 Creating Docker network...")
            client.networks.create("vps_network", driver="bridge")

        # Generate VPS ID and credentials
        vps_id = str(uuid.uuid4())[:8]
        username = f"@{ctx.author.name}"
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        
        await status_msg.edit(content="🔄 Creating container...")
        
        # Create container with systemd
        container = client.containers.run(
            image="ubuntu:22.04",
            command="bash -c 'apt-get update && apt-get install -y systemd-sysv tmate && /lib/systemd/systemd'",
            detach=True,
            privileged=True,
            cap_add=["ALL", "SYS_ADMIN"],
            security_opt=["seccomp:unconfined"],
            volumes={
                '/sys/fs/cgroup': {'bind': '/sys/fs/cgroup', 'mode': 'ro'},
                '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'},
                '/var/lib/docker': {'bind': '/var/lib/docker', 'mode': 'rw'},
                '/etc/docker': {'bind': '/etc/docker', 'mode': 'rw'}
            },
            name=f"vps_{vps_id}",
            hostname="CatHosting Vps",
            environment={
                "container": "docker",
                "DOCKER_HOST": "unix:///var/run/docker.sock"
            },
            network="vps_network",
            mem_limit=f"{ram}m",
            memswap_limit=f"{ram}m",
            cpu_period=100000,
            cpu_quota=int(cpu * 100000),
            restart_policy={"Name": "unless-stopped"}
        )

        await status_msg.edit(content="🔄 Setting up container...")
        
        # Set up the container
        if not await setup_container(container.id, vps_id):
            container.stop()
            container.remove()
            await status_msg.edit(content="❌ Container setup failed")
            return

        await status_msg.edit(content="🔄 Configuring system...")

        # Store VPS data
        vps_data[user_id] = {
            "id": vps_id,
            "container_id": container.id,
            "ram": ram,
            "cpu": cpu,
            "disk": disk,
            "username": username,
            "password": password,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running"
        }
        save_vps_data()

        await status_msg.edit(content="🔄 Setting up SSH access...")

        # Get tmate session
        try:
            # Kill any existing tmate sessions
            container.exec_run("pkill tmate || true")
            
            # Create new tmate session
            result = container.exec_run("tmate -S /tmp/tmate.sock new-session -d && tmate -S /tmp/tmate.sock wait tmate-ready && tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}'", privileged=True)
            
            if result.exit_code != 0:
                await status_msg.edit(content="❌ Error getting tmate session")
                return

            ssh_url = result.output.decode().strip()
        except Exception as e:
            await status_msg.edit(content=f"❌ Error getting tmate session: {str(e)}")
            return

        await status_msg.edit(content="🔄 Sending credentials...")

        # Send credentials via DM
        try:
            embed = discord.Embed(
                title="🎉 VPS Created Successfully!",
                description="Here are your VPS credentials:",
                color=discord.Color.green()
            )
            embed.add_field(name="Username", value=username, inline=False)
            embed.add_field(name="Password", value=password, inline=False)
            embed.add_field(name="VPS ID", value=vps_id, inline=False)
            embed.add_field(name="Resources", value=f"RAM: {ram}MB\nCPU: {cpu} cores\nDisk: {disk}GB", inline=False)
            embed.add_field(name="Created At", value=vps_data[user_id]["created_at"], inline=False)
            embed.add_field(name="SSH Command", value=f"```{ssh_url}```", inline=False)
            await ctx.author.send(embed=embed)
            await status_msg.edit(content="✅ VPS created successfully! Check your DMs for credentials.")
        except:
            await status_msg.edit(content="❌ Could not send credentials via DM. Please enable DMs from server members.")

    except Exception as e:
        await ctx.send(f"❌ Error creating VPS: {str(e)}")

@bot.command(name='credits')
async def show_credits(ctx):
    """Show bot credits and license information"""
    embed = discord.Embed(
        title="VPS Deployer Bot",
        description="A powerful Discord bot for managing VPS instances with Docker containers.",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Developer Credits",
        value="**Developed by:** DpWorld\n**Discord ID:** dpworld\n**GitHub:** https://github.com/dpworld\n**Discord:** https://discord.gg/dpworld",
        inline=False
    )
    
    embed.add_field(
        name="License",
        value="""**MIT License**
Copyright (c) 2024 DpWorld

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.""",
        inline=False
    )
    
    embed.add_field(
        name="Features",
        value="""• Create and manage VPS instances
• Real-time resource monitoring
• Secure SSH access via tmate
• Systemd support
• Docker container management
• User-friendly interface""",
        inline=False
    )
    
    await ctx.send(embed=embed)

# Error handler for missing role
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You don't have permission to use this command!")
    else:
        print(f"Error: {error}")

# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN) 