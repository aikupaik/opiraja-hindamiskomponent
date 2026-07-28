# Stateless R KST service

This directory contains the production stateless KST calculation service,
its versioned internal API contract, and the Step 1 characterization assets
used as its regression baseline. The service performs no database, Shiny,
item-bank, or external network operations.

`plumber.R` constructs the router. Production logic lives in side-effect-free
modules under `src/`.

## Reproducible environment

The project uses R 4.6.1 and `renv`. Restore and verify the exact dependency
set with:

```sh
cd R
Rscript -e 'renv::restore(prompt = FALSE); renv::status()'
```

The ignored legacy `R/library/` directory is not added to `.libPaths()` and is
excluded from dependency discovery.

## Reference suite

The harness in `tests/reference/harness.R` sources `ATA_kst/api.R` and
`TP_kst/TP_loogika.R` into separate private environments. Before any behavior
is invoked, its `sb_get`, `sb_post`, and `sb_patch` functions are replaced with
in-memory stubs. `TP_kst/app.R` is not sourced; the inaccessible reliability
floor, safety cap, and stopping expressions are reproduced in the harness and
their source file and SHA-256 hash are recorded in the fixture.

Generate fixtures only with:

```sh
Rscript R/tests/reference/generate_fixtures.R --write
```

Check committed fixtures without changing them:

```sh
Rscript R/tests/reference/generate_fixtures.R --check
Rscript R/tests/testthat.R
```

Fixture JSON is language-neutral. Timestamps, R classes, vector names, and
database effects are excluded. Matrix row and column order is preserved, and
numbers are serialized with `jsonlite::toJSON(digits = NA)`. The manifest has
no generation timestamp, so two generations from the same source and runtime
are byte-identical. A reference hash change is an investigation signal, not
permission to regenerate.

`uncertain_prerequisite` is retained in profile fixtures and the HTTP contract.
It remains an empty array in valid legacy fixtures: the legacy rule requires a
node to be a prerequisite of every credible mastered state, while a valid
knowledge state containing a dependent also contains that prerequisite.

## Experimental configuration

`config/kst.json` is the single experimental KST configuration. Its canonical
form uses recursively sorted keys, UTF-8, full-precision numbers, and no
insignificant whitespace. The formulas are:

```text
floor(n) = min(max(7, ceiling(1.5 * n)), 10)
cap(n)   = max(2 * n, floor(n) + 1)
```

The versioned hash format is `kst-config-v1:sha256:<hex>`, where `<hex>` is the
SHA-256 digest of the exact canonical file bytes.

## Internal API contract

`contracts/internal-kst-v1.openapi.json` defines the stateless internal
legacy boundary and remains frozen:

- `GET /health`
- `POST /internal/v1/kst/model`
- `POST /internal/v1/kst/advance`

HTTP node references are strings. One-based matrix column indices stay inside
R. Validation failures use HTTP 422 and unexpected failures use HTTP 500, both
with `{"error":{"code","message","details"}}`.

The English profile mapping is frozen in the contract and tests. One
production behavior intentionally differs from the characterized prototype:
`kmassesshalfsplit()` randomly samples exact ties, while the internal contract
selects the first tied node in declared node order for reproducible sessions.
The legacy fixture therefore stores the complete allowed-node set for ties.

`contracts/internal-kst-v2.openapi.json` defines the candidate-aware boundary:

- `POST /internal/v2/kst/model` builds the graph model and returns the
  configuration-derived `reliability_floor` and `safety_cap`;
- `POST /internal/v2/kst/select` selects only from ordered item candidates;
- `POST /internal/v2/kst/advance` updates with the administered candidate's
  scalar `beta` and `eta`, then completes or selects from remaining candidates.

Candidate IDs are opaque, nonblank, and unique. Candidate order resolves exact
half-split ties. If no candidate remains after a nonterminal update, v2
completes with `item_inventory_exhausted` and `confidence_limited=true`.

## Lühiraport: seadistus ja lepingud

Fail `config/kst.json` koondab KST-hindamise uurimuslikud parameetrid ühte
versioonitavasse kohta. Test võib loomulikult lõppeda, kui kõige tõenäolisema
teadmusoleku tõenäosus on vähemalt `0.8` ja vastuste arv on saavutanud
reliaabluse alampiiri. Alampiir on
`min(max(7, ceiling(1.5 × n)), 10)`, kus `n` on sõlmede arv. Turvapiir
`max(2 × n, alampiir + 1)` lõpetab testi ka siis, kui nõutud kindlust ei
saavutata. Lõpp-tagasiside usutavate teadmusolekute hulk peab katma vähemalt
`0.9` posteriorjaotuse massist.

Konfiguratsiooni räsi seob tulemuse täpselt kasutatud parameetritega. See
võimaldab hiljem võrrelda katseid ja kontrollida, kas tulemuste erinevus võis
tuleneda seadistuse muutmisest. Parameetri muutmine mõjutab tulevikus uusi
teste; juba alanud testi juures tuleb säilitada selle algne seadistus ja räsi.

Fail `contracts/internal-kst-v1.openapi.json` kirjeldab külmutatud pärand-
andmevahetust. Fail `contracts/internal-kst-v2.openapi.json` kirjeldab uute
sessioonide kandidaaditeadlikku R-arvutusteenuse
andmevahetust. Mudeli päring võtab vastu järjestatud sõlmed, eeldusseosed ja
tagastab teadmusruumi, ühtlase priorjaotuse ja tuletatud peatamispiirid.
Valiku päring saab ainult kasutamata ülesandekandidaadid. Edasiliikumise päring
kasutab vastatud konkreetse ülesande vea- ja äraarvamisparameetreid ning
tagastab järgmise kandidaadi või lõpp-profiili.

Leping fikseerib ka ingliskeelsed väljanimed ja veavastuste kuju. Täpsete
poolitusviikide korral valib tulevane teenus deklareeritud sõlmejärjestuses
esimese kandidaadi, mis teeb hindamissessioonid korratavaks; pärandkoodi
juhuslik viigikäitumine on võrdlusandmetes säilitatud lubatud kandidaatide
hulgana.
