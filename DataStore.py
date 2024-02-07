import asyncio
import datetime
import importlib

from fastapi import HTTPException

from RequestObject import AddExRequest, SetExStatusRequest, SetMartinRequest, SetTrendRequest
import StatisticsDao
from typing import Dict, Iterable, List
import schedule
from Controller import Controller
import ExchangeDao 
from OrderInfoDao import OrderInfoDB, OrderInfoDB_Insert, OrderInfoDB_Query_All, OrderInfoDB_Update
from StrategyOrderDao import StrategyOrder
import StrategyOrderDao
from sdk.BinanceSdk import BinanceSdk
from sdk.BitgetSdk import BitgetSdk
from sdk.OkxSdk import OkxSdk
from sdk.OrderClass import AccountInfo, SwapPostion
import aiomysql
import json
import os
import sys
from log import logger
ex_list: List[ExchangeDao.ExchangeDb] = []
controller_list: Dict[int, Controller] = {}

spot_positions: Dict[int, List[AccountInfo]] = {}
swap_positions: Dict[int, List[SwapPostion]] = {}
swap_account: Dict[int, AccountInfo] = {}
spot_account:Dict[int,AccountInfo]={}
strategy_orders:List[StrategyOrder]=[]

order_info:Dict[int,List[OrderInfoDB]]={}
json_conf:dict={}


async def create_pool():
    global db_pool
    db_pool= await aiomysql.create_pool(
        host=json_conf['DB']['DB_HOST'],
        port=json_conf['DB']['DB_PORT'],
        user=json_conf['DB']['DB_USER'],
        password=json_conf['DB']['DB_PASS'],
        db=json_conf['DB']['DB_NAME'],
        autocommit=True,
        minsize=5,
        maxsize=10,
        echo=True,
        pool_recycle=3,
        loop=asyncio.get_event_loop()
    )

def write_json_conf():
    file_path = "conf.json"
    with open(file_path, "w", encoding="utf-8") as json_file:
        json.dump(json_conf, json_file,ensure_ascii=False, indent=4)

async def add_ex(data:AddExRequest):
    try:
        name = f"{data.ex.lower().capitalize()}Controller"
        module = importlib.import_module(name)
        class_ = getattr(module, name)
        db=ExchangeDao.ExchangeDb(ex=data.ex,account=data.account,apikey=data.apikey,api_secret=data.api_secret,api_password=data.api_password)
        await ExchangeDao.insert(db)
        instance = class_(db)
        ex_list.append(db)
        controller_list[db.id] = instance
        spot_positions[db.id]=[]
        swap_positions[db.id]=[]
        swap_account[db.id]=AccountInfo()
        spot_account[db.id]=AccountInfo()
        order_info[db.id]=[]
        await instance.init()
        return db
    except Exception as e:
        from HttpListener import Status
        raise HTTPException(status_code=Status.ParamsError.value,
                                detail=f"Error: Class {data.ex} not found in module")  

async def set_ex_status(data:SetExStatusRequest):
    try:
        if  data.id in controller_list:
            controller_list[data.id].cancel_job()
            del controller_list[data.id]
            del spot_positions[data.id]
            del swap_positions[data.id]
            del swap_account[data.id]
            del spot_account[data.id]
            del order_info[data.id]
        if data.status==2:
            return await ExchangeDao.del_physical(data.id)
        elif data.status==1:
            return await ExchangeDao.delete_soft(data.id)
        else:
            try:
                all=ExchangeDao.exchange_db_query(True)
                dbfind=[a for a in all if a.id==data.id]
                if len(db)>0:
                    db=dbfind[0]
                    ExchangeDao.restore(db.id)
                    name = f"{db.ex.lower().capitalize()}Controller"
                    module = importlib.import_module(name)
                    class_ = getattr(module, name)
                    instance = class_(db)
                    ex_list.append(db)
                    controller_list[db.id] = instance
                    spot_positions[db.id]=[]
                    swap_positions[db.id]=[]
                    swap_account[db.id]=AccountInfo()
                    spot_account[db.id]=AccountInfo()
                    order_info[db.id]=[]
                    await instance.init()
                    return db
                else:
                    from HttpListener import Status
                    raise HTTPException(status_code=Status.ParamsError.value,
                                detail=f"exchange_info表里查不到相关id={data.id}的信息")     
            except  Exception as e:
                from HttpListener import Status
                raise HTTPException(status_code=Status.ParamsError.value,
                                detail=f"恢复交易所状态错误 err={e}")   
    except Exception as e:
        from HttpListener import Status
        raise HTTPException(status_code=Status.ParamsError.value,
                                detail=f"设置交易所状态信息错误 err={e}")

def update_martin_setting(data:SetMartinRequest):
    if data.use_ratio:
        json_conf['Martin']['HUOXING_INVEST_USE_RATIO']=data.use_ratio
        import math
        json_conf['Martin']['HUOXING_RATIO_INVEST']=math.fabs(data.ratio)
    else:
        if len(data.fixed)==4:
            json_conf['Martin']['HUOXING_FIXED_INVERST']=data.fixed
            json_conf['Martin']['HUOXING_INVEST_USE_RATIO']=data.use_ratio
        else:
            logger.error('设置马丁的固定投入金额数组长度不为4')
            from HttpListener import Status
            raise HTTPException(status_code=Status.ParamsError.value,
                                detail='设置马丁的固定投入金额数组长度不为4')
    json_conf['Martin']['MAX_HUOXING_COUNT']=data.max_count
    json_conf['Martin']['HUOXING_EXCEPT_NUM']=data.except_num 
    write_json_conf()

def update_trend_setting(data:SetTrendRequest):
    
    json_conf['Trend']['TREND_RATIO_INVEST'] =data.use_ratio
    json_conf['Trend']['TREND_TP_RATIO'] =data.tp
    if data.use_ratio:
        json_conf['Trend']['TREND_RATIO_INVEST'] =data.num 
    else:    
        json_conf['Trend']['TREND_FIXED_INVEST'] =data.num

    write_json_conf()

async def init():
    global ex_list,order_info,json_conf
    current_dir = os.path.dirname(os.path.realpath(__file__))
    conf_file_path = os.path.join(current_dir, 'conf.json')
    try:
        with open(conf_file_path, 'r', encoding="utf-8") as file:
            json_conf = json.load(file)
    except Exception as e:
        print(f"读取配置文件错误,程序退出 err={e}")
        sys.exit(1)
        
    await create_pool()           
    ex_list = await ExchangeDao.exchange_db_query()
    order_info_list = await OrderInfoDB_Query_All()
    for i in ex_list:
        order_info[i.id]=[]
    for info in order_info_list:
        order_info[info.exId].append(info)
    schedule.every().hour.at(":00").do(lambda:asyncio.create_task(every20minTask()))
    schedule.every().hour.at(":20").do(lambda:asyncio.create_task(every20minTask()))
    schedule.every().hour.at(":40").do(lambda:asyncio.create_task(every20minTask()))
    schedule.every(2).hours.do(lambda:asyncio.create_task(OkxSdk.request_baseinfo()))
    schedule.every(2).hours.do(lambda: asyncio.create_task(BinanceSdk.request_baseinfo()))
    schedule.every(2).hours.do(lambda: asyncio.create_task(BitgetSdk.request_baseinfo()))
    await asyncio.gather(
        BinanceSdk.request_baseinfo(),
        BitgetSdk.request_baseinfo(),
        OkxSdk.request_baseinfo()
    )
    
async def every20minTask():
    l=[]
    today = datetime.datetime.now()
    if today.second!=0 or today.minute%20!=0:
        return
    total=0
    for id,acc in swap_account.items():
        db=StatisticsDao.TradingStatistics()
        db.datetime=today
        db.money=acc.total
        if id in spot_account:
            db.money+=spot_account[id].unrealizedPL+spot_account[id].total
        db.exId=id
        l.append(db)
        total+=db.money
    db=StatisticsDao.TradingStatistics()
    db.money=total
    db.exId=0
    db.datetime=today
    l.append(db)
    await StatisticsDao.insert(l)

def getController(id: int):
    return controller_list.get(id, None)

def insertStrategyOrder(so:StrategyOrderDao):
    strategy_orders.append(so)
def delStrategyOrderById(id:int):
    result=next(filter(lambda item: item.id == id, strategy_orders), None)
    if result:
        result.deleted=True
        strategy_orders.remove(result)
        StrategyOrderDao.update_strategy_order(result)
async def insert_orderinfo(data: OrderInfoDB):
    await OrderInfoDB_Insert(data)
    order_info[data.exId].append(data)


async def update_orderinfo(data):
    if isinstance(data, OrderInfoDB):
        await OrderInfoDB_Update(data)
    elif isinstance(data, Iterable):
        for d in data:
            await OrderInfoDB_Update(d)


async def del_orderinfo(data):
    if isinstance(data, OrderInfoDB):
        data.delete = True
        order_info[data.exId].remove(data)
        await OrderInfoDB_Update(data)
    elif isinstance(data, Iterable):
        for d in data:
            d.delete = True
            order_info[d.exId].remove(d)
            await OrderInfoDB_Update(d)

