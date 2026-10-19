# Configurações de temperatura

Abra a aba **Configurações** no painel local (`http://IP-DO-BRIDGE:8088/`).

## Mosturação

A potência automática é o menor valor entre a saída do PID e o teto interpolado abaixo. As diferenças são relativas ao alvo da etapa:

| Diferença °C | Teto % |
| --- | --- |
| −3 ou menos | 100 |
| −2 | 75 |
| −1 | 60 |
| 0 | 50 |
| +0,5 | 30 |
| +1 ou mais | 0 |

Os pontos são editáveis. Temperaturas devem crescer, potências não podem crescer e o último ponto deve ter potência zero. O PID considera o teto na integração para evitar manter demanda acumulada acima do permitido. Esta curva limita a demanda de potência; não garante ausência de ultrapassagem térmica por inércia ou atraso do sensor.

## Fervura

Selecione **Fervura** para o recipiente correspondente. O padrão reconhece `mash` como mosturação e `boil` como fervura. Outros IDs usam mosturação até serem configurados.

A temperatura local de fervura substitui o alvo das etapas desse recipiente. Ajuste conforme a temperatura observada e a calibração do sensor; não há cálculo automático por altitude. Não selecione este perfil para um recipiente com etapas de pré-aquecimento em outras temperaturas.

Padrões iniciais: **100 °C** e **100%** de manutenção. Ajuste a potência à sua instalação. Antes do alvo, aquecimento em 100%; ao atingir o alvo, potência de manutenção e início da contagem. Durante o patamar, mantém a potência configurada. Excesso crítico corta a demanda automática também na fervura. As janelas de acionamento existentes permanecem inalteradas.

## Alertas

Acima de **alvo +3 °C**, o painel exibe **Acima do previsto** em vermelho e emite o alarme existente. A condição só encerra em **alvo +2,5 °C ou menos**, evitando alternância por pequenas oscilações. Confirmar o alarme silencia o aviso; o estado vermelho permanece até a recuperação. O alerta é avaliado também na rampa. Um novo episódio gera novo alarme.

**Congelar contagem do patamar** é opcional e vem desativado, preservando a contagem anterior. Ativado, exclui da contagem os intervalos detectados em excesso crítico e impede o avanço automático durante esses intervalos. Não reverte efeitos já ocorridos na mostura. Controle manual e fail-safe continuam com suas prioridades existentes; estes tetos governam apenas o automático.

## Salvar e restaurar

- **Salvar configurações** persiste ajustes locais em `data/private/control_settings.json` por substituição atômica. Não é necessário reiniciar.
- Alterações entram na **próxima execução iniciada por Iniciar**, não em uma simples retomada.
- Uma execução guarda seu snapshot de configuração no estado persistido, inclusive para recuperação após queda.
- **Restaurar padrões de fábrica** restaura os valores versionados em `data/control_defaults.json`, com a mesma regra de próxima execução.
- Faça backup de `data/private/` junto aos dados locais.

## Validação após aplicar

Reinicie o Bridge para carregar o novo código. Confira perfis, temperatura local e potência de fervura antes de iniciar. Em backend simulado, injete temperaturas em torno do alvo e confira os limites e o alerta. A validação em Raspberry Pi, com água e posteriormente mostura, ainda é necessária para ajustar a curva à inércia da planta.

Sem migração de banco. Testes: `python -m pytest -q`.
