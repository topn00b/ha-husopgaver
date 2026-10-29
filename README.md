# Husopgaver

Lokal Home Assistant-integration til familiens husopgaver: tilbagevendende opgaver, rotation, point og godkendelse af børnenes opgaver. Alt kører i Home Assistant, uden cloud og uden ekstra container.

> **Status:** under udvikling (v0.2.0). Kan installeres og prøves: personer, opgaver, rotation, point, godkendelse, todo-lister, kalender og services virker. Betingelser (kalender/entitet), eksempler og dashboardkortet mangler. Se [SPEC.md](SPEC.md) for kravene og byggeplanen.

## Installation (HACS)

1. HACS → menu (⋮) → **Custom repositories**.
2. Tilføj `https://github.com/topn00b/ha-husopgaver` med typen **Integration**.
3. Installér **Husopgaver**, og genstart Home Assistant.
4. **Indstillinger → Enheder og tjenester → Tilføj integration → Husopgaver**.

Kræver Home Assistant 2026.10 eller nyere.

## Kom i gang

1. Åbn **Husopgaver** under Enheder og tjenester.
2. **Tilføj person** for hvert familiemedlem. Knyt personen til en person i Home Assistant, så fravær og godkendelse virker. Sæt "Kan godkende" for de voksne og "Afkrydsninger skal godkendes" for børnene.
3. **Tilføj opgave**: navn, point, personer, tildeling og gentagelse. Næste trin viser felterne for den valgte gentagelse.
4. Brug todo-listerne `todo.husopgaver_<person>` i appen eller på et dashboard. Afkrydsning giver point, og fjernes fluebenet inden for 10 minutter, fortrydes det.

Indstillinger (dage frem på listerne, pointvindue, fravær, fortryd-vindue og listen "Alle opgaver") findes under **Konfigurer**.
