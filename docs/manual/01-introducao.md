# 01 — Introdução

## Para que serve este sistema

Este sistema faz uma coisa simples: **controla automaticamente o aquecimento
e as bombas da sua brassagem**, seguindo a receita que você configurou.

Você define a receita uma vez (temperaturas, tempos de patamar, adições de
lúpulo) e o sistema executa sozinho — mantendo a temperatura certa em cada
etapa, contando o tempo, avisando na hora de adicionar lúpulo, e alertando
quando cada fase termina. Você fica livre pra fazer outras coisas durante a
brassagem em vez de ficar olhando o termômetro.

O painel roda no seu celular, computador ou tablet, pela rede Wi-Fi de casa
— você não precisa instalar nada no celular, é só abrir o navegador.

## O que o sistema controla

- **Temperatura de cada vasilha** (mostura, fervura, ou qualquer outra que
  você tiver) — sobe até o alvo e mantém ali pelo tempo configurado.
- **Bombas de recirculação** — ligam e desligam automaticamente conforme a
  etapa da receita.
- **Alertas de lupulagem** — toca um som e exibe um aviso na tela nos
  momentos certos (ex.: "faltam 60 minutos para o fim da fervura — hora do
  lúpulo de amargor").
- **Avisos de início e fim de fase** — um alarme sonoro quando a mostura
  termina, quando a fervura começa, etc.

## O que o sistema NÃO faz (por enquanto)

- Não controla válvulas automáticas de transferência de líquido.
- Não mede densidade do mosto.
- Não faz o controle de fermentação (só brassagem por enquanto).
- Não tem receitas pré-configuradas — você precisa montar a sua (ver
  [Primeiros Passos](02-primeiros-passos.md)).

## Onde o sistema roda

Em um Raspberry Pi conectado à sua placa de controle (ex.: MAZZA Handmade
CraftBeerPi), que por sua vez está conectada aos aquecedores, bombas e
sensores de temperatura. O Raspberry Pi fica ligado durante toda a brassagem.
