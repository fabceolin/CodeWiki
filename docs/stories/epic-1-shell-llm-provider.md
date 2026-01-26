# Epic 1: Shell-Based LLM Provider

## Epic Goal

Adicionar suporte para comunicação LLM via comando shell (Claude Code CLI), permitindo que usuários sem acesso a APIs HTTP possam utilizar o CodeWiki através de CLIs de LLM instaladas localmente.

## Epic Description

### Existing System Context

- **Current functionality:** Comunicação LLM exclusivamente via protocolo HTTP OpenAI-compatible
- **Technology stack:** pydantic-ai, OpenAI SDK, LiteLLM, keyring para secrets
- **Integration points:**
  - `codewiki/src/be/llm_services.py` - factory de modelos e chamadas diretas
  - `codewiki/src/be/agent_orchestrator.py` - uso de `pydantic_ai.Agent` com `OpenAIModel`
  - `codewiki/src/config.py` - configuração de base_url, api_key, models
  - `codewiki/cli/config_manager.py` - persistência de credenciais

### Architectural Decision

**Decisão:** Implementação direta no CodeWiki (Opção B)

**Alternativa considerada:** Usar `the_edge_agent` como provider layer intermediário.

**Motivos da decisão:**
1. Sem dependência externa adicional
2. Integração direta com pydantic-ai
3. Pipeline mais simples para o usuário final
4. Escopo controlado (foco no `claude` CLI)

**Referência de implementação:** O projeto `the_edge_agent` (`/home/fabricio/src/the_edge_agent/python/src/the_edge_agent/actions/llm_actions.py`) contém uma implementação madura de shell providers que serve como referência técnica. Funções chave:
- `_execute_shell_provider()` - execução síncrona
- `_stream_shell_provider()` - execução com streaming
- `_get_default_shell_providers()` - configurações padrão de CLIs
- `_format_messages_for_cli()` - formatação de mensagens

### Enhancement Details

**What's being added:**

- Novo provider de LLM baseado em execução de comandos shell (`claude` CLI)
- Abstração que permite trocar entre API HTTP e Shell CLI
- Configuração para especificar o comando/CLI a ser usado

**How it integrates:**

- Nova classe `ShellModel` compatível com interface pydantic-ai
- Extensão do `ConfigManager` para suportar `provider_type: shell | api`
- Factory pattern em `llm_services.py` para selecionar provider

**Success criteria:**

- [ ] Usuário pode configurar `codewiki config set --provider shell --shell-command "claude"`
- [ ] Geração de documentação funciona identicamente com ambos providers
- [ ] Zero breaking changes na API existente

## Stories

| # | Story | Description | Estimate |
|---|-------|-------------|----------|
| 1.1 | Shell LLM Adapter | Criar adaptador que executa comando shell, passa prompt via stdin/args, e captura resposta stdout | M |
| 1.2 | Provider Configuration | Estender configuração CLI para suportar escolha de provider (api/shell) e parâmetros do comando shell | S |
| 1.3 | pydantic-ai Integration | Criar `ShellModel` que implementa interface compatível com pydantic-ai para uso no `AgentOrchestrator` | L |

## Compatibility Requirements

- [x] Existing APIs remain unchanged (API HTTP continua funcionando)
- [x] Database schema changes are backward compatible (N/A)
- [x] UI changes follow existing patterns (CLI segue padrão Click existente)
- [x] Performance impact is minimal (shell calls são inerentemente mais lentos, mas aceitável)

## Risk Mitigation

- **Primary Risk:** CLIs de LLM têm interfaces heterogêneas (diferentes flags, formatos de I/O)
- **Mitigation:** Foco inicial no `claude` CLI com arquitetura extensível para outros
- **Rollback Plan:** Feature flag `--provider` permite voltar para API a qualquer momento; default permanece API

## Definition of Done

- [ ] All stories completed with acceptance criteria met
- [ ] Existing functionality verified through testing (pytest passa)
- [ ] Integration points working correctly
- [ ] Documentation updated (README, DEVELOPMENT.md)
- [ ] No regression in existing features (testes existentes passam)

## Technical Notes

### Claude CLI Interface

O comando `claude` aceita prompts via:
- Flag `-p` ou `--prompt`: `claude -p "your prompt here"`
- Stdin pipe: `echo "your prompt" | claude`

Flags relevantes:
- `--output-format json` - Saída estruturada (opcional)
- `--dangerously-skip-permissions` - Pula confirmações interativas
- `--model <model>` - Especifica modelo (opcional)

### Arquitetura Final

```
┌─────────────────────────────────────────────────────────────┐
│                      llm_services.py                        │
├─────────────────────────────────────────────────────────────┤
│  create_model(config) ─────┬────────────────────────────>   │
│                            │                                │
│              ┌─────────────┴─────────────┐                  │
│              │    provider_type check    │                  │
│              └─────────────┬─────────────┘                  │
│                            │                                │
│         ┌──────────────────┼──────────────────┐             │
│         ▼                  ▼                  ▼             │
│   ┌──────────┐      ┌───────────┐      ┌───────────┐        │
│   │ APIModel │      │ShellModel │      │ Future... │        │
│   │(existing)│      │  (new)    │      │           │        │
│   └──────────┘      └───────────┘      └───────────┘        │
│                            │                                │
│                            ▼                                │
│                   ┌─────────────────┐                       │
│                   │ ShellLLMAdapter │                       │
│                   │  (subprocess)   │                       │
│                   └─────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### Reference Implementation

Código de referência do the_edge_agent (linhas relevantes):

```python
# llm_actions.py:153-191 - Default shell providers config
def _get_default_shell_providers():
    return {
        "claude": {
            "command": "claude",
            "args": ["-p", "{prompt}", "--dangerously-skip-permissions"],
            "timeout": 108000,
        },
        # ... outros providers
    }

# llm_actions.py:220-378 - Core execution logic
def _execute_shell_provider(shell_provider, messages, timeout, **kwargs):
    # 1. Get config
    # 2. Build command with {prompt} substitution
    # 3. Execute via subprocess.Popen
    # 4. Handle timeout, errors, exit codes
    # 5. Return {"content": stdout, "usage": {}, "provider": "shell"}
```
