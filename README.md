# Husopgaver

Lokal Home Assistant-integration til familiens husopgaver: tilbagevendende opgaver, rotation, point og godkendelse af børnenes opgaver. Alt kører i Home Assistant, uden cloud og uden ekstra container.

- Opgaver med engangs-, interval-, ugentlig og årlig gentagelse, med eller uden tidspunkt.
- Tildeling: fast, på skift, færrest point eller én per person. Fravær (person væk hjemmefra) tages i betragtning.
- Point per uge, måned, i alt og siden udbetaling.
- Godkendelse af børnenes afkrydsninger, også med knapper i en notifikation.
- Betingelser: en opgave er ikke nødvendig, når kalenderen siger, I er væk, eller en entitet har en bestemt state.
- Todo-lister per person, en kalender og et eget dashboardkort.
- Sommer- og vintertid er håndteret og testet.

Kræver Home Assistant 2026.10 eller nyere.

## Installation (HACS)

1. HACS → menu (⋮) → **Custom repositories**.
2. Tilføj `https://github.com/topn00b/ha-husopgaver` med typen **Integration**.
3. Installér **Husopgaver**, og genstart Home Assistant.
4. **Indstillinger → Enheder og tjenester → Tilføj integration → Husopgaver**.

## Kom i gang

1. Åbn **Husopgaver** under Enheder og tjenester.
2. **⋮ → Tilføj person** (Add person) for hvert familiemedlem.
   - Knyt personen til en person i Home Assistant. Det bruges til fravær og til at vide, hvem der må godkende.
   - Sæt **Kan godkende** for de voksne og **Afkrydsninger skal godkendes** for børnene.
   - Vælg evt. en farve til dashboardkortet og et notify-mål til notifikationer.
3. Åbn **Husopgaver** i sidemenuen. Siden kommer automatisk for alle brugere, også i companion-appen. Opret opgaverne med **+ Ny opgave**.
4. Kalender- og entitetsbetingelser, vindue for afkrydsning og indbyggede notifikationer sættes på integrationssiden: **⋮ → Add chore / Tilføj opgave**, eller tandhjulet på en opgave.

**Konfigurer** på integrationen har indstillingerne:

| Indstilling | Standard |
|---|---|
| Dage frem på listerne | 2 |
| Pointvindue for "Færrest point" | 30 dage |
| Fravær efter | 24 timer væk hjemmefra |
| Fortryd-vindue | 10 minutter |
| Listen "Alle opgaver" | Fra |

## Sådan virker det

### Status
- **Kommende:** før forfaldsdagen. Vises på listerne inden for "dage frem".
- **Forfalden:** fra midnat på forfaldsdagen, eller fra tidspunktet, hvis opgaven har et.
- **Overskredet:** fra midnat dagen efter, eller 1 time efter tidspunktet.
- En overskredet opgave hober sig ikke op: den er én opgave, uanset hvor mange gange den er sprunget over.

### Tildeling
| Tildeling | Hvem |
|---|---|
| Fast | Altid den første person. |
| På skift | Personerne i rækkefølge. Fraværende springes over. |
| Færrest point | Den med færrest point i pointvinduet. Står det lige, den der længst har ikke lavet netop denne opgave. |
| Alle | Hver person har sin egen forekomst, fx børnenes morgenrutine. |
| Den, der har tid | Intet navn på. Står hos alle de valgte, og den, der krydser af, får pointene, fx opvaskemaskinen. Krydses den af på den fælles tablet uden filter, spørger kortet, hvem der gjorde det. |

Krydser en anden af end den tildelte, går pointene til den, der krydsede af.

### Opfølgende opgaver
Vælg **Hvor tit? → Efter en anden opgave** for en opgave, der kommer efter en anden, fx:

1. **Vask tøj** (hver onsdag).
2. **Hæng vasketøj op**: efter "Vask tøj", med det samme, "den, der har tid".
3. **Tag vasketøj ned**: efter "Hæng vasketøj op", dagen efter.

Den opfølgende opgave dukker op, når den forrige er krydset af, og venter igen, når den selv er lavet. Fortrydes afkrydsningen, forsvinder den opfølgende opgave igen.

### Godkendelse
Når et barn krydser af, afventer opgaven godkendelse og giver først point, når en voksen godkender. Det kan gøres:
- på listen `todo.husopgaver_godkendelse`,
- med knapperne i notifikationen (indbygget eller [egen automation](examples/automation_godkendelse.yaml)),
- med servicen `husopgaver.approve`.

Godkendelse kræver en Home Assistant-bruger, der er knyttet til en person med **Kan godkende**. Den fælles køkkenbruger kan ikke godkende.

### Fortryd
Fjernes fluebenet inden for fortryd-vinduet, rulles afkrydsningen tilbage: point, forfald og tildeling. Det gælder kun den seneste handling på en opgave.

### Betingelser
- **Kalender-nøgleord:** Ikke nødvendig, hvis en begivenhed med et af nøgleordene er i gang på opgavens tidspunkt (uden tidspunkt: den dag). Tjekkes på et fast tidspunkt på forfaldsdagen, fx kl. 14.
- **Entitet:** Kun nødvendig, når entiteten har en bestemt state, fx `input_boolean.gaester` = `on`.
- En opgave, der ikke er nødvendig, logges med 0 point og forsvinder fra listerne. Rotationen rykker ikke.
- Er kalenderen eller entiteten utilgængelig, bliver opgaven stående med "Betingelse ukendt".

Se [eksemplet med aftensmad](examples/betingelse_aftensmad.md).

## Historik og statistik

Husopgaver-siden har fanerne **Opgaver**, **Historik** og **Statistik**:

- **Historik** viser, hvem der har lavet, sprunget over eller fået afvist hvad, dag for dag.
- **Statistik** viser point og antal per person, point per uge eller måned og hvem der laver hvad.

Vælg periode (7 dage til alt) og evt. en person med filteret øverst. Loggen gemmes for altid, også for slettede opgaver og personer.

## Entiteter

| Entitet | Indhold |
|---|---|
| `todo.husopgaver_<person>` | Personens opgaver. Afkrydsning krediteres listens ejer. Et nyt punkt bliver en engangsopgave med 1 point. |
| `todo.husopgaver_alle` | Alle opgaver (valgfri). Afkrydsning krediteres den tildelte. |
| `todo.husopgaver_godkendelse` | Afventende godkendelser. Afkrydsning godkender. |
| `sensor.husopgaver_<person>_point` | Ugens point. Attributter: `month`, `all_time`, `since_settlement`, `pending`, `completed_count`, `overdue_count`. |
| `calendar.husopgaver` | Opgavernes kommende forekomster. |

Entitets-id'erne er faste uanset Home Assistants sprog.

## Services

| Service | Felter |
|---|---|
| `husopgaver.complete` | `chore`, `person` (valgfri) |
| `husopgaver.skip` | `chore`, `person` (ved "Alle") |
| `husopgaver.reassign` | `chore`, `person` |
| `husopgaver.snooze` | `chore`, `duration`, `person` (ved "Alle") |
| `husopgaver.approve` / `reject` / `undo` | `log_id` eller `chore` |
| `husopgaver.settle` | `person` |
| `husopgaver.create_chore` / `update_chore` / `delete_chore` | Opgavens felter |

`chore` kan være opgavens navn, id eller todo-punkt. `person` kan være navn, id eller person-entitet. Handlingerne returnerer `log_id`, og `create_chore` returnerer `chore_id`.

```yaml
action: husopgaver.complete
data:
    chore: Tøm opvaskemaskinen
    person: Barn 1
```

```yaml
action: husopgaver.create_chore
data:
    name: Skift sengetøj
    assignees:
        - Voksen 1
        - Voksen 2
    assignment: round_robin
    repeat: interval
    every: 2
    unit: week
    points: 3
```

## Events

`husopgaver_due`, `husopgaver_overdue`, `husopgaver_reminder`, `husopgaver_completed`, `husopgaver_skipped`, `husopgaver_not_needed`, `husopgaver_approval_requested`, `husopgaver_rejected`

Data: `chore_id`, `chore_name`, `person_id`, `person_name`, `person_entity`, `notify_target`, `points`, `due` (ISO) og `log_id`, når der er en log-post.

Påmindelser laves som almindelige automationer på eventsene, se [eksemplet](examples/automation_paamindelse.yaml). Alternativt kan "Indbyggede notifikationer" slås til per opgave.

## Dashboard

**Husopgaver i sidemenuen** kommer automatisk, når integrationen er sat op. Den viser dashboardkortet på hele siden for alle brugere, så der er intet dashboard at lave. Vil du også have kortet på et af dine egne dashboards, så brug kortet herunder.

- **Dashboardkortet** `custom:husopgaver-card` følger med integrationen og kræver ingen ekstra installation. Det viser opgaverne grupperet som Afventer godkendelse, Overskredet, I dag, Kommende og Senere, med personfilter, afkrydsning med ét tryk og pointtavle.
  - **"+ Ny opgave"** i kortet opretter en opgave med få tryk: hvad, hvem, hvor tit. Tryk på en opgaves navn for at rette eller slette den. Det er den nemmeste måde at oprette opgaver på, også for resten af familien.
  - Tilføj kortet: rediger et dashboard → **Tilføj kort** → søg efter **Husopgaver**, eller brug YAML nedenfor.

  ```yaml
  type: custom:husopgaver-card
  ```

  Se [eksemplet](examples/dashboard_husopgaver_card.yaml) og kortets indstillinger i den visuelle editor.
- **Kun indbyggede kort:** [examples/dashboard_koekken.yaml](examples/dashboard_koekken.yaml) har kalender, en liste per person, pointtavle og godkendelser.

## Eksempler

| Fil | Indhold |
|---|---|
| [dashboard_husopgaver_card.yaml](examples/dashboard_husopgaver_card.yaml) | Køkkentablet med dashboardkortet. |
| [dashboard_koekken.yaml](examples/dashboard_koekken.yaml) | Køkkentablet med indbyggede kort. |
| [automation_paamindelse.yaml](examples/automation_paamindelse.yaml) | Påmindelse til den tildelte ved forfald. |
| [automation_godkendelse.yaml](examples/automation_godkendelse.yaml) | Notifikation med Godkend og Afvis til de voksne. |
| [automation_nfc.yaml](examples/automation_nfc.yaml) | Kryds af med et NFC-tag. |
| [betingelse_aftensmad.md](examples/betingelse_aftensmad.md) | Aftensmad, der ikke er nødvendig, når familien er væk. |

## Data

Personer og opgaver ligger i integrationens konfiguration. Tilstand og log ligger i `.storage/husopgaver.<entry_id>`. Loggen slettes aldrig, heller ikke når en person eller opgave slettes.

## Licens

[MIT](LICENSE)
