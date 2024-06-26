import asyncio
import math
from fastapi import HTTPException
import schedule
from HttpListener import Status
import TGBot
from log import logger
from Controller import Controller
from ExchangeDao import ExchangeDb
from OrderInfoDao import OrderInfoDB
from sdk.BinanceSdk import BinanceSdk
import utils
import DataStore
from sdk.OrderClass import AccountInfo, OrderInfo
import Const
import MovingAssetDao
from MovingAssetDao import MovingAssetDB
import datetime


class BinanceController(Controller):
    def __init__(self, exdata: ExchangeDb) -> None:
        super().__init__(exdata)
        self.sdk = BinanceSdk(
            exdata.apikey, exdata.api_secret, exdata.api_password)
        self.exdata = exdata
        self.job = None
        self.check_profit = False
        # movingdata=none时资金在future，不等于空时资金在理财
        self.movingData: MovingAssetDB = None
        self.simpleearnId: str = None

    async def init(self):
        self.movingData = await MovingAssetDao.MovingAssetDB_query(self.exdata.id)
        result = await self.sdk.get_simple_earn_id()
        if isinstance(result, str):
            msg = f"binance sdk 没有申购活期的usdt产品"
            logger.error(msg)
        else:
            self.simpleearnId = result[0]
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
                if len(remaining_elements) > 0:
                    btc = await self.sdk.request_spot_price("BTCUSDT")
                    spot_total_price = 0
                    if isinstance(btc, float):
                        for i in remaining_elements:
                            i.unrealizedPL = i.unrealizedPL*btc
                            spot_total_price += i.unrealizedPL
                    filtered_elements[0].unrealizedPL = spot_total_price
            else:
                spot_acc.total = 0
                spot_acc.available = 0
                spot_acc.unrealizedPL = 0

                DataStore.spot_positions[self.exdata.id] = spot_list
                if len(spot_list) > 0:
                    btc = await self.sdk.request_spot_price("BTCUSDT")
                    spot_total_price = 0
                    if isinstance(btc, float):
                        for i in spot_list:
                            i.unrealizedPL = i.unrealizedPL*btc
                            spot_total_price += i.unrealizedPL
                        spot_acc.unrealizedPL = spot_total_price

        else:
            DataStore.spot_positions[self.exdata.id].clear()
        swap_list = await self.sdk.request_swap_positions()
        if isinstance(swap_list, list):
            DataStore.swap_positions[self.exdata.id] = swap_list

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
        for ord in DataStore.order_info[self.exdata.id]:
            if ord.isswap:
                server_info = await self.sdk.query_swap_order_info(ord.symbol, ord.orderId)
                if not isinstance(server_info, str):
                    self.update_orderdb(
                        update_list, del_list, ord, server_info)
                if ord.status == Const.ORDER_STATUS_FILLED:
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
                        if len(ord.sl_id) > 0:
                            result = await self.sdk.query_swap_order_info(ord.symbol, ord.sl_id)
                            if not isinstance(result, str):
                                if result.status != Const.ORDER_STATUS_LIVE:
                                    del_list.add(ord)
                        if len(ord.tp_id) > 0:
                            result = await self.sdk.query_swap_order_info(ord.symbol, ord.tp_id)
                            if not isinstance(result, str):
                                if result.status != Const.ORDER_STATUS_LIVE:
                                    del_list.add(ord)
                                if result.status == Const.ORDER_STATUS_FILLED and DataStore.json_conf['TransferProfit'] > 0:
                                    self.check_profit = True
                                    asyncio.create_task(
                                        self.get_swap_pnl(ord.symbol, ord.tp_id))
            else:
                server_info = await self.sdk.query_spot_order_info(ord.symbol, ord.orderId)
                if not isinstance(server_info, str):
                    self.update_orderdb(
                        update_list, del_list, ord, server_info)
                if ord.status == Const.ORDER_STATUS_FILLED:
                    if ord.sltp_status == Const.SLTP_STATUS_READY:
                        if ord.sl > 0:
                            result = await self.sdk.set_spot_sl(ord.symbol, ord.size, ord.sl, False)
                            if not isinstance(result, str):
                                ord.sl_id = result[0]
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                update_list.add(ord)
                        if ord.tp > 0:
                            result = await self.sdk.set_spot_tp(ord.symbol, ord.size, ord.tp, False)
                            if not isinstance(result, str):
                                ord.sltp_status = Const.SLTP_STATUS_FINISH
                                ord.tp_id = result[0]
                                update_list.add(ord)
                    elif ord.sltp_status == Const.SLTP_STATUS_FINISH:
                        if ord.sl > 0 and len(ord.sl_id) > 0:
                            result = await self.sdk.query_spot_order_info(ord.symbol, ord.sl_id)
                            if not isinstance(result, str):
                                if result.status != Const.ORDER_STATUS_LIVE:
                                    del_list.add(ord)
                        if ord.tp > 0 and len(ord.tp_id) > 0:
                            result = await self.sdk.query_spot_order_info(ord.symbol, ord.tp_id)
                            if not isinstance(result, str):
                                if result.status != Const.ORDER_STATUS_LIVE:
                                    del_list.add(ord)
        if len(update_list) > 0:
            await DataStore.update_orderinfo(update_list)
        if len(del_list) > 0:
            await DataStore.del_orderinfo(del_list)
        # 当开启无仓位转移资金到理财时，检查理财产品id，可用资金与全部资金是否相等，转移利润是否完成。
        if self.movingData == None and self.check_profit == False and self.simpleearnId != None and math.floor(swap_acc.available*1000) == math.floor(swap_acc.total*1000) and swap_acc.unrealizedPL == 0 and self.exdata.no_move_asset == False and swap_acc.total > 1 and len(swap_list) == 0:
            await self.move_asset_to_simpleearn(math.floor(swap_acc.total*10**2)/10**2)

################################################### swap#############################################################################################################

    async def _make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int) -> OrderInfoDB:
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        if symbol not in BinanceSdk.swap_baseinfo:
            msg = f"binance sdk 没有{symbol}这个交易对"
            logger.error(msg)

            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if self.movingData != None and self.exdata.no_move_asset == False and self.simpleearnId != None:
            await self.move_asset_to_future()
        size = 0
        if orderType == Const.ORDER_TYPE_MARKET:
            mark_price = await self.sdk.request_swap_price(symbol)
            if isinstance(mark_price, str):
                msg = f"binance make_swap_order 请求价格失败:{mark_price}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            size = self.sdk.count_pos_by_price(
                self.sdk.swap_baseinfo[symbol], money, mark_price, DataStore.json_conf['LEVERAGE'])
        else:
            size = self.sdk.count_pos_by_price(
                self.sdk.swap_baseinfo[symbol], money, price, DataStore.json_conf['LEVERAGE'])
        order_result = await self.sdk.make_swap_order(symbol, size, posSide, orderType, price)
        if isinstance(order_result, str):
            msg = f"binance make_swap_order 下单失败:{order_result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        else:
            info = OrderInfoDB()
            info.exId = self.exdata.id
            info.orderId = order_result[0]
            info.posSide = posSide
            info.size = size
            info.isswap = True
            info.symbol = symbol
            info.orderType = orderType
            info.marginMode = 'cross'
            return info

    async def make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str):

        info = await self._make_swap_order(symbol, money, posSide, price, orderType)
        info.orderFrom = orderFrom
        info.sl = sl
        info.tp = tp
        await DataStore.insert_orderinfo(info)
        msg = f'binance make_swap_order 下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if orderType == Const.ORDER_TYPE_LIMIT:
            if sl > 0 or tp > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)
        else:
            if sl > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)
                result = await self.sdk.set_swap_sl(info.symbol, info.size, info.posSide, sl, False)
                if isinstance(result, str):
                    msg = f"binance controller set_swap_sl 错误 info={info.to_json()} err={result} "
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    info.sl_id = result[0]
                    info.sltp_status = Const.SLTP_STATUS_FINISH
                    await DataStore.update_orderinfo(info)
            if tp > 0:
                info.sltp_status = Const.SLTP_STATUS_READY
                await DataStore.update_orderinfo(info)
                result = await self.sdk.set_swap_tp(info.symbol, info.size, info.posSide, tp, False)
                if isinstance(result, str):
                    msg = f"binance controller set_swap_tp 错误 info={info.to_json()} err={result} "
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    info.tp_id = result[0]
                    info.sltp_status = Const.SLTP_STATUS_FINISH
                    await DataStore.update_orderinfo(info)

        return info

    # 通过订单手动平仓或关闭订单
    async def close_swap_by_order(self, id) -> bool:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"binance controller close_swap_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        orderInfo = await self.sdk.query_swap_order_info(info.symbol, info.orderId)
        if isinstance(orderInfo, str):
            msg = f"binance query_swap_order_info 未找到相关订单信息:orderId={info.orderId} err={orderInfo} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if orderInfo.status == Const.ORDER_STATUS_FILLED:
            result = await self.sdk.close_swap_order_by_market(info.symbol, info.size, info.posSide)
            if isinstance(result, str):
                msg = f"binance close_swap_by_order  平仓失败 info={info.to_json()} result={result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                msg = f'binance close_swap_by_order  平仓成功 {info.to_json()} '
                logger.info(msg)
                await TGBot.send_close_msg(msg)
                if len(info.sl_id) > 0:
                    await self.sdk.cancel_swap_order(info.symbol, info.sl_id)
                if len(info.tp_id) > 0:
                    await self.sdk.cancel_swap_order(info.symbol, info.tp_id)
                if DataStore.json_conf['TransferProfit'] > 0:
                    self.check_profit = True
                    asyncio.create_task(
                        self.get_swap_pnl(info.symbol, result[0]))
        elif orderInfo.status == Const.ORDER_STATUS_LIVE:

            result = await self.sdk.cancel_swap_order(info.symbol, info.orderId)
            if isinstance(result, str):
                msg = f"binance close_swap_by_order 关闭订单失败 info={info.to_json()} result={result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                msg = f'binance close_swap_by_order 订单取消成功 {info.to_json()}'
                logger.info(msg)
                await TGBot.send_close_msg(msg)
                if len(info.sl_id) > 0:
                    await self.sdk.cancel_swap_order(info.symbol, info.sl_id)
                if len(info.tp_id) > 0:
                    await self.sdk.cancel_swap_order(info.symbol, info.tp_id)

        else:
            msg = f"binance query_swap_order_info 当前订单状态为 status={orderInfo.status} 无法手动关闭"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        await DataStore.del_orderinfo(info)
        return True
    # 通过仓位手动全部平仓

    async def close_swap_by_pos(self, symbol, posSide) -> bool:
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        del_info_list = []
        size=0
        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.posSide == posSide and i.isswap and i.status == Const.ORDER_STATUS_FILLED:
                size +=i.size
                del_info_list.append(i)
               
        if len(del_info_list)>0:
            result = await self.sdk.close_swap_order_by_market(symbol, size, posSide)
            if isinstance(result, str):
                msg = f"binance close_swap_by_pos {symbol}平仓失败   err={result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
            else:
                msg = f'binance close_swap_by_pos {symbol}平仓成功'
                logger.info(msg)
                await TGBot.send_close_msg(msg)
                
                for i in del_info_list:
                    if len(i.tp_id) > 0:
                        await self.sdk.cancel_swap_order(i.symbol, i.tp_id)
                    if len(i.sl_id) > 0:
                        await self.sdk.cancel_swap_order(i.symbol, i.sl_id)
                if DataStore.json_conf['TransferProfit'] > 0:
                    self.check_profit = True
                    asyncio.create_task(
                        self.get_swap_pnl(symbol, result[0]))
            await DataStore.del_orderinfo(del_info_list)

        return True
    # 设置仓位的止盈止损

    # SLTPMarketDB:
    async def set_swap_sltp_by_pos(self, symbol, posSide, sl, tp) -> bool:
        symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
        for i in DataStore.order_info[self.exdata.id]:
            if i.symbol == symbol and i.isswap and i.posSide == posSide and i.status == Const.ORDER_STATUS_FILLED:

                if len(i.sl_id) > 0:
                    await self.sdk.cancel_swap_order(i.symbol, i.sl_id)
                    i.sl = 0
                    i.sl_id = ''
                    i.sltp_status = Const.SLTP_STATUS_NONE
                    await DataStore.update_orderinfo(i)
                if len(i.tp_id) > 0:
                    await self.sdk.cancel_swap_order(i.symbol, i.tp_id)
                    i.tp = 0
                    i.tp_id = ''
                    i.sltp_status = Const.SLTP_STATUS_NONE
                    await DataStore.update_orderinfo(i)
                if sl > 0:
                    result = await self.sdk.set_swap_sl(i.symbol, i.size, i.posSide, sl, False)
                    if isinstance(result, str):
                        msg = f"binance set_swap_sl 失败 symbol={symbol} posSide={posSide} size={i.size}  result={result}"
                        logger.error(msg)
                        i.sl = sl
                        i.sltp_status = Const.SLTP_STATUS_READY
                        await DataStore.update_orderinfo(i)
                        await TGBot.send_err_msg(msg)
                    else:
                        i.sl = sl
                        i.sl_id = result[0]
                        i.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(i)
                if tp > 0:
                    result = await self.sdk.set_swap_tp(i.symbol, i.size, i.posSide, tp, False)
                    if isinstance(result, str):
                        msg = f"binance set_swap_tp 失败 symbol={symbol} posSide={posSide} size={i.size}  result={result}"
                        logger.error(msg)
                        i.tp = tp
                        i.sltp_status = Const.SLTP_STATUS_READY
                        await DataStore.update_orderinfo(i)
                        await TGBot.send_err_msg(msg)
                    else:
                        i.tp = tp
                        i.tp_id = result[0]
                        i.sltp_status = Const.SLTP_STATUS_FINISH
                        await DataStore.update_orderinfo(i)

        return True
    # 设置订单的止盈止损

    async def set_swap_sltp_by_order(self, id, sl, tp) -> OrderInfoDB:
        # 判断订单状态，状态为1时，如果是交易员，通过交易员接口修改止盈止损，如果是普通用户，则先删除再重建止盈止损
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"binance set_swap_sltp_by_order 未找到ID={id}的订单"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        order_info = await self.sdk.query_swap_order_info(info.symbol, info.orderId)
        if isinstance(order_info, str):
            msg = f"binance query_swap_order_info 未找到ID={info.orderId}的订单 result={order_info}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if order_info.status == Const.ORDER_STATUS_FILLED:
            if len(info.sl_id) > 0:
                await self.sdk.cancel_swap_order(info.symbol, info.sl_id)
                info.sl = 0
                info.sl_id = ''
                info.sltp_status = Const.SLTP_STATUS_NONE
                await DataStore.update_orderinfo(i)
            if len(info.tp_id) > 0:
                await self.sdk.cancel_swap_order(info.symbol, info.tp_id)
                info.tp = 0
                info.tp_id = ''
                info.sltp_status = Const.SLTP_STATUS_NONE
                await DataStore.update_orderinfo(i)
            if sl > 0:
                result = await self.sdk.set_swap_sl(info.symbol, info.size, info.posSide, sl, False)
                if isinstance(result, str):
                    msg = f"binance set_swap_sl 错误 info={info.to_json()} sl={sl}  result={result}"
                    logger.error(msg)
                    i.sl = sl
                    i.sltp_status = Const.SLTP_STATUS_READY
                    await DataStore.update_orderinfo(i)
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
                    msg = f"binance set_swap_tp 错误 info={info.to_json()} tp={tp}  result={result}"
                    logger.error(msg)
                    i.tp = tp
                    i.sltp_status = Const.SLTP_STATUS_READY
                    await DataStore.update_orderinfo(i)
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
            msg = f"binance set_swap_sltp_by_order 错误 info={info.to_json()} 当前订单状态为{order_info.status} 不能设置止盈止损"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        return info

    async def get_swap_pnl(self, symbol: str, orderId: str):
        await asyncio.sleep(2)
        pnl = await self.sdk.get_swap_pnl_history(symbol, orderId)
        if isinstance(pnl, float):
            if pnl > 0:
                _pnl = math.floor(pnl*DataStore.json_conf['TransferProfit'] * 10**4) / 10**4
                result = await self.sdk.transfer(1, 0, _pnl)
                if isinstance(result, tuple):
                    msg = f"binance symbol={symbol} 盈利 {pnl} 划转 {_pnl} 到现金账户 tranId={result[0]}"
                    logger.info(msg)
                    if self.simpleearnId != None:
                        result = await self.sdk.move_to_simple_earn(self.simpleearnId, _pnl)
                        if isinstance(result, str):
                            msg = f"binance get_swap_pnl 申购活期理财 {_pnl} 失败  err={result}"
                            logger.error(msg)
                            await TGBot.send_err_msg(msg)
                        else:
                            msg = f"binance get_swap_pnl 申购活期理财 {_pnl} 成功 transid={result}"
                            logger.info(msg)
                else:
                    msg = f"binance symbol={symbol} 盈利 {pnl} 划转 {_pnl} 到现金账户失败  err={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
        else:
            msg = f"binance get_swap_pnl_history 错误 symbol={symbol} orderId={orderId} err={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
        self.check_profit = False

################################################### SPOT#############################################################################################################
    async def _make_spot_order(self, symbol: str, money: float, price: float, orderType: int):
        symbol = utils.get_spot_symbol(symbol, self.exdata.ex)
        if symbol not in BinanceSdk.spot_baseinfo:
            msg = f"binance sdk 没有{symbol}这个交易对"
            logger.error(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        size = 0
        if orderType == Const.ORDER_TYPE_MARKET:
            mark_price = await self.sdk.request_spot_price(symbol)
            if isinstance(mark_price, str):
                msg = f"binance sdk request_spot_price 交易所请求价格失败:symbol={symbol} err={mark_price} "
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)

            size = self.sdk.count_pos_by_price(
                self.sdk.swap_baseinfo[symbol], money, mark_price, 1)
        else:
            size = self.sdk.count_pos_by_price(
                self.sdk.swap_baseinfo[symbol], money, price, 1)
        result = await self.sdk.make_spot_order(symbol, size, orderType, price)
        if isinstance(result, str):
            msg = f"binance sdk _make_spot_order 下单失败:symbol={symbol} size={size} err={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        db = OrderInfoDB()
        db.exId = self.exdata.id
        db.orderId = result[0]
        db.isswap = False
        db.size = size
        db.symbol = symbol
        db.orderType = orderType
        return db
    # 币安现货没有全仓止盈止损。只能在每个订单上设置止盈止损

    async def make_spot_order(self, symbol: str, money: float, price: float, orderType: int, sl: float, tp: float, sltp_type: int, orderFrom: str) -> OrderInfoDB:
        info = await self._make_spot_order(symbol, money, price, orderType)
        info.orderFrom = orderFrom
        await DataStore.insert_orderinfo(info)
        msg = f'binance spot 开仓下单成功 {info.to_json()}'
        logger.info(msg)
        await TGBot.send_open_msg(msg)
        if sl <= 0 and tp <= 0:
            return info
        info.sl = sl
        info.tp = tp
        if orderType == Const.ORDER_TYPE_LIMIT:
            info.sltp_status = Const.SLTP_STATUS_READY
            await DataStore.update_orderinfo(info)
        else:
            if sl > 0:
                result = await self.sdk.set_spot_sl(info.symbol, info.size, sl)
                if isinstance(result, str):
                    msg = f"binance controller set_spot_sl 设置订单止损失败 info={info.to_json()} err={result} "
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    info.sltp_status = Const.SLTP_STATUS_FINISH
                    await DataStore.update_orderinfo(info)
            if tp > 0:
                result = await self.sdk.set_spot_tp(info.symbol, info.size, tp)
                if isinstance(result, str):
                    msg = f"binance controller set_spot_tp 设置订单止盈失败 info={info.to_json()} err={result} "
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                    raise HTTPException(
                        status_code=Status.ExchangeError.value, detail=msg)
                else:
                    info.sltp_status = Const.SLTP_STATUS_FINISH
                    await DataStore.update_orderinfo(info)
        return info

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
            msg = f"binance controller set_spot_sltp_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)

        if info.status == Const.ORDER_STATUS_FILLED:
            if len(info.sl_id) > 0:
                result = await self.sdk.cancel_spot_order(info.symbol, info.sl_id)
                if isinstance(result, str):
                    msg = f"binance controller cancel_spot_order 删除订单止损错误 info={info.to_json()} error={result} "
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                else:
                    info.sl = 0
                    info.sl_id = ''
                    info.sltp_status = Const.SLTP_STATUS_NONE
                    await DataStore.update_orderinfo(info)
            if len(info.tp_id) > 0:
                result = await self.sdk.cancel_spot_order(info.symbol, info.tp_id)
                if isinstance(result, str):
                    msg = f"binance controller cancel_spot_order 删除订单止盈错误 info={info.to_json()} error={result} "
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
                    msg = f"binance controller set_spot_sl 设置订单止损错误 info={info.to_json()} error={result} "
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
                    msg = f"binance controller set_spot_tp 设置订单止盈错误 info={info.to_json()} error={result} "
                    logger.error(msg)
                    info.tp = tp
                    info.sltp_status = Const.SLTP_STATUS_READY
                    await DataStore.update_orderinfo(info)
                    await TGBot.send_err_msg(msg)
                else:
                    info.tp = tp
                    info.tp_id = result[0]
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

    async def close_spot_by_order(self, id) -> bool:
        info: OrderInfoDB = None
        for i in DataStore.order_info[self.exdata.id]:
            if i.id == id:
                info = i
                break
        if info is None:
            msg = f"biinance close_spot_by_order 未找到相关id={id} "
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        orderInfo = await self.sdk.query_spot_order_info(info.symbol, info.orderId)
        if isinstance(orderInfo, str):
            msg = f"binance sdk query_spot_order_info 未找到相关订单信息:info={info.to_json()} result={orderInfo}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            raise HTTPException(
                status_code=Status.ExchangeError.value, detail=msg)
        if orderInfo.status == Const.ORDER_STATUS_LIVE:
            result = await self.sdk.cancel_spot_order(info.symbol, info.orderId)
            if isinstance(result, str):
                msg = f"binance sdk cancel_spot_order 删除订单失败:info={info.to_json()} result={result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                await DataStore.del_orderinfo(info)
                msg = f"binance sdk cancel_spot_order 删除订单成功:info={info.to_json()}"
                logger.info(msg)
                await TGBot.send_close_msg(msg)
        elif orderInfo.status == Const.ORDER_STATUS_FILLED:
            result = await self.sdk.close_spot_order_by_market(info.symbol, info.size_exec)
            if isinstance(result, str):
                msg = f"binance sdk close_spot_by_order 订单市价平仓失败:info={info.to_json()} result={result}"
                logger.error(msg)
                await TGBot.send_err_msg(msg)
                raise HTTPException(
                    status_code=Status.ExchangeError.value, detail=msg)
            else:
                msg = f'binance close_spot_by_order  平仓成功 {info.to_json()} '
                logger.info(msg)
                await DataStore.del_orderinfo(info)
                await TGBot.send_close_msg(msg)
                if len(info.sl_id) > 0:
                    result = await self.sdk.cancel_spot_order(info.symbol, info.sl_id)
                    if isinstance(result, str):
                        msg = f"binance sdk cancel_spot_order 删除订单止损失败:info={info.to_json()} result={result}"
                        logger.error(msg)
                if len(info.tp_id) > 0:
                    result = await self.sdk.cancel_spot_order(info.symbol, info.tp_id)
                    if isinstance(result, str):
                        msg = f"binance sdk cancel_spot_order 删除订单止盈失败:info={info.to_json()} result={result}"
                        logger.error(msg)
        else:
            msg = f"binance sdk query_spot_order_info 订单状态已取消 无法关闭:info={info.to_json()} status={orderInfo.status}"
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
                result = await self.sdk.close_spot_order_by_market(i.symbol, i.size)
                if isinstance(result, str):
                    msg = f"binance sdk close_spot_order_by_market 现货平仓失败:info={i.to_json()} result={result}"
                    logger.error(msg)
                    await TGBot.send_err_msg(msg)
                else:
                    msg = f'binance close_spot_by_pos 平仓成功 {i.to_json()}'
                    logger.info(msg)
                    await TGBot.send_close_msg(msg)
                    if len(i.sl_id) > 0:
                        await self.sdk.cancel_spot_order(i.symbol, i.sl_id)
                    if len(i.tp_id) > 0:
                        await self.sdk.cancel_spot_order(i.symbol, i.tp_id)
                    del_list.append(i)
        await DataStore.del_orderinfo(del_list)
        return True

    async def setlever(self, symbol: str, lever: int):
        if len(symbol) == 0:
            for i, v in BinanceSdk.swap_baseinfo.items():
                await self.sdk.setlever(i, lever)
                await asyncio.sleep(0.1)
        else:
            symbol = utils.get_swap_symbol(symbol, self.exdata.ex)
            await self.sdk.setlever(symbol, lever)
        return True

    async def move_asset_to_simpleearn(self, money: float):
        result = await self.sdk.transfer(1, 0, money)
        if isinstance(result, str):
            msg = f"binance move_asset_to_simpleearn 转移资金到现金账户失败: result={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            return
        await asyncio.sleep(0.1)
        result = await self.sdk.move_to_simple_earn(self.simpleearnId, money)
        if isinstance(result, str):
            msg = f"binance move_asset_to_simpleearn 申购活期理财失败: result={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            await self.sdk.transfer(0, 1, money)
            return
        else:
            msg = f"binance move_to_simple_earn 申购活期理财成功 资金为{money}"
            logger.info(msg)
        db = MovingAssetDB(
            exid=self.exdata.id, money=money, datetime=datetime.datetime.now(), transid=str(result))
        await MovingAssetDao.MovingAssetDB_Insert(db)
        self.movingData = db

    async def move_asset_to_future(self):
        result = await self.sdk.fedeem_simple_earn(self.simpleearnId, self.movingData.money)
        if isinstance(result, str):
            msg = f"binance move_asset_to_future 从活期理财提取资金{self.movingData.money}失败: result={result}"
            logger.error(msg)
            return
        else:
            msg = f"binance move_asset_to_future 从活期理财提取资金{self.movingData.money}成功 redeemId={result}"
            logger.info(msg)
        await asyncio.sleep(0.1)    
        result = await self.sdk.transfer(0, 1, self.movingData.money)
        if isinstance(result, str):
            msg = f"binance move_asset_to_future 转移资金{self.movingData.money}到合约账户失败: result={result}"
            logger.error(msg)
            await TGBot.send_err_msg(msg)
            await self.sdk.move_to_simple_earn(self.simpleearnId, self.movingData.money)
            return
        else:
            msg = f"binance move_asset_to_future 转移资金{self.movingData.money}到合约账户成功"
            logger.info(msg)
        self.movingData.isdelete = True
        await MovingAssetDao.MovingAssetDB_Update(self.movingData)
        self.movingData = None
        await asyncio.sleep(0.1) 
