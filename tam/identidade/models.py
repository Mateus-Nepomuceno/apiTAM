from datetime import datetime, timezone
from typing import Annotated

from beanie import Document, Indexed
from pydantic import EmailStr, Field

from .schemas import PerfilUsuario


class UsuarioModel(Document):
    nome: str
    email: Annotated[EmailStr, Indexed(unique=True)]
    perfil: PerfilUsuario = PerfilUsuario.MEMBRO
    departamento: str
    senha: str
    criado_em: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    class Settings:
        name = 'usuarios'
