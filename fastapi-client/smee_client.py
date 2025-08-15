import asyncio

class SmeeClientManager:
    def __init__(self, smee_url, target_url):
        self.smee_url = smee_url
        self.target_url = target_url
        self.process = None

    async def start(self):
        command = f"pysmee forward {self.smee_url} {self.target_url}"
        self.process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        print(f"Smee client started for {self.smee_url}")

    async def stop(self):
        if self.process:
            self.process.terminate()
            await self.process.wait()
            print("Smee client stopped.")
