import asyncio
from typing import Dict, List
from fastapi import HTTPException
import schedule
from HttpListener import Status
# from SLTPMarketDao import SLTPMarketDB
from log import logger
from Controller import Controller
from ExchangeDao import ExchangeDb
from OrderInfoDao import OrderInfoDB
from sdk.BitgetSdk import BitgetSdk
from sdk.OrderClass import AccountInfo, OrderInfo
import TGBot
import DataStore
import utils
import Const
import time
# 因为bitget在limit订单时只能设置仓位止盈止损，而不是设置止盈止损计划，如果触发则全仓会被平仓,如果在makeorder里直接设置分批止盈止损，是无法第一时间查到策略id的，也就无法知晓，当前订单情况。


class BitgetController(Controller):
    def __init__(self, exdata: ExchangeDb) -> None:
        super().__init__(exdata)
        self.last_open_time: float = 0
        self.lock = asyncio.Lock()
        self.sdk = BitgetSdk(
            exdata.apikey, exdata.api_secret, exdata.api_password)
        self.exdata = exdata
        self.job = None

    async def init(self):
        await self.sdk.init()
        self.job = schedule.every(DataStore.json_conf['DATA_REFRESH_TIME']).seconds.do(
            lambda: asyncio.create_task(self.every_min_task()))
        await self.every_min_task()

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
        spot_list = await self.sdk.request_spot_positions()
        if isinstance(spot_list, list):
            filtered_elements = [
                element for element in spot_list if element.symbol == "USDT"]
            remaining_elements = [
                element for element in spot_list if element.symbol != "USDT"]
            spot_acc = DataStore.spot_account[self.exdata.id]
            if filtered_elements:
                spot_acc.available = filtered_elements[0].available
                spot_acc.total = filtered_elements[0].total
                spot_acc.unrealizedPL = filtered_elements[0].unrealizedPL
                DataStore.spot_positions[self.exdata.id] = remaining_elements
                spot_total = sum(
                    spot.unrealizedPL for spot in remaining_elements)
                filtered_elements[0].unrealizedPL = spot_total
            else:
                spot_acc.total = 0
                spot_acc.available = 0
                spot_acc.unrealizedPL = 0
                DataStore.spot_positions[self.exdata.id] = spot_list
                spot_total = sum(spot.unrealizedPL for spot in spot_list)
                spot_acc.unrealizedPL = spot_total
        else:
            DataStore.spot_positions[self.exdata.id] = []

        swap_list = await self.sdk.request_swap_positions()
        if isinstance(swap_list, list):
            DataStore.swap_positions[self.exdata.id] = swap_list
        else:
            DataStore.swap_positions[self.exdata.id] = []
        swap_account = await self.sdk.request_swap_account()
        if not isinstance(swap_account, str):
            swap_acc = DataStore.swap_account[self.exdata.id]
            swap_acc.available = swap_account.available
            swap_acc.symbol = swap_account.symbol
            swap_acc.total = swap_account.total
            swap_acc.unrealizedPL = swap_account.unrealizedPL
        saving = await self.sdk.get_saving_funding()
        if isinstance(saving, float):
            DataStore.spot_account[self.exdata.id].funding = saving
        del_list: set = set()
        update_list: set = set()
        swap_subpos: Dict[str:Dict[str:str]] = {}
        spot_subpos: Dict[str:Dict[str:str]] = {}
        spot_sltp_plan: Dict[str:List[str]] = {}
        del_subpos: Dict[str:List[str]] = {}
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
                        if len(ord.subPosId) == 0 and ord.orderId in swap_subpos[ord.symbol]:
                            ord.subPosId = swap_subpos[ord.symbol][ord.orderId]
                            update_list.add(ord)
                        if ord.sltp_status == Const.SLTP_STATUS_READY and len(ord.subPosId) > 0:
                            # 设置带单的止盈止损
                            result = await self.sdk.set_swap_sltp_by_copytrader(ord.symbol, ord.subPosId, ord.sl, ord.tp)
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
                        # 如果不是带单账号
                        if ord.sltp_status == Const.SLTP_STATUS_READY:
                            if ord.sl > 0:
                                result = await self.sdk.set_swap_sl(ord.symbol, ord.size, ord.posSide, ord.sl, False)
                                if not isinstance(result, str):
                                    ord.sltp_status = Const.SLTP_STATUS_FINISH
                                    ord.sl_id = result[0]
                                    update_list.add(ord)
                            if ord.tp > 0:
                                result = await self.sdk.set_swap_tp(ord.symbol, ord.size, ord.posSide, ord.tp, False)
                                if not isinstance(result, str):
                                    ord.sltp_status = Const.SLTP_STATUS_FINISH
                                    ord.tp_id = result[0]
                                    update_list.add(ord)
                        elif ord.sltp_status == Const.SLTP_STATUS_FINISH:
                            if ord.sl > 0:
                                result = await self.sdk.query_swap_order_plan(ord.symbol, ord.sl_id)
                                if not isinstance(result, str):
                                    if result.status != Const.ORDER_STATUS_LIVE:
                                        del_list.add(ord)
                            if ord.tp > 0:
                                result = await self.sdk.query_swap_order_plan(ord.symbol, ord.tp_id)
                                if not isinstance(result, str):
                                    if result.status != Const.ORDER_STATUS_LIVE:
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
                        if ord.sltp_status == Const.SLTP_STATUS_READY and len(ord.subPosId) > 0:
                            # 设置带单的止盈止损
                            result = await self.sdk.set_spot_sltp_by_copytrader(ord.symbol, ord.subPosId, ord.sl, ord.tp)
                            if not isinstance(result, str):
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                update_list.add(ord)
                        # 如果没有subposId 说明订单已经平掉
                        if (ord.symbol in spot_subpos and ord.symbol in spot_subpos and ord.orderId not in spot_subpos[ord.symbol]) or (ord.symbol not in swap_subpos and not isinstance(subpos, str)):
                            del_list.add(ord)
                    else:
                        if ord.sltp_status == Const.SLTP_STATUS_READY:
                            if ord.sl > 0:
                                result = await self.sdk.set_spot_sl(ord.symbol, ord.size, ord.sl, False)
                                if not isinstance(result, str):
                                    ord.sltp_status = Const.SLTP_STATUS_FINISH
                                    ord.sl_id = result[0]
                                    update_list.add(ord)
                            if ord.tp > 0:
                                result = await self.sdk.set_spot_tp(ord.symbol, ord.size, ord.tp, False)
                                if not isinstance(result, str):
                                    ord.sltp_status = Const.SLTP_STATUS_FINISH
                                    ord.tp_id = result[0]
                                    update_list.add(ord)
                        elif ord.sltp_status == Const.SLTP_STATUS_FINISH:
                            if ord.symbol not in spot_sltp_plan:
                                result = await self.sdk.query_spot_plan_order(ord.symbol)
                                if not isinstance(result, str):
                                    spot_sltp_plan[ord.symbol] = result
                            if (len(ord.sl_id) > 0 and ord.symbol in spot_sltp_plan and ord.sl_id not in spot_sltp_plan[ord.symbol]) or (len(ord.tp_id) > 0 and ord.symbol in spot_sltp_plan and ord.tp_id not in spot_sltp_plan[ord.symbol]):
                                del_list.add(ord)

        if len(update_list) > 0:
            await DataStore.update_orderinfo(update_list)
        if len(del_list) > 0:
            await DataStore.del_orderinfo(del_list)
        if DataStore.json_conf['TransferProfit'] > 0:
            for i, v in del_subpos:
                asyncio.create_task(self.get_swap_pnl(i, v))

    # fromType 0 为现金账户，1为合约账户

    async def transfer(self, fromType: int, toType: int, usdt: float):
        result = await self.sdk.transfer(fromType, toType, usdt)
        if isinstance(result, str):
            msg = f"bitget transfer error:fromType={fromType} toType={toType} usdt={usdt} result={result}"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            logger.info(
                f"bitget 交易所 transfer 成功 fromType={fromType} toType={toType} usdt={usdt}")
        return {fromType: fromType, toType: toType, usdt: usdt}

    async def setlever(self, symbol: str, lever: int):
        if len(symbol) == 0:
            for i, v in BitgetSdk.swap_baseinfo.items():
                await self.sdk.setlever(i, lever)
                await asyncio.sleep(0.1)
        else:
            symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
            await self.sdk.setlever(symbol, lever)
        return True

    async def _make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int):

        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        if symbol not in BitgetSdk.swap_baseinfo:
            msg = f"bitget sdk 没有{symbol}这个交易对"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            size = 0
            if orderType == Const.ORDER_TYPE_MARKET:
                mark_price = await self.sdk.request_swap_price(symbol)
                if isinstance(mark_price, str):
                    msg = f"bitget make_swap_order 请求价格失败:{mark_price}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    size = self.sdk.count_pos_by_price(
                        self.sdk.swap_baseinfo[symbol], money, mark_price, DataStore.json_conf['LEVERAGE'])
            else:
                size = self.sdk.count_pos_by_price(
                    self.sdk.swap_baseinfo[symbol], money, price, DataStore.json_conf['LEVERAGE'])
            order_result = await self.sdk.make_swap_order(symbol, size, posSide, orderType, price)
            if isinstance(order_result, str):
                msg = f"bitget make_swap_order 下单失败:symbol={symbol} size={size} err={order_result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                db = OrderInfoDB()
                db.symbol = symbol
                db.exId = self.exdata.id
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
            logger.error(
                f'bitget controller request_swap_subpositions 错误 info={info.to_json()} err={result}')
        else:
            for i in result:
                if i.orderId == info.orderId:
                    info.subPosId = i.subPosId
                    await DataStore.update_orderinfo(info)
                    if info.sltp_status == Const.SLTP_STATUS_READY:
                        sltp = await self.sdk.set_swap_sltp_by_copytrader(info.symbol, info.subPosId, info.sl, info.tp)
                        if isinstance(sltp, str):
                            msg = f'bitget controller set_swap_sltp_by_copytrader 错误 info={info.to_json()} err={sltp}'
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                        else:
                            info.sltp_status = Const.SLTP_STATUS_FINISH
                            await DataStore.update_orderinfo(info)
                    break

    # 合约开单
    async def make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str):
        if self.sdk.swap_copytrader:
            async with self.lock:
                time_ = time.time()
                if (time_-self.last_open_time) < 1:
                    await asyncio.sleep(max(0, time_ - self.last_open_time))

        info = await self._make_swap_order(symbol, money, posSide, price, orderType)
        info.orderFrom = orderFrom
        info.sl = sl
        info.tp = tp
        await DataStore.insert_orderinfo(info)
        msg = f'bitget make_swap_order 下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if orderType == Const.ORDER_TYPE_MARKET:
            if self.sdk.swap_copytrader:
                if sl > 0 or tp > 0:
                    info.sltp_status = Const.SLTP_STATUS_READY
                    await DataStore.update_orderinfo(info)
                    asyncio.create_task(self.query_swap_subPosId(info))
            else:
                if sl > 0:
                    result = await self.sdk.set_swap_sl(
                        info.symbol, info.size, info.posSide, sl, False)
                    if isinstance(result, str):
                        msg = f"bitget controller set_swap_sl 错误 info={info.to_json()} err={result} "
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                        raise HTTPException(
                            status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        info.sl_id = result[0]
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
                if tp > 0:
                    result = await self.sdk.set_swap_tp(
                        info.symbol, info.size, info.posSide, tp, False)
                    if isinstance(result, str):
                        msg = f"bitget controller set_swap_tp 错误 info={info.to_json()} err={result} "
                        logger.error(msg)
                        await TGBot.send_open_msg(msg)
                        raise HTTPException(
                            status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        info.tp_id = result[0]
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
        else:
            # 限价下单
            if sl > 0 or tp > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)
        self.last_open_time = time.time()
        return info
    # 通过订单手动平仓或关闭订单

    async def close_swap_by_order(self, id):
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"bitget close_swap_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            orderInfo = await self.sdk.query_swap_order_info(info.symbol, info.orderId)
            if isinstance(orderInfo, str):
                msg = f"bitget query_swap_order_info 未找到相关订单信息:info={info.to_json()} err={orderInfo} "
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                if orderInfo.status == Const.ORDER_STATUS_FILLED:
                    if self.sdk.swap_copytrader:
                        if len(info.subPosId) > 0:
                            result = await self.sdk.close_swap_order_by_copytrader(info.subPosId)
                            if isinstance(result, str):
                                msg = f"bitget close_swap_by_order 平仓失败 info={info.to_json()} result={result}"
                                logger.error(msg)
                                await TGBot.send_err_msg(msg)
                                raise HTTPException(
                                    status_code=Status.ExchangeError.value, detail=msg)
                            else:
                                msg = f'bitget close_swap_by_order 平仓成功 {info.to_json()}'
                                logger.info(msg)
                                await DataStore.del_orderinfo(info)
                                await TGBot.send_close_msg(msg)
                                if DataStore.json_conf['TransferProfit'] > 0:
                                    asyncio.create_task(self.get_swap_pnl(
                                        info.symbol, info.subPosId))
                        else:
                            msg = f"bitget close_swap_order subPosId为空 {info.to_json()}"
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                            raise HTTPException(
                                status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        result = await self.sdk.close_swap_order_by_market(info.symbol, info.size, info.posSide)
                        if isinstance(result, str):
                            msg = f"bitget close_swap_order_by_market 平仓失败 info={info.to_json()} result={result}"
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                            raise HTTPException(
                                status_code=Status.ExchangeError.value, detail=msg)
                        else:
                            msg = f'bitget close_swap_by_order 平仓成功 {info.to_json()}'
                            logger.info(msg)
                            await DataStore.del_orderinfo(info)
                            if len(info.sl_id) > 0:
                                result = await self.sdk.cancel_swap_sl_order(info.symbol, info.sl_id, False)
                            if len(info.tp_id) > 0:
                                result = await self.sdk.cancel_swap_tp_order(info.symbol, info.tp_id, False)
                            await TGBot.send_close_msg(msg)
                elif orderInfo.status == Const.ORDER_STATUS_LIVE:

                    result = await self.sdk.cancel_swap_order(info.symbol, info.orderId)
                    if isinstance(result, str):
                        msg = f"bitget cancel_swap_order 手动关闭订单失败 info={info.to_json()} result={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                        raise HTTPException(
                            status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        msg = f'bitget close_swap_by_order 取消订单成功 {info.to_json()}'
                        logger.info(msg)
                        await DataStore.del_orderinfo(info)
                        if len(info.sl_id) > 0:
                            result = await self.sdk.cancel_swap_sl_order(info.symbol, info.sl_id, False)
                        if len(info.tp_id) > 0:
                            result = await self.sdk.cancel_swap_tp_order(info.symbol, info.tp_id, False)
                        await TGBot.send_close_msg(msg)
                else:
                    msg = f"bitget cancel_swap_order 当前订单状态为 status={orderInfo.status} 无法手动关闭"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)

        return True
    # 手动全部平仓

    async def close_swap_by_pos(self, symbol, posSide):
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        del_info_list = []
        subposIds = []
        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.posSide == posSide and i.isswap and i.status == Const.ORDER_STATUS_FILLED:
                if len(i.subPosId) > 0:
                    result = await self.sdk.close_swap_order_by_copytrader(i.subPosId)
                    if isinstance(result, str):
                        msg = f"bitget close_swap_order_by_copytrader 失败 info={i.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        msg = f'bitget close_swap_by_pos 平仓成功 {i.to_json()}'
                        logger.info(msg)
                        del_info_list.append(i)
                        await TGBot.send_close_msg(msg)
                        subposIds.append(i.subPosId)
                else:
                    result = await self.sdk.close_swap_order_by_market(i.symbol, i.size, i.posSide)
                    if isinstance(result, str):
                        msg = f"bitget close_swap_order_by_market 失败 info={i.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        msg = f'bitget close_swap_by_pos 平仓成功 {i.to_json()}'
                        logger.info(msg)
                        if len(i.tp_id) > 0:
                            await self.sdk.cancel_swap_tp_order(i.symbol, i.tp_id, False)
                        if len(i.sl_id) > 0:
                            await self.sdk.cancel_swap_sl_order(i.symbol, i.sl_id, False)
                        del_info_list.append(i)
                        await TGBot.send_close_msg(msg)
        await DataStore.del_orderinfo(del_info_list)
        if DataStore.json_conf['TransferProfit'] > 0 and len(subposIds) > 0:
            asyncio.create_task(self.get_swap_pnl(symbol, subposIds))
        return True

    # 设置合约仓位止盈止损
    async def set_swap_sltp_by_pos(self, symbol, posSide, sl, tp) -> bool:
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)

        for i in DataStore.order_info[self.exdata.id]:
            if i.isswap and i.symbol == symbol and i.posSide == posSide and i.status == Const.ORDER_STATUS_FILLED:
                if len(i.subPosId) > 0:
                    result = await self.sdk.set_swap_sltp_by_copytrader(i.symbol, i.subPosId, sl, tp)
                    if isinstance(result, str):
                        msg = f"bitget  set_swap_sltp_by_pos 设置带单止盈止损失败 info={i.to_json()} err={result}"
                        logger.error(msg)
                        i.sl = sl
                        i.tp = tp
                        i.sltp_status = Const.SLTP_STATUS_READY
                        await DataStore.update_orderinfo(i)
                        await TGBot.send_err_msg(msg)
                    else:
                        i.sl = sl
                        i.tp = tp
                        i.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(i)
                else:
                    if len(i.sl_id) > 0:
                        await self.sdk.cancel_swap_sl_order(i.symbol, i.sl_id, False)
                        i.sl_id = ''
                        i.sl = 0
                        i.sltp_status = Const.SLTP_STATUS_NONE
                        await DataStore.update_orderinfo(i)
                    if len(i.tp_id) > 0:
                        await self.sdk.cancel_swap_tp_order(i.symbol, i.tp_id, False)
                        i.tp = 0
                        i.tp_id = ''
                        i.sltp_status = Const.SLTP_STATUS_NONE
                        await DataStore.update_orderinfo(i)
                    i.sl = sl
                    i.tp = tp
                    if sl > 0:
                        result = await self.sdk.set_swap_sl(i.symbol, i.size, i.posSide, sl, False)
                        if isinstance(result, str):
                            msg = f"bitget set_swap_sl 失败 info={i.to_json()} result={result}"
                            logger.error(msg)
                            i.sltp_status = Const.SLTP_STATUS_READY
                            await DataStore.update_orderinfo(i)
                            await TGBot.send_err_msg(msg)
                        else:
                            i.sltp_status = Const.SLTP_STATUS_FINISH
                            await DataStore.update_orderinfo(i)
                    if tp > 0:
                        result = await self.sdk.set_swap_tp(i.symbol, i.size, i.posSide, tp, False)
                        if isinstance(result, str):
                            msg = f"bitget set_swap_tp 失败 info={i.to_json()} result={result}"
                            logger.error(msg)
                            i.sltp_status = Const.SLTP_STATUS_READY
                            await DataStore.update_orderinfo(i)
                            await TGBot.send_err_msg(msg)
                        else:
                            i.sltp_status = Const.SLTP_STATUS_FINISH
                            await DataStore.update_orderinfo(i)

        return True
    # 设置合约订单止盈止损

    async def set_swap_sltp_by_order(self, id, sl, tp):

        # 判断订单状态，状态为1时，如果是交易员，通过交易员接口修改止盈止损，如果是普通用户，则先删除再重建止盈止损
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"bitget set_swap_sltp_by_order 未找到ID={id}的订单"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            order_info = await self.sdk.query_swap_order_info(info.symbol, info.orderId)
            if isinstance(order_info, str):
                msg = f"bitget query_swap_order_info 查询订单失败 info={info.to_json()} err={order_info}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                if order_info.status == Const.ORDER_STATUS_FILLED:
                    if self.sdk.swap_copytrader:
                        result = await self.sdk.set_swap_sltp_by_copytrader(info.symbol, info.subPosId, sl, tp)
                        if isinstance(result, str):
                            msg = f"bitget set_swap_sltp_by_copytrader 错误 info={info.to_json()} sl={sl} tp={tp} err={result}"
                            logger.error(msg)
                            info.sl = sl
                            info.tp = tp
                            if sl <= 0 and tp <= 0:
                                info.sltp_status = Const.SLTP_STATUS_NONE
                            else:
                                info.sltp_status = Const.SLTP_STATUS_READY
                            await DataStore.update_orderinfo(info)
                            await TGBot.send_err_msg(msg)
                            raise HTTPException(
                                status_code=Status.ExchangeError.value, detail=msg)
                        else:
                            info.sl = sl
                            info.tp = tp
                            if sl <= 0 and tp <= 0:
                                info.sltp_status = Const.SLTP_STATUS_NONE
                            else:
                                info.sltp_status = Const.SLTP_STATUS_FINISH
                            await DataStore.update_orderinfo(info)
                    else:
                        if len(info.sl_id) > 0:
                            info.sl = 0
                            info.sl_id = ''
                            info.sltp_status = Const.SLTP_STATUS_NONE

                            await DataStore.update_orderinfo(i)
                            await self.sdk.cancel_swap_sl_order(info.symbol, info.sl_id)
                        if len(info.tp_id) > 0:
                            info.tp = 0
                            info.tp_id = ''
                            info.sltp_status = Const.SLTP_STATUS_NONE
                            await DataStore.update_orderinfo(i)
                            await self.sdk.cancel_swap_tp_order(info.symbol, info.tp_id)
                        if sl > 0:
                            result = await self.sdk.set_swap_sl(info.symbol, info.size, info.posSide, sl, False)
                            if isinstance(result, str):
                                msg = f"bitget set_swap_sl 错误 info={info.to_json()} sl={sl}  err={result}"
                                logger.error(msg)
                                info.sltp_status = Const.SLTP_STATUS_READY
                                info.sl = sl
                                await DataStore.update_orderinfo(info)
                                await TGBot.send_err_msg(msg)
                                raise HTTPException(
                                    status_code=Status.ExchangeError.value, detail=msg)
                            else:
                                info.sl = sl
                                info.sl_id = result[0]
                                info.sltp_status = Const.SLTP_STATUS_FINISH
                                await DataStore.update_orderinfo(info)
                        if tp > 0:
                            result = await self.sdk.set_swap_tp(info.symbol, info.size, info.posSide, tp, False)
                            if isinstance(result, str):
                                msg = f"bitget set_swap_tp 错误 info={info.to_json()} tp={tp}  err={result}"
                                logger.error(msg)
                                info.sltp_status = Const.SLTP_STATUS_READY
                                info.tp = tp
                                await DataStore.update_orderinfo(info)
                                await TGBot.send_err_msg(msg)
                                raise HTTPException(
                                    status_code=Status.ExchangeError.value, detail=msg)
                            else:
                                info.tp = tp
                                info.tp_id = result[0]
                                info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
                elif order_info.status == Const.ORDER_STATUS_LIVE or order_info.status == Const.ORDER_STATUS_PARTIALLY_FILLED:
                    info.sl = sl
                    info.tp = tp
                    if sl > 0 or tp > 0:
                        info.sltp_status = Const.SLTP_STATUS_READY
                    else:
                        info.sltp_status = Const.SLTP_STATUS_NONE
                    await DataStore.update_orderinfo(info)
                else:
                    msg = f"bitget set_swap_sltp_by_order 错误 info={info.to_json()} 当前订单状态为{order_info.status} 不能设置止盈止损"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
        return info

    async def get_swap_pnl(self, symbol: str, id):
        await asyncio.sleep(2)
        pnl = await self.sdk.get_swap_history_by_subpos(symbol, id)
        if isinstance(pnl, float):
            if pnl > 0:
                _pnl = pnl*DataStore.json_conf['TransferProfit']
                result = await self.sdk.transfer(1, 0, _pnl)
                if isinstance(result, tuple):
                    msg = f"bitget symbol={symbol} 盈利 {pnl} 划转 {_pnl} 到资金账户 tranId={result[0]}"
                    logger.info(msg)
                else:
                    msg = f"bitget symbol={symbol} 盈利 {pnl} 划转 {_pnl} 到资金账户失败 err={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
        else:
            msg = f"bitget get_swap_history_by_subpos 错误 symbol={symbol} subPosId={id} err={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
################################################### SPOT#############################################################################################################

    async def _make_spot_order(self, symbol: str, money: float, price: float, orderType: int):
        symbol = utils.get_spot_symbol(symbol, self.exdata.ex)
        if symbol not in BitgetSdk.spot_baseinfo:
            msg = f"bitget sdk 没有{symbol}这个交易对"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            size = 0
            if orderType == Const.ORDER_TYPE_MARKET:
                mark_price = await self.sdk.request_spot_price(symbol)
                if isinstance(mark_price, str):
                    msg = f"bitget sdk request_spot_price 交易所请求价格失败:{mark_price}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    size = self.sdk.count_pos_by_price(
                        self.sdk.swap_baseinfo[symbol], money, mark_price, 1)
            else:
                size = self.sdk.count_pos_by_price(
                    self.sdk.swap_baseinfo[symbol], money, price, 1)
            result = await self.sdk.make_spot_order(symbol, size, orderType, price)
            if isinstance(result, str):
                msg = f"bitget sdk _make_spot_order 下单失败:symbol={symbol} size={size} err={result}"
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
            logger.error(
                f'bitget controller request_spot_subpositions 错误 info={info.to_json()} err={result}')
            return
        for i in result:
            if i.orderId == info.orderId:
                info.subPosId = i.subPosId
                await DataStore.update_orderinfo(info)
                if info.sltp_status == Const.SLTP_STATUS_READY:
                    result = await self.sdk.set_spot_sltp_by_copytrader(info.subPosId, info.sl, info.tp)
                    if isinstance(result, str):
                        msg = f"bitget sdk set_spot_sltp_by_copytrader 设置现货带单订单止盈止损失败:info={info.to_json()} result={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
                break

    async def make_spot_order(self, symbol: str, money: float, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str) -> OrderInfoDB:
        info = await self._make_spot_order(symbol, money, price, orderType)
        info.orderFrom = orderFrom
        await DataStore.insert_orderinfo(info)
        msg = f'bitget make_spot_order 下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if sl <= 0 and tp <= 0:
            return info
        # bitget现货 不支持全仓止盈止损,只能订单止盈止损
        if sltp_type == Const.SLTP_TYPE_POS or sltp_type == Const.SLTP_TYPE_ORDER:
            if self.sdk.spot_copytrader:
                info.sl = sl
                info.tp = tp
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)
                asyncio.create_task(self.query_spot_subPosId(info))
            else:
                if orderType == Const.ORDER_TYPE_MARKET:
                    info.status = Const.ORDER_STATUS_FILLED
                    await DataStore.update_orderinfo(info)
                await self.set_spot_sltp_by_order(info.id, sl, tp)

        return info

    async def close_spot_by_order(self, id) -> bool:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"bitget close_spot_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            orderInfo = await self.sdk.query_spot_order_info(info.symbol, info.orderId)
            if isinstance(orderInfo, str):
                msg = f"bitget sdk query_spot_order_info 未找到相关订单信息:info={info.to_json()} err={orderInfo}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                if orderInfo.status == Const.ORDER_STATUS_LIVE:
                    result = await self.sdk.cancel_spot_order(info.symbol, info.orderId)
                    if isinstance(result, str):
                        msg = f"bitget sdk cancel_spot_order 关闭订单失败:info={info.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                        raise HTTPException(
                            status_code=Status.ExchangeError.value, detail=msg)
                    else:
                        msg = f'bitget close_spot_by_order 取消订单成功 {info.to_json()}'
                        logger.info(msg)
                        await DataStore.del_orderinfo(info)
                        await TGBot.send_close_msg(msg)
                        if self.sdk.spot_copytrader == False:
                            if len(i.sl_id) > 0:
                                await self.sdk.cancel_spot_plan_order(i.sl_id)
                            if len(i.tp_id) > 0:
                                await self.sdk.cancel_spot_plan_order(i.tp_id)
                elif orderInfo.status == Const.ORDER_STATUS_FILLED:
                    if len(info.subPosId) > 0:
                        result = await self.sdk.close_spot_order_by_copytrader(info.symbol, info.subPosId)
                        if isinstance(result, str):
                            msg = f"bitget sdk close_spot_order_by_copytrader 失败:info={info.to_json()} err={result}"
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                        else:
                            msg = f'bitget close_spot_by_order 平仓成功 {info.to_json()}'
                            logger.info(msg)
                            await DataStore.del_orderinfo(info)
                            await TGBot.send_close_msg(msg)
                    else:
                        result = await self.sdk.close_spot_order_by_market(info.symbol, info.size)
                        if isinstance(result, str):
                            msg = f"bitget sdk close_spot_order_by_market 失败:info={info.to_json()} err={result}"
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                        else:
                            msg = f'bitget close_spot_by_order 平仓成功 {info.to_json()}'
                            logger.info(msg)
                            await DataStore.del_orderinfo(info)
                            if len(info.sl_id) > 0:
                                await self.sdk.cancel_spot_plan_order(info.sl_id)
                            if len(info.tp_id) > 0:
                                await self.sdk.cancel_spot_plan_order(info.tp_id)
                            await TGBot.send_close_msg(msg)
                else:
                    msg = f"bitget sdk query_spot_order_info 订单状态已取消 无法关闭:info={info.to_json()} status={orderInfo.status}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
        return True

    async def close_spot_by_pos(self, symbol) -> bool:
        del_list = []
        symbol = utils.get_spot_symbol(symbol, self.exdata.ex)
        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.isswap == False and i.status == Const.ORDER_STATUS_FILLED:

                if len(i.subPosId) > 0:
                    result = await self.sdk.close_spot_order_by_copytrader(i.symbol, i.subPosId)
                    if isinstance(result, str):
                        msg = f"bitget sdk close_spot_order_by_copytrader 现货带单平仓失败:info={i.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        del_list.append(i)
                        msg = f'bitget close_spot_by_pos 平仓成功 {i.to_json()}'
                        logger.info(msg)
                        await TGBot.send_close_msg(msg)
                else:
                    result = await self.sdk.close_spot_order_by_market(i.symbol, i.size)
                    if isinstance(result, str):
                        msg = f"bitget sdk close_spot_order_by_market 现货平仓失败:info={i.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        msg = f'bitget close_spot_by_pos 平仓成功 {i.to_json()}'
                        logger.info(msg)
                        if len(i.sl_id) > 0:
                            await self.sdk.cancel_spot_plan_order(i.sl_id)
                        if len(i.tp_id) > 0:
                            await self.sdk.cancel_spot_plan_order(i.tp_id)
                        del_list.append(i)
                        await TGBot.send_close_msg(msg)
        await DataStore.del_orderinfo(del_list)
        return True

    # SLTPMarketDB:
    async def set_spot_sltp_by_pos(self, symbol, sl, tp) -> bool:
        symbol = utils.get_spot_symbol(symbol, self.exdata.id)
        for i in DataStore.order_info[self.exdata.id]:
            if i.isswap == False and i.symbol == symbol and i.status == Const.ORDER_STATUS_FILLED:
                try:
                    await self.set_spot_sltp_by_order(i.id, sl, tp)
                except:
                    pass
        return True

    async def set_spot_sltp_by_order(self, id, sl, tp) -> OrderInfoDB:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"bitget controller set_spot_sltp_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if info.status == Const.ORDER_STATUS_FILLED:
            if self.sdk.spot_copytrader:
                result = await self.sdk.set_spot_sltp_by_copytrader(info.subPosId, sl, tp)
                if isinstance(result, str):
                    msg = f"bitget sdk set_spot_sltp_by_copytrader 设置现货带单止盈止损失败 info={info.to_json()} err={result} "
                    logger.error(msg)
                    info.sl = sl
                    info.tp = tp
                    info.sltp_status = Const.SLTP_STATUS_READY
                    await DataStore.update_orderinfo(info)
                    await TGBot.send_err_msg(msg)
                else:
                    info.sl = sl
                    info.tp = tp
                    if sl > 0 or tp > 0:
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                    else:
                        info.sltp_status = Const.SLTP_STATUS_NONE
                    await DataStore.update_orderinfo(info)
            else:
                if len(info.sl_id) > 0:
                    result = await self.sdk.cancel_spot_plan_order(i.symbol, i.sl_id)
                    if isinstance(result, str):
                        msg = f"bitget sdk cancel_spot_plan_order 现货删除止损订单失败:info={info.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sl = 0
                        info.sl_id = ''
                        info.sltp_status = Const.SLTP_STATUS_NONE
                        await DataStore.update_orderinfo(info)
                if len(info.tp_id) > 0:
                    result = await self.sdk.cancel_spot_plan_order(i.symbol, i.tp_id)
                    if isinstance(result, str):
                        msg = f"bitget sdk cancel_spot_plan_order 现货删除止盈订单失败:info={info.to_json()} err={result}"
                        logger.error(msg)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.tp = 0
                        info.tp_id = ''
                        info.sltp_status = Const.SLTP_STATUS_NONE
                        await DataStore.update_orderinfo(info)
                if sl > 0:
                    result = await self.sdk.set_spot_sl(info.symbol, info.size, sl)
                    if isinstance(result, str):
                        msg = f"bitget sdk set_spot_sl 现货设置订单止损失败:info={info.to_json()} err={result}"
                        logger.error(msg)
                        info.sl = sl
                        info.sltp_status = Const.SLTP_STATUS_READY
                        await DataStore.update_orderinfo(info)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sl = sl
                        info.sl_id = result[0]
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(info)
                if tp > 0:
                    result = await self.sdk.set_spot_tp(info.symbol, info.size, tp)
                    if isinstance(result, str):
                        msg = f"bitget sdk set_spot_tp 现货设置订单止盈失败:info={info.to_json()} err={result}"
                        logger.error(msg)
                        info.tp = tp
                        info.sltp_status = Const.SLTP_STATUS_READY
                        await DataStore.update_orderinfo(info)
                        await TGBot.send_err_msg(msg)
                    else:
                        info.sltp_status = Const.SLTP_STATUS_FINISH
                        info.tp = tp
                        info.tp_id = result[0]
                        await DataStore.update_orderinfo(info)
        else:
            info.sl = sl
            info.tp = tp
            if sl > 0 or tp > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
            else:
                info.sltp_status = Const.SLTP_STATUS_NONE
            await DataStore.update_orderinfo(info)
        return info
