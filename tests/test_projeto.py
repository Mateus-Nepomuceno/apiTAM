from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import pytest

from tam.projeto.models import ProjetoModel, SaudeProjeto, StatusProjeto
from tam.tarefa.models import TarefaModel

PROGRESSO_INICIAL = 30


def buscar(client, projeto_id):
    return client.portal.call(ProjetoModel.get, projeto_id)


def test_criar_projeto_nao_autenticado(client, admin):
    payload = {
        'nome': 'Projeto Sem Auth',
        'descricao': 'Tentativa sem token',
        'responsavel_id': str(admin.id),
        'data_inicio': datetime.now(timezone.utc).isoformat(),
        'data_entrega': (
            datetime.now(timezone.utc) + timedelta(days=10)
        ).isoformat(),
    }
    response = client.post('/projetos/', json=payload)
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_membro_nao_cria_projeto(client, membro, token_de):
    payload = {
        'nome': 'Projeto de Membro',
        'descricao': 'Membro não deve ter permissão de criação',
        'responsavel_id': str(membro.id),
        'data_inicio': datetime.now(timezone.utc).isoformat(),
        'data_entrega': (
            datetime.now(timezone.utc) + timedelta(days=10)
        ).isoformat(),
    }
    response = client.post(
        '/projetos/', json=payload, headers=token_de(membro)
    )
    assert response.status_code == HTTPStatus.FORBIDDEN


def test_gestor_cria_projeto_com_sucesso(client, gestor, token_de):
    agora = datetime.now(timezone.utc)
    payload = {
        'nome': 'Projeto Gestor Alpha',
        'descricao': 'Criado pelo gestor',
        'responsavel_id': str(gestor.id),
        'status': 'Planejamento',
        'saude_projeto': 'NoPrazo',
        'data_inicio': agora.isoformat(),
        'data_entrega': (agora + timedelta(days=30)).isoformat(),
    }
    response = client.post(
        '/projetos/', json=payload, headers=token_de(gestor)
    )
    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['nome'] == payload['nome']
    assert corpo['status'] == StatusProjeto.PLANEJAMENTO.value
    assert corpo['saude_projeto'] == SaudeProjeto.NO_PRAZO.value
    assert corpo['responsavel_id'] == str(gestor.id)
    assert corpo['percentual_progresso'] == 0.0

    salvo = buscar(client, corpo['_id'])
    assert salvo is not None
    assert salvo.nome == payload['nome']


def test_admin_cria_projeto_com_sucesso(client, admin, token_de):
    agora = datetime.now(timezone.utc)
    payload = {
        'nome': 'Projeto Diretoria',
        'descricao': 'Criado pelo administrador',
        'responsavel_id': str(admin.id),
        'data_inicio': agora.isoformat(),
        'data_entrega': (agora + timedelta(days=60)).isoformat(),
    }
    response = client.post('/projetos/', json=payload, headers=token_de(admin))
    assert response.status_code == HTTPStatus.CREATED
    assert response.json()['nome'] == payload['nome']


def test_criar_projeto_com_data_entrega_anterior_ao_inicio(
    client, gestor, token_de
):
    agora = datetime.now(timezone.utc)
    payload = {
        'nome': 'Projeto Invalido',
        'descricao': 'Datas inconsistentes',
        'responsavel_id': str(gestor.id),
        'data_inicio': agora.isoformat(),
        'data_entrega': (agora - timedelta(days=5)).isoformat(),
    }
    response = client.post(
        '/projetos/', json=payload, headers=token_de(gestor)
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_listar_projetos_autenticado(client, criar_projeto, membro, token_de):
    qtd_projetos = 2
    criar_projeto(nome='Projeto 1')
    criar_projeto(nome='Projeto 2')

    response = client.get('/projetos/', headers=token_de(membro))
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert len(corpo) >= qtd_projetos


def test_listar_projetos_com_filtro_status(
    client, criar_projeto, gestor, token_de
):
    criar_projeto(nome='Ativo 1', status=StatusProjeto.ATIVO)
    criar_projeto(nome='Planejamento 1', status=StatusProjeto.PLANEJAMENTO)

    response = client.get('/projetos/?status=Ativo', headers=token_de(gestor))
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert all(p['status'] == StatusProjeto.ATIVO.value for p in corpo)
    assert any(p['nome'] == 'Ativo 1' for p in corpo)
    assert not any(p['nome'] == 'Planejamento 1' for p in corpo)


def test_listar_projetos_com_filtro_saude(
    client, criar_projeto, admin, token_de
):
    criar_projeto(nome='No Prazo', saude_projeto=SaudeProjeto.NO_PRAZO)
    criar_projeto(nome='Em Risco', saude_projeto=SaudeProjeto.EM_RISCO)

    response = client.get('/projetos/?saude=EmRisco', headers=token_de(admin))
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert all(
        p['saude_projeto'] == SaudeProjeto.EM_RISCO.value for p in corpo
    )
    assert any(p['nome'] == 'Em Risco' for p in corpo)
    assert not any(p['nome'] == 'No Prazo' for p in corpo)


def test_obter_projeto_por_id_existente(
    client, criar_projeto, membro, token_de
):
    projeto = criar_projeto(nome='Projeto Detalhado')

    response = client.get(f'/projetos/{projeto.id}', headers=token_de(membro))
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert corpo['_id'] == str(projeto.id)
    assert corpo['nome'] == 'Projeto Detalhado'


def test_obter_projeto_por_id_inexistente(client, membro, token_de):
    response = client.get(
        '/projetos/000000000000000000000000', headers=token_de(membro)
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_transicao_de_status_acumula_historico(
    client, criar_projeto, gestor, token_de
):
    projeto = criar_projeto(
        responsavel=gestor,
        nome='Projeto Auditoria',
        status=StatusProjeto.PLANEJAMENTO,
    )

    response = client.patch(
        f'/projetos/{projeto.id}',
        json={'status': 'Ativo'},
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.OK
    corpo = response.json()
    assert corpo['status'] == StatusProjeto.ATIVO.value
    assert len(corpo['historico_status']) == 1

    historico = corpo['historico_status'][0]
    assert historico['status_anterior'] == StatusProjeto.PLANEJAMENTO.value
    assert historico['status_novo'] == StatusProjeto.ATIVO.value
    assert historico['autor_id'] == str(gestor.id)


def test_atualizar_projeto_com_data_entrega_anterior_ao_inicio(
    client, criar_projeto, gestor, token_de
):
    projeto = criar_projeto(responsavel=gestor)

    response = client.patch(
        f'/projetos/{projeto.id}',
        json={
            'data_entrega': (
                projeto.data_inicio - timedelta(days=1)
            ).isoformat()
        },
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.parametrize(
    ('ator', 'participa', 'esperado'),
    [
        ('admin', False, HTTPStatus.OK),
        ('gestor', True, HTTPStatus.OK),
        ('gestor', False, HTTPStatus.FORBIDDEN),
        ('membro', True, HTTPStatus.FORBIDDEN),
    ],
)
def test_permissao_de_edicao_de_projeto(
    client, criar_projeto, token_de, request, ator, participa, esperado
):
    usuario_ator = request.getfixturevalue(ator)
    projeto = criar_projeto(
        descricao='Descricao Original',
        membros_equipe=[usuario_ator.id] if participa else [],
    )

    response = client.patch(
        f'/projetos/{projeto.id}',
        json={'descricao': 'Nova Descricao'},
        headers=token_de(usuario_ator),
    )
    assert response.status_code == esperado

    salvo = buscar(client, projeto.id)
    if esperado == HTTPStatus.OK:
        assert salvo.descricao == 'Nova Descricao'
    else:
        assert salvo.descricao == 'Descricao Original'


def test_atualizar_projeto_inexistente(client, gestor, token_de):
    response = client.patch(
        '/projetos/000000000000000000000000',
        json={'nome': 'Qualquer'},
        headers=token_de(gestor),
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


@pytest.mark.parametrize(
    ('ator', 'participa', 'esperado'),
    [
        ('admin', False, HTTPStatus.NO_CONTENT),
        ('gestor', True, HTTPStatus.NO_CONTENT),
        ('gestor', False, HTTPStatus.FORBIDDEN),
        ('membro', True, HTTPStatus.FORBIDDEN),
    ],
)
def test_permissao_de_exclusao_de_projeto(
    client, criar_projeto, token_de, request, ator, participa, esperado
):
    usuario_ator = request.getfixturevalue(ator)
    projeto = criar_projeto(
        membros_equipe=[usuario_ator.id] if participa else []
    )

    response = client.delete(
        f'/projetos/{projeto.id}', headers=token_de(usuario_ator)
    )
    assert response.status_code == esperado

    salvo = buscar(client, projeto.id)
    if esperado == HTTPStatus.NO_CONTENT:
        assert salvo is None
    else:
        assert salvo is not None


def test_gestor_apaga_projeto(client, criar_projeto, gestor, token_de):
    projeto = criar_projeto(responsavel=gestor, nome='Projeto Para Apagar')

    response = client.delete(
        f'/projetos/{projeto.id}', headers=token_de(gestor)
    )
    assert response.status_code == HTTPStatus.NO_CONTENT

    get_res = client.get(f'/projetos/{projeto.id}', headers=token_de(gestor))
    assert get_res.status_code == HTTPStatus.NOT_FOUND


def test_apagar_projeto_inexistente(client, gestor, token_de):
    response = client.delete(
        '/projetos/000000000000000000000000', headers=token_de(gestor)
    )
    assert response.status_code == HTTPStatus.NOT_FOUND


def test_criar_projeto_registra_historico_inicial(client, gestor, token_de):
    agora = datetime.now(timezone.utc)
    payload = {
        'nome': 'Novo',
        'descricao': '',
        'responsavel_id': str(gestor.id),
        'status': 'Ativo',
        'percentual_progresso': PROGRESSO_INICIAL,
        'marcos': [{'titulo': 'Marco sem data'}],
        'data_inicio': agora.isoformat(),
        'data_entrega': (agora + timedelta(days=1)).isoformat(),
    }
    response = client.post(
        '/projetos/', json=payload, headers=token_de(gestor)
    )
    assert response.status_code == HTTPStatus.CREATED
    corpo = response.json()
    assert corpo['percentual_progresso'] == PROGRESSO_INICIAL
    assert corpo['marcos'][0]['data_prevista'] is None
    assert len(corpo['historico_status']) == 1
    assert corpo['historico_status'][0]['status_novo'] == 'Ativo'
    assert corpo['historico_status'][0]['nota'] == 'Projeto criado'


def test_apagar_projeto_remove_tarefas(
    client, criar_projeto, criar_tarefa, admin, token_de
):
    projeto = criar_projeto()
    tarefa = criar_tarefa(projeto_id=projeto.id)

    response = client.delete(
        f'/projetos/{projeto.id}', headers=token_de(admin)
    )
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert client.portal.call(TarefaModel.get, tarefa.id) is None


@pytest.mark.parametrize(
    ('ator', 'participa', 'esperado'),
    [
        ('admin', False, HTTPStatus.OK),
        ('membro', True, HTTPStatus.OK),
        ('membro', False, HTTPStatus.FORBIDDEN),
        ('gestor', False, HTTPStatus.FORBIDDEN),
    ],
)
def test_alternar_marco(
    client, criar_projeto, token_de, request, ator, participa, esperado
):
    usuario_ator = request.getfixturevalue(ator)
    projeto = criar_projeto(
        marcos=[{'titulo': 'M1', 'concluido': False}],
        membros_equipe=[usuario_ator.id] if participa else [],
    )

    response = client.post(
        f'/projetos/{projeto.id}/marcos/0/alternar',
        headers=token_de(usuario_ator),
    )
    assert response.status_code == esperado
    assert buscar(client, projeto.id).marcos[0].concluido == (
        esperado == HTTPStatus.OK
    )


def test_alternar_marco_inexistente(client, criar_projeto, admin, token_de):
    projeto = criar_projeto()
    response = client.post(
        f'/projetos/{projeto.id}/marcos/3/alternar', headers=token_de(admin)
    )
    assert response.status_code == HTTPStatus.NOT_FOUND
