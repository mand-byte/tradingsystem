import DataStore
from log import logger
import Const
import re
import utils


async def make_tv_order(data):
    try:
        symbol = ''
        if data.ticker.endswith("USDT.P"):
            symbol = data.ticker[:-len('USDT.P')]

        if data.market_position == "flat":
            # 全平
            posside = ''
            if data.action == "sell":
                posside = 'long'
            else:
                posside = 'short'
            for _, value in DataStore.controller_list.items():
                if value.exdata.no_close == True:
                    continue
                try:
                    await value.close_swap_by_pos(symbol, posside)
                except:
                    pass

        elif (data.action == "buy" and data.market_position == "long") or (data.action == "sell" and data.market_position == "short"):
            # 开仓

            if data.tv_type == Const.ORDER_FROM_HUOXING:
                pattern = r'(\d+\.?\d*)'
                match = re.findall(pattern, data.comment)
                if match:
                    num = int(match[0])
                    tp = float(match[1])
                    for id, value in DataStore.controller_list.items():
                        if value.exdata.no_open == True:
                            continue
                        if DataStore.json_conf['Martin']['MAX_HUOXING_COUNT'] > 0:
                            sy = utils.get_swap_symbol(symbol, value.exdata.ex)
                            contian = False
                            count = set()
                            try:
                                for i in DataStore.order_info[id]:
                                    if i.isswap and i.symbol == sy and i.posSide == data.market_position:
                                        contian = True
                                        break
                                    if i.isswap and i.symbol != sy and i.posSide == data.market_position and i.orderFrom == Const.ORDER_FROM_HUOXING:
                                        count.add(i.symbol)
                                # 马丁同一方向最大只开n种不同标的单，除非已经开过单 或是马丁m以上
                                if (contian == False and len(count) < DataStore.json_conf['Martin']['MAX_HUOXING_COUNT']) or contian or num > DataStore.json_conf['Martin']['HUOXING_EXCEPT_NUM']:
                                    # 修改之前订单的止盈止损
                                    await value.set_swap_sltp_by_pos(symbol, data.market_position, 0, tp)
                                    if DataStore.json_conf['Martin']['HUOXING_INVEST_USE_RATIO']:
                                        money = DataStore.swap_account[id].total * \
                                            DataStore.json_conf['Martin']['HUOXING_RATIO_INVEST']*math.pow(
                                                1.618, num-1)
                                        await value.make_swap_order(symbol, money, data.market_position, float(data.price), Const.ORDER_TYPE_MARKET, 0, tp, Const.SLTP_TYPE_POS, data.tv_type)
                                    else:
                                        await value.make_swap_order(symbol, DataStore.json_conf['Martin']['HUOXING_FIXED_INVERST'][num-1], data.market_position, float(data.price), Const.ORDER_TYPE_MARKET, 0, tp, Const.SLTP_TYPE_POS, data.tv_type)
                            except Exception as e:
                                logger.error(
                                    f'tv {data.tv_type} make_swap_order err ={e}')
                        else:
                            try:
                                # 修改之前订单的止盈止损
                                await value.set_swap_sltp_by_pos(symbol, data.market_position, 0, tp)
                                import math
                                if DataStore.json_conf['Martin']['HUOXING_INVEST_USE_RATIO']:
                                    money = DataStore.swap_account[id].total * \
                                        DataStore.json_conf['Martin']['HUOXING_RATIO_INVEST']*math.pow(
                                            1.618, num-1)
                                    await value.make_swap_order(symbol, money, data.market_position, float(data.price), Const.ORDER_TYPE_MARKET, 0, tp, Const.SLTP_TYPE_POS, data.tv_type)
                                else:
                                    await value.make_swap_order(symbol, DataStore.json_conf['Martin']['HUOXING_FIXED_INVERST'][num-1], data.market_position, float(data.price), Const.ORDER_TYPE_MARKET, 0, tp, Const.SLTP_TYPE_POS, data.tv_type)
                            except Exception as e:
                                logger.error(
                                    f'tv {data.tv_type} make_swap_order err ={e}')

            elif data.tv_type == Const.ORDER_FROM_TREND:
                tp = 0
                sl = 0
                if DataStore.json_conf['Trend']['TREND_TP_RATIO'] > 0:
                    if data.action == "buy" and data.market_position == "long":
                        tp = round(
                            float(data.price)*(1+DataStore.json_conf['Trend']['TREND_TP_RATIO']), 1)
                    else:
                        tp = round(
                            float(data.price)*(1-DataStore.json_conf['Trend']['TREND_TP_RATIO']), 1)
                if DataStore.json_conf['Trend']['TREND_SL_RATIO'] > 0:
                    if data.action == "buy" and data.market_position == "long":
                        sl = round(
                            float(data.price)*(1-DataStore.json_conf['Trend']['TREND_SL_RATIO']), 1)
                    else:
                        sl = round(
                            float(data.price)*(1+DataStore.json_conf['Trend']['TREND_SL_RATIO']), 1)
                                
                for id, value in DataStore.controller_list.items():
                    try:
                        if DataStore.json_conf['Trend']['TREND_INVEST_USE_RATIO']:

                            money = DataStore.swap_account[id].total * \
                                DataStore.json_conf['Trend']['TREND_RATIO_INVEST']
                            await value.make_swap_order(symbol, money, data.market_position, float(data.price), Const.ORDER_TYPE_MARKET, sl, tp, Const.SLTP_TYPE_POS, data.tv_type)
                        else:
                            await value.make_swap_order(symbol, DataStore.json_conf['Trend']['TREND_FIXED_INVEST'], data.market_position, float(data.price), Const.ORDER_TYPE_MARKET, sl, tp, Const.SLTP_TYPE_POS, data.tv_type)
                    except Exception as e:
                        logger.error(
                            f'tv {data.tv_type} make_swap_order err ={e}')
            else:
                logger.error(
                    f"tvcontroller make_tv_order error tv_type={data.tv_type}")

        else:
            # 平掉单个仓位
            for id, con in DataStore.controller_list.items():
                if con.exdata.no_close == True:
                    continue
                s = utils.get_swap_symbol(symbol, con.exdata.ex)
                for v in DataStore.order_info[id]:
                    if v.isswap and s == v.symbol and v.status == Const.ORDER_STATUS_FILLED and v.posSide == data.market_position:
                        await con.close_swap_by_order(v.id)
                        break

    except Exception as e:
        logger.error(f'make_tv_order err ={e}')
