from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tam.core.database import init_db
from tam.core.settings import Settings
from tam.identidade.routers import auth, usuarios
from tam.projeto.routers import projeto
from tam.tarefa.routers import tarefa
from tam.treinamento.routers import matricula, treinamento


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origem.strip()
        for origem in Settings().CORS_ORIGINS.split(',')
        if origem.strip()
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(treinamento.router)
app.include_router(matricula.router)
app.include_router(projeto.router)
app.include_router(tarefa.router)


@app.get('/health', tags=['health'])
async def health():
    return {'status': 'ok'}
