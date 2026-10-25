from datetime import datetime, timezone
from enum import Enum

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field


class StatusProjeto(str, Enum):
    PLANEJAMENTO = 'Planejamento'
    ATIVO = 'Ativo'
    PAUSADO = 'Pausado'
    CONCLUIDO = 'Concluido'
    CANCELADO = 'Cancelado'


class SaudeProjeto(str, Enum):
    NO_PRAZO = 'NoPrazo'
    EM_RISCO = 'EmRisco'
    ATRASADO = 'Atrasado'


class Marco(BaseModel):
    titulo: str
    data_prevista: datetime
    concluido: bool = False


class HistoricoStatus(BaseModel):
    status_anterior: StatusProjeto
    status_novo: StatusProjeto
    data_alteracao: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    autor_id: PydanticObjectId


class ProjetoModel(Document):
    nome: str
    descricao: str
    responsavel_id: PydanticObjectId
    status: StatusProjeto = StatusProjeto.PLANEJAMENTO
    saude_projeto: SaudeProjeto = SaudeProjeto.NO_PRAZO
    percentual_progresso: float = Field(default=0.0, ge=0.0, le=100.0)
    membros_equipe: list[PydanticObjectId] = Field(default_factory=list)
    marcos: list[Marco] = Field(default_factory=list)
    historico_status: list[HistoricoStatus] = Field(default_factory=list)
    data_inicio: datetime
    data_entrega: datetime

    class Settings:
        name = 'projetos'
