from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routes import authroute, clientroute, adminroute


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Инициализация базы данных...")
    await init_db()
    print("База данных готова к работе!")
    
    yield 
    
    print("Завершение работы сервера...")
    


app = FastAPI(
    title="Brow Master TMA API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(authroute.router)
app.include_router(clientroute.router)
app.include_router(adminroute.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)