import importlib
import schedule
import DataStore
import TGBot
import HttpListener
import asyncio

async def Run():
    await DataStore.init()
    for ex in DataStore.ex_list:
        name = f"{ex.ex.lower().capitalize()}Controller"
        module = importlib.import_module(name)
        class_ = getattr(module, name)
        instance = class_(ex)
        DataStore.controller_list[ex.id] = instance
        asyncio.create_task(instance.init())
    asyncio.create_task(TGBot.start())
    while True:
        schedule.run_pending()
        await asyncio.sleep(0.1)

   


HttpListener.run(Run)


