from datetime import datetime
from typing import Annotated, Optional
from uuid import uuid4

from beanie import PydanticObjectId
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)

from .models import PrioridadeTarefa, StatusTarefa

PyObjectId = Annotated[str, BeforeValidator(str)]


class ItemChecklistSchema(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    titulo: str
    concluido: bool = False


class ComentarioCreate(BaseModel):
    texto: str


class ComentarioSchema(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    autor_id: PyObjectId
    texto: str
    criado_em: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class HistoricoStatusTarefaSchema(BaseModel):
    status_anterior: StatusTarefa
    status_novo: StatusTarefa
    data_alteracao: datetime
    autor_id: PyObjectId

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class TarefaBase(BaseModel):
    titulo: str
    descricao: Optional[str] = None
    projeto_id: Optional[PydanticObjectId] = None
    responsavel_id: Optional[PydanticObjectId] = None
    status: StatusTarefa = StatusTarefa.PENDENTE
    prioridade: PrioridadeTarefa = PrioridadeTarefa.MEDIA
    etiquetas: list[str] = Field(default_factory=list)
    checklist: list[ItemChecklistSchema] = Field(default_factory=list)
    data_inicio: Optional[datetime] = None
    data_prazo: Optional[datetime] = None


class TarefaCreate(TarefaBase):
    criador_id: Optional[PydanticObjectId] = None

    @model_validator(mode='after')
    def validar_datas(self) -> 'TarefaCreate':
        inicio = self.data_inicio
        prazo = self.data_prazo
        if inicio is not None and prazo is not None:
            if inicio.tzinfo is None and prazo.tzinfo is not None:
                inicio = inicio.replace(tzinfo=prazo.tzinfo)
            elif inicio.tzinfo is not None and prazo.tzinfo is None:
                prazo = prazo.replace(tzinfo=inicio.tzinfo)
            if prazo < inicio:
                raise ValueError(
                    'A data de prazo não pode ser anterior à data de início.'
                )
        return self


class TarefaUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    projeto_id: Optional[PydanticObjectId] = None
    responsavel_id: Optional[PydanticObjectId] = None
    status: Optional[StatusTarefa] = None
    prioridade: Optional[PrioridadeTarefa] = None
    etiquetas: Optional[list[str]] = None
    checklist: Optional[list[ItemChecklistSchema]] = None
    novo_comentario: Optional[str] = None
    data_inicio: Optional[datetime] = None
    data_prazo: Optional[datetime] = None

    @model_validator(mode='after')
    def validar_datas(self) -> 'TarefaUpdate':
        if (
            self.data_inicio is not None
            and self.data_prazo is not None
            and self.data_prazo < self.data_inicio
        ):
            raise ValueError(
                'A data de prazo não pode ser anterior à data de início.'
            )
        return self


class TarefaResponse(BaseModel):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    titulo: str
    descricao: Optional[str] = None
    projeto_id: Optional[PyObjectId] = None
    responsavel_id: Optional[PyObjectId] = None
    criador_id: PyObjectId
    status: StatusTarefa
    prioridade: PrioridadeTarefa
    etiquetas: list[str] = Field(default_factory=list)
    checklist: list[ItemChecklistSchema] = Field(default_factory=list)
    comentarios: list[ComentarioSchema] = Field(default_factory=list)
    historico_status: list[HistoricoStatusTarefaSchema] = Field(
        default_factory=list
    )
    data_inicio: Optional[datetime] = None
    data_prazo: Optional[datetime] = None
    data_conclusao: Optional[datetime] = None
    criado_em: datetime
    atualizado_em: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class FiltroTarefa(BaseModel):
    projeto_id: Optional[PydanticObjectId] = None
    responsavel_id: Optional[PydanticObjectId] = None
    status: Optional[StatusTarefa] = None
    prioridade: Optional[PrioridadeTarefa] = None
    etiqueta: Optional[str] = None
    skip: int = 0
    limit: int = 100
