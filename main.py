import os
import google.generativeai as genai
import logging
import requests
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Gemini API
GEMINI_API_KEY = "AIzaSyD-3oW_zoKiH2AO_KNlUtD8CoOTcnnNjHA"

try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-pro",
        generation_config={
            "temperature": 1,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
        }
    )
    logger.info("Gemini API configured successfully")
except Exception as e:
    logger.error(f"Failed to configure Gemini API: {str(e)}")
    raise

app = FastAPI(title="TaskFlow")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class Subtask(BaseModel):
    title: str
    deadline: Optional[str] = None
    completed: bool = False

class Task(BaseModel):
    title: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = None
    deadline: str
    priority: str
    subtasks: List[Subtask] = []

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        valid_priorities = ['low', 'medium', 'high']
        if v.lower() not in valid_priorities:
            raise ValueError(f"Priority must be one of {valid_priorities}")
        return v.lower()

class TaskRepository:
    _tasks = []
    _current_id = 0

    @classmethod
    def add_task(cls, task: dict):
        task['id'] = cls._current_id + 1
        cls._current_id += 1
        cls._tasks.append(task)
        return task

    @classmethod
    def get_tasks(cls):
        return cls._tasks

def generate_subtasks(task: Task) -> List[Subtask]:
    try:
        formatted_prompt = f"""
        Break down this task into subtasks:
        Title: {task.title}
        Description: {task.description or 'No additional description'}
        Deadline: {task.deadline}

        Return a JSON array of subtasks in this format:
        [{{"title": "subtask title", "deadline": "subtask deadline"}}]
        """
        
        response = model.generate_content(formatted_prompt)
        logger.info(f"Gemini API response: {response.text}")
        
        try:
            subtasks = json.loads(response.text)
            return [Subtask(**subtask) for subtask in subtasks]
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Failed to parse subtasks: {e}")
            return [Subtask(title=f"Plan {task.title}", deadline=task.deadline)]
            
    except Exception as e:
        logger.error(f"Subtask generation error: {e}")
        return [Subtask(title=f"Initial step for {task.title}", deadline=task.deadline)]

@app.post("/api/create-task", response_model=Task)
async def create_task(task: Task):
    try:
        logger.info(f"Received task creation request: {task.dict()}")
        task.subtasks = generate_subtasks(task)
        stored_task = TaskRepository.add_task(task.dict())
        logger.info(f"Task created successfully: {stored_task}")
        return stored_task
    except Exception as e:
        logger.error(f"Task creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("create-task.html", {"request": request})

@app.get("/api/get-tasks")
async def get_tasks():
    tasks = TaskRepository.get_tasks()
    logger.info(f"Returning tasks: {json.dumps(tasks, indent=2)}")
    return tasks

def fetch_tasks():
    try:
        response = requests.get('http://localhost:8000/api/get-tasks')
        response.raise_for_status()
        tasks = response.json()
        logger.info(f"Fetched tasks: {json.dumps(tasks, indent=2)}")
        return tasks
    except requests.RequestException as e:
        logger.error(f"Error fetching tasks: {e}")
        return []

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)