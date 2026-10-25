from datetime import datetime, timezone
from typing import Optional

from beanie import Document, PydanticObjectId
from pydantic import Field

from .schemas import (
    CategoriaTreinamento,
    ModuloTreinamento,
    StatusMatricula,
)


class TreinamentoModel(Document):
    instrutor_id: PydanticObjectId
    titulo: str
    categoria: CategoriaTreinamento
    carga_horaria: int
    modulos: list[ModuloTreinamento] = Field(default_factory=list)
    criado_em: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Settings:
        name = 'treinamentos'


class MatriculaTreinamentoModel(Document):
    aluno_id: PydanticObjectId
    treinamento_id: PydanticObjectId
    status: StatusMatricula = StatusMatricula.MATRICULADO
    percentual_progresso: float = 0
    modulos_concluidos: list[str] = Field(default_factory=list)
    url_certificado: Optional[str] = None
    iniciado_em: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    concluido_em: Optional[datetime] = None

    class Settings:
        name = 'matriculas_treinamento'
