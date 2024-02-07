import math
from .SDKBase import SDKBase
import datetime
import aiohttp
import json
from . import OrderClass
# okx的止盈止损在api页面的撮合交易-策略交易里


class OkxSdk(SDKBase):
    name = "okx"
    _rest = "https://aws.okx.com"
    spot_baseinfo={}
    swap_baseinfo={}
    def __init__(self, api_key: str, api_secret: str, api_password: str = None) -> None:
        super().__init__(api_key, api_secret, api_password)


    def count_pos_by_price(self, minQty, money, price, lever=10):
        sz = price/lever*minQty
        sz = math.floor(money/sz)
        return sz

    async def getConf(self):
        api = {
            "method": "GET",
            "url": "/api/v5/account/config",
            "payload": {
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            if result['data'][0]['roleType'] == '1':
                self.swap_copytrader = True
            else:
                self.swap_copytrader = False
            if result['data'][0]['spotRoleType'] == '1':
                self.spot_copytrader = True
            else:
                self.spot_copytrader = False
        else:
            self.swap_copytrader = False
            self.spot_copytrader = False    
    async def init(self):
        await self.getConf()
        
    async def send_request(self, api):
        headers = {
            "OK-ACCESS-KEY": self.keyconf['apiKey'],
            "OK-ACCESS-TIMESTAMP": "",
            "OK-ACCESS-PASSPHRASE": self.keyconf['password'],
            "OK-ACCESS-SIGN": "",
            "Content-Type": "application/json",
            'x-simulated-trading': '0',
            "Accept": "application/json"
        }
        current_time = datetime.datetime.utcnow()
        formatted_time = current_time.strftime(
            "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        headers['OK-ACCESS-TIMESTAMP'] = formatted_time
        method = api["method"]

        sign_str = None
        try:
            if method == "GET":
                params = self.praseParam(api['payload'])
                if len(params) == 0:
                    sign_str = f"{formatted_time}{method}{api['url']}"
                else:
                    sign_str = f"{formatted_time}{method}{api['url']}?{params}"
                headers['OK-ACCESS-SIGN'] = self.get_sign(
                    self.keyconf['secret'], sign_str)
                url = f"{OkxSdk._rest}{api['url']}?{params}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, headers=headers) as response:
                        return await response.text()
            elif method == "POST":
                if len(api['payload']) == 0:
                    sign_str = f"{formatted_time}{method}{api['url']}"
                else:
                    sign_str = f"{formatted_time}{method}{api['url']}{json.dumps(api['payload'])}"
                headers['OK-ACCESS-SIGN'] = self.get_sign(
                    self.keyconf['secret'], sign_str)
                url = f"{OkxSdk._rest}{api['url']}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, json=api['payload'], headers=headers) as response:
                        return await response.text()
        except Exception as e:
            return f'{{"e": "{e}"}}'
    @staticmethod
    async def request_baseinfo():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"{OkxSdk._rest}/api/v5/public/instruments?instType=SWAP") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if 'code' in result and result['code'] == "0":
                        data = result['data']
                        OkxSdk.swap_baseinfo.clear()
                        for d in data:
                            if d['state'] == 'live':
                                OkxSdk.swap_baseinfo[d['instId']] = float(
                                    d['ctVal'])        
        except Exception as e:
            print(f'okx request_baseinfo swap err={e}')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"{OkxSdk._rest}/api/v5/public/instruments?instType=SPOT") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if 'code' in result and result['code'] == "0":
                        data = result['data']
                        OkxSdk.spot_baseinfo.clear()
                        for d in data:
                            if d['state'] == 'live':
                                OkxSdk.spot_baseinfo[d['instId']] = float(
                                    d['minSz'])
        except Exception as e:
            print(f'okx request_baseinfo spot err={e}')   

    async def request_swap_price(self, symbol):
        api = {
            "method": "GET",
            "url": "/api/v5/public/mark-price",
            "payload": {
                "instId": symbol,
                "instType": "SWAP"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return float(result['data'][0]['markPx'])
        return response

    async def request_spot_price(self, symbol):
        api = {
            "method": "GET",
            "url": "/api/v5/public/mark-price",
            "payload": {
                "instId": symbol,
                "instType": "SPOT"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return float(result['data'][0]['markPx'])
        return response

    async def request_swap_subpositions(self, symbol: str) -> list[OrderClass.OrderInfo]:
        api = {
            "method": "GET",
            "url": "/api/v5/copytrading/current-subpositions",
            "payload": {
                "instId": symbol,
                "instType": "SWAP"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            _result: list[OrderClass.OrderInfo] = []
            for i in result['data']:
                subinfo = OrderClass.OrderInfo()
                subinfo.orderId = i['openOrdId']
                subinfo.symbol = i['instId']
                subinfo.subPosId = i['subPosId']
                subinfo.leverage = int(float(i['lever']))
                subinfo.openTime = datetime.datetime.fromtimestamp(
                    float(i['openTime']) / 1000.0)
                subinfo.size = float(i['subPos'])
                subinfo.tp = float(i['tpTriggerPx']) if len(
                    i['tpTriggerPx']) > 0 else 0.0
                subinfo.sl = float(i['slTriggerPx']) if len(
                    i['slTriggerPx']) > 0 else 0.0
                subinfo.posSide = i['posSide']
                subinfo.priceAvg = float(i['openAvgPx'])
                subinfo.marginMode = i['mgnMode']
                _result.append(subinfo)
            return _result
        else:
            return response

    async def request_swap_positions(self, symbol=None):
        api = {
            "method": "GET",
            "url": "/api/v5/account/positions",
            "payload": {
                "instType": "SWAP"
            }
        }
        if isinstance(symbol, str):
            api['payload']['instId'] = symbol
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            _result = []
            for i in result['data']:
                sp = OrderClass.SwapPostion()
                sp.leverage = int(float(i['lever']))
                sp.symbol = i['instId']
                sp.posSide = i['posSide']
                sp.size = float(i['pos'])
                sp.priceAvg = float(i['avgPx'])
                sp.upl = float(i['upl'])
                sp.marginMode = i['mgnMode']
                sp.margin = float(i['imr'])
                _result.append(sp)
            return _result
        else:
            return response

    async def request_swap_account(self, symbol=None):
        api = {
            "method": "GET",
            "url": "/api/v5/account/balance",
            "payload": {

            }
        }
        if isinstance(symbol, str):
            api['payload']['ccy'] = symbol
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            _result = []
            usdt = OrderClass.AccountInfo()
            for i in result['data'][0]['details']:
                account = OrderClass.AccountInfo()
                account.symbol = i['ccy']
                account.available = float(i['availBal'])
                account.total = float(i['cashBal'])
                account.unrealizedPL = float(i['upl'])
                account.total+=account.unrealizedPL
                if account.symbol == 'USDT':
                    usdt = account
                else:
                    _result.append(account)
            return usdt, _result
        else:
            return response

    async def query_swap_order_info(self, symbol: str, orderId: str):
        api = {
            "method": "GET",
            "url": "/api/v5/trade/order",
            "payload": {
                "instId": symbol,
                "ordId": orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            soi = OrderClass.OrderInfo()
            data = result['data'][0]
            soi.leverage = int(float(data['lever']))
            soi.marginMode = data['tdMode']
            soi.openTime = datetime.datetime.fromtimestamp(
                float(data['cTime']) / 1000.0)
            soi.symbol = symbol
            soi.orderId = orderId
            if data['state'] == "filled":
                soi.status = 1
                soi.priceAvg = float(data['avgPx'])
            elif data['state'] == "partially_filled":
                soi.status = 2
                soi.priceAvg = float(data['avgPx'])
            elif data['state'] == "live":
                soi.status = 0
            else:
                soi.status = -1
            soi.posSide = data['posSide']

            soi.size = float(data['accFillSz'])
            if 'attachAlgoOrds' in data and len(data['attachAlgoOrds']) > 0:
                soi.sl = float(data['attachAlgoOrds'][0]['slTriggerPx']) if len(
                    data['attachAlgoOrds'][0]['slTriggerPx']) > 0 else 0.0
                soi.tp = float(data['attachAlgoOrds'][0]['tpTriggerPx']) if len(
                    data['attachAlgoOrds'][0]['tpTriggerPx']) > 0 else 0.0
                soi.sl_id = data['attachAlgoOrds'][0]['attachAlgoId']
            return soi
        else:
            return response

    # 合约下单,不用带止盈止损，用set_swap_tp_sl设置止损，cancel_swap_tp_sl取消止损,如果下单成功，设置止盈失败，就取消订单
    async def make_swap_order(self, symbol: str, size: float, posSide: str, orderType: int = 0, price: float = 0):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/order",
            "payload": {
                'instId': symbol,
                'tdMode': 'cross',
                'side': 'buy' if posSide == 'long' else 'sell',
                'posSide': posSide,
                'ordType': 'limit' if orderType == 1 else 'market',
                'sz': str(size),
            }
        }
        if orderType == 1:
            api['payload']['px'] = str(price)
        # sl_id = ''
        # if sl > 0 or tp > 0:
        #     sl_id = str(int(datetime.datetime.now().timestamp()*1000))
        #     api['payload']['attachAlgoClOrdId'] = sl_id
        #     if sl > 0:
        #         api['payload']['slTriggerPx'] = str(sl)
        #         api['payload']['slOrdPx'] = '-1'
        #     if tp > 0:
        #         api['payload']['tpTriggerPx'] = str(tp)
        #         api['payload']['tpOrdPx'] = '-1'
        response = await self.send_request(api)
        result = json.loads(response)

        if 'code' in result and result['code'] == "0":
            return (result['data'][0]['ordId'],)
        else:
            return response

    async def cancel_swap_order(self, symbol: str, orderId: str):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/cancel-order",
            "payload": {
                'instId': symbol,
                'ordId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response

    async def close_swap_order_by_market(self, symbol: str, size: str, posSide: str):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/order",
            "payload": {
                'instId': symbol,
                'tdMode': 'cross',
                'side': 'sell' if posSide == 'long' else 'buy',
                'posSide': posSide,
                'ordType': 'market',
                'sz': str(size),
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response

    async def close_swap_order_by_copytrader(self, subPosId: str):
        api = {
            "method": "POST",
            "url": "/api/v5/copytrading/close-subposition",
            "payload": {
                'instType': 'SWAP',
                'subPosId': subPosId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response

    async def modify_spot_sl_tp(self, symbol: str, size: float, algoClOrdId: str, sl: float, tp: float):
        return self.modify_swap_sl_tp(symbol, size, algoClOrdId, sl, tp)
    
    #tdmode 0为逐仓，1为全仓 2为cash 3为spot_isolated：现货逐仓(仅适用于现货带单)
    async def set_sltp(self,symbol:str,size:float,posSide:str,sl:float,tp:float,sltp_type:int,tdmode:int):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/order-algo",
            "payload": {
                'instId': symbol,
                'tdMode':'isolated' if tdmode==0 else 'cross' if tdmode==1 else 'cash' if tdmode==2 else 'spot_isolated',
                'reduceOnly':True,
                'cxlOnClosePos':True
            }
        }
        if tdmode<=1:
            if posSide=='long':
                api['method']['side']='sell'
            else:
                api['method']['side']='buy'
        else:
            api['method']['side']='sell'
        if sl >0 and tp>0:
            api['method']['ordType']='oco'
        else:
            api['method']['ordType']='conditional'
        if sltp_type==1:
            api['method']['sz']=str(size)
        else:
            api['method']['closeFraction']='1'    
        if tp>0:
            api['method']['tpTriggerPx']=str(tp)
            api['method']['tpOrdPx']='-1'
        if sl>0:
            api['method']['slTriggerPx']=str(sl)
            api['method']['slOrdPx']='-1'
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return (result['data'][0]['algoId'],)
        else:
            return response
    # tp为0即删除止盈
    async def modify_swap_sl_tp(self, symbol: str, size: float, algoClOrdId: str, sl: float, tp: float):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/amend-algos",
            "payload": {
                'instId': symbol,
                'algoClOrdId': algoClOrdId,
                'newSz': str(size),
                'newTpOrdPx': '-1',
                'newTpTriggerPxType': 'last',
                'newTpTriggerPx': str(tp),
                'newSlOrdPx': '-1',
                'newSlTriggerPxType': 'last',
                'newSlTriggerPx': str(sl),

            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return (result['data'][0]['algoClOrdId'],)
        else:
            return response

    async def make_spot_order(self, symbol: str, size: float, orderType: int = 0, price: float = 0):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/order",
            "payload": {
                'instId': symbol,
                'tdMode': 'cash',
                'side': 'buy',
                'ordType': 'limit' if orderType == 1 else 'market',
                'sz': str(size),
                'tgtCcy': 'base_ccy'
            }
        }
        if orderType == 1:
            api['payload']['px'] = str(price)
       
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return (result['data'][0]['ordId'], )
        else:
            return response

    async def close_spot_order_by_market(self, symbol: str, size: float):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/order",
            "payload": {
                'instId': symbol,
                'tdMode': 'cash',
                'side': 'sell',
                'ordType': 'market',
                'sz': str(size),
                'tgtCcy': 'base_ccy'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        print(result)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response

    # 带单现货平仓
    async def close_spot_order_by_copytrader(self, symbol: str, subPosId: str):
        api = {
            "method": "POST",
            "url": "/api/v5/copytrading/close-subposition",
            "payload": {
                'subPosId': subPosId,
                'instType': 'SPOT'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response

    async def request_spot_subpositions(self, symbol: str) -> list[OrderClass.OrderInfo]:
        api = {
            "method": "GET",
            "url": "/api/v5/copytrading/current-subpositions",
            "payload": {
                "instId": symbol,
                "productType": "SPOT"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            _result = []
            for i in result['data']:
                subinfo = OrderClass.OrderInfo()
                subinfo.orderId = i['openOrdId']
                subinfo.symbol = i['instId']
                subinfo.subPosId = i['subPosId']
                subinfo.openTime = datetime.datetime.fromtimestamp(
                    float(i['openTime']) / 1000.0)
                subinfo.size = float(i['subPos'])
                subinfo.tp = float(i['tpTriggerPx']) if len(
                    i['tpTriggerPx']) > 0 else 0.0
                subinfo.sl = float(i['slTriggerPx']) if len(
                    i['slTriggerPx']) > 0 else 0.0
                subinfo.priceAvg = float(i['openAvgPx'])
                _result.append(subinfo)
            return _result
        else:
            return response

    async def query_spot_order_info(self, symbol: str, orderId: str):
        api = {
            "method": "GET",
            "url": "/api/v5/trade/order",
            "payload": {
                "instId": symbol,
                "ordId": orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            soi = OrderClass.OrderInfo()
            data = result['data'][0]
            soi.openTime = datetime.datetime.fromtimestamp(
                float(data['cTime']) / 1000.0)
            soi.symbol = symbol
            soi.orderId = orderId
            if data['state'] == "filled" or data['state'] == "partially_filled":
                soi.status = 0
                soi.priceAvg = float(data['avgPx'])
            elif data['state'] == "live":
                soi.status = 1
            else:
                soi.status = -1
            soi.posSide = data['posSide']

            soi.size = float(data['accFillSz'])
            if 'attachAlgoOrds' in data and len(data['attachAlgoOrds']) > 0:
                soi.sl = float(data['attachAlgoOrds'][0]['slTriggerPx']) if len(
                    data['attachAlgoOrds'][0]['slTriggerPx']) > 0 else 0.0
                soi.tp = float(data['attachAlgoOrds'][0]['tpTriggerPx']) if len(
                    data['attachAlgoOrds'][0]['tpTriggerPx']) > 0 else 0.0
                soi.sl_id = data['attachAlgoOrds'][0]['attachAlgoId']
            return soi
        else:
            return response
        

    async def query_algo(self, algoClOrdId: str):
        api = {
            "method": "GET",
            "url": "/api/v5/trade/order-algo",
            "payload": {
                'algoClOrdId': algoClOrdId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        soi = OrderClass.OrderInfo()
        if 'code' in result and result['code'] == "0":
            if isinstance(result['data'], list) and len(result['data']) > 0:
                s = result['data'][0]['state']
                if s == 'live':
                    soi.status = 0
                elif s == 'effective':
                    soi.status = 1
                elif s == 'partially_effective':
                    soi.status = 2
                else:
                    soi.status=-1    
            return soi
        else:
            return response

    async def cancel_spot_order(self, symbol: str, orderId: str):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/cancel-order",
            "payload": {
                'instId': symbol,
                'ordId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response

    async def transfer(self, fromType: int, toType: int, usdt: float):
        api = {
            "method": "POST",
            "url": "/api/v5/asset/transfer",
            "payload": {
                'type': '0',
                'ccy': 'USDT',
                'amt': str(usdt),
                'from': '6' if fromType == 1 else '18',
                'to': '6' if toType == 1 else '18',
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response
    async def close_swap_by_pos(self,symbol:str,posSide:str,mgnMode:str):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/close-position",
            "payload": {
                'instId': symbol,
                'posSide': posSide,
                'mgnMode': mgnMode,
                'autoCxl':True
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response
        
    async def cancel_algo(self,symbol,id):
        api = {
            "method": "POST",
            "url": "/api/v5/trade/cancel-algos",
            "payload": {
                'instId': symbol,
                'algoId': id
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response
    async def set_sltp_by_copytrader(self,subposId:str,sl:float,tp:float):
        api = {
            "method": "POST",
            "url": "/api/v5/copytrading/algo-order",
            "payload": {
                'subPosId': subposId
            }
        }
        if sl>0:
            api['payload']['slTriggerPx']=str(sl)
        # else:
        #     api['payload']['slTriggerPx']='0' 
        if tp>0:
            api['payload']['tpTriggerPx']=str(tp)
        # else:
        #     api['payload']['tpTriggerPx']='0'     
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response
    async def setlever(self,symbol:str,lever:int):
        api = {
            "method": "POST",
            "url": "/api/v5/account/set-leverage",
            "payload": {
                'instId': symbol,
                'lever':str(lever),
                'mgnMode':'cross'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'code' in result and result['code'] == "0":
            return True
        else:
            return response 
