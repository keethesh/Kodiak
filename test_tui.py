import asyncio
from kodiak.tui.app import KodiakApp

async def test():
    app = KodiakApp()
    async with app.run_test() as pilot:
        print("App started successfully! No CSS errors.")

if __name__ == "__main__":
    asyncio.run(test())
