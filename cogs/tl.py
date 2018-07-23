import discord
from datetime import datetime, timedelta
from discord.ext import commands
from string import ascii_lowercase
from itertools import chain, zip_longest
from random import choice
from math import log, log10, floor
from collections import defaultdict
from pprint import pprint
import os
import asyncio
import re
import datetime as dt
import time
UOT = 60
SCIFI = re.compile(r'^([^a-z]+)([A-Za-z]+)$')
LIFI = re.compile(r'^([0-9\.]+)[^0-9]+([0-9,]+)$')
TIME_SUCKER = re.compile(r'([0-9]+)([^0-9]+)?')
LETTERS = re.compile(r'^[hms]')
MAP = dict(w='weeks', d='days', h='hours', m='minutes', s='seconds')

def round_to_x(x, n):
    return round(x, -int(floor(log10(x))) + (n - 1))

def boss_hitpoints(level: int) -> int:
    return round(100000*pow(level, pow(level, .028))+.5)

def advance_start(level: int) -> float:
    return round(100*min(.003*pow(log(level+4),2.741), .9), 2)

def clan_damage(level: int) -> float:
    return round(pow(1.0233, level) + pow(level, 1.05), 2)

async def process_time(input_time: str) -> timedelta:
    match = TIME_SUCKER.findall(input_time)
    units = [
        MAP[getattr(LETTERS.match(m[1].strip()), 'string', None)
        or 'hms'[i]]
        for i, m
        in enumerate(match)
    ]
    measures = [int(x[0]) or 0 for x in match]
    return (timedelta(**{unit: measures[i] or 0 for i, unit in enumerate(units)}),
        {unit: measures[i] or 0 for i, unit in enumerate(units)})


def is_gm_or_admin():
    async def _is_gm_or_admin(ctx):
        msg = ctx.message
        roles = [r.id for r in msg.author.roles]
        g = await ctx.bot.cogs['Helpers'].get_record('server', msg.guild.id)
        is_admin = g.roles.get('admin') in roles
        is_owner = msg.author.id == msg.guild.owner_id
        is_gm = g.roles.get('grandmaster') in roles
        if is_admin or is_owner or is_gm:
            return True
        elif not g.roles.get('grandmaster'):
            await ctx.send('Ask your server admin to set the GM role')
        else:
            await ctx.send('Oof, you need to be a GM to do this.')
        return False
    return commands.check(_is_gm_or_admin)

def is_gm_or_master():
    async def _is_gm_or_master(ctx):
        m = ctx.message
        roles = [r.id for r in m.author.roles]
        g = await ctx.bot.cogs['Helpers'].get_record('server', m.guild.id)
        is_gm = g.roles.get('grandmaster') in roles
        is_master = g.tt.get('master') in roles
        if is_gm or is_master:
            return True
        elif not g.roles.get('grandmaster'):
            await ctx.send('Ask your server admin to set the GM role')
        else:
            await ctx.send('Oof, you need to be a GM or master to do this.')
        return False
    return commands.check(_is_gm_or_master)

def can_do_timers():
    async def _can_do_timers(ctx):
        m = ctx.message
        g = await ctx.bot.cogs['Helpers'].get_record('server', m.guild.id)
        roles = [a.id for a in m.author.roles]
        is_gm = g.roles.get('grandmaster') in roles
        is_master = g.tt.get('master') in roles
        is_timer = g.tt.get('timer') in roles
        if is_gm or is_master or is_timer:
            return True
        asyncio.ensure_future(ctx.send('You do not have the necessary permissions.'))
        return False
    return commands.check(_can_do_timers)

def tl_checks():
    async def _tl_checks(ctx):
        m = ctx.message
        g = await ctx.bot.cogs['Helpers'].get_record('server', m.guild.id)
        if not g.tt.get('tl_channel'):
            await ctx.send('The Gm or a master needs to set up a TL channel.\n'
                           '`e.tt setchannel tl #abc123`')
            return False
        elif not g.tt.get('cq_number'):
            await ctx.send('The Gm or a master should set the CQ number.\n'
                           'This is the cq of the _next_ TL, not the one that\n'
                           'was just killed.\n'
                           '`e.tt setcq 1589`')
            return False
        elif not g.tt.get('timer_text') or not g.tt.get('ping_text') or not g.tt.get('now_text'):
            await ctx.send(
                'The Gm or a master should set the timer texts.\n'
                'There are three separate texts to set. Alternatively,\n'
                'you can just to `e.tt settexts default`.\n'
                'The three commands are:\n'
                '`e.tt settext timer {TIME} until boss #{CQ} ({SPAWN} UTC)`\n'
                '`e.tt settext ping {TIME} until boss #{CQ} ({SPAWN} UTC) @everyone`\n'
                '`e.tt settext now BOSS #{CQ} SPAWNED @everyone!!!`\n')
            return False
        return True
    return commands.check(_tl_checks)

def when_check():
    async def _when_check(ctx):
        m = ctx.message
        g = await ctx.bot.cogs['Helpers'].get_record('server', m.guild.id)
        if not g.tt.get('when_channel'):
            await ctx.send('GM or master needs to set up the when channel.\n'
                           '`e.tt setchannel when #abc123`')
            return False
        return True
    return commands.check(_when_check)

class TapTitans():
    """docstring for TapTitans"""
    def __init__(self, bot):
        self.bot = bot
        self.helpers = self.bot.get_cog('Helpers')
        self.last_check = int(time.time())

    async def timer_check(self):
        while self is self.bot.get_cog('TapTitans'):
            if int(time.time()) - self.last_check >= 9.999998:
                asyncio.ensure_future(self.update_timers())
            await asyncio.sleep(9.999999)
    async def update_timers(self):
        guilds = [s for s in self.bot._servers if s.tt.get('next_boss')]
        await asyncio.gather(*[self.update_timer(guild) for guild in guilds])
    async def update_timer(self, guild):
        if isinstance(guild.tt.get('next_boss'), float) and guild.tt.get('boss_message'):
            g = self.bot.get_guild(int(guild.id))
            if g is not None:
                c = g.get_channel(guild.tt['tl_channel'])
            if c is None:
                return
            _next = guild.tt['next_boss']
            _now = datetime.utcnow().timestamp()
            _m,_s = divmod(_next-_now, 60)
            _h,_m = divmod(_m, 60)
            m = await c.get_message(guild.tt['boss_message'])
            final_ping = 0
            last_ping = guild.tt['last_ping']
            intervals = guild.tt.get('ping_intervals', [15,5,1])
            TIME, SPAWN, ROUND, CQ = (
                f'**{round(_h):02}:{round(_m):02}:{round(_s):02}**',
                (datetime.utcnow()+timedelta(hours=_h,minutes=_m,seconds=_s)).strftime('%I%p'),
                0,
                guild.tt['cq_number']
            )
            if _h >= 0 and last_ping < min([_next-i*60 for i in intervals]):
                result = guild.tt['timer_text'].format(
                    TIME=TIME, SPAWN=SPAWN, ROUND=ROUND, CQ=CQ
                )
            elif _h >= 0:
                result = guild.tt['ping_text'].format(
                    TIME=TIME, SPAWN=SPAWN, ROUND=ROUND, CQ=CQ
                )
            # elif not guild.tt['boss_message'] and _h < 0:
            #     avgttk = guild.tt.get('avgttk', 65)
            #     if _next + avgttk*60 < _now:
            #         #do after ping
            #     elif _now-last_ping >= 3600:
            #         # do round ping
            else:
                final_ping = 1
                result = guild.tt['now_text'].format(
                    TIME=TIME, SPAWN=SPAWN, ROUND=ROUND, CQ=CQ
                )
                guild.tt['cq_number'] += 1
                guild.tt['last_ping'] = _now
                asyncio.ensure_future(c.send(
                    content=result
                ))
                guild.tt['boss_message'] = 0
                guild.tt['when_message'] = 0
            # last_ping = guild.tt['last_ping']
            current = round(((_next-_now)/60)+.5)
            if guild.tt.get('when_channel') and guild.tt.get('when_message'):
                c = g.get_channel(guild.tt['when_channel'])
                m2 = await c.get_message(guild.tt['when_message'])
                if not final_ping:
                    asyncio.ensure_future(m2.edit(
                        content=guild.tt['timer_text'].format(
                            TIME=TIME, SPAWN=SPAWN, ROUND=ROUND, CQ=CQ
                        )
                    ))
                else:
                    asyncio.ensure_future(m2.edit('Boss spawned!'))
            
            did_ping = 0
            if not final_ping and not did_ping:
                for preping in intervals:
                    in_window = _next-preping*60<_now
                    passed_prev = last_ping < _next-preping*60

                    if in_window and passed_prev and _h>=0 and not did_ping:
                        guild.tt['last_ping'] = _now
                        result = guild.tt['ping_text'].format(
                            TIME=TIME, SPAWN=SPAWN, ROUND=ROUND, CQ=CQ
                        )
                        m = await c.send(result)
                        guild.tt['boss_message'] = m.id
                        did_ping = 1

            if not did_ping and not final_ping:
                asyncio.ensure_future(m.edit(
                    content = result
                ))

    # @when_check()
    # @commands.command(name='when')
    # async def when(self, ctx):
    #     g = await self.helpers.get_record('server', ctx.message.guild.id)
    #     if getattr(g['config'], 'boss_msg', None):
    #         c = ctx.message.guild.get_channel(g['config'].chan_when)
    #         _next = g['config'].next_boss
    #         _now = datetime.utcnow().timestamp()
    #         _m,_s = divmod(_next-_now, 60)
    #         _h,_m = divmod(_m, 60)
    #         _h, _m, _s = [max(0, round(x)) for x in (_h,_m,_s)]

    #         when_msg = await c.send(
    #             f'Titanlord arrives in **{_h:02}:{_m:02}:{_s:02}**'
    #         )
    #         setattr(g['config'], 'when_msg', when_msg.id)
    #     else:
    #         asyncio.ensure_future(ctx.send("Oops, there's no boss active rn."))

    @commands.group(pass_context=True, invoke_without_command=True, name="tt")
    async def tt(self, ctx):
        await ctx.send('TT2 commands')

    @is_gm_or_master()
    @tt.command(name='setchannel')
    async def _setchannel(self, ctx, kind, channel):
        """
        Allows you to set up a clan related channel for the bot.
        - the bot must have permission to send+edit+delete+pin messages
        Examples:
        ```
        e.tt setchannel tl #boss-timers
        e.tt setchannel when #clan-lounge
        e.tt setchannel paste #cq-exports
        e.tt setchannel report #weekly-update
        ```
        """
        if kind not in ['tl', 'when', 'paste', 'report']:
            await ctx.send('Channel kind must be one of: tl, when, paste, report')
        guild = ctx.message.guild
        if channel.startswith('#'):
            channel = channel[1:]
        if channel.isnumeric():
            channel = next((c.name for c in guild.channels if c.id == int(channel)), None)
        if channel:
            g = await self.helpers.get_record('server', ctx.message.guild.id)
            result = await self.helpers.choose_channel(ctx, ctx.message.guild, channel)
            if result:
                g.tt[f'{kind}_channel'] = result.id
                await ctx.send(f'Set the {kind} channel to {result.mention}!')

    @is_gm_or_master()
    @tt.command(name='settext', aliases=['setmessage', 'setmsg'])
    async def settext(self, ctx, kind):
        m = ctx.message
        a = m.author
        if a.bot:
            return
        if kind.lower() not in ['ping', 'now', 'timer', 'round', 'after']:
            await ctx.send('`kind` must be one of: `ping`, `now`, `timer`, `round`, `after`')
            return
        
        g = await self.helpers.get_record('server', m.guild.id)
        c = g.tt
        pfx = await self.bot.get_prefix(ctx.message)
        mc = m.content
        passed = 0
        while not passed:
            for p in pfx:
                if mc.startswith(p):
                    mc = mc[len(p):]
                    passed = 1
        mc = re.sub(r'^[^\s]+', '', mc).strip()
        mc = re.sub(r'^[^\s]+', '', mc).strip()
        mc = re.sub(r'^[^\s]+', '', mc).strip()
        g.tt[f'{kind.lower()}_text'] = mc
        e = await self.helpers.build_embed(mc, 0xffffff)
        asyncio.ensure_future(ctx.send(
            f'Set the {kind.lower()} text to:',
            embed=e))

    @is_gm_or_master()
    @tt.command(name='settz')
    async def settz(self, ctx, tz):
        """Sets the clan's timezone.\nCan be any **whole** digit, positive or negative,\n
        between -12 and 15.
        Examples:
        ```\n.tt settz +7\n.tt settz -10\n```
        """
        m = ctx.message
        g = await self.helpers.get_record('server', m.guild.id)
        a = m.author
        if a.bot:
            return
        if re.match(r'^[0-9-+]+$', tz):
            tz = int(tz)
            if 15 > round(tz-.5,0) > -13:
                g.tt['tz'] = tz
                if tz > 0:
                    tz = f'+{tz}'
                asyncio.ensure_future(ctx.send(f'Set the timezone to UTC{tz}.'))
                return

        asyncio.ensure_future(ctx.send('You did not supply a valid timezone setting.'))


    @is_gm_or_master()
    @tt.command(name='settexts')
    async def settexts(self, ctx):
        m = ctx.message
        a = m.author
        if a.bot:
            return
        chooser = await ctx.send(
            'This command will override any set (or unset) texts with the '
            'default values.\n'
            'Please type `confirm` or `cancel`.'
        )
        def check(m):
            return m.content.lower().strip() in ['confirm', 'cancel']
        try:
            msg = await self.bot.wait_for('message', check=check)
        except asyncio.TimeoutError as e:
            asyncio.ensure_future(chooser.delete())
            asyncio.ensure_future(msg.channel.send('Query timed out.'))
            return
        else:
            asyncio.ensure_future(chooser.delete())
            if 'onfir' in msg.content.lower():
                g = await self.helpers.get_record('server', m.guild.id)
                g.tt.update(dict(
                    timer_text='{TIME} until boss #{CQ} ({SPAWN} UTC)',
                    ping_text='{TIME} until boss #{CQ} ({SPAWN} UTC) @everyone',
                    now_text='BOSS #{CQ} SPAWNED @everyone!!!',
                    round_text='Ding! Time for round {ROUND}, @everyone',
                    after_text='Hey {TIMER}, set the timer and export CQ data!'
                ))
                # g.tt['timer_text'] = '{TIME} until boss #{CQ} ({SPAWN} UTC)'
                # g.tt['ping_text'] = '{TIME} until boss #{CQ} ({SPAWN} UTC) @everyone'
                # g.tt['now_text'] = 'BOSS #{CQ} SPAWNED @everyone!!!'
                # g.tt['round_text'] = 'Ding! Time for round {ROUND}, @everyone'
                # g.tt['after_text'] = 'Hey {TIMER}, set the timer and export CQ data!'
                asyncio.ensure_future(ctx.send(
                    ':ideograph_advantage: Set the texts to the defaults.'))
            elif 'ance' in msg.content.lower():
                asyncio.ensure_future(ctx.send(
                    'Action cancelled.'))

    @is_gm_or_admin()
    @tt.command(name='setrank')
    async def _setrank(self, ctx, rank, role):
        """
        Sets a discord role to an in-game clan rank.
        - you can specify a role by name or ID
        - emojis will be automatically converted to unicode
        Example:
        ```
        e.tt setrank timer :bell:
        ```
        """
        if rank not in ['master', 'knight', 'captain', 'recruit', 'guest',
            'vip', 'applicant', 'alumni', 'timer']:
            await ctx.send('The rank must be a valid name of an in-game role'
                ' or a tt2 related rank. You can choose from:\n```\nmaster,'
                ' knight, captain, recruit, guest, vip, applicant, alumni,'
                ' timer\n```')
            return
        guild = ctx.message.guild
        if role:
            if role.startswith('#'):
                role = role[1:]
            g = await self.helpers.get_record('server', ctx.message.guild.id)
            result =await self.helpers.choose_role(ctx, ctx.message.guild, role)
            if result:
                g.tt[rank] = result.id
                asyncio.ensure_future(self.helpers.try_mention(ctx, f'{rank} role', result))

    @can_do_timers()
    @tl_checks()
    @commands.group(name='tl', aliases=['boss', 'titanlord', 'setboss'], invoke_without_command=True)
    async def tl(self, ctx, *time):
        """
        Sets a timer running until the next titanlord spawn.
        - accepts most timestam formats\n- requires master or higher, or timer role set
        Examples:
        ```\n.tl dead\n.tl in 5h30m\n.tl 3:22:20\n```
        You can also set the boss by using the TTK, which is, IMO, much easier.
        ```\n.tl ttk 2m20s\n```
        """
        set_by_ttk, next_boss = False, None
        if time[0] == 'ttk':
            set_by_ttk = True
        if time[0] in ['in', 'now', 'dead', 'ttk']:
            guild = ctx.message.guild
            g = await self.helpers.get_record('server', ctx.message.guild.id)
            if time[0] == 'dead':
                time = '6h'
            elif time[0] == 'now':
                time='0s'
                result = g.tt['now_text'].format(
                    CQ=g.tt.get('cq_number',1)
                )
                c = guild.get_channel(g.tt['tl_channel'])
                _now = datetime.utcnow().timestamp()
                g.tt['next_boss'] = _now
                g.tt['cq_number'] += 1
                g.tt['last_ping'] = _now
                asyncio.ensure_future(c.send(
                    content=result
                ))
                g.tt['boss_message'] = 0
                g.tt['when_message'] = 0
                return
            else:
                time = ' '.join(time[1:]).strip()
            _next, _units = await process_time(time)
            now = datetime.utcnow()
            g.tt['last_ping'] = now.timestamp()
            # print(_next.total_seconds())
            if not set_by_ttk:
                next_boss = now.timestamp()+_next.total_seconds()
                res = ':ideograph_advantage: Set a timer running for **{}**'.format(
                    ', '.join(f'{v} {k}' for k, v in _units.items())
                )
            elif g.tt.get('next_boss') and set_by_ttk:
                next_boss = g.tt['next_boss']+_next.total_seconds()+21605
                ts = next_boss-now.timestamp()
                
                _m,_s = divmod(ts, 60)
                _h,_m = divmod(_m, 60)
                res = ':ideograph_advantage: Set a timer for {:02} hours, {:02} minutes, {:02} seconds.'.format(
                    round(_h), round(_m), round(_s)
                )
            elif set_by_ttk and not g.tt.get('next_boss'):
                asyncio.ensure_future(ctx.send('Oops, you cannot set by TTK until'
                    ' a boss has spawned beforehand.'))
                return

            if g.tt.get('next_boss'):
                icon = 'https://i.imgur.com/{}.png'.format(choice([
                    '2Zep8pE', 'Y8OWqXd', 'r7i7rlR', 'VLjcRBe', 'TBZAL4A',
                    'eYtmbjg', 'Y6jfEhM']))
                c_dmg = round_to_x(clan_damage(g.tt['cq_number']-1)*100,3)
                c_adv = advance_start(g.tt['cq_number']-1)
                c_hp = boss_hitpoints(g.tt['cq_number']-1)

                c_offset = g.tt.get('tz', 0)
                c_spawn = datetime.fromtimestamp(next_boss+(c_offset*60*60))
                # print(c_spawn)
                if c_offset > 0:
                    c_offset = f'+{c_offset}'
                c_spawn = c_spawn.strftime('%H:%M:%S UTC{}').format(c_offset or '')
                field1 = f'Adv. start is **{c_adv}%** & damage bonus is **{c_dmg}%**.'
                field2 = f'Spawns at **{c_spawn}** with **{c_hp:,}** hitpoints.'
                e = await self.helpers.full_embed(
                    "Killed in {}", thumbnail=icon,
                    fields={
                        'Bonuses':field1,
                        'Next Boss':field2 
                    },
                    author=dict(name=f'Boss #{g.tt["cq_number"]-1}',
                                image=icon)
                )
                await guild.get_channel(g.tt['tl_channel']).send(embed=e)

            g.tt['next_boss'] = next_boss
            await guild.get_channel(g.tt['tl_channel']).send(res)
            boss_msg = await guild.get_channel(g.tt['tl_channel']).send(
                f'**{_next}** until boss arrives'
            )
            g.tt['boss_message'] = boss_msg.id

    @is_gm_or_master()
    @tt.command(name='setcq')
    async def setcq(self, ctx, cq):
        """
        Allows you to set the clan's current quest level _of the next boss_.
        Requires: GM or Master ranks
        Example:
        ```
        .tt setcq 1580
        ```
        """
        if not cq.isnumeric():
            asyncio.ensure_future(ctx.send(
                'You must supply a valid numerical value for the cq number.'))
        else:
            g = await self.helpers.get_record('server', ctx.message.guild.id)
            g.tt['cq_number'] = int(cq)
            asyncio.ensure_future(ctx.send(
                f':ideograph_advantage: Updated the CQ number to `{cq}`!'))
    
    # @is_gm_or_master()
    # @tt.command(name='report')
    # async def _report(self, ctx):
    #     TD = dt.date.today()
    #     TD = datetime(TD.year, TD.month, TD.day, 0, 0)
    #     this_monday = TD + timedelta(days=-TD.weekday())
    #     last_monday = TD + timedelta(days=-TD.weekday(), weeks=-1)
    #     g = await self.helpers.get_record('server', ctx.message.guild.id)
    #     c = getattr(g['config'], 'chan_paste', None)
    #     print(c)
    #     if c:
    #         c = ctx.message.guild.get_channel(c)
    #         messages = await c.history(limit=100).flatten()
    #         result = [m for m in messages]
    #         cqs = [int(re.match(r'```CQ (\d+)', r.content).group(1))
    #                for r in result
    #                if re.match(r'```CQ \d+', r.content)
    #                and r.created_at > last_monday
    #                and r.created_at < this_monday]
    #         result = [r.content.split('\n')
    #                   for r in result
    #                   if r.content.startswith('```')
    #                   and r.created_at > last_monday
    #                   and r.created_at < this_monday]
    #         result = [[
    #             s.replace('```','').split(',') for s in r
    #             if len(s.split(','))==4
    #             and not s.startswith('```')
    #             and s.split(',')[0].isnumeric()
    #         ] for r in result]

    #         headers = ['rank', 'name', 'id', 'damage']
    #         started, ended, total = min(cqs), max(cqs), len(result)
    #         missed = ended - started - total
    #         all_hits = list(chain.from_iterable(result))
    #         #pprint(all_hits)
    #         result = defaultdict(lambda: dict(
    #             id='', name='', hit=0, dmg=0, atd=0
    #         ))
    #         for hit in all_hits:
    #             id = hit[2]
    #             if not result[id]['id']:
    #                 result[id]['id']=id
    #             if int(hit[3])>0:
    #                 result[id]['hit'] += 1
    #                 result[id]['dmg'] += int(hit[3])
    #             if not result[id]['name']:
    #                 u = next((x['id'] for x in self.bot._users
    #                           if getattr(x['config'], 'tt_code', None)==hit[2]), hit[1])
    #                 if isinstance(u, int):
    #                     u = ctx.guild.get_member(u)
    #                     if u:
    #                         u = u.mention
    #                     result[id]['name']=u
    #                 else:
    #                     result[id]['name']=hit[1]
    #         final = []
    #         for id, data in result.items():
    #             result[id]['atd'] = round((result[id]['hit']+missed)/total*100)
    #             final.append(result[id])
    #         final = sorted(final, key=lambda x: x['atd'], reverse=True)
    #         # row = "{:<26} {:<8} {:<8}"
    #         # pprint(final[0:5])
    #         # content1='\n'.join(
    #         #     row.format(
    #         #         r['name'], f"{round(r['atd'],0)}%",
    #         #         self.helpers.human_format(r['dmg'])
    #         #     ) for r in final[0:25]
    #         # )
    #         # content2='\n'.join(
    #         #     row.format(
    #         #         r['name'], f"{round(r['atd'],0)}%",
    #         #         self.helpers.human_format(r['dmg'])
    #         #     ) for r in final[26:]
    #         # )#10: 62% (598.20M)
    #         # e1 = await self.helpers.build_embed(content1, 0xffffff)
    #         # e2 = await self.helpers.build_embed(content2, 0xffffff)
    #         colours = [0x146B3A, 0xF8B229, 0xEA4630, 0xBB2528]
    #         started_at = 0
    #         report_to = c = getattr(g['config'], 'chan_report', None)
    #         if report_to:
    #             report_to = ctx.message.guild.get_channel(report_to)
    #             for chunk in self.helpers.chunker(final, 21):
    #                 e3 = await self.helpers.build_embed(f'Attendance report part {started_at+1}.',
    #                     colours[started_at])
    #                 for i,r in enumerate(chunk):
    #                     name = f'#{started_at*18+i+1}: {r["atd"]}% ({self.helpers.human_format(r["dmg"])})'
    #                     e3.add_field(
    #                         name=f'{name:<24}',
    #                         value=r['name'], inline=True)
    #                 asyncio.ensure_future(report_to.send(embed=e3))
    #                 started_at+=1


    @is_gm_or_master()
    @tt.command(name='setinterval', aliases=['setintervals'])
    async def setinterval(self, ctx):
        """
        Set the intevral for when the timer will ping users. IN MINUTES.
        Requires: GM or Master ranks.
        Example:
        ```
        .tt setinterval 60 15 5 2 1
        .tt setinterval 15,2,1
        ```
        """
        pfx = await self.bot.get_prefix(ctx.message)
        mc = ctx.message.clean_content
        passed = 0
        while not passed:
            for p in pfx:
                if mc.startswith(p):
                    mc = mc[len(p):]
                    passed = 1
        mc = mc[len(ctx.command.name):].strip()
        rs = [int(i) for i in re.findall(r'\d+', mc)]
        g = await self.helpers.get_record('server', ctx.message.guild.id)
        g.tt['ping_intervals'] = rs
        await ctx.send(':ideograph_advantage: Ping intervals set to: {}'.format(
            ', '.join([f'`{x}`' for x in rs])
        ))


    @is_gm_or_master()
    @tl_checks()
    @tl.command(name='clear', aliases=['wipe'])
    async def _clear(self, ctx):
        g = await self.helpers.get_record('server', ctx.message.guild.id)
        g.tt['next_boss'] = 0
        g.tt['boss_message'] = 0
        g.tt['when_message'] = 0
        asyncio.ensure_future(ctx.send(
            ':ideograph_advantage: Cleared the boss timer!'))

    @commands.command(name='claim')
    async def _claim(self, ctx, key, value):
        """
        Sets a support code tied to your discord ID.
        - does not currently support DMs
        - autodeletes when you do it
        Example:
        ```
        e.claim supportcode abc123
        ```
        """
        if not key in ['sc','supportcode','cc','clancode']:
            return
        a = ctx.message.author
        g = ctx.message.guild
        
        if key.startswith('s') and not a.bot:
            if not isinstance(ctx.message.channel, discord.abc.PrivateChannel):
                await ctx.message.delete()
            if a:
                used = next((x for x in self.bot._users
                             if x.tt.get('code') == value.strip()), None)
                # print(used)
                if used:
                    await ctx.send(
                        'Sorry, somebody already used that code.\n'
                        'If it was not you, do the verify command.\n'
                        'Example: `e.verify supportcode abc123`')
                    return 
                g = await self.bot.cogs['Helpers'].get_record('user', a.id)
                if not g.tt.get('code'):
                    g.tt['code'] = value.strip()
                    await ctx.send(f'Set the support code for the user {a.name}#'
                                   f'{a.discriminator}.')
                else:
                    await ctx.send('You have already claimed a code. Please use'
                                   ' `verify` if you would like to change it.\n'
                                   'Example: `e.verify supportcode abc123')


    # @tt.command(pass_context=True, name='convert', alias=["notation"])
    # async def _convert(self, ctx, kind: str='sci', val: str='1e+5000'):
    #     if kind.startswith('l'):
            
    #         number, letter = SCIFI.findall(val.strip())[0]
    #         map_to_alpha = [ascii_lowercase.index(x) for x in letter.lower()]
    #         a_to_one = [x+1 for x in map_to_alpha[:-2]]+map_to_alpha[-2:]
    #         dict_map = dict(enumerate(a_to_one))
    #         map_to_alpha = [pow(26, x) for x in  list(dict_map.keys())[::-1]]
    #         result = sum([x*a_to_one[i] for i, x in enumerate(map_to_alpha)])
    #         result = '{}e{:,}'.format(number, result*3)
    #     else:
    #         number, notation = LIFI.findall(val.strip())[0]
    #         notation = int(notation.replace(',',''))
    #         modulo = notation % 3
    #         exponent = notation / 3
    #         output = []
    #         while exponent > 26:
    #             result, remainder = divmod(exponent, 26)
    #             output.append(remainder)
    #             exponent = result
    #         output.append(exponent)
    #         multiple = pow(10, modulo)
    #         l = len(output)
    #         if l > 2:
    #             output = [x for x in output[:-(l-2)]]+[max(x-1, 0) for x in output[-(l-2):]]
    #         last_result = ''.join([ascii_lowercase[int(last)] for last in output[::-1]])
    #         result = '{}{}'.format(number*multiple, last_result)
    #     flip = {'s': 'letter', 'l': 'scientific'}
    #     await ctx.send(f'Conversion of {val} from {kind} to {flip[kind[0].lower()]} is **{result}**')
    
def setup(bot):
    cog = TapTitans(bot)
    loop = asyncio.get_event_loop()
    loop.create_task(cog.timer_check())
    bot.add_cog(cog)
