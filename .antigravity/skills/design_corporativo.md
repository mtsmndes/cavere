# SKILL: Cavere Design System — Ambipar Corporate Edition
*Versão: 1.1.0 (correção de paleta)*
*Contexto:* Esta skill substitui a identidade "InfinitePay Standard" por uma identidade
inspirada na marca **Ambipar** real (verde-limão/chartreuse vibrante + base clara neutra),
elevada a um padrão de produto SaaS muito acima do site institucional — que é um site de
marketing com foto de fundo, menu poluído e uso do verde limitado a barra superior e
destaques de texto. Aqui pegamos a cor de identidade e aplicamos com disciplina de
dashboard operacional, não replicamos a página de marketing.

**Nota sobre a cor:** o hex abaixo (`#CEDC00`) é uma extração aproximada por inspeção visual
do print enviado. Se você tiver o manual de marca ou o SVG do logo, me envie para eu calibrar
o hex exato — cores extraídas de screenshot podem variar um pouco por compressão/exibição.

---

## 1. Fundamentos da Identidade Visual & Tipografia

- **Família Tipográfica Principal:** `Inter` ou `Plus Jakarta Sans` via Google Fonts.
- **Fonte Monoespaçada (IDs, protocolos, códigos de equipamento):** `JetBrains Mono` ou
  `IBM Plex Mono` — alinhamento tabular limpo em `#SOL-1`, `RAD-003`, etc.
- **Escala de Pesos:** `400` (secundário) · `500` (labels/menu) · `600` (títulos de card,
  botões, dados de tabela) · `700` (headers) · `800` (métricas hero, uso pontual).

### Paleta de Cores — Identidade Ambipar (corrigida)

**Cor de Acento (Verde-Limão — a assinatura visual da marca):**
- `--accent-500: #CEDC00` — cor de identidade principal, usar em destaques, CTAs e realces
- `--accent-600: #B8C400` — hover do acento (mesma tonalidade, levemente mais escura)
- `--accent-700: #9DA800` — active/pressed
- `--accent-on: #14171a` — texto/ícone SOBRE o acento (o limão é muito claro para texto branco em cima — usar sempre texto quase-preto sobre ele, como no site original)
- `--accent-glow: rgba(206, 220, 0, 0.25)` — anel de foco, sombra sutil

**Base Neutra (estrutura — assume o papel que antes era do navy):**
- `--ink-900: #14171a` — texto primário/headings, quase preto (não azul-marinho)
- `--ink-700: #2c3136` — sidebar escura / superfícies de estrutura, cinza-grafite neutro
- `--ink-500: #5b6168` — texto secundário/muted
- `--ink-300: #9aa0a6` — texto desabilitado, ícones decorativos

**Superfícies Claras:**
- `--canvas: #f5f6f4` — fundo global (leve tom quente/neutro, não azulado)
- `--surface: #ffffff` — cards
- `--border: #e4e6e1` — bordas padrão
- `--border-subtle: #edefec` — divisores internos

**Estados e Alertas (Badges):**
| Estado | Fundo | Texto | Uso |
|---|---|---|---|
| Sucesso / Disponível | `#e3f5d8` | `#3f6e12` | Equipamento disponível, termo concluído |
| Atenção / Em Operação | `#f5f7c9` | `#7a7f00` | Pendente — tom próximo ao acento mas neutralizado para não virar CTA |
| Crítico / Emergencial | `#fde3e3` | `#b91c1c` | Bloqueado, atraso crítico |
| Neutro | `#edefec` | `#5b6168` | Arquivado, rascunho |
| Info | `#e6eef7` | `#2c5a8c` | Novo, em análise |

**Regra de disciplina de cor:** o verde-limão é usado como o site original usa —
**pontualmente, para o que precisa ser visto primeiro** (CTA principal, indicador de
destaque, marca/logo). Ele NUNCA vira cor de fundo de área grande (nada de sidebar
inteira em limão — no site original ele é usado em faixas finas e destaques de texto,
não em blocos enormes). Grandes áreas usam a base neutra grafite/branco; o limão aparece
como "pontuação", não como pano de fundo.

---

## 2. Espaçamento, Elevação e Grid
*(disciplina técnica mantida da versão anterior)*

- **Escala de espaçamento (base 4px):** `4·8·12·16·20·24·32·40·48·64px`.
- **Elevação:**
  - Nível 0: sem sombra, borda `1px solid var(--border)`.
  - Nível 1 (card): `0 4px 6px -1px rgba(20,23,26,0.04), 0 2px 4px -2px rgba(20,23,26,0.04)`
  - Nível 2 (dropdown): `0 10px 15px -3px rgba(20,23,26,0.06)`
  - Nível 3 (modal): `0 20px 25px -5px rgba(20,23,26,0.10)`
- **Grid:** container máximo `1440px`; sidebar `264px` expandida / `76px` colapsada.

---

## 3. Arquitetura de Componentes

### A. Sidebar de Navegação
- Fundo `var(--ink-700)` (grafite escuro neutro — NÃO usar o limão como fundo de área grande).
- Logotipo no topo em branco; ícone/badge de marca em `var(--accent-500)` com texto
  `var(--accent-on)` — essa é a única mancha grande de limão permitida, e mesmo assim
  contida a um badge pequeno.
- Item inativo: texto `var(--ink-300)`.
- Item ativo: fundo `rgba(206,220,0,0.12)`, texto branco, ícone `var(--accent-500)`,
  borda esquerda `3px solid var(--accent-500)`.

### B. Header de Página
- Fundo `#ffffff`, borda inferior `1px solid var(--border)`.
- Título peso `800`, `var(--ink-900)`. Descrição em `var(--ink-500)`.
- Pode ganhar um pequeno realce de texto no estilo "highlight" do site original: uma
  palavra-chave do título com fundo `var(--accent-500)` e texto `var(--accent-on)`,
  `padding: 2px 6px`, `border-radius: 4px` — é a assinatura mais reconhecível da marca
  (o "highlight" amarelo-esverdeado atrás de palavras no hero) e funciona muito bem
  também em título de dashboard, com moderação (uma palavra, não a frase toda).

### C. Cards e KPIs
- `border-radius: 14px`, borda `1px solid var(--border)`, sombra Nível 1.
- Cards de métrica: ícone em badge circular `40px`, fundo `rgba(206,220,0,0.15)`,
  ícone `var(--ink-900)` (não branco — o limão claro precisa de ícone escuro em cima).
  Número em `2.25rem`/peso `800`/`var(--ink-900)`.

### D. Botões
- **Primário:** fundo sólido `var(--accent-500)`, texto `var(--accent-on)` (quase preto —
  nunca branco sobre o limão, contraste insuficiente), peso `600`.
  Sombra `0 4px 12px var(--accent-glow)`. Hover: `var(--accent-600)` + leve `translateY(-1px)`.
- **Secundário (estrutural):** fundo `var(--ink-700)`, texto branco — ações estruturais
  importantes que não são "a ação do momento".
- **Terciário/outline:** borda `1.5px solid var(--border)`, fundo branco, texto `var(--ink-900)`.
- **Destrutivo:** fundo `#fde3e3`, texto `#b91c1c`.
- Padding mínimo `10px 20px`, `border-radius: 8px`, ícone+texto com gap `8px`.
- Nunca mais de UM botão primário (limão) visível por seção/card.

### E. Tabelas de Dados
- `<th>`: fundo `var(--ink-700)`, texto branco/uppercase, `letter-spacing: 0.05em`,
  `12px`, peso `600`.
- `<td>`: fundo branco, `align-middle`, padding `py-3 px-4`, separador
  `1px solid var(--border-subtle)`.
- Hover de linha: fundo `var(--canvas)`. Linha selecionada: `rgba(206,220,0,0.08)`.
- **Altura de linha fixa obrigatória** (ver Seção 4).
- Barra de progresso: trilho `var(--border)`, preenchimento `var(--accent-500)` sólido,
  altura mínima `8px`, `border-radius: 4px`.
- Linha com prioridade crítica: borda esquerda `3px solid #b91c1c` na linha inteira.

### F. Modais e Overlays
- Overlay: `rgba(20,23,26,0.5)` com leve `backdrop-filter: blur(2px)`.
- Modal: `border-radius: 16px`, sombra Nível 3.

### G. Ícones
- Biblioteca outline única (Lucide). `16px` inline, `20px` em botões, `24px` em headers.
  Cor herda do texto adjacente; ícones decorativos em `var(--ink-300)`.

---

## 4. Arquitetura de Informação e Estrutura de Telas (reestruturação, não maquiagem)

Esta seção existe porque um redesign visual sozinho NÃO resolve uma tela poluída — se a
tela empilha 3-4 painéis completos (cada um com seu próprio header, filtros e tabela) na
mesma rota, nenhuma paleta de cor vai consertar isso. O problema é de arquitetura de
informação, não de estilo. Antes de estilizar qualquer tela, decida a estrutura seguindo
estas regras.

### A. Uma responsabilidade principal por tela
- Cada rota/página deve ter **um** objetivo primário claro. Se você não consegue resumir
  o propósito da tela em uma frase curta ("ver e agir sobre solicitações pendentes"),
  a tela está fazendo coisa demais e precisa ser dividida em rotas separadas.
- Regra prática: no máximo **1 bloco de KPIs/resumo** + **1 painel de conteúdo principal**
  por tela. Se existe um segundo painel completo (com seu próprio header + filtros +
  tabela), ele vira uma aba, uma rota separada ou um card secundário no dashboard que
  leva para outra página — nunca fica empilhado inteiro na mesma rolagem.

### B. Painel Principal (Home) vira um resumo, não um agregador de tudo
- O "Painel Principal" deve mostrar: KPIs de topo + a fila de itens que precisam de ação
  AGORA (ex: solicitações em aberto). Qualquer outra lista completa (histórico, relatórios,
  outro tipo de fila) sai do Painel Principal e vira sua própria página, acessível pela
  sidebar — mesmo que hoje estejam todas amontoadas na home.
- Pergunta de corte: "isso é algo que o usuário precisa ver TODA VEZ que abre o sistema,
  ou é algo que ele busca quando precisa?" Só o primeiro grupo fica na home.

### C. Filtros: um controle por contexto, não vários grupos de botões
- Uma tabela tem **um** conjunto de filtros/abas por vez (ex: "Todos / Em Aberto /
  Finalizados"), nunca dois grupos de botões concorrendo por atenção na mesma área
  (ex: filtro de status + botão de ação em massa + outro filtro, tudo na mesma linha).
- Ações em massa (como "Fechar Finalizados") vão para um menu secundário (kebab menu ou
  botão "Ações" com dropdown), não como um botão do mesmo peso visual dos filtros de status.

### D. Progressive disclosure em vez de mostrar tudo de uma vez
- Detalhes de um item (ex: todos os itens cautelados de uma solicitação) não aparecem
  expandidos por padrão na tabela — aparecem ao clicar/expandir (drawer lateral, modal ou
  linha expansível). A tabela em modo padrão mostra só o resumo necessário para escanear
  rapidamente a lista inteira.
- Isso vale para a tela inteira também: se uma página tem "mais para mostrar", prefira um
  link "Ver tudo" que leva para uma página dedicada, em vez de renderizar tudo inline.

### E. Hierarquia de navegação clara: sidebar define páginas, não a página define seções
- A sidebar (Painel Principal, Histórico de Cautelas, Cadastros, etc.) deve refletir a
  divisão real do sistema em páginas independentes. Se uma "seção" dentro de uma página é
  grande e completa o suficiente para ter seu próprio filtro e tabela, ela provavelmente
  deveria ser um item de sidebar próprio, não uma seção dentro de outra página.
- Ao planejar a reestruturação, primeiro liste todas as "seções completas" que existem
  hoje espalhadas pelas páginas atuais, depois decida: isso é conteúdo de resumo (fica no
  dashboard, compacto) ou é conteúdo de gestão completo (vira página própria na sidebar)?

---

## 5. Checklist Anti-"Vibe Code" (mantido integralmente)

1. **Altura de linha fixa:** nenhuma célula de tabela empilha listas verticalmente;
   usar resumo compacto (`0/4`) + expansão em popover/drawer.
2. **Um sinal por informação:** não repetir progresso já mostrado em barra através de
   badges individuais por item.
3. **Um botão de ação primária por linha/estado:** mesma forma de componente, mudando
   texto/cor por estado — nunca misturar pílula + outline + sólido na mesma coluna.
4. **Revisão de idioma:** acentuação correta ("Gestão", "Visão", "Usuários", "Ação"),
   Title Case consistente.
5. **Densidade de cor:** máximo 2-3 elementos coloridos por linha de tabela.

---

## 6. O que Melhoramos em Relação ao Site Institucional da Ambipar

- **Sem foto de fundo genérica** (céu/floresta) atrás de conteúdo funcional — isso é ok
  para marketing, péssimo para um dashboard que precisa de legibilidade constante.
  Usamos o realce "highlight" de texto (que É um elemento de marca forte) sem depender
  da fotografia.
- **Sem menu de 8+ níveis** — navegação enxuta (Painel, Histórico, Cadastros).
- **Limão como pontuação, não como bloco decorativo** — no site ele aparece na barra
  superior inteira; num produto operacional isso cansaria a vista em uso prolongado,
  então reservamos para CTA, ícone de marca e o highlight de texto.
- **Ícones outline modernos (Lucide/Phosphor)**, não os ícones datados do site institucional.
- **Contraste de texto corrigido:** o site usa texto preto sobre limão só no highlight
  pontual — replicamos essa regra de contraste (nunca texto branco sobre o acento).

---

## 7. Diretrizes de Engenharia de Front-end (IDE Antigravity)

- Antes de escrever qualquer CSS, resolva a reestruturação da Seção 4: mapeie quais
  rotas/páginas vão existir e o que sai do Painel Principal. Estrutura primeiro, estilo depois.
- Centralizar todos os tokens de cor/espaçamento acima como variáveis CSS em `:root`.
- Ao migrar de qualquer versão anterior desta skill (verde InfinitePay ou navy/laranja),
  trocar sistematicamente para os tokens `--accent-500` (`#CEDC00`) e `--ink-700`
  (grafite) — migração completa tela por tela, nunca dois sistemas de cor coexistindo.
- **Atenção especial ao contraste:** qualquer texto ou ícone que caia sobre `--accent-500`
  deve usar `--accent-on` (quase preto), nunca branco.
- Validar cada tela nova contra as Seções 4 e 5 (estrutura + checklist visual) antes de entregar.
