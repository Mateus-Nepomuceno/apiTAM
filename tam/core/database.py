from beanie import init_beanie
from pymongo import AsyncMongoClient

from tam.identidade.models import UsuarioModel
from tam.projeto.models import ProjetoModel
from tam.tarefa.models import TarefaModel
from tam.treinamento.models import (
    MatriculaTreinamentoModel,
    TreinamentoModel,
)

from .settings import Settings


async def init_db():
    settings = Settings()
    client = AsyncMongoClient(settings.DATABASE_URL)

    await init_beanie(
        database=client[settings.DATABASE_NAME],
        document_models=[
            UsuarioModel,
            TreinamentoModel,
            MatriculaTreinamentoModel,
            ProjetoModel,
            TarefaModel,
        ]
    )
