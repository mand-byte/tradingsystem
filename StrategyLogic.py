

import datetime

import DataStore
from StrategyOrderDao import StrategyOrder, insert_strategy_order


async def MakeStrategyOrder(data):
    so=StrategyOrder()
    so.condition1=data.condition1
    so.condition2=data.condition2
    so.condition1status=0
    so.opentime=datetime.datetime.now()
    so.exids=data.exids
    so.isswap=data.isswap
    so.posSide=data.posSide
    so.symbol=data.symbol
    so.sl=data.sl
    so.tp=data.tp
    so.money=data.money
    so.deleted=False
    so.endtime=data.endtime
    result=await insert_strategy_order(so)
    if result:
        DataStore.insertStrategyOrder(so)
        return so
    else:
        return result

def CancelStrategyOrder(id:int):
    DataStore.delStrategyOrderById(id)



