#from asyncio.windows_events import NULL
import datetime
import pymongo as mongo
import discord
from discord.ext import commands
import os
import emoji

BotToken = os.environ['bottoken']
dburl = os.environ['dburl']

client = mongo.MongoClient(dburl)
db = client['Leaderboard']
print(client)
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix='!', intents = intents)
bot.remove_command('help')

@bot.event
async def on_ready():
    print("Ready")

@bot.command()
@commands.has_permissions(manage_channels = True)
async def setup(ctx):
    servername = str(ctx.guild)
    guild = ctx.guild
    clusterlist = db.list_collection_names()
    if(servername not in clusterlist):
        mycol = db[servername]
        mycol.insert_one({'name' : 'test'})
        mycol.delete_one({'name' : 'test'})
        db.create_collection(servername + '-points')

        db['Emojis'].insert_one({'Emoji' : '', 'pointvalue' : 20, 'server' : servername})

        async for member in guild.fetch_members():
            roles = []
            for x in member.roles:
                roles.append(x.name)
            if(member.bot == False):
                db[servername].insert_one({'user' : member.name + '#' + member.discriminator, 'points' : 0, 'roles' : roles, 'displayname' : member.display_name})

    else:
        await ctx.channel.send("Server already exists")
        return
    
    await ctx.channel.send("Setup complete. Set emoji to count with !changeemoji before checking messages.")

@bot.event
async def on_member_join(member):
    servername = str(member.guild)
    test = db[servername].find_one({'user' : member.name + '#' + member.discriminator})
    roles = []
    for x in member.roles:
        roles.append(x.name)

    if(test == None):
        db[servername].insert_one({'user' : member.name + '#' + member.discriminator, 'points' : 0, 'roles' : roles, 'displayname' : member.display_name})



@bot.command()
@commands.has_permissions(manage_channels = True)
async def setemoji(ctx, arg):
    servername = str(ctx.guild)

    #checks if the arg exists in standard emoji library. If so converts tohexadecimal and is added
    if(arg in emoji.UNICODE_EMOJI_ENGLISH):
        print('standard emoji')
        arg = f'U+{ord(arg):X}'
        db['Emojis'].update_one({'server' : servername}, {'$set': {'Emoji' : arg}})

    #if not it we pull the id and store that 
    else:
        db['Emojis'].update_one({'server' : servername}, {'$set': {'Emoji' : (arg.split(':', 2)[2]).replace('>', '')}})
    await ctx.channel.send('Emoji changed')

@bot.command()
@commands.has_permissions(manage_channels = True)
async def add(ctx, arg, num, note = None):
    servername = str(ctx.guild)
    check = db[servername].find_one({'displayname' : arg})
    if(check == None):
        await ctx.channel.send('User not found!')
        return

    db[servername].update_one({'displayname' : arg}, {'$inc' : {'points' : int(num)}})
    db[servername + '-points'].insert_one({'user' : arg, 'points' : num, 'note' : note, 'date' : datetime.datetime.utcnow()})
    points = db[servername].find_one({'displayname' : arg})
    
    await ctx.channel.send(f'{arg} point balance is now ' + str(points['points']))

@bot.command()
@commands.has_permissions(manage_channels = True)
async def sub(ctx, arg, num):
    servername = str(ctx.guild)
    check = db[servername].find_one({'displayname' : arg})
    if(check == None):
        await ctx.channel.send('User not found!')
        return

    record = db[servername].update_one({'displayname' : arg}, {'$inc' : {'points' : int(num) * -1}})
    points = db[servername].find_one({'displayname' : arg})
    if(points == None):
        await ctx.channel.send("User not found. Use display name. Names are case sensitive")
    else:
        await ctx.channel.send(f'{arg} point balance is now ' + str(points['points']))

@bot.command()
@commands.has_permissions(manage_channels = True)
async def setpoints(ctx, arg):
    servername = str(ctx.guild)
    db['Emojis'].update_one({'server' : servername}, {'$set' : {'pointvalue' : int(arg)}})
    await ctx.channel.send("Points added for reacting now equals " + str(db['Emojis'].find_one({'server' : servername})['pointvalue']))


@bot.command()
async def top(ctx, role = None):
    servername = str(ctx.guild)
    list = []
    if(role == None):
        cursor = db[servername].find({}, {'_id' : 0})

        for x in cursor:
            list.append(x)
        sortedlist = sorted(list, key= lambda i: i['points'], reverse= True)
    else:
        cursor = db[servername].find({}, {'_id' : 0})  

        for x in cursor:
            if(role in x['roles']):
                list.append(x)
            sortedlist = sorted(list, key= lambda i: i['points'], reverse= True)

    embed = discord.Embed(
        colour = discord.Colour.green(),
        title = ':coin:' + servername + ' Leaderboard'
    )
    embed.set_thumbnail(url= str(ctx.guild.icon_url_as(format= 'jpg', size= 64)))

    counter = 1
    for v in sortedlist:
        embed.add_field(name= (str(counter) +'. ' + v['displayname']), value= v['points'], inline= False)
        counter = counter + 1
        if(counter == 11):
            break
    
    await ctx.channel.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_channels = True)
async def msgcheck(ctx, arg):
    servername = str(ctx.guild)
    counterreaction = None
    clusterlist = db.list_collection_names()
    

    counteremoji = (db['Emojis'].find_one({'server' : servername}, {'Emoji' : 1, '_id' : 0}))['Emoji'] 
    pointvalue = db['Emojis'].find_one({'server' : servername})['pointvalue']

    list = arg.split('/')
    messageid = list[6]
    message = await ctx.channel.fetch_message(messageid)

    reactions = message.reactions

    #finds the reaction with the counter emoji
    for x in reactions:

       #if reactionemoji is in standard unicode library convert to hex
        if(x.emoji in emoji.UNICODE_EMOJI_ENGLISH):
            reactionemoji = f'U+{ord(x.emoji):X}'
            print('reactionemoji = ' + reactionemoji)
        #else it is a partial emoji and set to the id
        else:
            reactionemoji = str(x.emoji.id)

        #if the emoji is equal to the set counter emoji then allocate points to its users
        if(reactionemoji == counteremoji):
            counterreaction = x

            #checks if users that reacted exist. Adds if not. Else it updates existing users points
            #this for loop may be unnecessary now
            async for user in counterreaction.users():
                test = db[servername].find_one({'user' : str(user)})
                if(test == None):
                    db[servername].insert_one({'user' : str(user), 'points' : pointvalue, 'roles' : [], 'displayname' : user.display_name})
                else:
                    db[servername].update_one({'user' : str(user)}, {'$inc': {'points' : pointvalue}})

    if(counterreaction == None):
        await ctx.channel.send('Set counter reaction not found in message!')
    await ctx.channel.send("Points allocated!")

@bot.command()
async def points(ctx, arg):
    servername = str(ctx.guild)

    check = db[servername].find_one({'displayname' : arg})
    if(check == None):
        await ctx.channel.send('User not found!')
        return
    
    cursor = db[servername].find({}, {'_id': 0}).sort('points', -1)
    ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(n//10%10!=1)*(n%10<4)*n%10::4])

    counter = 1
    for x in cursor:
        if(x['displayname'] == arg):
            points = x['points']
            place = ordinal(counter)
            await ctx.channel.send(f'{arg} is in {place} ranking with {points} points')
        counter = counter + 1

@bot.command()
async def log(ctx, arg):
    servername = str(ctx.guild)
    check = db[servername + '-points'].find_one({'user' : arg})
    if(check == None):
        await ctx.channel.send('User not found!')
        return
    cursor = db[servername + '-points'].find({'user' : arg, 'note' :{'$ne' : None}}, {'_id' : 0})
    message = ''

    userid = db[servername].find_one({'displayname' : arg})['user']
    member = ctx.guild.get_member_named(userid)
    avatar = member.avatar_url_as(format= 'jpg', size= 64)

    embed = discord.Embed(
        colour = discord.Colour.green(),
        title = f':coin: {arg} Point Log:'
    )
    embed.set_thumbnail(url= str(avatar))

    for x in cursor:
        points = x['points']
        notes = x['note']
        date = datetime.datetime.strftime(x['date'], '%m/%d')
        END = '\033[0m'
        
        embed.add_field(name=f'  {points} points on {date}', value=notes, inline = False)
    
    await ctx.channel.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_channels = True)
async def reset(ctx):
    servername = str(ctx.guild)
    await ctx.channel.send(f'This command resets points to 0 and clears the point log. Type y/n to confirm')
    msg = await bot.wait_for('message', check = lambda m: m.author == ctx.author)
    if(msg.content == 'y'):
        db[servername +'-points'].delete_many({})
        db[servername].update_many({}, {'$set' : {'points' : 0}})
        await ctx.channel.send('Reset successful')
    elif(msg.content == 'n'):
        await ctx.channel.send('Command canceled')
    else:
        await ctx.channel.send('Incorrect input!')
    

@bot.command()
@commands.has_permissions(manage_channels = True)
async def clearlog(ctx, arg = None):
    servername = str(ctx.guild)
    if(arg != None):
        await ctx.channel.send(f'You are about to clear the point history for {arg}. Type y/n to confirm')
        msg = await bot.wait_for('message', check = lambda m: m.author == ctx.author)
        if(msg.content == 'y'):
            db[servername +'-points'].delete_many({'user' : arg})
            await ctx.channel.send(f'Point history deleted for user {arg}')
        elif(msg.content == 'n'):
            await ctx.channel.send('Command canceled')
        else:
            await ctx.channel.send('Incorrect input!') 
    else:
        await ctx.channel.send('You are about to clear the entire point history. Type y/n to confirm')
        msg = await bot.wait_for('message', check = lambda m: m.author == ctx.author)
        if(msg.content == 'y'):
            db[servername +'-points'].delete_many({})
            await ctx.channel.send('Point history deleted')
        elif(msg.content == 'n'):
            await ctx.channel.send('Command canceled')
        else:
            await ctx.channel.send('Incorrect input!')
        

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        colour = discord.Colour.orange(),
        title = 'Help'
    )
    embed.add_field(name='<value>*', value = 'Command values marked with * are optional')
    embed.add_field(name='!setup', value='Registers server with bot database', inline = False)
    embed.add_field(name='!setemoji <emoji>', value='Change the emoji to be counted in reactions', inline = False)
    embed.add_field(name= '!msgcheck <message link>', value= 'Allocates points for users who reacted with set emoji', inline= False)
    embed.add_field(name= '!points <user>', value= 'Returns the amount of points and place of user in the leaderboard', inline= False)
    embed.add_field(name='!add <user> <points> <notes>*', value='Adds points to x user. Notes must be enclose in " "')
    embed.add_field(name='!sub <user> <points>', value= 'Subtracts points from x user', inline = False)
    embed.add_field(name='!setpoints <number>', value='Sets the amount of points the counter emoji adds to each users score', inline = False)
    embed.add_field(name='!top <role>*', value='Shows a scoreboard of users in the server', inline= False)
    embed.add_field(name= '!log <user>', value= 'Shows a history of awarded points to user with notes')
    embed.add_field(name= '!clearlog<user>*', value= 'Clears entire point hitory log. If a user is specified, only clears log for that user', inline= False)
    embed.add_field(name= '!reset', value= 'Resets everyones points to 0. Clears entire point history log')
    await ctx.channel.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    
    await ctx.channel.send(error)

@bot.event
async def on_member_update(before, after):
    server = str(after.guild)

    if(before.display_name != after.display_name): 
        db[server].update_many({'displayname' : before.display_name}, {'$set': {'displayname' : after.display_name}})
        db[server +'-points'].update_many({'user' : before.display_name}, {'$set': {'user' : after.display_name}})

    if(before.roles != after.roles):
        rolelist = []
        roles = after.roles
        for x in roles:
            rolelist.append(x.name)
        db[server].update_one({'displayname' : after.display_name}, {'$set': {'role' : rolelist}})
        print(rolelist)

bot.run(BotToken)



