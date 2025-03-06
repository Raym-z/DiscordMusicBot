import discord
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
client = discord.Client(intents=intents)

voice_clients = {}
queues = {}

yt_dl_options = {"format": "bestaudio/best"}
ytdl = yt_dlp.YoutubeDL(yt_dl_options)

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.25"'
}

def create_now_playing_embed(title, url, author, formatted_duration, next_song_title, thumbnail, requester):
    embed = discord.Embed(title="🎵 Now Playing", description=f"**[{title}]({url})**", color=discord.Color.blue())
    embed.set_thumbnail(url=thumbnail)
    embed.add_field(name="**====================================================**", value="", inline=False)
    embed.add_field(name=f"Author: **{author}**", value="", inline=True)
    embed.add_field(name=f"Duration: **{formatted_duration}**", value="", inline=True)
    embed.add_field(name=f"Next Song: **{next_song_title}**", value=f"", inline=True)
    embed.add_field(name="Volume: `25%`", value="", inline=True)
    embed.add_field(name="Loop: `Off`", value="", inline=True)
    embed.set_footer(text=f"Requested by {requester}", icon_url=requester.avatar.url if requester.avatar else requester.default_avatar.url)
    return embed

async def play_next(guild_id, message_channel):
    """Plays the next song in the queue and updates the embed."""
    if guild_id in queues and queues[guild_id]:
        next_song_data = queues[guild_id].pop(0)  
        next_song = next_song_data["player"]
        next_song_title = next_song_data["title"]
        next_song_url = next_song_data["url"]
        next_song_author = next_song_data["author"]
        next_song_duration = next_song_data["duration"]
        next_song_thumbnail = next_song_data["thumbnail"]
        next_song_requester = next_song_data["requester"]

        if voice_clients.get(guild_id) and voice_clients[guild_id].is_connected():
            voice_clients[guild_id].play(next_song, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild_id, message_channel), client.loop))

            upcoming_song_title = "None"
            if queues[guild_id]:
                upcoming_song_data = queues[guild_id][0]
                upcoming_song_title = upcoming_song_data["title"]

            embed = create_now_playing_embed(
                next_song_title, next_song_url, next_song_author, next_song_duration, 
                upcoming_song_title, next_song_thumbnail, next_song_requester
            )

            await message_channel.send(embed=embed)
    else:
        if guild_id in voice_clients:
            await voice_clients[guild_id].disconnect()
            del voice_clients[guild_id]

@client.event
async def on_ready():
    print(f'{client.user} is now jamming!')

@client.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = message.guild.id

    if message.content.startswith("?play"):
        if not message.author.voice:
            await message.channel.send("You need to be in a voice channel to use this command.")
            return
        try:
            await message.delete()
            voice_client = voice_clients.get(guild_id)
            if not voice_client or not voice_client.is_connected():
                voice_client = await message.author.voice.channel.connect()
                voice_clients[guild_id] = voice_client
                queues[guild_id] = []

            url = message.content.split()[1]
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            
            song = data.get('url', None)
            if not song:
                await message.channel.send("Could not retrieve audio stream. The video might be restricted.")
                return

            title = data.get('title', 'Unknown Title')
            duration = data.get('duration', 0) 
            formatted_duration = f"{duration // 60}:{duration % 60:02}"
            author = data.get('uploader', 'Unknown Artist')
            player = discord.FFmpegOpusAudio(song, **ffmpeg_options)
            
            next_song_title = "None"
            if queues[guild_id]:
                next_song_data = queues[guild_id][0]
                next_song_title = getattr(next_song_data, 'title', 'Unknown')
                
            if not voice_client.is_playing():
                voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild_id, message.channel), client.loop))
                embed = create_now_playing_embed(title, url, author, formatted_duration, next_song_title, data.get('thumbnail', ''), message.author)
                await message.channel.send(embed=embed)
            else:
                queues[guild_id].append({
                    "player": player,
                    "title": title,
                    "url": url,
                    "author": author,
                    "duration": formatted_duration,
                    "thumbnail": data.get("thumbnail", ""),
                    "requester": message.author
                })

                await message.channel.send(f"**{title}** added to the queue!")

        except Exception as e:
            await message.channel.send(f"Error playing the song: {str(e)}")


    elif message.content.startswith("?skip"):
        try:
            if guild_id in voice_clients and voice_clients[guild_id].is_playing():
                voice_clients[guild_id].stop()
                await play_next(guild_id, message.channel) 
                await message.channel.send("Skipped to the next song!" if queues[guild_id] else "No more songs in the queue.")
            else:
                await message.channel.send("No song is currently playing.")
        except Exception as e:
            await message.channel.send(f"Error skipping the song: {str(e)}")


    elif message.content.startswith("?pause"):
        try:
            if guild_id in voice_clients and voice_clients[guild_id].is_playing():
                voice_clients[guild_id].pause()
        except Exception as e:
            await message.channel.send(f"Error pausing the song: {str(e)}")

    elif message.content.startswith("?resume"):
        try:
            if guild_id in voice_clients and voice_clients[guild_id].is_paused():
                voice_clients[guild_id].resume()
        except Exception as e:
            await message.channel.send(f"Error resuming the song: {str(e)}")

    elif message.content.startswith("?stop"):
        try:
            if guild_id in voice_clients and voice_clients[guild_id].is_connected():
                voice_clients[guild_id].stop()
                queues[guild_id] = []
                await voice_clients[guild_id].disconnect()
                del voice_clients[guild_id]
        except Exception as e:
            await message.channel.send(f"Error stopping the bot: {str(e)}")
        
    elif message.content.startswith("?queue"):
        if guild_id in queues and queues[guild_id]:
            queue_list = "\n".join([f"**{song_data['title']}**" for song_data in queues[guild_id]])
            await message.channel.send(f"**Upcoming Songs:**\n{queue_list}")
        else:
            await message.channel.send("No songs in the queue.")


client.run(TOKEN)
