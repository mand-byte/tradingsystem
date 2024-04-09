import asyncio
import math
from typing import Dict
from fastapi import HTTPException
import schedule
from HttpListener import Status
from log import logger
from Controller import Controller
from ExchangeDao import ExchangeDb
from OrderInfoDao import OrderInfoDB
from sdk.OkxSdk import OkxSdk
from sdk.OrderClass import AccountInfo, OrderInfo
import utils
import DataStore
import Const
import TGBot
import MovingAssetDao
from MovingAssetDao import MovingAssetDB
import datetime


class OkxController(Controller):
    def __init__(self, exdata: ExchangeDb) -> None:
        super().__init__(exdata)
        self.sdk = OkxSdk(
            exdata.apikey, exdata.api_secret, exdata.api_password)
        self.exdata = exdata
        self.job = None
        self.check_profit = False
        self.movingData: MovingAssetDB = None

    async def init(self):
        self.movingData = await MovingAssetDao.MovingAssetDB_query(self.exdata.id)
        await self.sdk.init()
        await self.every_min_task()

        self.job = schedule.every(DataStore.json_conf['DATA_REFRESH_TIME']).seconds.do(
            lambda: asyncio.create_task(self.every_min_task()))

    def cancel_job(self):
        schedule.cancel_job(self.job)

    def update_orderdb(self, u_set: set[OrderInfoDB], d_set: set[OrderInfoDB], info: OrderInfoDB, result: OrderInfo):
        need_update = False
        if info.leverage != result.leverage:
            info.leverage = result.leverage
            need_update = True
        if info.openTime != result.openTime:
            info.openTime = result.openTime
            need_update = True
        if info.priceAvg != result.priceAvg and result.priceAvg != 0:
            info.priceAvg = result.priceAvg
            need_update = True
        if info.marginMode != result.marginMode:
            info.marginMode = result.marginMode
            need_update = True
        if info.status != result.status:
            info.status = result.status
            need_update = True
        if info.size_exec != result.size:
            info.size_exec = result.size
            need_update = True
        if info.status < 0 and info not in d_set:
            d_set.add(info)
        elif info not in u_set and need_update:
            u_set.add(info)

    async def every_min_task(self):
        swap_list = await self.sdk.request_swap_positions()
        if isinstance(swap_list, list):
            DataStore.swap_positions[self.exdata.id] = swap_list

        swap_account = await self.sdk.request_swap_account()
        swap_acc = DataStore.swap_account[self.exdata.id]
        spot_acc = DataStore.spot_account[self.exdata.id]
        if not isinstance(swap_account, str):
            swap_acc.available = swap_account[0].available
            swap_acc.symbol = swap_account[0].symbol
            swap_acc.total = swap_account[0].total
            swap_acc.unrealizedPL = swap_account[0].unrealizedPL
            DataStore.spot_positions[self.exdata.id] = swap_account[1]
            spot_total = sum(spot.unrealizedPL for spot in swap_account[1])
            spot_acc.unrealizedPL = spot_total

        saving = await self.sdk.get_saving_funding()
        if isinstance(saving, float):
            spot_acc.funding = saving
        balance = await self.sdk.get_asset_balance()
        if isinstance(saving, float):
            spot_acc.funding += balance
        del_list: set = set()
        update_list: set = set()
        swap_subpos: Dict[str:Dict[str:str]] = {}
        spot_subpos: Dict[str:Dict[str:str]] = {}

        del_subpos: Dict[str:list[str]] = {}
        for ord in DataStore.order_info[self.exdata.id]:
            if ord.isswap:
                server_info = await self.sdk.query_swap_order_info(ord.symbol, ord.orderId)
                if not isinstance(server_info, str):
                    self.update_orderdb(
                        update_list, del_list, ord, server_info)
                if ord.status == Const.ORDER_STATUS_FILLED:
                    if self.sdk.swap_copytrader:
                        subpos = None
                        if ord.symbol not in swap_subpos:
                            subpos = await self.sdk.request_swap_subpositions(ord.symbol)
                            if not isinstance(subpos, str):
                                lis = {i.orderId: i.subPosId for i in subpos}
                                swap_subpos[ord.symbol] = lis
                        if len(ord.subPosId) == 0 and ord.symbol in swap_subpos and ord.orderId in swap_subpos[ord.symbol]:
                            ord.subPosId = swap_subpos[ord.symbol][ord.orderId]
                            update_list.add(ord)
                        if ord.sltp_status == Const.SLTP_STATUS_READY:
                            # 设置带单的止盈止损
                            result = await self.sdk.set_sltp_by_copytrader(ord.subPosId, ord.sl, ord.tp)
                            if not isinstance(result, str):
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                update_list.add(ord)
                        # 如果没有subposId 说明订单已经平掉
                        if (ord.symbol in swap_subpos and ord.symbol in swap_subpos and ord.orderId not in swap_subpos[ord.symbol]) or (ord.symbol not in swap_subpos and not isinstance(subpos, str)):
                            del_list.add(ord)
                            if ord.symbol not in del_subpos:
                                del_subpos[ord.symbol] = []
                            del_subpos[ord.symbol].append(ord.subPosId)

                    else:
                        if ord.sltp_status == Const.SLTP_STATUS_READY:
                            result = await self.sdk.set_sltp(ord.symbol, ord.size, ord.posSide, ord.sl, ord.tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CROSS)
                            if not isinstance(result, str):
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                ord.sl_id = result[0]
                                update_list.add(ord)
                        # 如果不是带单账号
                        if len(ord.sl_id) > 0:
                            result = await self.sdk.query_algo(ord.sl_id)
                            if not isinstance(result, str):
                                if result.status == Const.ORDER_STATUS_FILLED:
                                    del_list.add(ord)

            else:
                server_info = await self.sdk.query_spot_order_info(ord.symbol, ord.orderId)
                if not isinstance(server_info, str):
                    self.update_orderdb(
                        update_list, del_list, ord, server_info)
                if ord.status == Const.ORDER_STATUS_FILLED:
                    if self.sdk.spot_copytrader:
                        subpos = None
                        if ord.symbol not in spot_subpos:
                            subpos = await self.sdk.request_spot_subpositions(ord.symbol)
                            if not isinstance(subpos, str):
                                lis = {i.orderId: i.subPosId for i in subpos}
                                spot_subpos[ord.symbol] = lis
                        if len(ord.subPosId) == 0 and ord.symbol in spot_subpos and ord.orderId in spot_subpos[ord.symbol]:
                            ord.subPosId = spot_subpos[ord.symbol][ord.orderId]
                            update_list.add(ord)
                        if ord.sltp_status == Const.SLTP_STATUS_READY:
                            # 设置带单的止盈止损
                            result = await self.sdk.set_sltp_by_copytrader(ord.subPosId, ord.sl, ord.tp)
                            if not isinstance(result, str):
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                update_list.add(ord)
                        # 如果没有subposId 说明订单已经平掉
                        if (ord.symbol in spot_subpos and ord.symbol in spot_subpos and ord.orderId not in spot_subpos[ord.symbol]) or (ord.symbol not in swap_subpos and not isinstance(subpos, str)):
                            del_list.add(ord)

                    else:
                        # 如果不是带单账号
                        if ord.sltp_status == Const.SLTP_STATUS_READY:
                            result = await self.sdk.set_sltp(ord.symbol, ord.size, ord.posSide, ord.sl, ord.tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CASH)
                            if not isinstance(result, str):
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                ord.sl_id = result[0]
                                update_list.add(ord)
                        if len(ord.sl_id) > 0:
                            result = await self.sdk.query_algo(ord.sl_id)
                            if not isinstance(result, str):
                                if result.status != Const.ORDER_STATUS_LIVE:
                                    del_list.add(ord)

        if len(update_list) > 0:
            await DataStore.update_orderinfo(update_list)
        if len(del_list) > 0:
            await DataStore.del_orderinfo(del_list)
        if DataStore.json_conf['TransferProfit'] > 0 and len(del_subpos) > 0:
            self.check_profit = True
            for i, v in del_subpos.items():
                asyncio.create_task(self.get_swap_pnl(i, v))

        if self.movingData == None and self.check_profit == False and math.floor(swap_acc.available*1000) == math.floor(swap_acc.total*1000) and swap_acc.unrealizedPL == 0 and self.exdata.no_move_asset == False and swap_acc.total > 1 and len(swap_list) == 0:
            await self.move_asset_to_simpleearn(math.floor(swap_acc.total*10**2)/10**2)

    async def setlever(self, symbol: str, lever: int):
        if len(symbol) == 0:
            for i, v in OkxSdk.swap_baseinfo.items():
                await self.sdk.setlever(i, lever)
                await asyncio.sleep(0.1)
        else:
            symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
            await self.sdk.setlever(symbol, lever)
        return True


################################################################################################################################################################


    async def _make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int):
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        if symbol not in self.sdk.swap_baseinfo:
            msg = f"okx sdk 没有{symbol}这个交易对"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if self.exdata.no_move_asset==False and self.movingData!=None:
            await self.move_asset_to_future()
        size = 0
        if orderType == Const.ORDER_TYPE_MARKET:
            mark_price = await self.sdk.request_swap_price(symbol)
            if isinstance(mark_price, str):
                msg = f"okx make_swap_order 请求价格失败:{mark_price}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            size = self.sdk.count_pos_by_price(
                OkxSdk.swap_baseinfo[symbol], money, mark_price, DataStore.json_conf['LEVERAGE'])
        else:
            size = self.sdk.count_pos_by_price(
                OkxSdk.swap_baseinfo[symbol], money, price, DataStore.json_conf['LEVERAGE'])
        order_result = await self.sdk.make_swap_order(symbol, size, posSide, orderType, price)
        if isinstance(order_result, str):
            msg = f"okx make_swap_order symbol={symbol} posSide={posSide} size={size} 下单失败:result={order_result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            db = OrderInfoDB()
            db.exId = self.exdata.id
            db.symbol = symbol
            db.orderId = order_result[0]
            db.posSide = posSide
            db.size = size
            db.isswap = True
            db.orderType = orderType
            return db

    async def query_swap_subPosId(self, info: OrderInfoDB):
        await asyncio.sleep(10)
        result = await self.sdk.request_swap_subpositions(info.symbol)
        if isinstance(result, str):
            logger.info(
                f'okx controller query_subPosId 错误 info={info.to_json()} err={result}')
            return
        for i in result:
            if i.orderId == info.orderId:
                info.subPosId = i.subPosId
                if info.sltp_status == Const.SLTP_STATUS_READY:
                    result = await self.sdk.set_sltp_by_copytrader(info.subPosId, info.sl, info.tp)
                    if isinstance(result, str):
                        await DataStore.update_orderinfo(info)
                        msg = f'okx controller set_sltp_by_copytrader 错误 info={info.to_json()} err={result}'
                        logger.info(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
                break

    # 网页合约开单
    # sltp_type:int 0为仓位止盈止损 1为订单止盈止损 orderType 0 为市价 1 为限价
    async def make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str) -> OrderInfoDB:
        info = await self._make_swap_order(symbol, money, posSide, price, orderType)
        info.orderFrom = orderFrom
        info.sl = sl
        info.tp = tp
        await DataStore.insert_orderinfo(info)
        msg = f'okx make_swap_order 下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if orderType == Const.ORDER_TYPE_MARKET:
            if self.sdk.swap_copytrader:
                if sl > 0 or tp > 0:
                    info.sltp_status = Const.SLTP_STATUS_READY
                asyncio.create_task(self.query_swap_subPosId(info))
            else:
                if sl > 0 or tp > 0:
                    result = await self.sdk.set_sltp(
                        info.symbol, info.size, info.posSide, sl, tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CROSS)
                    if isinstance(result, str):
                        msg = f"okx controller set_sltp 错误 info={info.to_json()} err={result} "
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                        raise HTTPException(
                            status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        info.sl_id = result[0]
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)

        else:
            # 限价下单
            if sl > 0 or tp > 0:
                info.sl = sl
                info.tp = tp
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)

        return info
    # 通过订单手动平仓或关闭订单

    async def close_swap_by_order(self, id) -> bool:
        info = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info == None:
            msg = f"okx controller close_swap_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        result = await self.sdk.query_swap_order_info(info.symbol, info.orderId)
        if isinstance(result, str):
            msg = f"okx controller query_swap_order_info 未找到相关订单信息:info={info.to_json()} err={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if result.status == Const.ORDER_STATUS_LIVE:
            result = await self.sdk.cancel_swap_order(info.symbol, info.orderId)
            if isinstance(result, str):
                msg = f"okx controller cancel_swap_order 失败:info={info.to_json()} result={result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                logger.info(f'okx close_swap_by_order 关闭订单成功 {info.to_json()}')
                await DataStore.del_orderinfo(info)
        elif result.status == Const.ORDER_STATUS_FILLED:
            if self.sdk.swap_copytrader:
                result = await self.sdk.close_swap_order_by_copytrader(info.subPosId)
                if isinstance(result, str):
                    msg = f"okx controller close_swap_order_by_copytrader 失败:info={info.to_json()} result={result}"
                    logger.error(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    msg = 'okx close_swap_by_order 平单成功 {info.to_json()}'
                    logger.info(msg)
                    await DataStore.del_orderinfo(info)
                    await TGBot.send_close_msg(msg)
                    if DataStore.json_conf['TransferProfit'] > 0:
                        self.check_profit = True
                        asyncio.create_task(self.get_swap_pnl(
                            info.symbol, info.subPosId))
            else:
                result = await self.sdk.close_swap_order_by_market(info.symbol, info.size, info.posSide)
                if isinstance(result, str):
                    msg = f"okx controller close_swap_order_by_market 失败:info={info.to_json()} result={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    logger.info(
                        f'okx close_swap_by_order 平单成功 {info.to_json()}')
                    if len(info.sl_id) > 0:
                        await self.sdk.cancel_algo(info.symbol, info.sl_id)
                    await DataStore.del_orderinfo(info)
        else:
            msg = f"okx query_swap_order_info 当前订单状态为 status={result.status} 无法手动关闭"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        # await self.check_swap_sltp_market_order(info.symbol,info.posSide)

    # async def check_swap_sltp_market_order(self, symbol, posSide):
    #     count = 0
    #     for i in DataStore.order_info[self.exdata.id]:
    #         if i.symbol == symbol and posSide==i.posSide and i.isswap:
    #             count = 1
    #             break
    #     if count == 0:
    #         for i in DataStore.sltp_market[self.exdata.id]:
    #             if i.symbol == symbol and i.posSide == posSide and i.isswap:
    #                 result = await self.sdk.cancel_algo(i.symbol, i.sl_id)
    #                 if isinstance(result, str):
    #                     msg = f"okx controller cancel_algo 失败 symbol={symbol} result={result}"
    #                     logger.error(msg)
    #                     raise HTTPException(
    #                         status_code=Status.ExchangeError.value, detail=msg)

    #                 await DataStore.del_SLTPMarket(i)
    #                 break
    # 通过仓位手动全部平仓
    async def close_swap_by_pos(self, symbol, posSide) -> bool:
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        result = await self.sdk.close_swap_by_pos(symbol, posSide, 'cross')
        if isinstance(result, str):
            msg = f"okx controller close_swap_by_pos 错误 symbol={symbol} err={result} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            return False
        else:
            msg = f'okx close_swap_by_pos 平单成功 {symbol} {posSide}'
            logger.info(msg)
            del_list = []
            subposIds = []
            for i in DataStore.order_info[self.exdata.id]:
                if i.symbol == symbol and i.posSide == posSide and i.isswap and i.status == Const.ORDER_STATUS_FILLED:
                    if len(i.sl_id) > 0:
                        await self.sdk.cancel_algo(i.symbol, i.sl_id)
                    del_list.append(i)
                    if len(i.subPosId) > 0:
                        subposIds.append(i.subPosId)
            if DataStore.json_conf['TransferProfit'] > 0 and len(subposIds) > 0:
                self.check_profit = True
                asyncio.create_task(self.get_swap_pnl(symbol, subposIds))
        # for i in DataStore.sltp_market[self.exdata.id]:
        #     if i.symbol==symbol and i.posSide==posSide and i.isswap:
        #         await DataStore.del_SLTPMarket(i)
        #         break
            await DataStore.del_orderinfo(del_list)
            await TGBot.send_close_msg(msg)
        return True
    # 设置仓位的止盈止损

    # SLTPMarketDB:
    async def set_swap_sltp_by_pos(self, symbol, posSide, sl, tp) -> bool:
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.isswap and i.posSide == posSide and i.status == Const.ORDER_STATUS_FILLED:

                if len(i.subPosId) > 0:
                    result = await self.sdk.set_sltp_by_copytrader(i.subPosId, sl, tp)
                    i.sl = sl
                    i.tp = tp
                    if isinstance(result, str):
                        i.sltp_status = Const.SLTP_STATUS_READY
                        msg = f'okx controller set_sltp_by_copytrader 错误 info={i.to_json()} err={result}'
                        logger.info(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        i.sltp_status = Const.SLTP_STATUS_FINISH
                    await DataStore.update_orderinfo(i)
                elif len(i.sl_id) > 0:
                    await self.sdk.cancel_algo(i.symbol, i.sl_id)
                    i.sl = 0
                    i.tp = 0
                    i.sl_id = ''
                    i.sltp_status = Const.SLTP_STATUS_NONE
                    await DataStore.update_orderinfo(i)
                    if sl > 0 or tp > 0:
                        result = await self.sdk.set_sltp(i.symbol, i.size, i.posSide, sl, tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CROSS)
                        if isinstance(result, str):
                            i.sl = sl
                            i.tp = tp
                            i.sltp_status = Const.SLTP_STATUS_READY
                            await DataStore.update_orderinfo(i)
                            msg = f"okx set_sltp 失败 symbol={symbol} posSide={posSide} size={i.size}  result={result}"
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                        else:
                            i.sl = sl
                            i.tp = tp
                            i.sl_id = result[0]
                            await DataStore.update_orderinfo(i)

        # for i in DataStore.sltp_market[self.exdata.id]:
        #     if i.symbol==symbol and i.posSide==posSide and i.isswap:
        #         await self.sdk.cancel_algo(i.symbol,i.sl_id)
        #         #await DataStore.del_SLTPMarket(i)
        #         break
        # if sl<=0 and tp<=0:
        #     return None
        # result=await self.sdk.set_sltp(symbol,0,posSide,sl,tp,Const.SLTP_TYPE_POS,Const.TDMODE_CROSS)
        # if isinstance(result,str):
        #     msg = f"okx controller set_swap_sltp 失败 symbol={symbol} result={result}"
        #     logger.error(msg)
        #     raise HTTPException(
        #                     status_code=Status.ExchangeError.value, detail=msg)
        # sltp=await DataStore.insert_SLTPMarket(self.exdata.id,symbol,True,posSide,sl,tp,result[0],'')
        return True
    # 设置订单的止盈止损

    async def set_swap_sltp_by_order(self, id, sl, tp) -> OrderInfoDB:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"okx set_swap_sltp_by_order 未找到ID={id}的订单"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if info.status == Const.ORDER_STATUS_FILLED:
            if len(info.subPosId) > 0:
                result = await self.sdk.set_sltp_by_copytrader(info.subPosId, sl, tp)
                if isinstance(result, str):
                    msg = f"okx sdk set_sltp_by_copytrader 设置带单止盈止损失败 info={info.to_json()} err={result}"
                    logger.error(msg)
                    info.sl = sl
                    info.tp = tp
                    info.sltp_status = Const.SLTP_STATUS_READY
                    await TGBot.send_err_msg(msg)
                else:
                    info.sl = sl
                    info.tp = tp
                    info.sltp_status = Const.SLTP_STATUS_FINISH
                await DataStore.update_orderinfo(info)
            else:
                if len(info.sl_id) > 0:
                    result = await self.sdk.cancel_algo(info.symbol, info.sl_id)
                    if isinstance(result, str):
                        msg = f"okx sdk cancel_algo 取消委托订单失败 info={info.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sl = 0
                        info.tp = 0
                        info.sltp_status = Const.SLTP_STATUS_NONE
                        await DataStore.update_orderinfo(info)
                if sl > 0 or tp > 0:
                    result = await self.sdk.set_sltp(info.symbol, info.size, info.posSide, sl, tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CROSS)
                    info.sl = sl
                    info.tp = tp
                    if isinstance(result, str):
                        msg = f"okx sdk set_sltp 设置订单止盈止损失败 info={info.to_json()} err={result}"
                        logger.error(msg)
                        info.sltp_status = Const.SLTP_STATUS_READY
                        await TGBot.send_err_msg(msg)
                    else:

                        info.sltp_status = Const.SLTP_STATUS_FINISH
                    await DataStore.update_orderinfo(info)
        elif info.status == Const.ORDER_STATUS_LIVE:
            info.sl = sl
            info.tp = tp
            if sl > 0 or tp > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
            else:
                info.sltp_status = Const.SLTP_STATUS_NONE
            await DataStore.update_orderinfo(info)

        return info

    async def get_swap_pnl(self, symbol: str, id):
        await asyncio.sleep(2)
        pnl = await self.sdk.get_swap_history_by_subpos(symbol, id)
        if isinstance(pnl, float):
            if pnl > 0:
                _pnl = math.floor(pnl*DataStore.json_conf['TransferProfit'] * 10**4) / 10**4
                result = await self.sdk.transfer(1, 0, _pnl)
                if isinstance(result, tuple):
                    msg = f"okx symbol={symbol} 盈利 {pnl} 划转 {_pnl} 到资金账户 tranId={result[0]}"
                    logger.info(msg)
                    result = await self.sdk.move_fedeem_simple_earn(_pnl, True)
                    if isinstance(result, str):
                        msg = f"okx get_swap_pnl 申购活期理财 {_pnl} 失败  err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        msg = f"okx get_swap_pnl 申购活期理财 {_pnl} 成功 "
                        logger.info(msg)
                else:
                    msg = f"okx symbol={symbol} 盈利 {pnl} 划转 {_pnl} 到资金账户失败 err={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
        else:
            msg = f"okx get_swap_history_by_subpos 错误 symbol={symbol} subPosId={id} err={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
        self.check_profit = False

################################################### SPOT#############################################################################################################

    async def _make_spot_order(self, symbol: str, money: float, price: float, orderType: int):
        symbol = utils.get_spot_symbol(symbol, self.exdata.ex)
        if symbol not in self.sdk.spot_baseinfo:
            msg = f"okx sdk 没有{symbol}这个交易对"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)

        size = 0
        if orderType == Const.ORDER_TYPE_MARKET:
            mark_price = await self.sdk.request_spot_price(symbol)
            if isinstance(mark_price, str):
                msg = f"okx sdk request_spot_price 交易所请求价格失败:{mark_price}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                size = super(OkxSdk, self.sdk).count_pos_by_price(
                    OkxSdk.spot_baseinfo[symbol], money, mark_price, 1)
        else:
            size = super(OkxSdk, self.sdk).count_pos_by_price(
                OkxSdk.spot_baseinfo[symbol], money, price, 1)

        result = await self.sdk.make_spot_order(symbol, size, orderType, price)
        if isinstance(result, str):
            msg = f"okx sdk _make_spot_order 下单失败:symbol={symbol} size={size} result={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            db = OrderInfoDB()
            db.exId = self.exdata.id
            db.orderId = result[0]
            db.isswap = False
            db.size = size
            db.symbol = symbol
            db.orderType = orderType
            return db

    async def query_spot_subPosId(self, info: OrderInfoDB):
        await asyncio.sleep(10)
        result = await self.sdk.request_spot_subpositions(info.symbol)
        if isinstance(result, str):
            logger.info(
                f'okx controller request_spot_subpositions 错误 symbol={info.symbol} err={result}')
            return
        for i in result:
            if i.orderId == info.orderId:
                info.subPosId = i.subPosId
                await DataStore.update_orderinfo(info)
                if info.sltp_status == Const.SLTP_STATUS_READY:
                    sltp = await self.sdk.set_sltp_by_copytrader(info.subPosId, info.sl, info.tp)
                    if isinstance(sltp, str):
                        msg = f'okx controller query_spot_subPosId 错误 symbol={info.symbol} err={sltp}'
                        logger.info(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
                break

    async def make_spot_order(self, symbol: str, money: float, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str) -> OrderInfoDB:
        info = await self._make_spot_order(symbol, money, price, orderType)
        info.orderFrom = orderFrom
        await DataStore.insert_orderinfo(info)
        msg = f'okx make_spot_order 下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if orderType == Const.ORDER_TYPE_MARKET:
            if self.sdk.swap_copytrader:
                if sl > 0 or tp > 0:
                    info.sltp_status = Const.SLTP_STATUS_READY
                asyncio.create_task(self.query_spot_subPosId(info))
            else:
                if sl > 0 or tp > 0:
                    result = await self.sdk.set_sltp(
                        info.symbol, info.size, info.posSide, sl, tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CASH)
                    if isinstance(result, str):
                        msg = f"okx controller set_sltp 错误 info={info.to_json()} err={result} "
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                        raise HTTPException(
                            status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        info.sl_id = result[0]
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)

        else:
            # 限价下单
            if sl > 0 or tp > 0:
                info.sl = sl
                info.tp = tp
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)

        return info

    async def close_spot_by_order(self, id) -> bool:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"okx close_spot_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        orderInfo = await self.sdk.query_spot_order_info(info.symbol, info.orderId)
        if isinstance(orderInfo, str):
            msg = f"okx sdk query_spot_order_info 未找到相关订单信息:info={info.to_json()} result={orderInfo}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if orderInfo.status == Const.ORDER_STATUS_LIVE:
            result = await self.sdk.cancel_spot_order(info.symbol, info.orderId)
            if isinstance(result, str):
                msg = f"okx sdk cancel_spot_order 失败:info={info.to_json()} result={result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
            else:
                msg = f'okx close_spot_by_order 取消订单成功 {info.to_json()}'
                logger.info(msg)
                await TGBot.send_close_msg(msg)
        elif orderInfo.status == Const.ORDER_STATUS_FILLED:
            if len(info.subPosId) > 0:
                result = await self.sdk.close_spot_order_by_copytrader(info.symbol, info.subPosId)
                if isinstance(result, str):
                    msg = f"okx sdk close_spot_order_by_copytrader 失败:info={info.to_json()} result={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                else:
                    msg = f'okx close_spot_by_order 平单成功 {info.to_json()}'
                    logger.info(msg)
                    await TGBot.send_close_msg(msg)
            else:
                result = await self.sdk.close_spot_order_by_market(info.symbol, info.size)
                if isinstance(result, str):
                    msg = f"okx sdk close_spot_order_by_market 失败:info={info.to_json()} result={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                else:
                    msg = f'okx close_spot_by_order 平单成功 {info.to_json()}'
                    logger.info(msg)
                    await TGBot.send_close_msg(msg)
        else:
            msg = f"okx sdk query_spot_order_info 订单状态已取消 无法关闭:info={info.to_json()} status={orderInfo.status}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        await DataStore.del_orderinfo(info)
        # await self.check_spot_sltp_market_order(info.symbol)
        return True

    async def close_spot_by_pos(self, symbol) -> bool:
        del_list = []
        symbol = utils.get_spot_symbol(symbol, self.exdata.ex)

        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.isswap == False and i.status == Const.ORDER_STATUS_FILLED:

                if len(i.subPosId) > 0:
                    result = await self.sdk.close_spot_order_by_copytrader(i.symbol, i.subPosId)
                    if isinstance(result, str):
                        msg = f"okx sdk close_spot_order_by_copytrader 现货带单平仓失败:info={i.to_json()} result={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        msg = f'okx close_spot_by_pos 平单成功 {i.to_json()}'
                        logger.info(msg)
                        await TGBot.send_err_msg(msg)
                        del_list.append(i)
                else:
                    result = await self.sdk.close_spot_order_by_market(i.symbol, i.size)
                    if isinstance(result, str):
                        msg = f"okx sdk close_spot_order_by_copytrader 现货平仓失败:info={i.to_json()} result={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        msg = f'okx close_spot_by_pos 平单成功 {i.to_json()}'
                        logger.info(msg)
                        await TGBot.send_close_msg(msg)
                        del_list.append(i)

        await DataStore.del_orderinfo(del_list)

        return True

    # SLTPMarketDB:
    async def set_spot_sltp_by_pos(self, symbol, sl, tp) -> bool:
        symbol = utils.get_spot_symbol(symbol, self.exdata.id)
        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.isswap == False and i.status == Const.ORDER_STATUS_FILLED:
                if len(i.subPosId) > 0:
                    await self.sdk.set_sltp_by_copytrader(i.subPosId, sl, tp)
                    i.sl = sl
                    i.tp = tp
                    await DataStore.update_orderinfo(i)
                else:
                    if len(i.sl_id) > 0:
                        await self.sdk.cancel_algo(i.symbol, i.sl_id)
                        i.sl = 0
                        i.tp = 0
                        i.sl_id = ''
                        await DataStore.update_orderinfo(i)
                    if sl > 0 or tp > 0:
                        result = await self.sdk.set_sltp(i.symbol, i.size, '', sl, tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CASH)
                        if isinstance(result, str):
                            i.sl = sl
                            i.tp = tp
                            i.sltp_status = Const.SLTP_STATUS_READY
                            await DataStore.update_orderinfo(i)
                            msg = f"okx set_sltp 失败 symbol={symbol} size={i.size}  result={result}"
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                        else:
                            i.sl = sl
                            i.tp = tp
                            i.sl_id = result[0]
                            i.sltp_status = Const.SLTP_STATUS_FINISH
                            await DataStore.update_orderinfo(i)

        return True

    async def set_spot_sltp_by_order(self, id, sl, tp) -> OrderInfoDB:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"okx controller set_spot_sltp_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if info.status == Const.ORDER_STATUS_FILLED:

            if len(info.subPosId) > 0:
                result = await self.sdk.set_sltp_by_copytrader(info.subPosId, sl, tp)
                if isinstance(result, str):
                    msg = f"okx sdk set_sltp_by_copytrader 现货带单设置止盈止损失败:info={info.to_json()} result={result}"
                    logger.error(msg)
                    info.sl = sl
                    info.tp = tp
                    info.sltp_status = Const.SLTP_STATUS_READY
                    await DataStore.update_orderinfo(info)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    info.sl = sl
                    info.tp = tp
                    info.sltp_status = Const.SLTP_STATUS_FINISH
                    await DataStore.update_orderinfo(info)
            else:
                if len(info.sl_id) > 0:
                    result = await self.sdk.cancel_algo(i.symbol, i.sl_id)
                    if isinstance(result, str):
                        msg = f"okx sdk cancel_algo 现货删除订单止盈止损失败:info={info.to_json()} result={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sl = 0
                        info.tp = 0
                        info.sl_id = ''
                        await DataStore.update_orderinfo(info)

                if sl > 0 or tp > 0:
                    result = await self.sdk.set_sltp(info.symbol, info.size, '', sl, tp, Const.SLTP_TYPE_ORDER, Const.TDMODE_CASH)
                    if isinstance(result, str):
                        msg = f"okx sdk set_sltp 现货设置订单止盈止损失败:info={info.to_json()} result={result}"
                        logger.error(msg)
                        info.sl = sl
                        info.tp = tp
                        info.sltp_status = Const.SLTP_STATUS_READY
                        await DataStore.update_orderinfo(info)
                        await TGBot.send_err_msg(msg)
                        raise HTTPException(
                            status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        info.sl = sl
                        info.tp = tp
                        info.sl_id = result[0]
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
        elif info.status == Const.ORDER_STATUS_LIVE:
            info.sl = sl
            info.tp = tp
            if sl > 0 or tp > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
            else:
                info.sltp_status = Const.SLTP_STATUS_NONE
            await DataStore.update_orderinfo(info)

        return info

    async def move_asset_to_simpleearn(self, money: float):
        result = await self.sdk.transfer(1, 0, money)
        if isinstance(result, str):
            msg = f"okx move_asset_to_simpleearn 转移资金到现金账户失败: result={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            return
        await asyncio.sleep(0.1)
        result = await self.sdk.move_fedeem_simple_earn( money,True)
        if isinstance(result, str):
            msg = f"okx move_asset_to_simpleearn 申购活期理财失败: result={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            await self.sdk.transfer(0, 1, money)
            return
        else:
            msg = f"okx move_to_simple_earn 申购活期理财成功 资金为{money}"
            logger.info(msg)
        db = MovingAssetDB(exid=self.exdata.id, money= money, datetime= datetime.datetime.now(), transid='')
        await MovingAssetDao.MovingAssetDB_Insert(db)
        self.movingData = db

    async def move_asset_to_future(self):
        result = await self.sdk.move_fedeem_simple_earn( self.movingData.money,False)
        if isinstance(result, str):
            msg = f"okx move_asset_to_future 从活期理财提取资金{self.movingData.money}失败: result={result}"
            logger.error(msg)
            return
        else:
            msg = f"okx move_asset_to_future 从活期理财提取资金{self.movingData.money}成功"
            logger.info(msg)
        result = await self.sdk.transfer(0, 1, self.movingData.money)
        await asyncio.sleep(0.1)
        if isinstance(result, str):
            msg = f"okx move_asset_to_future 转移资金{self.movingData.money}到合约账户失败: result={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            await self.sdk.move_fedeem_simple_earn(self.movingData.money,True)
            return
        else:
            msg = f"okx move_asset_to_future 转移资金{self.movingData.money}到合约账户成功"
            logger.info(msg)
        self.movingData.isdelete = True
        await MovingAssetDao.MovingAssetDB_Update(self.movingData)
        self.movingData = None
        asyncio.sleep(0.1) 
