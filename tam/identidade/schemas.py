from datetime import datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

PyObjectId = Annotated[str, BeforeValidator(str)]


class PerfilUsuario(str, Enum):
    ADMIN = 'Admin'
    GESTOR = 'Gestor'
    MEMBRO = 'Membro'


class UsuarioBase(BaseModel):
    nome: str
    email: EmailStr
    perfil: PerfilUsuario
    departamento: str


class UsuarioCreate(UsuarioBase):
    senha: str


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    perfil: Optional[PerfilUsuario] = None
    departamento: Optional[str] = None
    senha: Optional[str] = None


class UsuarioResponse(UsuarioBase):
    id: Optional[PyObjectId] = Field(alias='_id', default=None)
    criado_em: datetime

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class Token(BaseModel):
    access_token: str
    token_type: str
