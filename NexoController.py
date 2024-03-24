import asyncio
from typing import Dict, List
import schedule
from Controller import Controller
from ExchangeDao import ExchangeDb
from OrderInfoDao import OrderInfoDB
from sdk.NexoSdk import NexoSdk
import DataStore
from sdk.OrderClass import AccountInfo, OrderInfo
import Const
import utils
from log import logger
from fastapi import HTTPException
from HttpListener import Status
import TGBot
import copy


class NexoController(Controller):
    def __init__(self, exdata: ExchangeDb) -> None:
        super().__init__(exdata)
        self.sdk = NexoSdk(
            exdata.apikey, exdata.api_secret, exdata.api_password)
        self.exdata = exdata
        self.job = None
        self.job2 = None

    async def init(self):
        await self.every_min_task()
        self.job = schedule.every(DataStore.json_conf['DATA_REFRESH_TIME']).seconds.do(
            lambda: asyncio.create_task(self.every_min_task()))
        await self.sdk.request_baseinfo()
        self.job2 = schedule.every(2).hours.do(
            lambda: asyncio.create_task(self.sdk.request_baseinfo()))

    def cancel_job(self):
        schedule.cancel_job(self.job)
        schedule.cancel_job(self.job2)

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
        spot_acc = DataStore.spot_account[self.exdata.id]
        swap_acc = DataStore.swap_account[self.exdata.id]
        if isinstance(spot_list, list):
            filtered_elements = [
                element for element in spot_list if element.symbol == "USDT"]
            remaining_elements = [
                element for element in spot_list if element.symbol != "USDT"]
            if filtered_elements:
                swap_acc.available = filtered_elements[0].available
                swap_acc.symbol = filtered_elements[0].symbol
                swap_acc.total = filtered_elements[0].total
                swap_acc.unrealizedPL = filtered_elements[0].unrealizedPL
                spot_acc.available = 0
                spot_acc.symbol = filtered_elements[0].symbol
                spot_acc.total = 0
                DataStore.spot_positions[self.exdata.id] = remaining_elements
                if len(remaining_elements) > 0:

                    spot_total_price = 0
                    for i in remaining_elements:
                        result = await self.sdk.request_spot_price(f"{i.symbol}/USDT", i.total, 'sell')
                        if isinstance(result, tuple):
                            # 暂不清楚unrealizedPL的单位是usdt还是货币本身，目前当作货币本身增值部分，这里转化为usdt部分
                            i.unrealizedPL = i.unrealizedPL*result[0]
                            spot_total_price = spot_total_price + \
                                i.total*result[0]
                    # 此处的现金账户未实现盈利为所有现货价值
                    spot_acc.unrealizedPL = spot_total_price
            else:
                spot_acc.available = 0
                spot_acc.symbol = 0
                spot_acc.total = 0
                DataStore.spot_positions[self.exdata.id] = spot_list
                spot_total = 0.0
                for i in spot_list:
                    result = await self.sdk.request_spot_price(f"{i.symbol}/USDT", i.total, 'sell')
                    if isinstance(result, tuple):
                        # 暂不清楚unrealizedPL的单位是usdt还是货币本身，目前当作货币本身增值部分，这里转化为usdt部分
                        i.unrealizedPL = i.unrealizedPL*result[0]
                        spot_total += i.total*result[0]
                spot_acc.unrealizedPL = spot_total

        swap_list = await self.sdk.request_swap_positions()
        if isinstance(swap_list, list):
            DataStore.swap_positions[self.exdata.id] = swap_list
        else:
            DataStore.swap_positions[self.exdata.id].clear()

        del_list: set = set()
        update_list: set = set()

        for ord in DataStore.order_info[self.exdata.id]:
            if ord.isswap:
                pass
                # server_info=await self.sdk.query_swap_order_info(ord.symbol,ord.orderId)
                # if not isinstance(server_info,str):
                #     self.update_orderdb(update_list,del_list,ord,server_info)
                # if ord.status==Const.ORDER_STATUS_FILLED:

                #     if ord.sltp_status==Const.SLTP_STATUS_READY:
                #         if ord.sl>0 or ord.tp>0:
                #            pass
                #     elif ord.sltp_status==Const.SLTP_STATUS_FINISH:
                #         if ord.sl>0 or ord.tp>0:
                #             pass
            else:
                server_info = await self.sdk.query_spot_order_info(ord.orderId)
                if not isinstance(server_info, str):
                    self.update_orderdb(
                        update_list, del_list, ord, server_info)
                if ord.status == Const.ORDER_STATUS_FILLED:
                    if ord.sltp_status == Const.SLTP_STATUS_READY:
                        if ord.sl > 0 or ord.tp > 0:
                            result = await self.sdk.set_spot_sltp(ord.symbol, ord.size, ord.sl, ord.tp)
                            if not isinstance(result, str):
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                ord.sl_id = result[0]
                                update_list.add(ord)

                    elif ord.sltp_status == Const.SLTP_STATUS_FINISH:
                        result = await self.sdk.query_spot_order_info(ord.sl_id)
                        if not isinstance(result, str):
                            if result.status == Const.ORDER_STATUS_FILLED or result.status == Const.ORDER_STATUS_NULL:
                                del_list.add(ord)

        if len(update_list) > 0:
            await DataStore.update_orderinfo(update_list)
        if len(del_list) > 0:
            await DataStore.del_orderinfo(del_list)

    async def _make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int):
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        if symbol not in NexoSdk.swap_baseinfo:
            msg = f"nexo sdk 没有{symbol}这个交易对"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            size = 0
            if orderType == Const.ORDER_TYPE_MARKET:
                mark_price = await self.sdk.request_swap_price(symbol)
                if isinstance(mark_price, str):
                    msg = f"nexo make_swap_order 请求价格失败:{mark_price}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    size = self.sdk.count_pos_by_price(
                        1 / (10 ** self.sdk.swap_baseinfo[symbol]['amountPrecision']), money, mark_price, DataStore.json_conf['LEVERAGE'])
            else:
                size = self.sdk.count_pos_by_price(
                    1 / (10 ** self.sdk.swap_baseinfo[symbol]['amountPrecision']), money, price, DataStore.json_conf['LEVERAGE'])

            order_result = await self.sdk.make_swap_order(symbol, size, posSide, orderType, price)
            if isinstance(order_result, str):
                msg = f"nexo make_swap_order 下单失败:symbol={symbol} size={size} err={order_result}"
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
    # nexo 合约功能不完善，不支持订单状态查询，止盈止损设置，限价订单

    async def make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str):
        info = await self._make_swap_order(symbol, money, posSide, price, orderType)
        info.orderFrom = orderFrom
        info.sl = sl
        info.tp = tp
        await DataStore.insert_orderinfo(info)
        msg = f'nexo make_swap_order 下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if orderType == Const.ORDER_TYPE_MARKET:
            pass
            # if sl > 0:
            #     result =await self.sdk.set_swap_sl(
            #         info.symbol, info.size, info.posSide, sl, False)
            #     if isinstance(result, str):
            #         msg = f"bitget controller set_swap_sl 错误 info={info.to_json()} err={result} "
            #         logger.error(msg)
            #         await TGBot.send_err_msg(msg)
            #         raise HTTPException(
            #             status_code=Status.ExchangeError.value, detail=msg)
            #     else:
            #         info.sl_id = result[0]
            #         info.sltp_status = Const.SLTP_STATUS_FINISH
            #         await DataStore.update_orderinfo(info)
            # if tp > 0:
            #     result =await self.sdk.set_swap_tp(
            #         info.symbol, info.size, info.posSide, tp, False)
            #     if isinstance(result, str):
            #         msg = f"bitget controller set_swap_tp 错误 info={info.to_json()} err={result} "
            #         logger.error(msg)
            #         await TGBot.send_open_msg(msg)
            #         raise HTTPException(
            #             status_code=Status.ExchangeError.value, detail=msg)
            #     else:
            #         info.tp_id = result[0]
            #         info.sltp_status = Const.SLTP_STATUS_FINISH
            #         await DataStore.update_orderinfo(info)
        else:
            # 限价下单
            if sl > 0 or tp > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)
        return info

    async def close_swap_by_order(self, id):
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"nexo close_swap_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)

        else:
            await self.sdk.close_swap_order_by_market(info.symbol, info.size, info.posSide)
            await DataStore.del_orderinfo(info)
            # orderInfo = await self.sdk.query_swap_order_info(info.symbol, info.orderId)
            # if isinstance(orderInfo, str):
            #     msg = f"nexo query_swap_order_info 未找到相关订单信息:info={info.to_json()} err={orderInfo} "
            #     logger.error(msg)
            #     await TGBot.send_err_msg(msg)
            #     raise HTTPException(
            #         status_code=Status.ExchangeError.value, detail=msg)
            # else:
            #     if orderInfo.status == Const.ORDER_STATUS_FILLED:
            #         if self.sdk.swap_copytrader:
            #             if len(info.subPosId) > 0:
            #                 result = await self.sdk.close_swap_order_by_copytrader(info.subPosId)
            #                 if isinstance(result, str):
            #                     msg = f"nexo close_swap_by_order 平仓失败 info={info.to_json()} result={result}"
            #                     logger.error(msg)
            #                     await TGBot.send_err_msg(msg)
            #                     raise HTTPException(
            #                         status_code=Status.ExchangeError.value, detail=msg)
            #                 else:
            #                     msg=f'nexo close_swap_by_order 平仓成功 {info.to_json()}'
            #                     logger.info(msg)
            #                     await DataStore.del_orderinfo(info)
            #                     await TGBot.send_close_msg(msg)
            #             else:
            #                 msg = f"nexo close_swap_order subPosId为空 {info.to_json()}"
            #                 logger.error(msg)
            #                 await TGBot.send_err_msg(msg)
            #                 raise HTTPException(
            #                     status_code=Status.ExchangeError.value, detail=msg)
            #         else:
            #             result = await self.sdk.close_swap_order_by_market(info.symbol, info.size, info.posSide)
            #             if isinstance(result, str):
            #                 msg = f"nexo close_swap_order_by_market 平仓失败 info={info.to_json()} result={result}"
            #                 logger.error(msg)
            #                 await TGBot.send_err_msg(msg)
            #                 raise HTTPException(
            #                     status_code=Status.ExchangeError.value, detail=msg)
            #             else:
            #                 msg=f'nexo close_swap_by_order 平仓成功 {info.to_json()}'
            #                 logger.info(msg)
            #                 await DataStore.del_orderinfo(info)
            #                 if len(info.sl_id) > 0:
            #                     result = await self.sdk.cancel_swap_sl_order(info.symbol, info.sl_id, False)
            #                 if len(info.tp_id) > 0:
            #                     result = await self.sdk.cancel_swap_tp_order(info.symbol, info.tp_id, False)
            #                 await TGBot.send_close_msg(msg)
            #     elif orderInfo.status == Const.ORDER_STATUS_LIVE:

            #         result = await self.sdk.cancel_swap_order(info.symbol, info.orderId)
            #         if isinstance(result, str):
            #             msg = f"nexo cancel_swap_order 手动关闭订单失败 info={info.to_json()} result={result}"
            #             logger.error(msg)
            #             await TGBot.send_err_msg(msg)
            #             raise HTTPException(
            #                 status_code=Status.ExchangeError.value, detail=msg)
            #         else:
            #             msg=f'nexo close_swap_by_order 取消订单成功 {info.to_json()}'
            #             logger.info(msg)
            #             await DataStore.del_orderinfo(info)
            #             if len(info.sl_id) > 0:
            #                 result = await self.sdk.cancel_swap_sl_order(info.symbol, info.sl_id, False)
            #             if len(info.tp_id) > 0:
            #                 result = await self.sdk.cancel_swap_tp_order(info.symbol, info.tp_id, False)
            #             await TGBot.send_close_msg(msg)
            #     else:
            #         msg = f"nexo cancel_swap_order 当前订单状态为 status={orderInfo.status} 无法手动关闭"
            #         logger.error(msg)
            #         await TGBot.send_err_msg(msg)
            #         raise HTTPException(
            #             status_code=Status.ExchangeError.value, detail=msg)

        return True

    async def close_swap_by_pos(self, symbol, posSide):
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        del_info_list = []
        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.posSide == posSide and i.isswap:
                del_info_list.append(i)
                await self.sdk.close_swap_order_by_market(i.symbol, i.size, i.posSide)
        await DataStore.del_orderinfo(del_info_list)
        return True

    async def set_swap_sltp_by_pos(self, symbol, posSide, sl, tp) -> bool:
        pass

    async def set_swap_sltp_by_order(self, id, sl, tp):
        pass

################################################### SPOT#############################################################################################################

    async def _make_spot_order(self, symbol: str, money: float, price: float, orderType: int):
        symbol = utils.get_spot_symbol(symbol, self.exdata.ex)
        if symbol not in NexoSdk.spot_baseinfo:
            msg = f"nexo sdk 没有{symbol}这个交易对"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            size = 0
            if orderType == Const.ORDER_TYPE_MARKET:
                mark_price = await self.sdk.request_spot_price(symbol, 1, 'buy')
                if isinstance(mark_price, str):
                    msg = f"nexo sdk request_spot_price 交易所请求价格失败:{mark_price}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    size = self.sdk.count_pos_by_price(
                        self.sdk.spot_baseinfo[symbol], money, mark_price, 1)
            else:
                size = self.sdk.count_pos_by_price(
                    self.sdk.swap_baseinfo[symbol], money, price, 1)
            result = await self.sdk.make_spot_order(symbol, size, orderType, price)
            if isinstance(result, str):
                msg = f"nexo sdk _make_spot_order 下单失败:symbol={symbol} size={size} err={result}"
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

    async def make_spot_order(self, symbol: str, money: float, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str) -> OrderInfoDB:
        info = await self._make_spot_order(symbol, money, price, orderType)
        info.orderFrom = orderFrom
        if orderType == Const.ORDER_TYPE_MARKET:
            info.status = Const.ORDER_STATUS_FILLED
        await DataStore.insert_orderinfo(info)
        msg = f'nexo make_spot_order 下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if sl <= 0 and tp <= 0:
            return info
        await self.set_spot_sltp_by_order(info.id, sl, tp)

        return info

    async def close_spot_by_order(self, id) -> bool:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"nexo controller close_spot_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        result = await self.sdk.close_spot_order_by_market(info.symbol, info.size)
        if isinstance(result, str):
            msg = f"nexo sdk close_spot_order_by_market 现货市价卖出失败:info={info.to_json()} err={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
        else:
            await DataStore.del_orderinfo(info)
            msg = f'nexo close_spot_by_order 平仓成功 {i.to_json()}'
            await TGBot.send_close_msg(msg)

    async def close_spot_by_pos(self, symbol) -> bool:
        del_list = []
        symbol = utils.get_spot_symbol(symbol, self.exdata.ex)
        for i in DataStore.order_info[self.exdata.id]:
            if i.isswap == False and i.symbol == symbol and i.status == Const.ORDER_STATUS_FILLED:
                result = await self.sdk.close_spot_order_by_market(i.symbol, i.size)
                if isinstance(result, str):
                    msg = f"nexo sdk close_spot_order_by_market 现货市价卖出失败:info={i.to_json()} err={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                else:
                    del_list.append(i)
        if len(del_list) > 0:
            await DataStore.del_orderinfo(del_list)
            msg = f'nexo close_spot_by_pos {symbol} 平仓成功'
            await TGBot.send_close_msg(msg)

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
            msg = f"nexo controller set_spot_sltp_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if info.status == Const.ORDER_STATUS_FILLED:
            if len(info.sl_id) > 0:
                result = await self.sdk.cancel_spot_order(i.sl_id)
                if isinstance(result, str):
                    msg = f"nexo sdk cancel_spot_order 现货删除止损订单失败:info={info.to_json()} err={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                else:
                    info.sl = 0
                    info.tp = 0
                    info.sl_id = ''
                    info.sltp_status = Const.SLTP_STATUS_NONE
                    await DataStore.update_orderinfo(info)

            if sl > 0 or tp > 0:
                result = await self.sdk.set_spot_sltp(info.symbol, info.size, sl, tp)
                if isinstance(result, str):
                    msg = f"nexo sdk set_spot_sl 现货设置订单止损失败:info={info.to_json()} err={result}"
                    logger.error(msg)
                    info.sl = sl
                    info.tp = tp
                    info.sltp_status = Const.SLTP_STATUS_READY
                    await DataStore.update_orderinfo(info)
                    await TGBot.send_err_msg(msg)
                else:
                    info.sl = sl
                    info.tp = tp
                    info.sl_id = result[0]
                    info.sltp_status = Const.SLTP_STATUS_FINISH
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
