import asyncio
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware
import datetime
from fastapi import Body, Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse
import uvicorn
import DataStore
from OrderInfoDao import OrderInfoDB
from RequestObject import AddExRequest, CancelOrderRequest, ClosePosRequest, CloseStrategyOrder, SetExSingalRequest, SetExStatusRequest, LoginRequest, MakeOrderRequest, ModifySlTp, SetLeverageRequest, SetLongShortRatioRequest, SetMartinRequest, SetProfitRequest, SetTGRequest, SetTrendRequest, StrategyOrderRequest, TvNotificationRequest
from StatisticsDao import query_total_by_range
import StrategyLogic
import UserDao
import jwt
import Const
from enum import Enum
import TVController


class Status(Enum):
    Unauthorized = 401
    TokenInvaild = 402
    TokenMissing = 403
    UserNotFound = 404
    UserUnauthorized = 405
    ParamsError = 410
    ExchangeError = 411


secret_key = "your_secret_key"
# 生成令牌


def generate_token(username, password, privilege):
    payload = {"username": username, "password": password, 'privilege': privilege,
               "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30)}
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token
# 验证令牌


async def verify_token(token):
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        if payload:
            us = await UserDao.UserDB_query(payload['username'], payload['password'])
            if us:
                return us
            else:
                raise HTTPException(status_code=Status.TokenInvaild.value,
                                    detail="Invalid token")
    except jwt.ExpiredSignatureError:
        # 令牌过期
        raise HTTPException(status_code=Status.TokenInvaild.value,
                            detail="Token has expired")
    except jwt.InvalidTokenError:
        # 无效的令牌
        raise HTTPException(status_code=Status.TokenInvaild.value,
                            detail="Invalid token")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
# 定义一个依赖项，用于获取请求头中的 token


def get_token(authorization: str = Header(...)):
    # 在实际应用中，你可能需要进行更复杂的 token 解析和验证逻辑
    # 这里仅仅是一个简单的演示
    if "Bearer" not in authorization:
        raise HTTPException(status_code=Status.TokenMissing.value,
                            detail="Invalid token type")
    token = authorization.replace("Bearer ", "")
    return token


@app.post('/ts/api/login')
async def vertify_login(LoginRequest: LoginRequest):
    print("login")
    result = await UserDao.UserDB_query(LoginRequest.username, LoginRequest.password)
    if result:
        token = generate_token(LoginRequest.username,
                               LoginRequest.password, result.privilege)
        return {"data": {'id': result.id, 'token': token, 'username': result.account}}
    else:
        return JSONResponse(status_code=Status.UserNotFound.value, content={"message": "User not found"})


@app.get('/ts/api/all-exchanges')
async def get_all_ex(token: str = Depends(get_token)):
    await verify_token(token)

    result = []
    for ex in DataStore.ex_list:
        result.append(ex.to_json())
    return {"data": result}


@app.get('/ts/api/all-orders')
async def get_all_orders(token: str = Depends(get_token)):
    await verify_token(token)

    result = []
    for _, d in DataStore.order_info.items():
        for i in d:
            result.append(i.to_json())
    return {"data": result}


@app.get('/ts/api/all-statistics')
async def get_statistics(exid: int = Query(), day: int = Query(), token: str = Depends(get_token)):
    await verify_token(token)
    current_time = datetime.datetime.utcnow()
    # 计算7天前的时间
    start = current_time - datetime.timedelta(days=day)
    exids = [exid]
    result = await query_total_by_range(exids, start, current_time)
    return {"data": result}


@app.get('/ts/api/all-accounts')
async def get_all_account(token: str = Depends(get_token)):
    await verify_token(token)

    return {"data": {
        'spot': DataStore.spot_account,
        'swap': DataStore.swap_account
    }}


@app.get('/ts/api/all-positions')
async def get_all_positions(token: str = Depends(get_token)):
    await verify_token(token)
    return {"data": {
        'spot': DataStore.spot_positions,
        'swap': DataStore.swap_positions
    }}


@app.post('/ts/api/make-order')
async def make_order(order: MakeOrderRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    if (order.tp == 0 and order.sl == 0):
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "tp or sl >0"})
    elif order.tp < 0 or order.sl < 0:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "tp and sl can not <0"})
    elif order.exid < 0:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "exid can not <0"})
    elif order.orderType == True and order.price <= 0:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "limit order price can not <=0"})
    controller = DataStore.getController(order.exid)
    if controller is None:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"交易所id{order.exid}不存在"})
    result: OrderInfoDB = None
    if order.isswap:
        if order.sltp_type == Const.SLTP_TYPE_POS:
            await controller.set_swap_sltp_by_pos(order.symbol, order.posSide, order.sl, order.tp)
        result = await controller.make_swap_order(order.symbol, order.money, 'long' if order.posSide else 'short', order.price, Const.ORDER_TYPE_LIMIT if order.orderType else Const.ORDER_TYPE_MARKET, order.sl, order.tp, order.sltp_type, Const.ORDER_FROM_WEB)
    else:
        if order.sltp_type == Const.SLTP_TYPE_POS:
            await controller.set_spot_sltp_by_pos(order.symbol, order.posSide, order.sl, order.tp)
        result = await controller.make_spot_order(order.symbol, order.money, order.price, Const.ORDER_TYPE_LIMIT if order.orderType else Const.ORDER_TYPE_MARKET, order.sl, order.tp, order.sltp_type, Const.ORDER_FROM_WEB)

    return {'data': result.to_json()}


@app.post('/ts/api/cancel-order')
async def cancel_order(data: CancelOrderRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    info = None
    for i, values in DataStore.order_info.items():
        find = False
        for v in values:
            if v.id == data.orderID:
                info = v
                find = True
                break
        if find:
            break
    if info is None:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"订单id:{data.orderID}不存在"})
    controller = DataStore.getController(info.exId)
    if controller is None:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"找不到相应的交易所控制器"})
    result: bool = False
    if info.isswap:
        result = await controller.close_swap_by_order(info.id)
    else:
        result = await controller.close_spot_by_order(info.id)
    return {'data': result}


@app.post('/ts/api/close-order')
async def close_order(data: CancelOrderRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    info = None
    for i, value in DataStore.order_info.items():
        for v in value:
            if v.id == data.orderID:
                info = v
    if info is None:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"订单id:{data.orderID}不存在"})
    controller = DataStore.getController(info.exId)
    if controller is None:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"找不到相应的交易所控制器"})
    result: OrderInfoDB = None
    if info.isswap:
        result = await controller.close_swap_by_order(info.id)
    else:
        result = await controller.close_spot_by_order(info.id)
    return {'data': result.to_json()}


@app.post('/ts/api/modify-sltp')
async def modify_sltp(data: ModifySlTp, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    controller = DataStore.getController(data.exid)
    if controller is None:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"找不到相应的交易所控制器"})
    info = None
    if data.id > 0:
        for v in DataStore.order_info[data.exid]:
            if v.id == data.id:
                info = v
        if info is None:
            return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"订单id:{data.id}不存在"})
        result: OrderInfoDB = None
        if info.isswap:
            result = await controller.set_swap_sltp_by_order(info.id, data.sl, data.tp)
        else:
            result = await controller.set_spot_sltp_by_order(info.id, data.sl, data.tp)
        return {'data': result.to_json()}
    else:
        if data.isswap:
            await controller.set_swap_sltp_by_pos(data.symbol, 'long' if data.posSide else 'short', data.sl, data.tp)
        else:
            await controller.set_spot_sltp_by_pos(data.symbol, data.sl, data.tp)
        return {'data': True}


@app.post('/ts/api/close-pos')
async def close_pos(data: ClosePosRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    controller = DataStore.getController(data.exId)
    if controller is None:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": f"找不到相应的交易所控制器"})
    result = None
    if data.isswap:
        result = await controller.close_swap_by_pos(data.symbol, data.posSide)
    else:
        result = await controller.close_spot_by_pos(data.symbol)
    return {'data': result}


@app.post('/ts/api/make-strategyorder')
async def make_strategy_order(data: StrategyOrderRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    if len(data.exids) <= 0:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "exid没有填充数据"})
    if data.isswap and data.posSide and data.condition1 > data.condition2:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "跌穿价格不能大于突破价格"})
    if data.isswap and data.posSide == False and data.condition1 < data.condition2:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "突破价格不能大于跌穿价格"})
    if data.sl == 0 and data.tp == 0:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "止盈止损必须设置一个"})
    if data.isswap and data.posSide and (data.condition2 < data.sl or data.condition2 > data.tp):
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "做多时止损价格不能高于开仓价格或止盈价格不能低于开仓价格"})
    if data.isswap and data.posSide == False and (data.condition2 > data.sl or data.condition2 < data.tp):
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "做空时止损价格不能低于开仓价格或止盈价格不能高于开仓价格"})
    if data.condition1 <= 0 or data.condition2 <= 0:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "条件1或条件2的价格不能为0"})
    result = await StrategyLogic.MakeStrategyOrder(data)
    if result:
        return {"data": result}
    return JSONResponse(status_code=Status.ParamsError.value, content={"message": "内部错误"})


@app.post('/ts/api/cancel-strategyorder')
async def cancel_strategy_order(data: CloseStrategyOrder, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    StrategyLogic.CancelStrategyOrder(data.id)
    return {'data': 'ok'}
TVIPS = ["52.89.214.238", "34.212.75.30", "54.218.53.128", "52.32.178.7"]


@app.post('/ts/api/tvnotification')
async def tvnotification(data: TvNotificationRequest, request: Request):
    client_ip = request.headers.get(
        "X-Real-IP") or request.headers.get("X-Forwarded-For") or request.client.host
    if client_ip in TVIPS:
        await TVController.make_tv_order(data)
        return {'data': 'ok'}
    else:
        return {'data': 'You are not allowed to send data to this server.'}


@app.get('/ts/api/get-setting')
async def get_setting(token: str = Depends(get_token)):
    user = await verify_token(token)
    conf = DataStore.json_conf.copy()
    del conf['DB']
    del conf['TG']
    return {'data': conf}


@app.get('/ts/api/get-ex-list')
async def get_ex_list(token: str = Depends(get_token)):
    user = await verify_token(token)

    import ExchangeDao
    all = await ExchangeDao.exchange_db_query(True)
    li = []
    for a in all:
        li.append(a.to_json())
    return {'data': li}


@app.post('/ts/api/set-ex-status')
async def set_exchange(data: SetExStatusRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})

    result = await DataStore.set_ex_status(data)
    return {'data': result}


@app.post('/ts/api/set-ex-tvsingal')
async def set_exchange_tvsginal(data: SetExSingalRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})

    result = await DataStore.set_ex_tvsingal(data)
    return {'data': result}


@app.post('/ts/api/add-ex')
async def add_exchange(data: AddExRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})

    result = await DataStore.add_ex(data)
    return {'data': result}


@app.post('/ts/api/set-tg')
async def set_tg(data: SetTGRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    DataStore.json_conf['TG_report_err'] = data.TG_report_err
    DataStore.json_conf['TG_report_open'] = data.TG_report_open
    DataStore.json_conf['TG_report_close'] = data.TG_report_close
    DataStore.write_json_conf()
    return {'data': data}


async def setleverage(lv):
    for i, v in DataStore.controller_list.items():
        await v.setlever('', lv)


@app.post('/ts/api/set-leverage')
async def set_leverage(data: SetLeverageRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    asyncio.create_task(setleverage(data.leverage))
    DataStore.write_json_conf()
    return {'data': 'ok'}


@app.post('/ts/api/set-martin')
async def set_martin(data: SetMartinRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})

    DataStore.update_martin_setting(data)
    return {'data': DataStore.json_conf['Martin']}


@app.post('/ts/api/set-trend')
async def set_trend(data: SetTrendRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})

    DataStore.update_trend_setting(data)
    return {'data': DataStore.json_conf['Trend']}


@app.post('/ts/api/set-profit-trans')
async def set_transfer_profit(data: SetProfitRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})
    if data.ratio >= 0 and data.ratio <= 1:
        DataStore.json_conf['TransferProfit'] = data.ratio
        DataStore.write_json_conf()
        return {'data': DataStore.json_conf['TransferProfit']}
    else:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "转移利润比例应该在0-1之间"})


@app.post('/ts/api/set-longshort-ratio')
async def set_longshort_ratio(data: SetLongShortRatioRequest, token: str = Depends(get_token)):
    user = await verify_token(token)
    if user.privilege <= 1:
        return JSONResponse(status_code=Status.UserUnauthorized.value, content={"message": "用户权限不足"})

    if data.long != 1 and data.long <= 1:
        data.short = 1
    elif data.short != 1 and data.short <= 1:
        data.long = 1
    else:
        return JSONResponse(status_code=Status.ParamsError.value, content={"message": "多空比例设置错误"})

    DataStore.json_conf['LongRatio'] = data.long
    DataStore.json_conf['ShortRatio'] = data.short
    DataStore.write_json_conf()    
    return {'data':data}

def run(task):
    app.add_event_handler('startup', lambda: asyncio.create_task(task()))
    uvicorn.run(app, host="127.0.0.1", port=3001, loop="auto")
