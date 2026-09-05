# SKILL: Enterprise Fintech Design System (InfinitePay Standard)
*Versão: 4.0.0-Enterprise*
*Contexto:* Este documento é a fonte definitiva de verdade para estilização de interfaces, UI/UX e engenharia de front-end do sistema **Cavere**. O objetivo é eliminar qualquer vestígio de "vibe code" ou protótipo gerado por IA, entregando acabamento visual equivalente a um SaaS corporativo fintech de alta performance. Esta skill deve ser lida integralmente pelo agente antes de gerar qualquer tela, componente ou trecho de estilo.

---

## 1. Fundamentos da Identidade Visual & Tipografia

- **Família Tipográfica Principal:** exclusivamente `Inter` ou `Plus Jakarta Sans` via Google Fonts:
  `<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">`
- **Fonte Monoespaçada (dados numéricos/financeiros):** `JetBrains Mono` ou `IBM Plex Mono` para valores monetários, IDs de transação e códigos — nunca usar a fonte padrão do sistema para números financeiros, pois alinhamento tabular é crítico em fintech.
- **Escala de Pesos:**
  - `400` — textos secundários, descrições, placeholders.
  - `500` — rótulos de formulários, itens de menu, texto de tabela padrão.
  - `600` — títulos de cards, botões de ação, dados de tabela em destaque.
  - `700` — headers principais (`<h1>`, `<h2>`).
  - `800` — usar com moderação, apenas em métricas de destaque (ex: valor total de dashboard).
- **Escala Tipográfica (rem, base 16px):**
  - Display: `2rem` / `line-height: 1.2`
  - H1: `1.5rem` / `1.3`
  - H2: `1.25rem` / `1.35`
  - H3: `1.125rem` / `1.4`
  - Body: `0.9375rem` / `1.5`
  - Small/Caption: `0.8125rem` / `1.4`

### Paleta de Cores Estrita (Modo Clean Corporativo)
- **Fundo Global (Canvas):** `#f8fafc`
- **Superfícies/Cards:** `#ffffff`
- **Superfície Elevada (modais, dropdowns):** `#ffffff` com sombra mais pronunciada (ver seção 2.B)
- **Bordas e Divisores:** `#e2e8f0` (padrão) / `#f1f5f9` (divisores internos sutis)
- **Texto Primário (Headings):** `#0f172a`
- **Texto Secundário (Body/Muted):** `#64748b`
- **Texto Desabilitado/Placeholder:** `#94a3b8`
- **Cor de Acento (Primary / CTA):** `#00C853`
- **Hover do Acento:** `#00b048`
- **Active/Pressed do Acento:** `#009e40`
- **Foco/Anel de destaque:** `rgba(0, 200, 83, 0.15)`

### Estados e Alertas (Badges)
| Estado | Fundo | Texto | Uso |
|---|---|---|---|
| Sucesso / Disponível | `#dcfce7` | `#166534` | Transação concluída, conta ativa |
| Alerta / Em Operação | `#fef9c3` | `#854d0e` | Processando, pendente |
| Perigo / Erro | `#fee2e2` | `#991b1b` | Falha, bloqueado, recusado |
| Neutro / Informativo | `#e2e8f0` | `#475569` | Rascunho, arquivado |
| Info / Destaque Secundário | `#dbeafe` | `#1e40af` | Novo recurso, em análise |

### Cores Semânticas para Dados Financeiros
- **Valores positivos/entrada:** `#166534` (texto) — nunca usar o verde de acento (`#00C853`) para não confundir com CTA.
- **Valores negativos/saída:** `#991b1b`
- **Gráficos financeiros:** paleta categórica com no máximo 6 cores (`#00C853`, `#3b82f6`, `#f59e0b`, `#8b5cf6`, `#ec4899`, `#64748b`), sempre dessaturadas o suficiente para não competir com o verde de acento.

---

## 2. Sistema de Espaçamento e Elevação

### A. Escala de Espaçamento (base 4px, escala 1.5x)
Usar exclusivamente múltiplos desta escala — nunca valores arbitrários (`padding: 13px` é proibido):
`4px · 8px · 12px · 16px · 20px · 24px · 32px · 40px · 48px · 64px`

### B. Escala de Elevação (Sombras)
- **Nível 0 (plano):** sem sombra, apenas borda `1px solid #e2e8f0`.
- **Nível 1 (card padrão):** `0 4px 6px -1px rgba(0,0,0,0.02), 0 2px 4px -2px rgba(0,0,0,0.02)`
- **Nível 2 (dropdown, popover):** `0 10px 15px -3px rgba(0,0,0,0.04), 0 4px 6px -4px rgba(0,0,0,0.04)`
- **Nível 3 (modal, dialog):** `0 20px 25px -5px rgba(0,0,0,0.06), 0 8px 10px -6px rgba(0,0,0,0.06)`
- **Regra:** nunca usar `box-shadow` com opacidade acima de `0.08` — sombras duras quebram a estética "clean corporativo".

### C. Grid e Layout
- Container máximo: `1440px`, com padding lateral responsivo (`px-4` mobile, `px-6` tablet, `px-8` desktop).
- Sidebar fixa de navegação: `260px` expandida / `72px` colapsada, com transição de `0.25s ease`.
- Gap padrão entre cards em grid: `24px` (desktop) / `16px` (mobile).

---

## 3. Arquitetura de Componentes

### A. Navegação (Navbar / Header)
- Altura fixa `64px`, padding `py-3 px-4`.
- Fundo branco, sombra Nível 1 apenas na base.
- Logotipo alinhado à esquerda; ações do usuário (avatar, notificações) à direita.
- Item ativo do menu: fundo `#f0fdf4` (verde muito suave), texto `#166534`, borda esquerda de `3px` na cor de acento.

### B. Cards e Containers
- `border-radius: 12px`
- `border: 1px solid #e2e8f0`
- Sombra Nível 1
- Cabeçalho do card: fundo `#f8fafc` ou divisória `1px solid #f1f5f9`, nunca cores berrantes.
- Padding interno: `20px` (compacto) ou `24px` (padrão).

### C. Tabelas de Dados (Data Tables Enterprise)
- `<th>`: fundo `#f8fafc`, texto uppercase, `letter-spacing: 0.05em`, cor `#475569`, peso `600`, `12px`.
- `<td>`: `align-middle`, padding `py-3 px-4`, separadores `1px solid #f1f5f9`.
- Linha em hover: fundo `#f8fafc` com transição `0.15s`.
- Linha selecionada: fundo `#f0fdf4`.
- Badges internos: pílula (`border-radius: 9999px`), padding `3px 10px`, `12px`, peso `600`.
- Valores numéricos/monetários: alinhados à direita, fonte monoespaçada.
- **Estado vazio (empty state):** ícone outline centralizado (`48px`, cor `#94a3b8`), texto secundário explicando a ausência de dados, e um CTA quando aplicável — nunca deixar a tabela simplesmente em branco.
- **Estado de carregamento:** usar skeleton loaders (blocos `#f1f5f9` com shimmer sutil), nunca spinners genéricos de Bootstrap centralizados na tela toda.

### D. Formulários e Inputs
- `border-radius: 8px`, `border: 1px solid #cbd5e1`, altura `40px` (padrão) / `36px` (compacto).
- Foco: borda `#00C853` + `box-shadow: 0 0 0 3px rgba(0,200,83,0.15)`, sem outline padrão do navegador.
- Estado de erro: borda `#ef4444` + mensagem de erro em `12px`, cor `#991b1b`, abaixo do campo.
- Estado desabilitado: fundo `#f8fafc`, texto `#94a3b8`, cursor `not-allowed`.
- Labels sempre acima do campo (nunca placeholder-only), peso `500`, `13px`, cor `#334155`.
- Botões de Ação (CTA): `border-radius: 8-10px`, peso `600`, `transition: all 0.2s ease-in-out`, `transform: translateY(-1px)` no hover, `translateY(0)` no active.
- Botão secundário: fundo transparente, borda `1px solid #cbd5e1`, texto `#334155`.
- Botão destrutivo: fundo `#fee2e2`, texto `#991b1b`, hover `#fecaca`.

### E. Modais e Overlays
- Overlay de fundo: `rgba(15, 23, 42, 0.4)` com `backdrop-filter: blur(2px)`.
- Modal: `border-radius: 16px`, sombra Nível 3, largura máxima `560px` (padrão) / `720px` (formulários complexos).
- Animação de entrada: `scale(0.96) → scale(1)` + fade, `0.2s ease-out`.

### F. Ícones
- Usar exclusivamente uma biblioteca de ícones outline consistente (Lucide ou Phosphor) — nunca misturar estilos (outline + filled) na mesma tela.
- Tamanho padrão: `16px` (inline com texto), `20px` (botões), `24px` (headers de seção).
- Cor padrão: herdar do texto adjacente; ícones decorativos em `#94a3b8`.

### G. Gráficos e Dashboards
- Grid de fundo sutil (`#f1f5f9`), sem bordas pesadas nos eixos.
- Tooltips de gráfico: fundo `#0f172a`, texto branco, `border-radius: 8px`, sombra Nível 2.
- Cards de métrica (KPI): número em destaque (peso `700-800`), variação percentual com ícone de seta e cor semântica (verde/vermelho conforme seção 1).

---

## 4. Acessibilidade e Responsividade
- Contraste mínimo AA (4.5:1) para todo texto sobre fundo — validar especialmente textos secundários (`#64748b`) sobre branco.
- Todo elemento interativo deve ter estado de `:focus-visible` visível (nunca `outline: none` sem substituto).
- Áreas de toque mínimas de `40x40px` em controles mobile.
- Breakpoints: `640px` (mobile), `768px` (tablet), `1024px` (desktop), `1440px` (wide).
- Testar sempre com zoom de texto a 200% sem quebra de layout.

---

## 5. Diretrizes de Engenharia de Front-end (IDE Antigravity)

- O agente não deve usar apenas classes utilitárias básicas do Bootstrap/Tailwind. Deve injetar um bloco de estilos customizado (`<style>` ou arquivo CSS dedicado) que sobrescreva os defaults rústicos do framework base.
- **Centralizar tokens:** todas as cores, espaçamentos e raios definidos aqui devem existir como variáveis CSS (`:root { --color-accent: #00C853; ... }`) — nunca hardcode hex diretamente nos componentes, para permitir tematização futura.
- Garantir responsividade total via Flexbox/Grid nativo (não depender só de `col-md-*` do Bootstrap para layouts complexos de dashboard).
- Eliminar qualquer margem ou espaçamento fora da escala definida na Seção 2.A.
- Toda tela nova deve ser validada mentalmente contra esta skill antes de ser entregue: tipografia, cores, espaçamento, elevação, estados (vazio/erro/carregando) e acessibilidade.
- Ao gerar componentes reutilizáveis, documentar variantes (default, hover, active, disabled, error) explicitamente no código, não deixar implícito.
- Nomear classes/variáveis em inglês e de forma semântica (`--surface-card`, `--text-muted`), evitando nomes genéricos como `.box1` ou `.blue-thing`.
