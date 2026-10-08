# QuantNiti brand kit

Built from logo concept 04 (neural pipeline on dark). All text is converted to outlines (Sora Bold), so every SVG renders identically everywhere with no font install needed.

## Folders
- `svg/icon/` - the mark alone. `on-dark`, `on-light`, `mono-white`, `mono-dark`. Transparent background, hollow nodes, works on any backdrop of the matching tone.
- `svg/wordmark/` - "QuantNiti" text only, same four variants.
- `svg/logo-horizontal/` and `svg/logo-stacked/` - full lockups, four variants each, plus `-with-bg` versions that include the dark (#1e1636) or lavender (#f9f8fc) background.
- `svg/app/` - `favicon.svg`, `app-icon-512.svg` (rounded), `app-icon-maskable.svg` (PWA, full bleed), `avatar-512.svg` (social profile picture).
- `svg/social/` - `og-image-1200x630.svg` for link previews.
- `svg/extras/` - animated loader (dark and light), pipeline pattern, glow background.
- `png/` - ready raster exports: favicons, apple-touch-icon, PWA icons, OG image, logos.
- `tokens/` - `brand.css` (CSS variables) and `brand-colors.json`.
- `components/QuantNitiIcon.jsx` - React icon component with `theme="dark" | "light"`.

## Which file to use
| Surface | File |
|---|---|
| Navbar on lavender or white | `logo-horizontal-on-light.svg` |
| Navbar on dark or indigo | `logo-horizontal-on-dark.svg` |
| Footer, one-colour print, stamps | `logo-horizontal-mono-white.svg` / `mono-dark.svg` |
| Login or splash screen | `logo-stacked-*` |
| Browser tab | `favicon.svg` and `favicon.ico` |
| Loading state | `extras/loader-animated.svg` |

## HTML head
```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<meta property="og:image" content="https://YOUR-DOMAIN/og-image.png">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&display=swap" rel="stylesheet">
```

## Web manifest icons
```json
{ "icons": [
  { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
  { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png" },
  { "src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
] }
```

## Colours
Indigo #403d88 (primary), Amethyst #8b639b (accent), Pink #f8b2b2 (highlight), Lavender #f9f8fc, White #ffffff, Dark #1e1636.
Pink is too light for text on light backgrounds; use it as an accent there, and as the main accent on dark or indigo.

## Usage rules
- Clear space around any logo: at least the height of the "Q".
- Minimum size: icon 16px, horizontal logo 100px wide, stacked logo 80px wide.
- Do not recolour, stretch, rotate, or add effects. Do not put the on-dark logo on a light background or the reverse.
- Typeface for UI and headings: Sora (SIL Open Font License, free for commercial use).
