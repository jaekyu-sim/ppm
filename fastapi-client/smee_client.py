import asyncio

class SmeeClientManager:
    def __init__(self, smee_url, target_url):
        self.smee_url = smee_url
        self.target_url = target_url
        self.process = None

    async def start(self):
        """Smee 클라이언트를 시작합니다"""
        try:
            cmd = ['npx', 'smee-client', '--url', self.smee_url, '--target', self.target_url]
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            print(f"Smee client started: {' '.join(cmd)}")
        except FileNotFoundError:
            print("Failed to start smee client: 'npx' not found.")
            print("Please ensure Node.js and npx are installed and in your PATH.")
        except Exception as e:
            print(f"Failed to start smee client: {str(e)}")

    async def stop(self):
        """Smee 클라이언트를 중지합니다"""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                print("Smee client stopped")
            except asyncio.TimeoutError:
                self.process.kill()
                print("Smee client forcefully killed")
