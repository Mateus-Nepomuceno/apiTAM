from datetime import datetime
from typing import Annotated, Optional

from beanie import PydanticObjectId
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from .models import SaudeProjeto, StatusProjeto

PyObjectId = Annotated[str, BeforeValidator(str)]


class MarcoSchema(BaseModel):
    titulo: str
    data_prevista: datetime
    concluido: bool = False


class HistoricoStatusSchema(BaseModel):
    status_anterior: StatusProjeto
    status_novo: StatusProjeto
    data_alteracao: datetime
    autor_id: PyObjectId

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class ProjetoBase(BaseModel):
    nome: str
    descricao: str
    status: StatusProjeto = StatusProjeto.PLANEJAMENTO
    saude_projeto: SaudeProjeto = SaudeProjeto.NO_PRAZO
    data_inicio: datetime
    data_entrega: datetime


class ProjetoCreate(ProjetoBase):
    responsavel_id: PydanticObjectId
    membros_equipe: list[PydanticObjectId] = Field(default_factory=list)
    marcos: list[MarcoSchema] = Field(default_factory=list)

    @model_validator(mode='after')
    def validar_datas(self) -> 'ProjetoCreate':
        inicio = self.data_inicio
        entrega = self.data_entrega
        if inicio.tzinfo is None and entrega.tzinfo is not None:
            inicio = inicio.replace(tzinfo=entrega.tzinfo)
        elif inicio.tzinfo is not None and entrega.tzinfo is None:
            entrega = entrega.replace(tzinfo=inicio.tzinfo)
        if entrega < inicio:
            raise ValueError(
                'A data de entrega não pode ser anterior à data de início.'
            )
        return self


class ProjetoUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    responsavel_id: Optional[PydanticObjectId] = None
    status: Optional[StatusProjeto] = None
    saude_projeto: Optional[SaudeProjeto] = None
    percentual_progresso: Optional[float] = Field(
        default=None, ge=0.0, le=100.0
    )
    membros_equipe: Optional[list[PydanticObjectId]] = None
    marcos: Optional[list[MarcoSchema]] = None
    data_inicio: Optional[datetime] = None
    data_entrega: Optional[datetime] = None

    @model_validator(mode='after')
    def validar_datas(self) -> 'ProjetoUpdate':
        if (
            self.data_inicio is not None
            and self.data_entrega is not None
            and self.data_entrega < self.data_inicio
        ):
            raise ValueError(
                'A data de entrega não pode ser anterior à data de início.'
            )
        return self


class ProjetoResponse(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    nome: str
    descricao: str
    responsavel_id: PyObjectId
    status: StatusProjeto
    saude_projeto: SaudeProjeto
    percentual_progresso: float
    membros_equipe: list[PyObjectId] = Field(default_factory=list)
    marcos: list[MarcoSchema] = Field(default_factory=list)
    historico_status: list[HistoricoStatusSchema] = Field(default_factory=list)
    data_inicio: datetime
    data_entrega: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )
