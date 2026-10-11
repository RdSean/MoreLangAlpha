# LangAlpha Web Design System — Quiet Workspace / NASA Mission

The app offers two light themes. Selectors and semantic tokens in
`web/src/styles/tokens.css` are the source of truth. Dark and automatic preferences
migrate to Quiet Workspace; OS appearance does not change the selected theme.

## Palette

| Role | Quiet Workspace | NASA Mission |
|---|---|---|
| Page | White | `#ECE5D6` warm paper |
| Canvas under cards | `#F5F4F1` | `#ECE5D6` |
| Card | White, neutral hairline | White, fine ink border |
| Main text | `#1F1F1E` | `#171717` |
| Accent | Configurable amber, default `#D07D33` | Fixed action red `#D63A2C` |
| Primary button | Ink / paper text | Action red / white text |
| Corners | `0.5rem` panels | `0.25rem` panels and controls |
| Depth | `--shadow-card` | Fine borders with restrained `--shadow-card` |

Use surface roles: `bg-page` for the application ground, `bg-canvas` beneath
card grids, `bg-card` for panels, `bg-tool-card` for transcript artifacts,
`bg-elevated` for menus/tooltips, `bg-input` for fields, `bg-popover` for Radix
floating menus. Floating surfaces retain their distinct roles. Every referenced
`--color-*` token must be declared; canvas painters resolve tokens through
`web/src/lib/themeTokens.ts`.

## Typography

Quiet retains Sora/Geist with Noto Sans SC. NASA uses Helvetica Neue / Helvetica /
Arial for Latin UI and reading text, with the same Noto Sans SC companion.
Textbook Chinese prose keeps LXGW WenKai / Noto Serif SC; NASA replaces only the
Latin serif faces. Labels, codes and data use `--font-label` / JetBrains Mono,
small uppercase Latin text and tabular numbers. Chinese text is not transformed.

## Accent discipline

Quiet amber is annotation only, not a button fill or glow. NASA red identifies
the decisive action, selected navigation or an urgent status. NASA Markdown uses
the muted mission palette: slate H1, dark olive H2, brick H3 and bold text, dark
ochre H4, and an ochre quote rule. Olive and ochre use the darker identity ink
variants for readable small headings. Paragraphs and secondary actions use neutral
ink. The experimental accent
picker belongs to Quiet; it is hidden under NASA and its stored preference survives
switching back.

NASA identity uses the muted four-color stripe: `#4C5A68`, `#7A7F4E`, `#D2A85E`,
`#A8432F`. User identity appears as a circular mission patch. Status colors remain
muted and accompanied by text or symbols; red is the sole vivid interface accent.
Code syntax and user-generated images retain their functional/content palettes.

## Panels and decoration

NASA uses fine rules, panel seams, task labels and small rivets. Identity stripes
stay on chrome; black/white warning stripes accompany processing, blocked and
error indicators. Very faint scratches may appear along shell edges, with
`pointer-events: none`. Never place texture over prose, images, formulas or inputs.
No neon, glow, holography, large decorative gradients or glass blur. Hard-edged
stripe patterns and tiny rivet shapes are not surface washes. Quiet appearance
remains independent of these NASA overrides.

NASA content grounds use local, static SVG paint grain and a faint registration
rail in desktop margins. At tablet/mobile widths only grain remains. Calendar
data and reward-pack art can use a low-contrast drafting grid; prose, card images,
and input surfaces stay clean. Reward pack edge colors identify the actual pack
type using existing muted identity inks. Reward and collection frames use the
NASA panel radius; all material styling remains under `data-theme="nasa"`.

## Interaction and motion

- Preserve navigation, workspace, Skills, MCP, SSE, checkpoint and education
  authorization behavior. Themes change presentation only.
- Mobile controls provide at least 44px targets; learning navigation stays
  scrollable, the composer respects safe areas, and narrow headers prioritize
  actions over optional task metadata.
- Focus rings are neutral and keyboard-visible. User avatars remain circular.
- Existing status glyph + text vocabulary remains authoritative in
  `pages/ChatAgent/components/taskStatusUi.tsx`.
- Motion signals state changes and respects `prefers-reduced-motion`. NASA activity
  labels use static ink instead of shimmer; recording retains its state indication
  without glowing decoration.
- Markdown, file previews and code/diff editors use light palettes in both themes.
  Explicit export/print rendering remains white-paper based.
