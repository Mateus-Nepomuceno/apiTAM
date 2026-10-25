from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

from tam.identidade.schemas import PyObjectId


class CategoriaTreinamento(str, Enum):
    TECNICO = 'Tecnico'
    SOFT_SKILLS = 'SoftSkills'
    ONBOARDING = 'Onboarding'
    CLOUD = 'Cloud'


class StatusMatricula(str, Enum):
    MATRICULADO = 'Matriculado'
    EM_ANDAMENTO = 'EmAndamento'
    CONCLUIDO = 'Concluido'
    DESISTENTE = 'Desistente'


class ModuloTreinamento(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    titulo: str
    descricao: Optional[str] = None
    ordem: int = Field(default=0, ge=0)


class TreinamentoBase(BaseModel):
    titulo: str
    categoria: CategoriaTreinamento
    carga_horaria: int = Field(gt=0)
    modulos: list[ModuloTreinamento] = Field(default_factory=list)


class TreinamentoCreate(TreinamentoBase):
    instrutor_id: Optional[PydanticObjectId] = None


class TreinamentoUpdate(BaseModel):
    instrutor_id: Optional[PydanticObjectId] = None
    titulo: Optional[str] = None
    categoria: Optional[CategoriaTreinamento] = None
    carga_horaria: Optional[int] = Field(default=None, gt=0)
    modulos: Optional[list[ModuloTreinamento]] = None


class TreinamentoResponse(TreinamentoBase):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    instrutor_id: PyObjectId
    criado_em: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class MatriculaCreate(BaseModel):
    treinamento_id: PydanticObjectId
    aluno_id: Optional[PydanticObjectId] = None


class MatriculaUpdate(BaseModel):
    status: Optional[StatusMatricula] = None
    percentual_progresso: Optional[float] = Field(default=None, ge=0, le=100)
    modulos_concluidos: Optional[list[str]] = None
    url_certificado: Optional[str] = None


class MatriculaResponse(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    aluno_id: PyObjectId
    treinamento_id: PyObjectId
    status: StatusMatricula
    percentual_progresso: float
    modulos_concluidos: list[str]
    url_certificado: Optional[str] = None
    iniciado_em: datetime
    concluido_em: Optional[datetime] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )
