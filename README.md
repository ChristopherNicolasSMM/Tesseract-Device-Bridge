# tesseract-device-bridge

Componente independente (não faz parte do repositório Tesseract, não segue
as skills 00–04 do Tesseract) que roda no Raspberry Pi (ou qualquer máquina
com GPIO/sensores) fazendo a ponte entre hardware físico e o broker MQTT.

Especificação completa de origem:
`docs/skills/05-proposta-addon-device-manager-e-mqtt.md` (lado Tesseract) +
spec deste componente (lado bridge).

## Decisões registradas desta fase

- **Repositório**: novo e separado do Tesseract. Compatibilidade com o
  `addon_device_manager` é só por convenção de nomes de chave no
  `devices.yml` — sem link automático ou submódulo.
- **`failsafe_timeout_seconds`**: promovido de "fora de escopo" para
  entregável da v1. Para cada atuador com `is_risk: true` e esse campo
  definido, o bridge aplica `failsafe_value` localmente se ficar sem
  conexão MQTT por mais tempo que o limite — complementa (não substitui)
  o LWT registrado pelo lado Tesseract.
- **Segurança do painel web**: decisão consciente de não ter autenticação
  na v1. O painel aciona atuadores reais diretamente, sem RBAC. Assume-se
  rede local confiável. **Se for exposto fora da rede local, é
  responsabilidade de quem fizer o deploy colocar atrás de VPN ou
  reverse-proxy com autenticação** — isso não é tratado pelo código deste
  repositório.

## Estrutura

```
tesseract-device-bridge/
├── gpio/
│   ├── base.py             # interface abstrata GPIOBackend (read/write/setup/teardown)
│   ├── simulated_backend.py # ✅ implementado e testado (Fase 1)
│   └── real_backend.py     # ⏳ pendente (Fase 5 — só ao testar em Pi real)
├── config.py               # ⏳ pendente (Fase 2)
├── mqtt_client.py          # ⏳ pendente (Fase 4)
├── bridge.py               # ⏳ pendente (Fase 4) — inclui lógica de failsafe local (Fase 5→4, antecipada)
├── panel/                  # ⏳ pendente (Fase 3)
├── tests/
│   └── test_simulated_backend.py  # ✅ 19 testes passando
├── devices.yml.example     # ✅ atualizado com failsafe_timeout_seconds
├── requirements.txt        # ✅
└── README.md
```

## Status do roadmap

| Fase | Item | Status |
|---|---|---|
| 1 | `gpio/base.py` + `gpio/simulated_backend.py` + testes | ✅ Concluído (19/19 testes) |
| 2 | `config.py` (carregar/validar `devices.yml`) | ⏳ Próximo |
| 3 | `panel/` (Flask) sobre `SimulatedGPIOBackend` | ⏳ Pendente |
| 4 | `mqtt_client.py` + `bridge.py` | ⏳ Pendente |
| 4b | Lógica de failsafe local (`failsafe_timeout_seconds`) | ⏳ Pendente — antecipada para v1 |
| 5 | `gpio/real_backend.py` | ⏳ Pendente — só com Pi real disponível |

## Rodando os testes

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```
