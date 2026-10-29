# Eksempel: aftensmad, der ikke er nødvendig, når familien er væk

Mønsteret er fast hver uge. Kalenderen bruges kun til det, der afviger.

| Opgave | Gentagelse | Tildeling | Betingelse |
|---|---|---|---|
| Aftensmad | Ugentlig: man, tor, fre, lør, søn kl. 18:00 | Færrest point | Kalender-nøgleord |
| Aftensmad onsdag | Ugentlig: ons kl. 18:00 | Fast: Voksen 1 | Ingen |

## Opsætning af "Aftensmad"

1. **Tilføj opgave**: navn "Aftensmad", tidspunkt 18:00, personer Voksen 1 og Voksen 2, tildeling "Færrest point", gentagelse "Ugentlig".
2. Under **Avanceret**: betingelse "Kalender-nøgleord".
3. Næste trin: ugedagene.
4. Sidste trin: kalender `calendar.familie`, nøgleord fx `Væk` og `Weekend ude`, tjek kl. 14:00.

## Sådan virker det

Kl. 14:00 på dagen hentes kalenderens begivenheder. Er en begivenhed med et af nøgleordene **i gang kl. 18:00**, er aftensmad ikke nødvendig den dag: den logges med 0 point, forsvinder fra listerne, og rotationen rykker ikke.

- En weekend væk fra fredag kl. 16 til søndag kl. 15: fredag og lørdag er ikke nødvendige, søndag kl. 18 er nødvendig.
- En heldagsbegivenhed gælder hele dagen.
- Er kalenderen utilgængelig kl. 14:00, bliver aftensmad stående med "Betingelse ukendt".
