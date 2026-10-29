# Husopgaver

Lokal Home Assistant-integration til familiens husopgaver: tilbagevendende opgaver, rotation, point og godkendelse af børnenes opgaver. Alt kører i Home Assistant, uden cloud og uden ekstra container.

> **Status:** under udvikling (v0.1.0). Kan endnu ikke bruges i praksis. Se [SPEC.md](SPEC.md) for kravene og byggeplanen.

## Installation (HACS)

1. HACS → menu (⋮) → **Custom repositories**.
2. Tilføj `https://github.com/topn00b/ha-husopgaver` med typen **Integration**.
3. Installér **Husopgaver**, og genstart Home Assistant.
4. **Indstillinger → Enheder og tjenester → Tilføj integration → Husopgaver**.

Kræver Home Assistant 2026.10 eller nyere.
