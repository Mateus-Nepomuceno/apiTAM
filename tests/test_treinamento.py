from http import HTTPStatus

import pytest
from beanie import PydanticObjectId

from tam.identidade.schemas import PerfilUsuario
from tam.treinamento.models import (
    MatriculaTreinamentoModel,
    TreinamentoModel,
)
from tam.treinamento.schemas import (
    CategoriaTreinamento,
    ModuloTreinamento,
    StatusMatricula,
)

NOVO_TREINAMENTO = {
    'titulo': 'Docker na prática',
    'categoria': 'Cloud',
    'carga_horaria': 8,
    'modulos': [
        {'titulo': 'Introdução', 'ordem': 1},
        {'titulo': 'Compose', 'ordem': 2},
    ],
}

PROGRESSO_METADE = 50
PROGRESSO_COMPLETO = 100


@pytest.fixture
def criar_treinamento(client, gestor):
    def _criar(**campos):
        treinamento = TreinamentoModel(
            instrutor_id=campos.get('instrutor_id', gestor.id),
            titulo=campos.get('titulo', 'Treinamento padrão'),
            categoria=campos.get('categoria', CategoriaTreinamento.TECNICO),
            carga_horaria=campos.get('carga_horaria', 10),
            modulos=campos.get(
                'modulos',
                [
                    ModuloTreinamento(id='mod-1', titulo='Módulo 1'),
                    ModuloTreinamento(id='mod-2', titulo='Módulo 2'),
                ],
            ),
        )
        client.portal.call(treinamento.insert)
        return treinamento

    return _criar


@pytest.fixture
def treinamento(criar_treinamento):
    return criar_treinamento()


@pytest.fixture
def matricular(client):
    def _matricular(aluno, treinamento, **campos):
        matricula = MatriculaTreinamentoModel(
            aluno_id=aluno.id, treinamento_id=treinamento.id, **campos
        )
        client.portal.call(matricula.insert)
        return matricula

    return _matricular


def buscar_treinamento(client, treinamento_id):
    return client.portal.call(TreinamentoModel.get, treinamento_id)


def buscar_matricula(client, matricula_id):
    return client.portal.call(MatriculaTreinamentoModel.get, matricula_id)


def ids(response):
    return {item['_id'] for item in response.json()}


@pytest.mark.parametrize('perfil', ['gestor', 'admin'])
def test_gestao_cria_treinamento(client, token_de, request, perfil):
    usuario = request.getfixturevalue(perfil)

    response = client.post(
        '/treinamentos/',
        json=NOVO_TREINAMENTO,
        headers=token_de(usuario),
    )

    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['titulo'] == NOVO_TREINAMENTO['titulo']
    assert corpo['categoria'] == 'Cloud'
    assert corpo['instrutor_id'] == str(usuario.id)
    assert corpo['criado_em']
    assert all(modulo['id'] for modulo in corpo['modulos'])

    salvo = buscar_treinamento(client, PydanticObjectId(corpo['_id']))
    assert salvo is not None
    assert len(salvo.modulos) == len(NOVO_TREINAMENTO['modulos'])


def test_cria_treinamento_com_instrutor_informado(
    client, token_de, admin, gestor
):
    response = client.post(
        '/treinamentos/',
        json={**NOVO_TREINAMENTO, 'instrutor_id': str(gestor.id)},
        headers=token_de(admin),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['instrutor_id'] == str(gestor.id)


def test_cria_treinamento_com_instrutor_inexistente(client, token_de, gestor):
    response = client.post(
        '/treinamentos/',
        json={**NOVO_TREINAMENTO, 'instrutor_id': str(PydanticObjectId())},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_membro_nao_cria_treinamento(client, token_de, membro):
    response = client.post(
        '/treinamentos/', json=NOVO_TREINAMENTO, headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_cria_treinamento_sem_token(client):
    response = client.post('/treinamentos/', json=NOVO_TREINAMENTO)

    assert response.status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize(
    'alteracao',
    [
        {'categoria': 'Inexistente'},
        {'carga_horaria': 0},
        {'carga_horaria': -5},
        {'titulo': None},
    ],
)
def test_cria_treinamento_com_dados_invalidos(
    client, token_de, gestor, alteracao
):
    response = client.post(
        '/treinamentos/',
        json={**NOVO_TREINAMENTO, **alteracao},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_cria_treinamento_sem_campos_obrigatorios(client, token_de, gestor):
    response = client.post('/treinamentos/', json={}, headers=token_de(gestor))

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_membro_lista_catalogo(client, token_de, membro, criar_treinamento):
    primeiro = criar_treinamento(titulo='Python básico')
    segundo = criar_treinamento(titulo='Git e GitHub')

    response = client.get('/treinamentos/', headers=token_de(membro))

    assert response.status_code == HTTPStatus.OK
    assert ids(response) == {str(primeiro.id), str(segundo.id)}


def test_lista_treinamentos_sem_token(client):
    response = client.get('/treinamentos/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_filtra_catalogo_por_categoria(
    client, token_de, membro, criar_treinamento
):
    cloud = criar_treinamento(categoria=CategoriaTreinamento.CLOUD)
    criar_treinamento(categoria=CategoriaTreinamento.ONBOARDING)

    response = client.get(
        '/treinamentos/',
        params={'categoria': 'Cloud'},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK
    assert ids(response) == {str(cloud.id)}


def test_busca_catalogo_por_titulo_sem_diferenciar_maiusculas(
    client, token_de, membro, criar_treinamento
):
    python = criar_treinamento(titulo='Python Avançado')
    criar_treinamento(titulo='Liderança')

    response = client.get(
        '/treinamentos/',
        params={'busca': 'python'},
        headers=token_de(membro),
    )

    assert ids(response) == {str(python.id)}


def test_busca_trata_caracteres_especiais_como_texto(
    client, token_de, membro, criar_treinamento
):
    cpp = criar_treinamento(titulo='Introdução a C++')
    criar_treinamento(titulo='Introdução a C')

    response = client.get(
        '/treinamentos/',
        params={'busca': 'C++'},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK
    assert ids(response) == {str(cpp.id)}


def test_combina_busca_e_categoria(
    client, token_de, membro, criar_treinamento
):
    alvo = criar_treinamento(
        titulo='AWS básico', categoria=CategoriaTreinamento.CLOUD
    )
    criar_treinamento(
        titulo='AWS para gestores', categoria=CategoriaTreinamento.SOFT_SKILLS
    )

    response = client.get(
        '/treinamentos/',
        params={'busca': 'aws', 'categoria': 'Cloud'},
        headers=token_de(membro),
    )

    assert ids(response) == {str(alvo.id)}


def test_pagina_catalogo(client, token_de, membro, criar_treinamento):
    for n in range(3):
        criar_treinamento(titulo=f'Curso {n}')

    response = client.get(
        '/treinamentos/',
        params={'limit': 2, 'skip': 1},
        headers=token_de(membro),
    )

    assert len(response.json()) == 2  # noqa: PLR2004


def test_obtem_treinamento(client, token_de, membro, treinamento):
    response = client.get(
        f'/treinamentos/{treinamento.id}', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['_id'] == str(treinamento.id)
    assert [m['id'] for m in response.json()['modulos']] == [
        'mod-1',
        'mod-2',
    ]


def test_obtem_treinamento_inexistente(client, token_de, membro):
    response = client.get(
        f'/treinamentos/{PydanticObjectId()}', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_obtem_treinamento_com_id_invalido(client, token_de, membro):
    response = client.get('/treinamentos/abc', headers=token_de(membro))

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_gestor_atualiza_treinamento(client, token_de, gestor, treinamento):
    response = client.patch(
        f'/treinamentos/{treinamento.id}',
        json={'titulo': 'Título novo', 'carga_horaria': 20},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['titulo'] == 'Título novo'
    salvo = buscar_treinamento(client, treinamento.id)
    assert salvo.titulo == 'Título novo'
    assert salvo.carga_horaria == 20  # noqa: PLR2004
    assert salvo.categoria == treinamento.categoria


def test_atualiza_modulos_do_treinamento(
    client, token_de, gestor, treinamento
):
    response = client.patch(
        f'/treinamentos/{treinamento.id}',
        json={'modulos': [{'titulo': 'Único módulo'}]},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.OK
    assert [m['titulo'] for m in response.json()['modulos']] == [
        'Único módulo'
    ]


def test_membro_nao_atualiza_treinamento(
    client, token_de, membro, treinamento
):
    response = client.patch(
        f'/treinamentos/{treinamento.id}',
        json={'titulo': 'Invasão'},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert (
        buscar_treinamento(client, treinamento.id).titulo == treinamento.titulo
    )


def test_atualiza_treinamento_inexistente(client, token_de, gestor):
    response = client.patch(
        f'/treinamentos/{PydanticObjectId()}',
        json={'titulo': 'X'},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_atualiza_treinamento_com_instrutor_inexistente(
    client, token_de, gestor, treinamento
):
    response = client.patch(
        f'/treinamentos/{treinamento.id}',
        json={'instrutor_id': str(PydanticObjectId())},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_gestor_apaga_treinamento(client, token_de, gestor, treinamento):
    response = client.delete(
        f'/treinamentos/{treinamento.id}', headers=token_de(gestor)
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert buscar_treinamento(client, treinamento.id) is None


def test_membro_nao_apaga_treinamento(client, token_de, membro, treinamento):
    response = client.delete(
        f'/treinamentos/{treinamento.id}', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert buscar_treinamento(client, treinamento.id) is not None


def test_apagar_treinamento_remove_matriculas(
    client, token_de, gestor, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.delete(
        f'/treinamentos/{treinamento.id}', headers=token_de(gestor)
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert buscar_treinamento(client, treinamento.id) is None
    assert buscar_matricula(client, matricula.id) is None


def test_gestor_que_nao_e_instrutor_nao_altera_treinamento(
    client, token_de, criar_usuario, treinamento
):
    outro_gestor = criar_usuario(PerfilUsuario.GESTOR)

    response = client.patch(
        f'/treinamentos/{treinamento.id}',
        json={'titulo': 'X'},
        headers=token_de(outro_gestor),
    )
    assert response.status_code == HTTPStatus.FORBIDDEN

    response = client.delete(
        f'/treinamentos/{treinamento.id}', headers=token_de(outro_gestor)
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_membro_instrutor_altera_treinamento(
    client, token_de, membro, criar_treinamento
):
    treinamento = criar_treinamento(instrutor_id=membro.id)

    response = client.patch(
        f'/treinamentos/{treinamento.id}',
        json={'descricao': 'Nova descrição'},
        headers=token_de(membro),
    )
    assert response.status_code == HTTPStatus.OK
    assert response.json()['descricao'] == 'Nova descrição'


def test_desmarcar_modulos_reabre_matricula(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)
    url = f'/matriculas/{matricula.id}'

    concluida = client.patch(
        url,
        json={'modulos_concluidos': ['mod-1', 'mod-2']},
        headers=token_de(membro),
    ).json()
    assert concluida['status'] == StatusMatricula.CONCLUIDO.value
    assert concluida['url_certificado']

    parcial = client.patch(
        url, json={'modulos_concluidos': ['mod-1']}, headers=token_de(membro)
    ).json()
    assert parcial['status'] == StatusMatricula.EM_ANDAMENTO.value
    assert parcial['concluido_em'] is None
    assert parcial['url_certificado'] is None

    zerada = client.patch(
        url, json={'modulos_concluidos': []}, headers=token_de(membro)
    ).json()
    assert zerada['status'] == StatusMatricula.MATRICULADO.value
    assert zerada['percentual_progresso'] == 0


def test_apaga_treinamento_inexistente(client, token_de, gestor):
    response = client.delete(
        f'/treinamentos/{PydanticObjectId()}', headers=token_de(gestor)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_membro_se_matricula(client, token_de, membro, treinamento):
    response = client.post(
        '/matriculas/',
        json={'treinamento_id': str(treinamento.id)},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['aluno_id'] == str(membro.id)
    assert corpo['treinamento_id'] == str(treinamento.id)
    assert corpo['status'] == StatusMatricula.MATRICULADO.value
    assert corpo['percentual_progresso'] == 0
    assert corpo['modulos_concluidos'] == []
    assert corpo['url_certificado'] is None
    assert corpo['iniciado_em']
    assert corpo['concluido_em'] is None
    assert buscar_matricula(client, PydanticObjectId(corpo['_id']))


def test_gestor_matricula_outro_aluno(
    client, token_de, gestor, membro, treinamento
):
    response = client.post(
        '/matriculas/',
        json={
            'treinamento_id': str(treinamento.id),
            'aluno_id': str(membro.id),
        },
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['aluno_id'] == str(membro.id)


def test_membro_nao_matricula_outro_aluno(
    client, token_de, membro, criar_usuario, treinamento
):
    outro = criar_usuario(PerfilUsuario.MEMBRO)

    response = client.post(
        '/matriculas/',
        json={
            'treinamento_id': str(treinamento.id),
            'aluno_id': str(outro.id),
        },
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_matricula_em_treinamento_inexistente(client, token_de, membro):
    response = client.post(
        '/matriculas/',
        json={'treinamento_id': str(PydanticObjectId())},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_matricula_de_aluno_inexistente(client, token_de, gestor, treinamento):
    response = client.post(
        '/matriculas/',
        json={
            'treinamento_id': str(treinamento.id),
            'aluno_id': str(PydanticObjectId()),
        },
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_matricula_sem_treinamento_id(client, token_de, membro):
    response = client.post('/matriculas/', json={}, headers=token_de(membro))

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_matricula_sem_token(client, treinamento):
    response = client.post(
        '/matriculas/', json={'treinamento_id': str(treinamento.id)}
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_matricula_duplicada(
    client, token_de, membro, treinamento, matricular
):
    matricular(membro, treinamento)

    response = client.post(
        '/matriculas/',
        json={'treinamento_id': str(treinamento.id)},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_rematricula_apos_desistencia(
    client, token_de, membro, treinamento, matricular
):
    matricular(membro, treinamento, status=StatusMatricula.DESISTENTE)

    response = client.post(
        '/matriculas/',
        json={'treinamento_id': str(treinamento.id)},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['status'] == StatusMatricula.MATRICULADO.value


def test_membro_lista_apenas_as_proprias_matriculas(
    client, token_de, membro, criar_usuario, treinamento, matricular
):
    outro = criar_usuario(PerfilUsuario.MEMBRO)
    propria = matricular(membro, treinamento)
    matricular(outro, treinamento)

    response = client.get('/matriculas/', headers=token_de(membro))

    assert response.status_code == HTTPStatus.OK
    assert ids(response) == {str(propria.id)}


def test_membro_nao_burla_filtro_de_aluno(
    client, token_de, membro, criar_usuario, treinamento, matricular
):
    outro = criar_usuario(PerfilUsuario.MEMBRO)
    propria = matricular(membro, treinamento)
    matricular(outro, treinamento)

    response = client.get(
        '/matriculas/',
        params={'aluno_id': str(outro.id)},
        headers=token_de(membro),
    )

    assert ids(response) == {str(propria.id)}


def test_gestor_lista_todas_as_matriculas(
    client, token_de, gestor, membro, criar_usuario, treinamento, matricular
):
    outro = criar_usuario(PerfilUsuario.MEMBRO)
    primeira = matricular(membro, treinamento)
    segunda = matricular(outro, treinamento)

    response = client.get('/matriculas/', headers=token_de(gestor))

    assert ids(response) == {str(primeira.id), str(segunda.id)}


def test_gestor_filtra_matriculas(
    client,
    token_de,
    gestor,
    membro,
    criar_usuario,
    criar_treinamento,
    matricular,
):
    outro = criar_usuario(PerfilUsuario.MEMBRO)
    curso_a = criar_treinamento(titulo='A')
    curso_b = criar_treinamento(titulo='B')
    ativa = matricular(membro, curso_a)
    concluida = matricular(outro, curso_a, status=StatusMatricula.CONCLUIDO)
    matricular(membro, curso_b)

    por_status = client.get(
        '/matriculas/',
        params={'status': 'Concluido'},
        headers=token_de(gestor),
    )
    por_treinamento = client.get(
        '/matriculas/',
        params={'treinamento_id': str(curso_a.id)},
        headers=token_de(gestor),
    )
    por_aluno = client.get(
        '/matriculas/',
        params={'aluno_id': str(outro.id)},
        headers=token_de(gestor),
    )

    assert ids(por_status) == {str(concluida.id)}
    assert ids(por_treinamento) == {str(ativa.id), str(concluida.id)}
    assert ids(por_aluno) == {str(concluida.id)}


def test_lista_matriculas_sem_token(client):
    response = client.get('/matriculas/')

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_membro_obtem_propria_matricula(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.get(
        f'/matriculas/{matricula.id}', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['_id'] == str(matricula.id)


def test_membro_nao_obtem_matricula_de_outro(
    client, token_de, membro, criar_usuario, treinamento, matricular
):
    outro = criar_usuario(PerfilUsuario.MEMBRO)
    matricula = matricular(outro, treinamento)

    response = client.get(
        f'/matriculas/{matricula.id}', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_gestor_obtem_qualquer_matricula(
    client, token_de, gestor, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.get(
        f'/matriculas/{matricula.id}', headers=token_de(gestor)
    )

    assert response.status_code == HTTPStatus.OK


def test_obtem_matricula_inexistente(client, token_de, membro):
    response = client.get(
        f'/matriculas/{PydanticObjectId()}', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_concluir_modulo_atualiza_progresso_e_status(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'modulos_concluidos': ['mod-1']},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert corpo['modulos_concluidos'] == ['mod-1']
    assert corpo['percentual_progresso'] == PROGRESSO_METADE
    assert corpo['status'] == StatusMatricula.EM_ANDAMENTO.value
    assert corpo['concluido_em'] is None

    salva = buscar_matricula(client, matricula.id)
    assert salva.status == StatusMatricula.EM_ANDAMENTO
    assert salva.percentual_progresso == PROGRESSO_METADE


def test_concluir_todos_os_modulos_conclui_a_matricula(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'modulos_concluidos': ['mod-1', 'mod-2']},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert corpo['percentual_progresso'] == PROGRESSO_COMPLETO
    assert corpo['status'] == StatusMatricula.CONCLUIDO.value
    assert corpo['concluido_em'] is not None


def test_concluir_modulos_em_etapas(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)
    url = f'/matriculas/{matricula.id}'

    client.patch(
        url, json={'modulos_concluidos': ['mod-1']}, headers=token_de(membro)
    )
    response = client.patch(
        url,
        json={'modulos_concluidos': ['mod-1', 'mod-2']},
        headers=token_de(membro),
    )

    assert response.json()['status'] == StatusMatricula.CONCLUIDO.value
    assert response.json()['percentual_progresso'] == PROGRESSO_COMPLETO


def test_modulos_repetidos_contam_uma_vez(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'modulos_concluidos': ['mod-1', 'mod-1']},
        headers=token_de(membro),
    )

    assert response.json()['modulos_concluidos'] == ['mod-1']
    assert response.json()['percentual_progresso'] == PROGRESSO_METADE


def test_modulo_invalido_e_rejeitado(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'modulos_concluidos': ['mod-que-nao-existe']},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    salva = buscar_matricula(client, matricula.id)
    assert salva.modulos_concluidos == []
    assert salva.status == StatusMatricula.MATRICULADO


def test_membro_nao_atualiza_matricula_de_outro(
    client, token_de, membro, criar_usuario, treinamento, matricular
):
    outro = criar_usuario(PerfilUsuario.MEMBRO)
    matricula = matricular(outro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'modulos_concluidos': ['mod-1']},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.FORBIDDEN


@pytest.mark.parametrize(
    'corpo',
    [
        {'percentual_progresso': 100},
        {'url_certificado': 'https://exemplo.com/certificado.pdf'},
        {'status': 'Concluido'},
    ],
)
def test_membro_nao_altera_campos_restritos(
    client, token_de, membro, treinamento, matricular, corpo
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}', json=corpo, headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    salva = buscar_matricula(client, matricula.id)
    assert salva.status == StatusMatricula.MATRICULADO
    assert salva.percentual_progresso == 0
    assert salva.url_certificado is None


def test_membro_desiste_do_treinamento(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'status': 'Desistente'},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['status'] == StatusMatricula.DESISTENTE.value


def test_progresso_reabre_matricula_desistente(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(
        membro, treinamento, status=StatusMatricula.DESISTENTE
    )

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'modulos_concluidos': ['mod-1']},
        headers=token_de(membro),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['status'] == StatusMatricula.EM_ANDAMENTO.value


def test_gestor_registra_certificado(
    client, token_de, gestor, membro, treinamento, matricular
):
    matricula = matricular(
        membro,
        treinamento,
        status=StatusMatricula.CONCLUIDO,
        percentual_progresso=PROGRESSO_COMPLETO,
    )
    url = 'https://exemplo.com/certificado.pdf'

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'url_certificado': url},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['url_certificado'] == url
    assert buscar_matricula(client, matricula.id).url_certificado == url


def test_gestor_conclui_matricula_manualmente(
    client, token_de, gestor, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'status': 'Concluido'},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()['status'] == StatusMatricula.CONCLUIDO.value
    assert response.json()['concluido_em'] is not None


def test_progresso_fora_do_intervalo(
    client, token_de, gestor, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.patch(
        f'/matriculas/{matricula.id}',
        json={'percentual_progresso': 150},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_atualiza_matricula_inexistente(client, token_de, gestor):
    response = client.patch(
        f'/matriculas/{PydanticObjectId()}',
        json={'status': 'Desistente'},
        headers=token_de(gestor),
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_gestor_apaga_matricula(
    client, token_de, gestor, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.delete(
        f'/matriculas/{matricula.id}', headers=token_de(gestor)
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert buscar_matricula(client, matricula.id) is None


def test_membro_nao_apaga_matricula(
    client, token_de, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)

    response = client.delete(
        f'/matriculas/{matricula.id}', headers=token_de(membro)
    )

    assert response.status_code == HTTPStatus.FORBIDDEN
    assert buscar_matricula(client, matricula.id) is not None


def test_apaga_matricula_inexistente(client, token_de, gestor):
    response = client.delete(
        f'/matriculas/{PydanticObjectId()}', headers=token_de(gestor)
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_treinamento_pode_ser_apagado_apos_remover_matriculas(
    client, token_de, gestor, membro, treinamento, matricular
):
    matricula = matricular(membro, treinamento)
    client.delete(f'/matriculas/{matricula.id}', headers=token_de(gestor))

    response = client.delete(
        f'/treinamentos/{treinamento.id}', headers=token_de(gestor)
    )

    assert response.status_code == HTTPStatus.NO_CONTENT
