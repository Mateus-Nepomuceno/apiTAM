from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field


class StatusTarefa(str, Enum):
    PENDENTE = 'Pendente'
    EM_ANDAMENTO = 'EmAndamento'
    EM_REVISAO = 'EmRevisao'
    CONCLUIDA = 'Concluida'
    CANCELADA = 'Cancelada'


class PrioridadeTarefa(str, Enum):
    BAIXA = 'Baixa'
    MEDIA = 'Media'
    ALTA = 'Alta'
    URGENTE = 'Urgente'


class ItemChecklist(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    titulo: str
    concluido: bool = False


class Comentario(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    autor_id: PydanticObjectId
    texto: str
    criado_em: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class HistoricoStatusTarefa(BaseModel):
    status_anterior: StatusTarefa
    status_novo: StatusTarefa
    data_alteracao: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    autor_id: PydanticObjectId


class TarefaModel(Document):
    titulo: str
    descricao: Optional[str] = None
    projeto_id: Optional[PydanticObjectId] = None
    responsavel_id: Optional[PydanticObjectId] = None
    criador_id: PydanticObjectId
    status: StatusTarefa = StatusTarefa.PENDENTE
    prioridade: PrioridadeTarefa = PrioridadeTarefa.MEDIA
    etiquetas: list[str] = Field(default_factory=list)
    checklist: list[ItemChecklist] = Field(default_factory=list)
    comentarios: list[Comentario] = Field(default_factory=list)
    historico_status: list[HistoricoStatusTarefa] = Field(default_factory=list)
    data_inicio: Optional[datetime] = None
    data_prazo: Optional[datetime] = None
    data_conclusao: Optional[datetime] = None
    criado_em: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    atualizado_em: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Settings:
        name = 'tarefas'
