from typing import List
from .SDKBase import SDKBase
import datetime
import aiohttp
import json
from . import OrderClass


class BitgetSdk(SDKBase):
    name = "bitget"
    _rest = "https://api.bitget.com"
    spot_baseinfo={}
    swap_baseinfo={}
    def __init__(self, api_key: str, api_secret: str, api_password: str = None) -> None:
        super().__init__(api_key, api_secret, api_password)
        

    async def getConf(self):
        api = {
            "method": "GET",
            "url": "/api/v2/spot/account/info",
            "payload": {
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        self.spot_copytrader=False
        self.swap_copytrader=False
        if 'code' in result and result['code'] == "00000":
            if result['data']['traderType']=='trader':
                self.spot_copytrader=True
                self.swap_copytrader=True


    async def init(self):
    
        await self.getConf()

    async def request_swap_price(self, symbol):
        api = {
            "method": "GET",
            "url": "/api/v2/mix/market/symbol-price",
            "payload": {
                "symbol": symbol,
                "productType": "USDT-FUTURES"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            return float(result['data'][0]['price'])
        return response

    async def request_spot_price(self, symbol):
        api = {
            "method": "GET",
            "url": "/api/v2/spot/market/tickers",
            "payload": {
                "symbol": symbol
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            return float(result['data'][0]['lastPr'])
        return response
    @staticmethod
    async def request_baseinfo():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"{BitgetSdk._rest}/api/v2/mix/market/contracts?productType=usdt-futures") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if 'code' in result and result['code'] == "00000":
                        data = result['data']
                        BitgetSdk.swap_baseinfo.clear()
                        for d in data:
                            if d['offTime'] == '-1' and d['limitOpenTime'] == '-1':
                                BitgetSdk.swap_baseinfo[d['symbol']] = float(
                                    d['minTradeNum'])
        except Exception as e:
            print(f'bitget request_baseinfo swap err={e}')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"{BitgetSdk._rest}/api/v2/spot/public/symbols") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if 'code' in result and result['code'] == "00000":
                        data = result['data']
                        BitgetSdk.spot_baseinfo.clear()
                        for d in data:
                            if d['status'] == 'online':
                                q = int(d['quantityPrecision'])
                                if q == 0:
                                    BitgetSdk.spot_baseinfo[d['symbol']] = 1
                                else:
                                    min_precision = 10 ** (-q)
                                    BitgetSdk.spot_baseinfo[d['symbol']
                                                       ] = min_precision
        except Exception as e:
            print(f'bitget request_baseinfo spot err={e}')   

    async def send_request(self, api):
        headers = {
            "ACCESS-KEY": self.keyconf['apiKey'],
            "ACCESS-TIMESTAMP": "",
            "ACCESS-PASSPHRASE": self.keyconf['password'],
            "ACCESS-SIGN": "",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        current_time = str(int(datetime.datetime.now().timestamp()*1000))
        headers['ACCESS-TIMESTAMP'] = current_time
        method = api["method"]
        sign_str = None
        try:
            if method == "GET":
                params = self.praseParam(api['payload'])
                if len(params) == 0:
                    sign_str = f"{current_time}{method}{api['url']}"
                else:
                    sign_str = f"{current_time}{method}{api['url']}?{params}"
                headers['ACCESS-SIGN'] = self.get_sign(
                    self.keyconf['secret'], sign_str)
                url = f"{BitgetSdk._rest}{api['url']}?{params}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, headers=headers) as response:
                        return await response.text()
            elif method == "POST":
                if len(api['payload']) == 0:
                    sign_str = f"{current_time}{method}{api['url']}"
                else:
                    sign_str = f"{current_time}{method}{api['url']}{json.dumps(api['payload'])}"
                headers['ACCESS-SIGN'] = self.get_sign(
                    self.keyconf['secret'], sign_str)
                url = f"{BitgetSdk._rest}{api['url']}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, json=api['payload'], headers=headers) as response:
                        return await response.text()
        except Exception as e:
            return f'{{"e": "{e}"}}'

    async def request_swap_subpositions(self, symbol: str):
        api = {
            "method": "GET",
            "url": "/api/v2/copy/mix-trader/order-current-track",
            "payload": {
                "symbol": symbol,
                "productType": "USDT-FUTURES",
                "limit": 50
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            _result: List[OrderClass.OrderInfo] = []
            if 'trackingList' in result['data'] and result['data']['trackingList'] is not None:
                for i in result['data']['trackingList']:
                    subinfo = OrderClass.OrderInfo()
                    subinfo.orderId = i['openOrderId']
                    subinfo.symbol = i['symbol']
                    subinfo.subPosId = i['trackingNo']
                    subinfo.leverage = int(float(i['openLeverage']))
                    subinfo.openTime = datetime.datetime.fromtimestamp(
                        float(i['openTime']) / 1000.0)
                    subinfo.size = float(i['openSize'])
                    subinfo.tp = float(i['presetStopSurplusPrice']) if len(
                        i['presetStopSurplusPrice']) > 0 else 0.0
                    subinfo.sl = float(i['presetStopLossPrice']) if len(
                        i['presetStopLossPrice']) > 0 else 0.0
                    subinfo.posSide = i['posSide']
                    subinfo.priceAvg = i['openPriceAvg']
                    _result.append(subinfo)
            return _result
        else:
            return response

    async def request_spot_subpositions(self, symbol: str):
        api = {
            "method": "GET",
            "url": "/api/v2/copy/spot-trader/order-current-track",
            "payload": {
                "symbol": symbol,
                "productType": "USDT-FUTURES",
                "limit": 50
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            _result = []
            if 'trackingList' in result['data']:
                for i in result['data']['trackingList']:
                    subinfo = OrderClass.OrderInfo()
                    subinfo.orderId=i['openOrderId']
                    subinfo.symbol = i['symbol']
                    subinfo.subPosId = i['trackingNo']
                    # subinfo.leverage=int(i['openLeverage'])
                    subinfo.openTime = datetime.datetime.fromtimestamp(
                        float(i['buyTime']) / 1000.0)
                    subinfo.size = float(i['buyFillSize'])
                    subinfo.tp = float(i['stopSurplusPrice']) if len(
                        i['stopSurplusPrice']) > 0 else 0.0
                    subinfo.sl = float(i['stopLossPrice']) if len(
                        i['stopLossPrice']) > 0 else 0.0
                    # subinfo.posSide=i['posSide']
                    subinfo.priceAvg = float(i['buyPrice'])
                    _result.append(subinfo)
            return _result
        else:
            return response

    async def request_swap_positions(self):
        api = {
            "method": "GET",
            "url": "/api/v2/mix/position/all-position",
            "payload": {
                "marginCoin": 'usdt',
                "productType": "USDT-FUTURES"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            _result = []
            for i in result['data']:
                sp = OrderClass.SwapPostion()
                sp.leverage = int(float(i['leverage']))
                sp.symbol = i['symbol']
                sp.posSide = i['holdSide']
                sp.size = float(i['total'])
                sp.priceAvg = float(i['openPriceAvg'])
                sp.upl = float(i['unrealizedPL'])
                sp.marginMode = i['marginMode']
                sp.margin = float(i['marginSize'])
                _result.append(sp)
            return _result
        else:
            return response

    async def request_swap_account(self):
        api = {
            "method": "GET",
            "url": "/api/v2/mix/account/accounts",
            "payload": {
                "productType": "USDT-FUTURES"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            account = OrderClass.AccountInfo()
            account.symbol = 'USDT'
            for i in result['data']:
                if i['marginCoin'] == 'USDT':
                    account.available = float(i['crossedMaxAvailable'])
                    account.total = float(i['usdtEquity'])
                    account.unrealizedPL = float(i['unrealizedPL'])
            return account
        else:
            return response

    async def request_spot_positions(self):
        api = {
            "method": "GET",
            "url": "/api/v2/spot/account/assets",
            "payload": {
                "assetType": "hold_only"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            _result = []
            for i in result['data']:
                if i['available'] != '0':
                    account = OrderClass.AccountInfo()
                    account.symbol = i['coin']
                    account.available = float(i['available'])
                    account.total = account.available+float(i['frozen'])
                    if account.total==0:
                        continue
                    if account.symbol != 'USDT':
                        p = await self.request_spot_price(f'{account.symbol}USDT')
                        if not isinstance(p, str):
                            account.unrealizedPL = account.total*p
                            _result.append(account)
                        else:
                            account.unrealizedPL=0    
                    else:
                        account.unrealizedPL = account.total
                        _result.append(account)
                    
            return _result
        else:
            return response

    async def query_swap_order_info(self, symbol: str, orderId: str):
        api = {
            "method": "GET",
            "url": "/api/v2/mix/order/detail",
            "payload": {
                'symbol': symbol,
                "productType": "USDT-FUTURES",
                'orderId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            soi = OrderClass.OrderInfo()
            data = result['data']
            soi.leverage = int(float(data['leverage']))
            soi.marginMode = data['marginMode']
            soi.openTime = datetime.datetime.fromtimestamp(
                float(data['cTime']) / 1000.0)
            soi.symbol = symbol
            soi.orderId = orderId
            if data['state'] == "filled":
                soi.status = 1
                soi.size = float(data['baseVolume'])
            elif data['state'] == "partially_filled":
                soi.status = 2
                soi.size = float(data['baseVolume'])
            elif data['state'] == "live":
                soi.status = 0
            else:
                soi.status = -1
            soi.posSide = data['posSide']

            soi.priceAvg = float(data['priceAvg']) if len(
                data['priceAvg']) > 0 else 0.0
            soi.sl = float(data['presetStopLossPrice']) if len(
                data['presetStopLossPrice']) > 0 else 0.0
            soi.tp = float(data['presetStopSurplusPrice']) if len(
                data['presetStopSurplusPrice']) > 0 else 0.0
            soi.tradeSide = data['tradeSide']
            soi.orderSource = data['orderSource']
            return soi
        else:
            return response
    # 带止盈止损下单时，先记录到sl,tp到数据库，每次用时先query_swap_order_info查询这个订单的状态是否为0，如果为1则删除订单，重新创建，如果为0，则用query_swap_order_plan获取sl_id,tp_id再去modify_swap_tp_sl修改sl和tp,如果需要修改的话
    # 合约下单

    async def make_swap_order(self, symbol: str, size: float, posSide: str, orderType: int = 0, price: float = 0):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/order/place-order",
            "payload": {
                'symbol': symbol,
                "productType": "USDT-futures",
                'marginMode': 'crossed',
                'marginCoin': 'USDT',
                'size': str(size),
                'side': 'buy' if posSide == 'long' else 'sell',
                'tradeSide': 'open',
                'orderType': 'market' if orderType == 0 else 'limit',
                'force': 'gtc'
            }
        }
        if orderType == 1:
            api['payload']['price'] = str(price)

        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":

            return (result['data']['orderId'],)
        else:
            return response

    async def query_swap_order_plan(self, symbol: str, orderId: str):
        api = {
            "method": "GET",
            "url": "/api/v2/mix/order/orders-plan-pending",
            "payload": {
                "productType": "USDT-FUTURES",
                'symbol': symbol,
                'planType': 'profit_loss',
                'orderId': orderId
            }
        }
        
        response = await self.send_request(api)
        result = json.loads(response)

        if 'code' in result and result['code'] == "00000":
            soi = OrderClass.OrderInfo()
            soi.status = 1
            if 'entrustedList' in result['data'] and result['data']['entrustedList'] is not None:
                data = result['data']['entrustedList'][0]
                if data['planStatus'] == 'not_trigger' or data['planStatus'] == 'live':
                    soi.status = 0

            return soi
        else:
            return response
    async def set_swap_sl(self, symbol: str, size: float, holdSide: str, sl: float,ispos:bool):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/order/place-tpsl-order",
            "payload": {
                'marginCoin': 'USDT',
                "productType": "USDT-futures",
                'symbol': symbol,
                'triggerType': 'fill_price',
                'executePrice': '0',
                'holdSide': holdSide,
                'triggerPrice': str(sl)
            }
        }
        if ispos==False:
            api['payload']['size']=str(size)
            api['payload']['planType']='loss_plan'
        else:
            api['payload']['planType']='pos_loss'
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return (result['data']['orderId'],)
        else:
            return response

 
    async def set_swap_tp(self, symbol: str, size: float, holdSide: str, tp: float,ispos:bool):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/order/place-tpsl-order",
            "payload": {
                'marginCoin': 'USDT',
                "productType": "USDT-futures",
                'symbol': symbol,
                'triggerType': 'fill_price',
                'executePrice': '0',
                'holdSide': holdSide,
                'triggerPrice': str(tp)
            }
        }
        if ispos==False:
            api['payload']['size']=str(size)
            api['payload']['planType']='profit_plan'
        else:
            api['payload']['planType']='pos_profit'
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return (result['data']['orderId'],)
        else:
            return response
        
    async def get_swap_history_by_subpos(self,symbol:str,subPos):
        _subpos=''
        if isinstance(subPos,str):
            _subpos=subPos
        elif isinstance(subPos,list):
            _subpos=sorted(subPos, key=int, reverse=True)[0]
        api = {
            "method": "GET",
            "url": "/api/v2/copy/mix-trader/order-history-track",
            "payload": {
                'symbol': symbol,
                'productType': 'USDT-FUTURES',
                'idLessThan': _subpos,
                'limit':1 if isinstance(subPos,str) else len(subPos)

            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            if isinstance(subPos,str):
                for i in result['data']['trackingList']:
                    if i['trackingNo']==subPos:
                        return float(i['achievedPL'])
            else:
                pnl=0.0
                for i in subPos:
                    for x in result['data']['trackingList']:
                        if i==x['trackingNo']:
                            pnl+= float(x['achievedPL'])
                            break
                return pnl        
        else:
            return response    

    async def set_spot_sltp_by_copytrader(self,subposId,sl,tp):
        api = {
            "method": "POST",
            "url": "/api/v2/copy/spot-trader/order-modify-tpsl",
            "payload": {
                'trackingNo': subposId
            }
        }
        if sl>0:
            api['payload']['stopLossPrice']=str(sl)
        else:
            api['payload']['stopLossPrice']='0'     
        if tp>0:
            api['payload']['stopSurplusPrice']=str(tp)
        else:
            api['payload']['stopSurplusPrice']='0'    
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response
    async def set_swap_sltp_by_copytrader(self,symbol,subposId,sl,tp):
        api = {
            "method": "POST",
            "url": "/api/v2/copy/mix-trader/order-modify-tpsl",
            "payload": {
                'symbol': symbol,
                'trackingNo': subposId,
                "productType": "USDT-FUTURES"
            }
        }
        if sl>0:
            api['payload']['stopLossPrice']=str(sl)
        else:
            api['payload']['stopLossPrice']='0'    
        if tp>0:
            api['payload']['stopSurplusPrice']=str(tp)
        else:
            api['payload']['stopSurplusPrice']='0'
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response
    async def cancel_swap_sl_order(self, symbol: str, sl_id: str,ispos:bool):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/order/cancel-plan-order",
            "payload": {
                'symbol': symbol,
                'marginCoin': 'USDT',
                "productType": "USDT-futures",
                'orderIdList': [{
                    "orderId": sl_id
                }]
            }
        }
        if ispos:
            api['payload']['planType']='pos_loss'
        else:
            api['payload']['planType']='loss_plan'    
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response

    async def cancel_swap_tp_order(self, symbol: str, tp_id: str,ismarket:bool):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/order/cancel-plan-order",
            "payload": {
                'symbol': symbol,
                'marginCoin': 'USDT',
                "productType": "USDT-futures",
                'orderIdList': [{
                    "orderId": tp_id
                }]
            }
        }
        if ismarket:
            api['payload']['planType']='pos_profit'
        else:
            api['payload']['planType']='profit_plan'
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response

    # 去掉订单

    async def cancel_swap_order(self, symbol: str, orderId: str):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/order/cancel-order",
            "payload": {
                'marginCoin': 'USDT',
                "productType": "USDT-futures",
                'symbol': symbol,
                'orderId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response
    # 市价平仓

    async def close_swap_order_by_market(self, symbol: str, size: str, posSide: str):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/order/place-order",
            "payload": {
                'symbol': symbol,
                "productType": "usdt-futures",
                'marginMode': 'crossed',
                'marginCoin': 'USDT',
                'size': str(size),
                'side': 'buy' if posSide == 'long' else 'sell',
                'tradeSide': 'close',
                'orderType': 'market',
                'force': 'gtc',
                'reduceOnly': 'YES'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response

    async def make_spot_order(self, symbol: str, size: float, orderType: int = 0, price: float = 0, sl: float = 0, tp: float = 0):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/place-order",
            "payload": {
                'symbol': symbol,
                'side': 'buy',
                'orderType': 'market' if orderType == 0 else 'limit',
                'force': 'gtc',
                'size': str(size),
            }
        }
        if orderType == 1:
            api['payload']['price'] = str(price)
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return (result['data']['orderId'],)
        else:
            return response

    # 现货订单取消

    async def cancel_spot_order(self, symbol: str, orderId: str):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/cancel-order",
            "payload": {
                'symbol': symbol,
                'orderId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response

    # 现货止盈止损
    async def set_spot_sl(self, symbol: str, size: float, sl: float):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/place-plan-order",
            "payload": {
                'symbol': symbol,
                'side': 'sell',
                'orderType': 'market',
                'size': str(size),
                'force': 'gtc',
                'planType': "amount",
                'triggerPrice': str(sl)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return (result['data']['orderId'],)
        else:
            return response

    async def set_spot_tp(self, symbol: str, size: float, tp: float):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/place-plan-order",
            "payload": {
                'symbol': symbol,
                'side': 'sell',
                'orderType': 'limit',
                'size': str(size),
                'force': 'gtc',
                'planType': "amount",
                'triggerPrice': str(tp),
                'executePrice': str(tp)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return (result['data']['orderId'],)
        else:
            return response

    async def modify_spot_plan_order(self, orderId: str, size: float, orderType: int, price: float):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/modify-plan-order",
            "payload": {
                'orderId': orderId,
                'triggerPrice': str(price),
                'orderType': 'market' if orderType == 0 else "limit",
                'executePrice': str(price),
                'size': str(size)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response

    async def query_spot_plan_order(self, symbol: str):
        api = {
            "method": "GET",
            "url": "/api/v2/spot/trade/current-plan-order",
            "payload": {
                'symbol': symbol,
                'limit': str(50)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            result = []
            if 'data' in result and result['data']['orderList'] is not None:
                for ord in result['data']['orderList']:
                    result.append(ord['orderId'])
            return result
        else:
            return response

    async def cancel_spot_plan_order(self, orderId: str):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/cancel-plan-order",
            "payload": {
                'orderId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response

    async def close_spot_order_by_market(self, symbol: str, size: float):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/place-order",
            "payload": {
                'symbol': symbol,
                'side': 'sell',
                'orderType': 'market',
                'force': 'gtc',
                'size': str(size),
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response
        
    async def close_swap_order_by_copytrader(self, subPosId: str):
        api = {
            "method": "POST",
            "url": "/api/v2/copy/mix-trader/order-close-positions",
            "payload": {
                'trackingNo': subPosId,
                'productType':'USDT-FUTURES'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response    

    # 带单现货平仓
    async def close_spot_order_by_copytrader(self, symbol: str, subPosId: str):
        api = {
            "method": "POST",
            "url": "/api/v2/copy/spot-trader/order-close-tracking",
            "payload": {
                'symbol': symbol,
                'trackingNoList': [subPosId]
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == '00000':
            return True
        else:
            return response

    # 现货订单查询

    async def query_spot_order_info(self, symbol: str, orderId: str):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/trade/orderInfo",
            "payload": {
                'orderId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            soi = OrderClass.OrderInfo()
            data = result['data'][0]
            soi.openTime = datetime.datetime.fromtimestamp(
                float(data['cTime']) / 1000.0)
            soi.symbol = symbol
            soi.orderId = orderId
            if data['status'] == "filled":
                soi.status = 1
                soi.size = float(data['baseVolume'])
            elif data['status'] =='partially_filled':
                soi.status = 2
                soi.size = float(data['baseVolume'])
            elif data['status'] == "live" or data['status'] == "init" or data['status'] == "new":
                soi.status = 0
            else:
                soi.status = -1
            soi.priceAvg = float(data['priceAvg']) if len(
                data['priceAvg']) > 0 else 0.0

            return soi
        else:
            return response

    async def transfer(self, fromType: int, toType: int, usdt: float):
        api = {
            "method": "POST",
            "url": "/api/v2/spot/wallet/transfer",
            "payload": {
                'fromType': 'usdt_futures' if fromType == 1 else "spot",
                'toType': 'spot' if toType == 0 else "usdt_futures",
                'amount':str(usdt),
                'coin':'USDT'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            return (result['data']['transferId'],)
        else:
            return response
        

    async def setlever(self,symbol:str,lever:int):
        api = {
            "method": "POST",
            "url": "/api/v2/mix/account/set-leverage",
            "payload": {
                'symbol': symbol,
                'productType':'USDT-FUTURES',
                'marginCoin':'usdt',
                'leverage':str(lever)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            return True
        return result
    
    async def get_saving_funding(self):
        api = {
            "method": "GET",
            "url": "/api/v2/earn/savings/account",
            "payload": {
                'ccy': "USDT"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            return float(result['data']['usdtAmount'])
            
        else:
            return response

    #理财宝产品列表         
    async def get_simple_earn_id(self):
        api = {
            "method": "GET",
            "url": "/api/v2/earn/savings/product",
            "payload": {
                'coin':"USDT",
                'filter':'available'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            for i in result['data']:
                if i['coin']=='USDT' and i['periodType']=='flexible' and i['productLevel']=='normal':
                    return (i['productId'],)
            return ''
        else:
            return response
    #理财宝申购
    async def move_to_simple_earn(self,productId:str,usdt:float):
        api = {
            "method": "POST",
            "url": "/api/v2/earn/savings/subscribe",
            "payload": {
                'productId':productId,
                'amount':str(usdt),
                'periodType':'flexible'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            return (result['data']['orderId'],)
        else:
            return response
    #理财宝赎回
    async def fedeem_simple_earn(self,productId:str,usdt:float):
        api = {
            "method": "POST",
            "url": "/api/v2/earn/savings/redeem",
            "payload": {
                'productId':productId,
                'amount':str(usdt),
                'periodType':'flexible'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "00000":
            return (result['data']['orderId'],)
        else:
            return response
