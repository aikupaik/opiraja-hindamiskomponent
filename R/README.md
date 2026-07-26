# R characterization assets

This directory contains Step 1 characterization assets only. It does not
contain a production R service or Plumber handlers.

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

`contracts/internal-kst-v1.openapi.json` defines the future stateless internal
service boundary:

- `GET /health`
- `POST /internal/v1/kst/model`
- `POST /internal/v1/kst/advance`

HTTP node references are strings. One-based matrix column indices stay inside
R. Validation failures use HTTP 422 and unexpected failures use HTTP 500, both
with `{"error":{"code","message","details"}}`.

The English profile mapping is frozen in the contract and tests. One future
behavior intentionally differs from the characterized prototype:
`kmassesshalfsplit()` randomly samples exact ties, while the internal contract
selects the first tied node in declared node order for reproducible sessions.
The legacy fixture therefore stores the complete allowed-node set for ties.

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

Fail `contracts/internal-kst-v1.openapi.json` kirjeldab R-arvutusteenuse
andmevahetust. Mudeli päring võtab vastu järjestatud sõlmed, eeldusseosed ja
sõlmepõhised vea- ning äraarvamisparameetrid ning tagastab teadmusruumi,
ühtlase priorjaotuse ja esimese küsimuse sõlme. Edasiliikumise päring uuendab
vastuse põhjal posteriorjaotust ning tagastab kas järgmise sõlme või
lõpp-profiili. Leping kasutab välises andmevahetuses sõlmede nimetusi, et
maatriksi R-spetsiifilised indeksid ei lekiks teistesse süsteemidesse.

Leping fikseerib ka ingliskeelsed väljanimed ja veavastuste kuju. Täpsete
poolitusviikide korral valib tulevane teenus deklareeritud sõlmejärjestuses
esimese kandidaadi, mis teeb hindamissessioonid korratavaks; pärandkoodi
juhuslik viigikäitumine on võrdlusandmetes säilitatud lubatud kandidaatide
hulgana.
