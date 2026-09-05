# SKILL: Enterprise Fintech Design System (InfinitePay Standard)
*Versão: 3.0.0-Enterprise*
*Contexto:* Este documento serve como a fonte definitiva de verdade para estilização de interfaces, UI/UX, e engenharia de front-end do sistema Cavere. O objetivo é eliminar totalmente qualquer vestígio de "vibe code" ou protótipo gerado por IA, entregando um produto com padrão de acabamento visual equivalente a um software SaaS de nível corporativo e fintech de alta performance.

---

## 1. Fundamentos da Identidade Visual & Tipografia
- **Família Tipográfica Principal:** Utilizar exclusivamente a fonte `Inter` ou `Plus Jakarta Sans` via Google Fonts (`<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">`).
- **Escala de Pesos:** 
  - `font-weight: 400` para textos secundários e descrições.
  - `font-weight: 500` para rótulos de formulários e itens de menu.
  - `font-weight: 600` para títulos de cards, botões de ação e dados de tabelas.
  - `font-weight: 700` para headers principais (`<h1>`, `<h2>`).
- **Paleta de Cores Estrita (Modo Clean Corporativo):**
  - **Fundo Global (Canvas):** `#f8fafc` (Cinza ultra-suave com toque azulado).
  - **Superfícies/Cards:** `#ffffff` (Branco absoluto).
  - **Bordas e Divisores:** `#e2e8f0` (Cinza claro refinado, sem linhas pretas duras).
  - **Texto Primário (Headings):** `#0f172a` (Slate 900 - quase preto, altamente legível).
  - **Texto Secundário (Body/Muted):** `#64748b` (Slate 500).
  - **Cor de Acento (Primary / CTA):** `#00C853` (Verde Esmeralda Tecnológico - identidade InfinitePay).
  - **Hover do Acento:** `#00b048`.
  - **Estados e Alertas (Badges):**
    - Sucesso / Disponível: Fundo `#dcfce7`, Texto `#166534`.
    - Alerta / Em Operação: Fundo `#fef9c3`, Texto `#854d0e`.
    - Perigo / Erro: Fundo `#fee2e2`, Texto `#991b1b`.

---

## 2. Arquitetura de Componentes e Layouts

### A. Navegação (Navbar / Header)
- Altura fixa ou fluida com padding generoso (`py-3 px-4`).
- Fundo totalmente branco com sombra sutil na base (`box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05)`).
- Logotipo limpo com ícone moderno alinhado ao texto em negrito.
- Links de navegação com transição suave de cor, espaçamento adequado e indicador visual sutil de página ativa.

### B. Cards e Containers (SaaS Surface)
- Todos os blocos de conteúdo devem usar containers limpos.
- `border-radius: 12px` (arredondamento moderno e fluido).
- `border: 1px solid #e2e8f0`.
- `box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px -2px rgba(0, 0, 0, 0.02)`.
- Cabeçalhos de cards devem ter fundo diferenciado muito sutil (`#f8fafc`) ou divisória limpa, evitando tarjas de cores berrantes.

### C. Tabelas de Dados (Data Tables Enterprise)
- Devem parecer painéis de controle de alto nível.
- Cabeçalhos de tabela (`<th>`): Fundo `#f8fafc`, texto em maiúsculas com espaçamento de letras sutil (`letter-spacing: 0.05em`), cor `#475569`, peso `600`, tamanho `12px`.
- Linhas (`<td>`): Alinhamento vertical central (`align-middle`), padding confortável (`py-3 px-4`), separadores finos entre linhas.
- Badges de status internos às tabelas devem ser estilizados estritamente como *pílulas* (`border-radius: 9999px`, padding horizontal de 10px, padding vertical de 3px, fonte `12px` em negrito).

### D. Formulários e Inputs
- Campos de texto, selects e textareas: `border-radius: 8px`, `border: 1px solid #cbd5e1`, altura confortável.
- Efeito de foco (`focus`): Remover o contorno padrão do navegador e aplicar uma borda sólida na cor de acento (`#00C853`) combinada com um anel de destaque sutil (`box-shadow: 0 0 0 3px rgba(0, 200, 83, 0.15)`).
- Botões de Ação (CTA): Cantos arredondados (`8px` ou `10px`), peso de fonte `600`, efeito de transição em `all 0.2s ease-in-out` e leve elevação no hover (`transform: translateY(-1px)`).

---

## 3. Diretrizes de Engenharia de Front-end (Bootstrap Avançado / Custom CSS)
- O agente não deve apenas usar classes utilitárias básicas do Bootstrap. Deve injetar blocos de estilos `<style>` customizados na base para refinar componentes que o Bootstrap padrão deixa rústicos.
- Garantir responsividade total via Flexbox e Grid (`row`, `col-md-*`).
- Eliminar qualquer margem ou espaçamento abrupto, mantendo respiro visual em todas as telas.