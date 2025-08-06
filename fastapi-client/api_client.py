import asyncio
from contextlib import asynccontextmanager
import subprocess
import sys
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import logging
import os
import json
import re
import aiohttp
import base64
from urllib.parse import quote

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn

# ==============================================================================
# 로깅 설정
# ==============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================================================================
# 데이터 모델 (Data Models)
# ==============================================================================
@dataclass
class CommitInfo:
    """커밋 정보를 담는 데이터 클래스"""
    author: str
    email: str
    message: str
    sha: str
    changed_files: List[Dict[str, Any]]
    file_contents: Dict[str, str]  # filename -> content
    programming_languages: Dict[str, str]  # filename -> language


class WebhookPayload(BaseModel):
    """GitHub webhook payload 모델"""
    action: Optional[str] = None
    repository: Dict[str, Any]
    commits: Optional[List[Dict[str, Any]]] = None
    head_commit: Optional[Dict[str, Any]] = None
    pusher: Optional[Dict[str, Any]] = None


# ==============================================================================
# 서비스 및 헬퍼 클래스 (Service & Helper Classes)
# ==============================================================================
class GitHubService:
    """GitHub API를 통해 데이터를 가져오는 서비스"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv('GITHUB_TOKEN')
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        headers = {}
        if self.token:
            headers['Authorization'] = f'token {self.token}'
            headers['Accept'] = 'application/vnd.github.v3+json'
        
        self.session = aiohttp.ClientSession(headers=headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_commit_files(self, repo_full_name: str, commit_sha: str) -> List[Dict[str, Any]]:
        """커밋에서 변경된 파일 목록을 가져옵니다"""
        url = f"https://api.github.com/repos/{repo_full_name}/commits/{commit_sha}"

        async with self.session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to get commit info: {response.status}")
                return []
            
            commit_data = await response.json()
            return commit_data.get('files', [])
    
    async def get_file_content(self, repo_full_name: str, file_path: str, ref: str = 'main') -> Optional[str]:
        """GitHub API를 통해 파일 내용을 가져옵니다"""
        encoded_path = quote(file_path, safe='/')
        url = f"https://api.github.com/repos/{repo_full_name}/contents/{encoded_path}?ref={ref}"
        
        async with self.session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to get file content for {file_path}: {response.status}")
                return None
            
            file_data = await response.json()
            
            if file_data.get('size', 0) > 1000000:  # 1MB 이상
                return await self.get_large_file_content(repo_full_name, file_path, ref)
            
            content = file_data.get('content', '')
            if content:
                try:
                    return base64.b64decode(content).decode('utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"Cannot decode file as UTF-8: {file_path}")
                    return None
            return None
    
    async def get_large_file_content(self, repo_full_name: str, file_path: str, ref: str) -> Optional[str]:
        """큰 파일의 경우 raw content를 직접 가져옵니다"""
        encoded_path = quote(file_path, safe='/')
        url = f"https://raw.githubusercontent.com/{repo_full_name}/{ref}/{encoded_path}"
        
        async with self.session.get(url) as response:
            if response.status == 200:
                try:
                    return await response.text()
                except UnicodeDecodeError:
                    logger.warning(f"Cannot decode large file as UTF-8: {file_path}")
                    return None
            else:
                logger.error(f"Failed to get large file content for {file_path}: {response.status}")
                return None


class LanguageDetector:
    """프로그래밍 언어를 감지하는 클래스"""
    
    LANGUAGE_EXTENSIONS = {
        '.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript (React)', '.ts': 'TypeScript',
        '.tsx': 'TypeScript (React)', '.java': 'Java', '.c': 'C', '.cpp': 'C++', '.cc': 'C++',
        '.cxx': 'C++', '.h': 'C/C++ Header', '.hpp': 'C++ Header', '.cs': 'C#', '.php': 'PHP',
        '.rb': 'Ruby', '.go': 'Go', '.rs': 'Rust', '.kt': 'Kotlin', '.swift': 'Swift',
        '.scala': 'Scala', '.sh': 'Shell', '.bash': 'Bash', '.zsh': 'Zsh', '.sql': 'SQL',
        '.html': 'HTML', '.css': 'CSS', '.scss': 'SCSS', '.sass': 'Sass', '.less': 'Less',
        '.xml': 'XML', '.json': 'JSON', '.yaml': 'YAML', '.yml': 'YAML', '.toml': 'TOML',
        '.ini': 'INI', '.cfg': 'Config', '.conf': 'Config', '.md': 'Markdown', '.txt': 'Text',
        '.dockerfile': 'Dockerfile', '.r': 'R', '.R': 'R', '.m': 'MATLAB/Objective-C',
        '.pl': 'Perl', '.lua': 'Lua', '.vim': 'Vim Script', '.dart': 'Dart', '.ex': 'Elixir',
        '.exs': 'Elixir Script'
    }
    
    @classmethod
    def detect_language(cls, filename: str) -> str:
        """파일명으로부터 프로그래밍 언어를 감지합니다"""
        path = Path(filename)
        if path.name.lower() in ['dockerfile', 'dockerfile.dev', 'dockerfile.prod']:
            return 'Dockerfile'
        if path.name.lower() in ['makefile', 'makefile.am', 'makefile.in']:
            return 'Makefile'
        return cls.LANGUAGE_EXTENSIONS.get(path.suffix.lower(), 'Unknown')


class MCPService:
    """내부 프로젝트의 MCP Server와 통신하는 서비스"""
    
    def __init__(self, mcp_server_url: str):
        self.mcp_server_url = mcp_server_url
    
    async def send_commit_analysis_request(self, commit_info: CommitInfo) -> bool:
        """MCP Server로 커밋 분석 요청을 보냅니다"""
        files = [
            {
                "fileName": filename,
                "language": commit_info.programming_languages.get(filename, 'Unknown'),
                "code": content
            }
            for filename, content in commit_info.file_contents.items()
        ]

        payload = {
            "author": commit_info.author,
            "email": commit_info.email,
            "message": commit_info.message,
            "sha": commit_info.sha,
            "files": files,
            # "requirement_number": self._extract_requirement_number(commit_info.message)
        }
        
        logger.info(f"Sending analysis request for commit {commit_info.sha[:8]}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.mcp_server_url}/analyze_commit",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Successfully sent commit analysis request for {commit_info.sha}")
                        return True
                    else:
                        logger.error(f"Failed to send commit analysis request: {response.status} - {await response.text()}")
                        return False
        except Exception as e:
            logger.error(f"Error sending commit analysis request: {str(e)}")
            return False
    
    def _extract_requirement_number(self, commit_message: str) -> Optional[str]:
        """커밋 메시지에서 요구사항 번호를 추출합니다"""
        patterns = [
            r'REQ[-_]?(\d+)', r'요구사항[-_]?(\d+)', r'#(\d+)',
            r'FEAT[-_]?(\d+)', r'REQUIREMENT[-_]?(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, commit_message, re.IGNORECASE)
            if match:
                return match.group(1)
        return None


class SmeeManager:
    """Smee 클라이언트를 관리하는 클래스"""
    
    def __init__(self, smee_url: str, target_url: str = "http://localhost:8000/webhook"):
        self.smee_url = smee_url
        self.target_url = target_url
        self.process: Optional[asyncio.subprocess.Process] = None
    
    async def start(self):
        """Smee 클라이언트를 시작합니다"""
        try:
            cmd = ['npx', 'smee-client', '--url', self.smee_url, '--target', self.target_url]
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            logger.info(f"Smee client started: {' '.join(cmd)}")
        except FileNotFoundError:
            logger.error("Failed to start smee client: 'npx' not found.")
            logger.info("Please ensure Node.js and npx are installed and in your PATH.")
        except Exception as e:
            logger.error(f"Failed to start smee client: {str(e)}")
    
    async def stop(self):
        """Smee 클라이언트를 중지합니다"""
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
                logger.info("Smee client stopped")
            except asyncio.TimeoutError:
                self.process.kill()
                logger.warning("Smee client forcefully killed")


# ==============================================================================
# FastAPI 라이프사이클 관리 (Lifespan Management)
# ==============================================================================
smee_manager: Optional[SmeeManager] = None
github_service: Optional[GitHubService] = None
mcp_service: Optional[MCPService] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan 이벤트 핸들러"""
    global smee_manager, github_service, mcp_service
    
    logger.info("Starting up GitHub Webhook Server...")
    
    smee_url = os.getenv('SMEE_URL')
    github_token = os.getenv('GITHUB_TOKEN')
    mcp_server_url = os.getenv('MCP_SERVER_URL', 'http://localhost:8001')
    
    if smee_url:
        smee_manager = SmeeManager(smee_url)
        await smee_manager.start()
    else:
        logger.warning("SMEE_URL not set. Smee client will not be started.")
    
    if not github_token:
        logger.warning("GITHUB_TOKEN not set. GitHub API calls may be rate limited.")
    
    github_service = GitHubService(github_token)
    mcp_service = MCPService(mcp_server_url)
    
    logger.info("GitHub Webhook Server started successfully")
    
    yield
    
    logger.info("Shutting down GitHub Webhook Server...")
    if smee_manager:
        await smee_manager.stop()
    logger.info("GitHub Webhook Server shut down")


# ==============================================================================
# FastAPI 앱 초기화 (App Initialization)
# ==============================================================================
app = FastAPI(
    title="GitHub Webhook Server",
    version="1.0.0",
    lifespan=lifespan
)


# ==============================================================================
# API 엔드포인트 (API Endpoints)
# ==============================================================================
@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "GitHub Webhook Server is running",
        "version": app.version,
        "endpoints": {"webhook": "/webhook", "health": "/health"}
    }

@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "smee_running": smee_manager is not None and smee_manager.process is not None,
        "github_service_ready": github_service is not None,
        "mcp_service_ready": mcp_service is not None
    }

@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """GitHub webhook을 처리하는 엔드포인트"""
    try:
        payload = await request.json()
        event_type = request.headers.get("X-GitHub-Event", "unknown")
        logger.info(f"Received '{event_type}' event")

        if event_type == "push" and ('commits' in payload or 'head_commit' in payload):
            background_tasks.add_task(process_push_event, payload)
            return {"status": "accepted", "message": "Push event received and processing started"}
        
        logger.info(f"Ignoring '{event_type}' event")
        return {"status": "ignored", "reason": f"Not a push event: {event_type}"}
        
    except json.JSONDecodeError:
        logger.error("Error decoding webhook payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ==============================================================================
# 비즈니스 로직 (Business Logic)
# ==============================================================================
async def process_push_event(payload: dict):
    """Push 이벤트를 처리하는 백그라운드 태스크"""
    try:
        repo_full_name = payload['repository']['full_name']
        commits = payload.get('commits', [])
        
        if not commits and payload.get('head_commit'):
            commits = [payload['head_commit']]
        
        if not commits:
            logger.info("No commits to process in push event")
            return
        
        async with GitHubService(os.getenv('GITHUB_TOKEN')) as github:
            for commit_data in commits:
                await process_single_commit(github, repo_full_name, commit_data)
                
    except KeyError as e:
        logger.error(f"Missing key in push event payload: {e}")
    except Exception as e:
        logger.error(f"Error in process_push_event: {str(e)}")


async def process_single_commit(github: GitHubService, repo_full_name: str, commit_data: dict):
    """단일 커밋을 처리합니다"""
    try:
        commit_sha = commit_data['id']
        author_info = commit_data.get('author', {})
        
        logger.info(f"Processing commit {commit_sha[:8]} by {author_info.get('name', 'Unknown')}")
        
        changed_files_info = await github.get_commit_files(repo_full_name, commit_sha)
        if not changed_files_info:
            logger.warning(f"No files found for commit {commit_sha}")
            return
        
        file_contents = {}
        programming_languages = {}
        
        for file_info in changed_files_info:
            if file_info.get('status') == 'removed':
                continue
            
            filename = file_info['filename']
            content = await github.get_file_content(repo_full_name, filename, commit_sha)
            if content is not None:
                file_contents[filename] = content
                programming_languages[filename] = LanguageDetector.detect_language(filename)
                logger.info(f"Retrieved content for {filename} ({programming_languages[filename]})")
            else:
                logger.warning(f"Could not retrieve content for {filename}")
        
        if not file_contents:
            logger.info(f"No processable file content found for commit {commit_sha}")
            return

        commit_info = CommitInfo(
            author=author_info.get('name', 'Unknown'),
            email=author_info.get('email', 'unknown@email.com'),
            message=commit_data.get('message', ''),
            sha=commit_sha,
            changed_files=changed_files_info,
            file_contents=file_contents,
            programming_languages=programming_languages
        )
        
        if mcp_service:
            if not await mcp_service.send_commit_analysis_request(commit_info):
                logger.error(f"Failed to send commit {commit_sha[:8]} to MCP server")
        else:
            logger.error("MCP service not initialized, cannot send analysis request")
            
    except KeyError as e:
        logger.error(f"Missing key in commit data: {e}")
    except Exception as e:
        logger.error(f"Error processing commit {commit_data.get('id', 'unknown')}: {str(e)}")


# ==============================================================================
# 메인 실행 블록 (Main Execution)
# ==============================================================================
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    if not os.getenv('SMEE_URL'):
        logger.error("FATAL: SMEE_URL environment variable is not set.")
        sys.exit(1)
    
    uvicorn.run(
        "api_client:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
