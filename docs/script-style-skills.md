# Script Style Integration (External Skills)

Date: 2026-05-02

## Skills reviewed

1. `copywriting`  
Source: `coreyhaines31/marketingskills`  
Usefulness for FlowKit: **High** (for hook, retention, clarity in narrator/script flow).

2. `manga-drama`  
Source: `freestylefly/canghe-skills`  
Usefulness for FlowKit: **Very High** (directly relevant to scene pacing for anime/comic storytelling).

3. `dramatic`  
Source: `bergside/awesome-design-skills`  
Usefulness for FlowKit: **Medium-High** (design-oriented, but principles map well to cinematic tension and visual staging).

## Applied in FlowKit

- Added script writing style modes in AI script generation:
  - `standard`
  - `copywriting`
  - `manga_drama`
  - `dramatic`

- Injected style profile instructions into:
  - one-shot script analysis prompt
  - long-story blueprint prompt
  - batched scene generation prompt
  - scene rebalance/repair prompt
  - YouTube transcript analysis prompt

## UX changes

- Added **“Phong cách kịch bản”** selector in AI setup modal.
- The selected style now drives scene prompt/video prompt/narrator generation behavior.

