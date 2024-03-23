from telethon.sync import TelegramClient, events
import DataStore
import telethon
import datetime
import StatisticsDao
import matplotlib.pyplot as plt
import matplotlib
from io import BytesIO
import asyncio
import calendar
matplotlib.use('Agg')


__username: str = None
__client: TelegramClient = None


async def start():
    global __client
    if len(DataStore.json_conf['TG']['TG_API_ID'])>0 and len(DataStore.json_conf['TG']['TG_TOKEN'])>0 and \
        len(DataStore.json_conf['TG']['TG_API_HASH'])>0:
        __client = TelegramClient('bot_session', DataStore.json_conf['TG']['TG_API_ID'], DataStore.json_conf['TG']['TG_API_HASH'])

        await start_tg_client(DataStore.json_conf['TG']['TG_TOKEN'])


async def send_err_msg(msg):
    if DataStore.json_conf['TG']['CHAT_ID']!=0 and DataStore.json_conf['TG_report_err']:
        await __client.send_message(DataStore.json_conf['TG']['CHAT_ID'], msg)

async def send_open_msg(msg):
    if DataStore.json_conf['TG']['CHAT_ID']!=0 and DataStore.json_conf['TG_report_open']:
        await __client.send_message(DataStore.json_conf['TG']['CHAT_ID'], msg)

async def send_close_msg(msg):
    if DataStore.json_conf['TG']['CHAT_ID']!=0 and DataStore.json_conf['TG_report_close']:
        await __client.send_message(DataStore.json_conf['TG']['CHAT_ID'], msg)        

async def start_tg_client(token):
    global __username
    await __client.start(bot_token=token)
    me = await __client.get_me()
    __username = me.username
    __client.add_event_handler(handle_text_command, events.NewMessage)
    try:
        await __client.run_until_disconnected()
    except:
        await asyncio.sleep(3)
        asyncio.create_task(start_tg_client(token))


async def handle_text_command(event: telethon.events.newmessage.NewMessage.Event):
    if event.message is not None:
        msg = event.message.message
        if msg.startswith('/'):
            text = msg[1:]
            command = ""
            msg = ""
            user = f'@{__username}'
            if user in text:
                strlist = text.split(user)
                command = strlist[0]
                if len(strlist) > 1:
                    msg = strlist[1]
            else:
                strlist = text.split(' ', 1)
                command = strlist[0]
                if len(strlist) > 1:
                    msg = strlist[1]
            if command == 'day':
                await handle_day_command(msg, event)
            elif command == 'month':
                await handle_month_command(msg, event)
            elif command == 'range':
                await handle_range_command(msg, event)
            elif command == 'info':
                await handle_position_command(msg, event)
            elif command == 'close_tv_pos':
                await handle_close_tv_pos_command(msg,event)     
            elif command == 'set_lever':
                await handle_set_lever_command(msg,event)

async def handle_day_command(msg, event):
   
        total = 0
        for id, acc in DataStore.swap_account.items():
            total = total+acc.total
        for id, acc in DataStore.spot_account.items():
            if DataStore.controller_list[id].exdata.ex == 'nexo':
                total += acc.unrealizedPL
            else:    
                total = total+acc.total+acc.unrealizedPL+acc.funding  
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        await event.respond(f"{today}总金额为{total:.2f}")


async def handle_month_command(msg, event):
    data_list = None
    if len(msg) == 0:
        start_month = datetime.datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_month = calendar.monthrange(start_month.year, start_month.month)[1]
        end_month=start_month.replace(day=last_day_of_month, hour=23, minute=59, second=59, microsecond=999999)
        data_list = await StatisticsDao.query_total_by_range([0],start_month,end_month)
    else:
        try:
            start_month = datetime.datetime.strptime(msg, '%Y-%m').replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_day_of_month = calendar.monthrange(start_month.year, start_month.month)[1]
            end_month=start_month.replace(day=last_day_of_month, hour=23, minute=59, second=59, microsecond=999999)
            data_list = await StatisticsDao.query_total_by_range([0],start_month,end_month)
        except:
            await event.respond("格式错误解析失败 日期格式应为/month 2023-09")
            return
    if data_list is None or len(data_list) == 0:
        await event.respond(f"{msg}未查到当月数据")
        return
    time_values = [d.datetime for d in data_list]
    values = [d.money for d in data_list]

    plt.plot(time_values, values, marker='o')
    plt.title('plot')
    plt.xlabel('time')
    plt.ylabel('money')
    # 保存曲线图到内存中
    img_buffer = BytesIO()
    img_buffer.name = 'image.png'
    plt.savefig(img_buffer, format='png')
    img_buffer.seek(0)
    await event.respond(file=img_buffer)


async def handle_range_command(msg, event):
    strlist = msg.split(' ', 1)
    try:
        start_month = datetime.datetime.strptime(strlist[0], '%Y-%m').replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_month = datetime.datetime.strptime(strlist[1], '%Y-%m')
        last_day_of_month = calendar.monthrange(end_month.year, end_month.month)[1]
        end_month=end_month.replace(day=last_day_of_month, hour=23, minute=59, second=59, microsecond=999999)
        data_list = await StatisticsDao.query_total_by_range([0],start_month, end_month)
        if len(data_list) == 0:
            await event.respond(f"未查到{msg}的数据")
            return
        time_values = [d.datetime for d in data_list]
        values = [d.money for d in data_list]
        plt.figure(figsize=(8, 6))
        plt.plot(time_values, values, marker='o')
        plt.title('plot')
        plt.xlabel('time')
        plt.ylabel('money')

        # 保存曲线图到内存中
        img_buffer = BytesIO()
        img_buffer.name = 'image.png'
        plt.savefig(img_buffer, format='png')
        img_buffer.seek(0)
     
        await event.respond(file=img_buffer)
    except Exception as e:
        await event.respond(f"格式错误解析失败 日期格式应为/range 2023-08 2023-09 error={e}")


async def handle_position_command(msg, event):
    msg = ""
    for ex in DataStore.ex_list:
        id = ex.id
        total=0
        if id in DataStore.swap_account:
            if ex.ex=='nexo':
                total=DataStore.swap_account[id].total+DataStore.spot_account[id].funding
            else:
                total=DataStore.swap_account[id].total+DataStore.spot_account[id].funding+DataStore.spot_account[id].total
        msg += f"{ex.ex} {ex.account} 详情：总资产:{total:.2f}\n"
        msg += "现货持仓:\n"
        if id in DataStore.spot_positions:
            for spot in DataStore.spot_positions[id]:
                msg += f"{spot.symbol} 总额:{spot.total:.4f} 可用:{spot.available:.4f}\n"
        msg += "合约持仓:\n"
        if id in DataStore.swap_positions:
            for swap in DataStore.swap_positions[id]:
                msg += f"{swap.symbol} 方向:{swap.posSide} 持仓模式:{swap.marginMode} 杠杆:{swap.leverage} 均价:{swap.priceAvg:.4f} 仓位:{swap.size} 未盈利:{swap.upl:.4f}\n"
        msg += '\n'
    if len(msg) > 0:
        await event.respond(msg)
    else:
        await event.respond("暂无任何信息")

async def handle_close_tv_pos_command(msg,event):
    strlist=msg.split(' ')
    symbol=''
    posSide=''
    try:
        symbol=strlist[0]
        posSide=strlist[1]
    except Exception as e:
        await event.respond(f"close_tv_pos 错误 指令为/close_tv_pos btc short, err={e}")
        return  
    for i,v in DataStore.controller_list.items():
            await v.close_swap_by_pos(symbol,posSide)
    await  event.respond(f"close_tv_pos {symbol} {posSide} 完成")  
    

async def handle_set_lever_command(msg,event):
    try:
        strlist=msg.split(' ')
        if len(strlist)==2:
            ex=strlist[0]
            lv= int(strlist[1])
            for i,v in DataStore.controller_list.items():
                if v.exdata.ex==ex:
                    await v.setlever('',lv)
        elif len(strlist)==3:    
            ex=strlist[0]
            symbol=strlist[1]
            lv= int(strlist[2])
            for i,v in DataStore.controller_list.items():
                if v.exdata.ex==ex:
                    await v.setlever(symbol,lv)
        else:
            await event.respond(f"set_lever 错误 指令为/set_lever binance 10或则 /set_lever binance btc 10")
            return          
        await event.respond("set_lever 完成")        
    except Exception as e:
        await event.respond(f"set_lever 错误 指令为/set_lever binance 10或则 /set_lever binance btc 10, err={e}")
