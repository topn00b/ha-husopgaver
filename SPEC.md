# Husopgaver: kravspecifikation

Husopgaver er en lokal custom integration til Home Assistant, som en familie bruger til at koordinere husholdningsopgaver. Den bruges på en køkkentablet og i HA's companion-app. Den kører 100 % lokalt og kræver ingen ekstra container, ingen cloud og ingen eksponering udefra.

- **Domæne:** `husopgaver`
- **Sprog:** Dansk (primært) og engelsk
- **Installation:** HACS som custom repository
- **Mindste HA-version:** 2026.10 (den version, der testes mod)

Dokumentet bruger kun pladsholdere: Voksen 1, Voksen 2, Barn 1 og Barn 2.

---

## 1. Principper

1. **Brugervenlighed først.** Afkrydsning sker med ét tryk. Oprettelse og redigering sker på én formular uden YAML.
2. **Idempotens.** Der skrives kun til storage, og state opdateres kun, når værdierne faktisk ændrer sig.
3. **Ingen polling.** Integrationen bruger `async_track_point_in_time` til næste relevante tidspunkt: forfald, overskridelse, påmindelse, tjek af betingelse og midnat.
4. **Rigtige data eller ingen data.** Der bruges ingen fallback-værdier. Ukendt er `unknown` eller `unavailable`, og det vises som ukendt.
5. **Tid.** Alt gemmes i UTC og beregnes i HA's tidszone med `homeassistant.util.dt`. Skift mellem sommer- og vintertid er dækket af tests.
6. **Storage.** Der bruges `helpers.storage.Store` med versionsnummer og migration.
7. **Kode.** Den er asynkron hele vejen, har type hints og bruger HA's oversættelser (`da.json` og `en.json`).
8. **Notifikationslogik ligger hos brugeren.** Integrationen sender events, og påmindelser laves som almindelige automationer. Der findes også en simpel, valgfri notify per opgave.

## 2. Datamodel

### Person (config subentry)
| Felt | Type | Note |
|---|---|---|
| `id` | str | Intern, stabil (uuid) |
| `name` | str | Visningsnavn |
| `person_entity` | `person.*` | Valgfri |
| `notify_target` | `notify.*` | Valgfri, børn behøver ingen |
| `color` | str | Valgfri farve til dashboardkortet |
| `can_approve` | bool | Kan godkende andres afkrydsninger (voksne) |
| `requires_approval` | bool | Afkrydsninger skal godkendes (børn) |
| `active` | bool | Inaktiv: tildeles intet, men historikken bevares |

Hver person får en HA-bruger knyttet via `person_entity` → `user_id`. Det bruges til at kontrollere, hvem der må godkende.

### Opgave (config subentry)
| Felt | Type | Standard |
|---|---|---|
| `id` | str (uuid) | |
| `name` | str | |
| `description` | str | Valgfri |
| `points` | int ≥ 0 | 1 |
| `assignees` | list[person_id] | Flueben ved oprettelse. Kun disse kan få opgaven. |
| `assignment` | `fixed` / `round_robin` / `least_points` / `each` | `least_points` |
| `schedule` | se nedenfor | |
| `due_time` | time | Valgfri |
| `notify_before` | duration | Valgfri |
| `complete_window` | duration | Valgfri. Opgaven kan først krydses af inden for dette vindue før forfald. |
| `requires_approval` | `auto` / `always` / `never` | `auto` (følger personen) |
| `condition` | se §5 | Valgfri |
| `builtin_notify` | bool | false |

Strategierne:
- `fixed`: altid den første i `assignees`.
- `round_robin`: på skift i rækkefølgen i `assignees`.
- `least_points`: den med færrest point i det rullende vindue. Se §4.
- `each`: hver person i `assignees` har sin egen forekomst. Bruges til børnerutiner.

### Schedule
| Type | Parametre |
|---|---|
| `none` | `due` (dato/tid), engangsopgave |
| `interval` | `every` (int), `unit` (`day`/`week`/`month`), `from` (`due`/`completion`) |
| `weekly` | `weekdays` (0–6, mandag = 0) |
| `yearly` | `dates` (liste af `MM-DD`) |

### Runtime-tilstand per opgave (og per person ved `each`)
- `next_due` (UTC)
- `assignee`
- `status`
- `snoozed_until`
- `pending_approval` (log-id eller `null`)
- `rr_index` (round robin)
- `condition_state` (`active` / `not_needed` / `unknown`)

### Log (kun tilføjelser, bevares altid)
| Felt | Note |
|---|---|
| `id` | uuid |
| `chore_id`, `person_id` | Bevares, også hvis opgaven eller personen slettes |
| `timestamp` | UTC |
| `points` | Pointværdi på udførelsestidspunktet |
| `action` | `completed` / `skipped` / `not_needed` / `pending` / `approved` / `rejected` / `undone` / `settled` |
| `ref` | Henvisning til den log-post, som `approved`, `rejected` eller `undone` gælder |
| `by_user` | HA-bruger, der udførte handlingen (til godkendelse og revision) |

En `pending`-post giver ingen point. Først en `approved`-post med `ref` til den udløser pointene.

### Storage
- **Store-nøgle:** `husopgaver.<entry_id>`, version 1, med `async_migrate_func`.
- **Opdeling:** Konfigurationen (personer og opgaver) ligger i config subentries. Runtime-tilstand og log ligger i Store.
- **Gemning:** `async_delay_save` bruges med en kort forsinkelse, og der gemmes kun, når noget er ændret.

## 3. Status og tidsregler
- `upcoming`: før forfaldsdagen.
- `due`: fra kl. 00:00 på forfaldsdagen. Er `due_time` sat, fra `due_time`.
- `overdue`: fra kl. 00:00 dagen efter forfaldsdagen. Er `due_time` sat, fra `due_time` + 1 time.
- `pending_approval`: krydset af, men afventer godkendelse fra en voksen.
- **Ingen ophobning:** En overskredet, tilbagevendende opgave er én forekomst, uanset hvor mange intervaller der er gået.

### Næste forfald
- **Første forfald** for en ny opgave: den første dag fra i dag, der passer til gentagelsen. Er `due_time` allerede passeret i dag, bliver det næste passende dag.
- `interval` / `from: due` regnes fra seriens startdato (`anchor`), så en månedlig opgave den 31. vender tilbage til den 31.
- `interval` / `from: due`: `next = previous_due + every`. Datoer, der er sprunget over, hoppes frem, indtil `next > now`.
- `interval` / `from: completion`: `next = completed_at (lokal dato) + every`. `due_time` beholdes.
- `month`: Dagen sættes til sidste dag i måneden, når den ikke findes. Udgangspunktet er altid *den oprindelige dag*: 31/1 → 28/2 → 31/3.
- `weekly`: næste ugedag på listen efter forfaldsdagen.
- `yearly`: næste dato på listen efter forfaldsdagen. Udføres opgaven før tid, fx 25/9, tæller det for den 1/10, og næste forfald bliver den 1/10 året efter.
- Alle beregninger foregår på **lokale datoer** og konverteres til UTC til sidst. Et tidspunkt som 02:30 på dagen for skift til sommertid, der ikke findes, rykkes frem. Ved skift til vintertid bruges den første forekomst af tidspunktet.

## 4. Tildeling
Tildelingen beregnes, når en opgave oprettes, og efter hver `completed`, `skipped` eller `not_needed`. Kandidaterne er de personer i `assignees`, der er aktive og ikke fraværende.

- **Fravær:** Hvis `person_entity` har været væk hjemmefra (enhver state end `home`, også en zone som fx arbejde) længere end en konfigurerbar tærskel (standard 24 timer), er personen fraværende. Hvis HA ikke kender personens state, regnes personen som tilgængelig, og det logges.
- **Alle fraværende:** Ved `round_robin` og `least_points` ses der bort fra fravær, så opgaven stadig får en ejer. Er ingen af personerne aktive, har opgaven ingen ejer.
- **`least_points`:** Opgaven går til den med færrest godkendte point i det rullende vindue (standard 30 dage, kan konfigureres). Står det lige, går den til den, der har udført *netop denne opgave* længst tid siden, eller aldrig. Står det stadig lige, afgør rækkefølgen i `assignees`.
- **`round_robin`:** Turen går til næste kandidat efter `rr_index`. Fraværende springes over, og `rr_index` rykker videre.
- **`fixed`:** første kandidat. Er den person fraværende, beholdes tildelingen (fast er fast).
- **Afkrydsning af en anden:** Krydser en person af, som ikke var tildelt, går pointene til den, der krydsede af. Den, der løfter mere, belønnes mere.

## 5. Betingelser (dynamiske opgaver)
Valgfri per opgave. Tjekket sker på `check_time`, fx kl. 14:00 på forfaldsdagen.
- **Kalender-nøgleord:** `calendar` og `keywords`. Er der en begivenhed med et af nøgleordene **i gang på opgavens tidspunkt** (`due_time`), er opgaven *ikke nødvendig*. Har opgaven ingen `due_time`, gælder enhver begivenhed den dag. Begivenhederne hentes med `calendar.get_events` på tidspunktet for tjekket, ikke løbende.
  - Eksempel: Et besøg fra tirsdag morgen til onsdag kl. 15 gør aftensmad kl. 18 tirsdag *ikke nødvendig*. Onsdag er den *nødvendig*.
  - Tests: en flerdagsbegivenhed, der slutter før `due_time`, en begivenhed, der starter efter `due_time`, og en heldagsbegivenhed.
- **Entitet:** `entity` og `active_state` (standard `on`). Opgaven er kun nødvendig, når entiteten har den state.
- **Ikke nødvendig:** Opgaven fjernes fra listerne og logges som `not_needed` med 0 point. Rotationen rykker ikke, og næste forfald beregnes.
- **Ukendt:** Er kalenderen eller entiteten `unavailable`/`unknown`, bliver opgaven stående med `condition_state: unknown`. Den skjules ikke stille.
  - Todo-punktet viser "Betingelse ukendt". Der prøves ikke igen; opgaven laves som normalt eller springes over.
- **Tidspunkt for tjek:** `check_time` på forfaldsdagen (lokal tid). Er tidspunktet allerede passeret, fx når opgaven lige er oprettet, tjekkes der med det samme.
- **Notifikationer** for en opgave med betingelse venter, til betingelsen er tjekket. En opgave, der ikke er nødvendig, giver ingen "forfalden" eller "overskredet".
- **Overlap** vurderes af integrationen selv ud fra begivenhedernes start og slut, så alle kalendertyper behandles ens. Heldagsbegivenheder gælder fra midnat til midnat lokal tid. Nøgleord sammenlignes med titlen uden forskel på store og små bogstaver.
- **Formular:** Betingelse vælges under Avanceret (ingen, kalender-nøgleord eller entitet). Derefter følger et trin med kalender, nøgleord og tidspunkt for tjek (standard 14:00), eller entitet og state.

## 6. Godkendelse
1. En person med `requires_approval`, eller en opgave med `always`, krydser af. Der oprettes en `pending`-post, og status bliver `pending_approval`. Opgaven bliver stående på listen med markeringen "Afventer godkendelse".
2. Eventet `husopgaver_approval_requested` sendes. Med `builtin_notify` får personer med `can_approve` en notifikation med knapperne **Godkend** og **Afvis**.
3. **Godkend:** en `approved`-post. Pointene tildeles, næste forfald og næste tildeling beregnes, og `husopgaver_completed` sendes.
4. **Afvis:** en `rejected`-post. Ingen point, opgaven vender tilbage som forfalden hos samme person, og `husopgaver_rejected` sendes.
5. **Håndhævelse:** `approve` og `reject` afvises med `ServiceValidationError`, hvis `context.user_id` ikke tilhører en person med `can_approve`. Notifikationsknapper bruger den HA-bruger, som telefonen er logget ind som.
6. **Den fælles tabletbruger** (fx "Køkken") er ikke knyttet til en person med `can_approve` og kan derfor ikke godkende.

## 7. Spærringer og fortryd
- **Tidlig afkrydsning:** Opgaven kan kun krydses af, når den er synlig på listen. Er `complete_window` sat, kun inden for vinduet. Ellers afvises det med en tydelig fejl.
- **Én gang per forekomst:** Gentaget afkrydsning af samme forekomst er en no-op (idempotent).
- **Fortryd:** Fjernes fluebenet inden for 10 minutter (kan konfigureres), oprettes en `undone`-post. Pointene trækkes tilbage, og forfald, tildeling og `rr_index` rulles tilbage.
  - Kun den seneste handling på en forekomst kan fortrydes. Fortrydes en godkendelse, afventer afkrydsningen igen.
  - Afkrydsning, afventende afkrydsning og spring over kan fortrydes. Afvisning kan ikke.
- **Udsæt:** `snooze` flytter forekomstens status og notifikationer til det nye tidspunkt. Gentagelsens rytme ændres ikke.
- **Notifikationer efter genstart:** Hvilke notifikationer (påmindelse, forfald, overskredet) der er sendt, gemmes per forekomst. Efter en genstart sendes kun den seneste, der er passeret, og ingen sendes to gange.
- **Genindlæsning:** Ventende ændringer skrives, før integrationen genindlæses, fx når en opgave rettes.

## 8. Entiteter
- **`todo.husopgaver_<person>`:**
  - Personens opgaver, der er `due`, `overdue`, `pending_approval` eller `upcoming` inden for vinduet (standard 2 dage).
  - Afkrydsning krediteres *listens ejer*.
  - Et nyt punkt i listen bliver til en engangsopgave hos ejeren med 1 point.
  - Redigering af et punkt opdaterer navn, beskrivelse og forfald.
  - Beskrivelsen viser point, status og eventuelt "Afventer godkendelse".
  - **Dagens afkrydsninger** står som udført på listen, indtil midnat. De beholder forekomstens id, så et ekstra tryk ikke gør noget. Fjernes fluebenet, fortrydes afkrydsningen (inden for fortryd-vinduet). En afkrydsning, der afventer godkendelse, står også som udført med "Afventer godkendelse".
  - **Sletning** fra listen virker kun for engangsopgaver. Tilbagevendende opgaver slettes på integrationens side.
  - Ændres navn eller beskrivelse, genindlæses integrationen. Ændres forfaldet, flyttes kun den forekomst.
- **`todo.husopgaver_alle`** (valgfri): Afkrydsning krediteres den tildelte.
- **`todo.husopgaver_godkendelse`:** Afventende godkendelser. Afkrydsning godkender og kræver en bruger med `can_approve`.
- **`sensor.husopgaver_<person>_point`:**
  - State: godkendte point i indeværende uge (mandag til søndag, lokal tid).
  - Attributter: `month`, `all_time`, `since_settlement`, `pending`, `completed_count`, `overdue_count`.
  - `since_settlement` regnes efter rækkefølgen i loggen: alt før den seneste udbetaling er afregnet.
- **`calendar.husopgaver`:** Forekomster af opgaverne inden for den forespurgte periode. Tilbagevendende opgaver udvides, og opgaver, der er ikke nødvendige, vises ikke.
  - Med tidspunkt varer en begivenhed 1 time (frem til "overskredet"). Uden tidspunkt er den heldags.
  - Kun den aktuelle forekomst viser personen. Ved rotation kendes de følgende personer ikke, så de vises uden navn. Ved `fixed` og `each` vises personen altid.
- **Entitets-id'er** er faste uanset HA's sprog: `todo.husopgaver_<person>`, `todo.husopgaver_alle`, `todo.husopgaver_godkendelse`, `sensor.husopgaver_<person>_point` og `calendar.husopgaver`.

## 9. Services
| Service | Felter |
|---|---|
| `husopgaver.complete` | `chore`, `person` (valgfri, standard er den tildelte) |
| `husopgaver.skip` | `chore`, `person` (kun ved `each`) |
| `husopgaver.reassign` | `chore`, `person` |
| `husopgaver.snooze` | `chore`, `duration` |
| `husopgaver.approve` | `log_id` eller `chore` |
| `husopgaver.reject` | `log_id` eller `chore` |
| `husopgaver.undo` | `log_id` eller `chore` |
| `husopgaver.settle` | `person`: nulstiller `since_settlement`, logger `settled`, sletter intet |
| `husopgaver.create_chore` / `update_chore` / `delete_chore` | Opgavens felter |

`chore` kan angives som opgavens id, todo-punkt eller navn. `person` kan angives som id, navn eller person-entitet. Navne sammenlignes uden forskel på store og små bogstaver. Er et navn ikke entydigt, gives der en fejl.

- **Svar:** `complete`, `skip`, `approve`, `reject`, `undo` og `settle` kan returnere `log_id` (`response_variable` i en automation). `create_chore` returnerer `chore_id`. Er en afkrydsning en no-op, er `log_id` `null`.
- **`snooze`** har også `person` til opgaver med `each`.
- **`create_chore` / `update_chore`:** Felterne er `name`, `description`, `points`, `assignees`, `assignment`, `repeat` (`none`/`interval`/`weekly`/`yearly`), `due`, `every`, `unit`, `from`, `weekdays` (`mon`–`sun`), `dates` (`MM-DD`), `due_time`, `notify_before`, `complete_window`, `approval` og `builtin_notify`. `update_chore` ændrer kun de angivne felter. Skiftes `repeat`, nulstilles de andre gentagelsesfelter. Betingelser sættes i brugerfladen (trin 7).
- Opret, ret og slet genindlæser integrationen.

Fejl giver `ServiceValidationError` med oversatte beskeder.

## 10. Events
`husopgaver_due`, `husopgaver_overdue`, `husopgaver_reminder`, `husopgaver_completed`, `husopgaver_skipped`, `husopgaver_not_needed`, `husopgaver_approval_requested`, `husopgaver_rejected`

Data: `chore_id`, `chore_name`, `person_id`, `person_name`, `person_entity`, `notify_target`, `points`, `due` (ISO). Når der er en relevant log-post, kommer også `log_id` med.

## 11. Konfiguration (kun via brugerfladen)
- **Config flow:** Opretter integrationen. Ingen spørgsmål ud over navnet.
- **Options:**
  - Vindue for "kommende" (2 dage)
  - Pointvindue for `least_points` (30 dage)
  - Fraværstærskel (24 timer)
  - Fortryd-vindue (10 minutter)
  - Om listen "Alle opgaver" skal oprettes
- **Subentry "Person":** Knappen "Tilføj person" og en formular. "Ret" og "Slet" findes på hver person.
  - Felter: navn, person i HA, notify-mål (liste over notify-tjenester, eller skriv selv), farve, kan godkende, afkrydsninger skal godkendes, aktiv.
- **Subentry "Opgave":** Knappen "Tilføj opgave" og *én* formular. Felterne er navn, beskrivelse og point, flueben for personerne, strategi, gentagelse og felterne for den valgte gentagelse, tidspunkt, påmindelse og avanceret (betingelse, godkendelse, vindue).
  - Næste trin viser altid felterne for den valgte gentagelse (engangs: forfald; interval: hver, enhed, regnes fra; ugentlig: ugedage; årlig: datoer). Ved "Ret" er felterne udfyldt, hvis typen er den samme.
  - Avanceret (godkendelse, vindue for afkrydsning, indbyggede notifikationer) er en sammenklappet sektion. Betingelser kommer i trin 7.
  - Ved "Ret" bevares rækkefølgen af personer, der stadig er valgt. Nye personer kommer bagerst.
  - Der kan ikke oprettes opgaver, før der findes mindst én person.
- **Sletning:** Når en person eller opgave slettes, bevares loggen.

## 12. Tests (`pytest-homeassistant-custom-component`, kører i GitHub Actions)
- **Næste forfald for alle typer:**
  - `interval` fra forfald og fra udførelse, dag/uge/måned og månedsslut.
  - `weekly`.
  - `yearly`, inklusive udført før tid og flere datoer.
  - Engangsopgave.
- **Sommertid:**
  - Forfald og interval hen over sidste søndag i marts og sidste søndag i oktober.
  - Et tidspunkt, der ikke findes, eller som forekommer to gange.
  - Midnat og ugegrænse ved skiftet.
- **Rotation:**
  - `round_robin`, også med fravær.
  - `least_points`, med uafgjort i begge led af tiebreak.
  - `each`.
- **Point:** uge, måned, all-time og siden udbetaling. Afventende point tælles ikke med.
- **Todo:**
  - Afkrydsning krediteres listens ejer.
  - Afkrydsning i "Alle opgaver" krediteres den tildelte.
  - Fortryd.
  - Nyt punkt bliver en engangsopgave.
- **Godkendelse:** godkend, afvis og afvisning af en uautoriseret bruger.
- **Betingelser:** kalender-nøgleord, entitet og ukendt.
- **Spærringer:** tidlig afkrydsning og dobbelt afkrydsning.
- **Storage:** gemmer kun ved ændring og migration.
- **Config flow og subentries.**
- **CI:** `hassfest` og HACS-validering.

## 13. Levering
- Struktur: `custom_components/husopgaver/`, `hacs.json`, `README.md`, `examples/` og `tests/`.
- README med opsætning, services, events og eksempler.
- **`examples/dashboard_koekken.yaml`:** Lovelace med 4 mellemrums indrykning og kun indbyggede kort.
  - Kalenderkort med `calendar.familie` og `calendar.husopgaver`.
  - Et todo-kort per person.
  - Pointtavle.
  - Kort med afventende godkendelser.
- **`examples/automation_paamindelse.yaml`:**
  - Trigger: `husopgaver_due`.
  - Sender til `notify_target` fra eventdata.
  - Ingen alias-variabler, entiteter bruges direkte.
- **`examples/automation_godkendelse.yaml`:** En actionable notification til de voksne.
- **Eksempel på en betingelse for aftensmad** baseret på kalenderen.

### Dashboardkort (`husopgaver-card`)
Et eget Lovelace-kort, der følger med integrationen. Opdelingen er inspireret af Donetick, men kode og design er vores eget.

- **Levering:** Kortet ligger i integrationen (`custom_components/husopgaver/frontend/`) og registreres automatisk som frontend-modul, når integrationen indlæses. Der kræves ingen ekstra installation i HACS og ingen ressource-opsætning.
- **Teknik:** Et rent web component uden byggetrin, CDN eller eksterne biblioteker. Det kører 100 % lokalt.
- **Data:** Websocket-kommandoen `husopgaver/occurrences` giver forekomsterne med status, person, point og forfald. Med en abonnements-variant opdateres kortet straks ved ændringer, uden polling.
- **Grupper:** Afventer godkendelse, Overskredet, I dag, Kommende (inden for vinduet) og Senere. Senere er sammenklappet som standard. Tomme grupper skjules.
- **Opgavekort:** navn, en farvet chip for personen, forfald ("i dag 18:00", "i morgen", "om 3 dage"), point og eventuelt markeringen "Afventer godkendelse" eller "Ikke nødvendig".
  - **Afkrydsning:** ét tryk på den store knap. Med et personfilter krediteres den valgte person, ellers den tildelte (samme regel som todo-listerne).
  - **Langt tryk eller menu:** spring over, udsæt, giv til en anden og fortryd.
  - Bruger de samme services som resten af integrationen, så godkendelse, spærringer og fejlbeskeder er de samme.
- **Personfilter:** chips med "Alle" og hver person øverst. Valget huskes per enhed, så hvert familiemedlems telefon kan stå på sig selv.
- **Pointtavle** (valgfri): ugens point per person, sorteret.
- **Farver:** Hver person har en valgfri farve i person-formularen. Ellers bruges en fast palet efter rækkefølge. Kortet bruger HA's tema-variabler og virker i lyst og mørkt tema.
- **Tablet:** Trykflader er mindst 48 px, og layoutet går fra én kolonne på telefon til grupper side om side på tablet.
- **Kortets indstillinger** (visuel editor): integrationen, standardfilter, om Senere og pointtavlen vises, og vinduet for Kommende.
- **Sprog:** dansk og engelsk efter brugerens sprog i HA.
- **Tests:** Websocket-kommandoen og abonnementet testes med pytest. Kortets rene funktioner (forfaldstekst, filter, farver, hvem der krediteres) testes med `node --test` i CI.
- **Gruppering** sker i integrationen (`husopgaver/subscribe` sender `group` per punkt), så den ligger ét sted og er testet i Python:
  - `pending`: afventer godkendelse. `overdue`: overskredet. `today`: forfald i dag. `upcoming`: inden for vinduet. `later`: senere. `done`: dagens afkrydsninger (kan fortrydes).
  - Svaret har også personer med ugens og afventende point og `viewer` (personen bag den indloggede bruger og om vedkommende kan godkende). Knapperne Godkend og Afvis vises kun for den, der kan godkende.
- **Klokkeslæt** vises altid som 24-timers HH:MM i HA's tidszone, uafhængigt af browserens locale-data.
- **Kortets indstillinger:** titel, standardfilter, dage i Kommende (tom: integrationens indstilling), vis Senere, vis Udført i dag og vis pointtavle.
- Kortet registreres kun, når HA's frontend kører (`after_dependencies`), og adressen har versionen med, så en opdatering ikke hentes fra cache.

## 14. Byggetrin
1. Datamodel og storage.
2. Schedule og tildeling med tests, inklusive sommertid.
3. Koordinator med timere, events, godkendelse og fortryd.
4. Entiteter: todo, sensor og calendar.
5. Services.
6. Config flow, options og subentries.
7. Betingelser.
8. README, dashboard og automationseksempler.
9. Dashboardkortet `husopgaver-card` med websocket-API, og et eksempeldashboard, der bruger det.

## 15. Uden for v1 (designet til at kunne udvides)
- **Belønninger:** et katalog, hvor point kan byttes til noget, som udvidelse af `settle`.
- **NFC:** `tag_scanned` → `complete`, via en tag-mapping per opgave.
- **Underopgaver:** `parent_id` på opgaven, nulstilles ved gentagelse.
