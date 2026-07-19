# Õpiraja hindamiskomponent (HK) — ATA / YG / TP

See repo sisaldab õpiraja teenuse hindamiskomponendi (HK) lähtekoodi: kolm osaliselt
iseseisvat R/Shiny rakendust + üks Supabase Edge Function, mis kõik suhtlevad
läbi ühise Supabase Postgres andmebaasi.

Kui sa pole varem R-iga töötanud — see dokument on kirjutatud just sulle. Enamik
sellest ei ole "mida kood teeb" (see on koodis endas kommentaaridena), vaid
**"mida sa R-i kohta teadma pead, et see kood üldse loogiline tunduks"**.

## Komponendid ja kus nad elavad

| Komponent | Mis see on | Kus jookseb | Peafailid |
| --- | --- | --- | --- |
| **ATA** (Automated Test Assembly) | Testi kokkupanemise mootor: KST-mudeli arvutus, ülesannete sidumine | shinyapps.io, rakendus `ATA_kst` | `app.R`, `api.R` |
| **TP** (Testipleier) | Kasutajale nähtav testi läbiviimise UI, adaptiivne küsimuste valik | shinyapps.io, rakendus `TP_kst` | `app.R`, `TP_loogika.R` |
| **YG** (Ülesandegeneraator) | AI-põhine (Gemini) uute testiülesannete loomine | Supabase Edge Function | `index.ts` |
| **HK_admin** | Arendusaegne simulaator/testtööriist (pole tootmise osa) | shinyapps.io, rakendus `OR_sim` | `app.R` |

Kõik komponendid on **täiesti eraldiseisvad protsessid** — nad ei kutsu teineteist
otse funktsioonikutsetega (nagu tavalises monoliitrakenduses), vaid suhtlevad
KAHEL viisil:
1. **Ühiste Supabase tabelite kaudu** (vt `Supabase_skeem_ja_tooajaotus.docx`) — see on
   peamine andmekanal.
2. **HTTP kutsetena üle Plumber-API otspunktide** (nt TP kutsub ATA `/api/test/status`
   endpoint'i pollimiseks) — see on OLEKUmasina edenemise signaal, mitte andmekanal.

## Miks "app.R sees peidetud API"? (ATA eripära)

ATA on tegelikult [Plumber](https://www.rplumber.io/) API (nagu Flask/Express, aga
R-is) — aga see on peidetud tavalise Shiny app'i `app.R` sisse, sest organisatsiooni
shinyapps.io konto ei luba Posit Connect'ita otsest Plumber-tüüpi deploy'd, ainult
Shiny-tüüpi rakendusi. `app.R` käivitab Plumber'i sisemiselt. Sellepärast asub
API loogika failis, mida sa tavaliselt Shiny UI koodiks peaksid — `api.R` ongi
päris API, `app.R` on ainult käivitusmehhanism selle ümber.

## R-i eripärad, mis TÄNA (17.07.2026) mitmel korral vigu tekitasid

Need pole "loetud kord ja unustatud" — need on mustrid, mis korduvad, kui uut
koodi lisad. Iga punkt maksis 1+ debug-tsükli.

### 1. Tühja andmebaasi-tulemuse "kuju" pole ennustatav

R-is teeb `httr`+`jsonlite` kombinatsioon midagi, mis teistest keeltest tulles
üllatab: kui Supabase (PostgREST) tagastab **mittetühja** tulemuse, saad
`data.frame`'i (tabelilaadne struktuur, `nrow()` töötab). Kui tulemus on **tühi**
(`"[]"`), saad **tavalise `list()`-i** (pikkus 0) — MITTE 0-realist `data.frame`'i.

```r
nrow(data.frame())   # 0  -- ok
nrow(list())         # NULL  -- "vale" kuju!
if (nrow(list()) > 0) ...   # viskab "argument is of length zero"
```

See ON kogu tänase esimese vea (`yg_read`/`nrow`) juurpõhjus — ja sama muster oli
juba varem tabanud teisi kohti. Kasuta ALATI abifunktsiooni `n_rida()` (defineeritud
`api.R` ja `TP_loogika.R` alguses), mitte otse `nrow()`, kui tulemus võib olla tühi:

```r
n_rida <- function(x) {
  if (is.null(x)) return(0L)
  if (is.data.frame(x)) return(nrow(x))
  length(x)
}
```

### 2. JSONB-veerud võivad tulla kahes eri kujus tagasi

Sama probleemi teine nägu: `testisessioonid.testi_loogika` (jsonb-veerg) tuleb
tagasi **stringina**, kui meie enda kood on sinna varem midagi kirjutanud, aga
**0-veeruga `data.frame`'ina**, kui väli on ikka veel vaikeväärtuses `{}`. Kasuta
`loe_jsonb_vali()` abifunktsiooni (`TP_loogika.R`), mitte otse `fromJSON()`.

### 3. R funktsioonid ootavad tihti täisvektoreid, mitte üksikväärtusi

`kstMatrix::kmassessbayesian(probs, ks, beta, eta, question, response)` — `beta`
ja `eta` peavad olema vektorid **üle KÕIGI mudeli sõlmede** (pikkus = `K` veergude
arv), mitte ühe konkreetse küsimuse skalaarväärtus. See on matemaatiline nõue
(Bayesi uuendus arvutab korraga üle kogu teadmusruumi), mitte R-i kummalisus —
aga viga, mis tekib valest kujust ("beta and pks do not fit in size"), on tüüpiline
R-i nõrk tüübikontroll: R ei takista sind saatmast valet pikkust, enne kui
funktsioon seda sisemiselt kasutama hakkab.

### 4. Komadega PostgREST-filtrid lähevad katki eestikeelse teksti peal

Kui sõlme/õpiväljundi nimi ise sisaldab koma (tavaline eestikeelses lauses), ja
sa ehitad PostgREST `in.(a,b,c)` filtri komadega ühendades, läheb filter katki
keset lauset. Kasuta eraldajana midagi, mis eestikeelses tekstis ei esine
(repo kasutab ` -> ` — nool koos tühikutega), ja/või ehita korduskutsed
(`eq.` üksikult tsüklis) `in.()` asemel, kui väli võib vaba teksti sisaldada.

### 5. Shiny app "ei logi" tavalist edukat täitmist vaikimisi

Kui midagi läheb valesti Shiny observer'i sees ilma nähtava veata, on server-log
sageli **tühi**, isegi kui midagi tegelikult juhtus (nt katkes vaikselt, taaskäivitus
jms). Ära usalda "logis pole midagi" kui "kõik on korras" tõendit — lisa
`message()`-logimine igasse olulisse sammu, kui midagi debugid (vt
`dbg()`/`samm()` abifunktsioonid `api.R`-is).

### 6. shinyapps.io tasuta tase "magab", kui rakendust mõnda aega ei kasutata

Esimene päring pärast pausi (cold start) võtab 1-2s kauem ja mõnikord tagastab
platvormi enda vahepealse vastuse enne, kui rakendus reaalselt üleval on — see
võib välja näha nagu koodiviga, aga pole. Korduva päringu/taaskatse loogika (vt
`api.R` `wake_tp()` muster) leevendab seda.

## Deploy-versiooni kinnitamine

Kuna shinyapps.io deploy ei anna alati selget kinnitust, et uus kood tegelikult
serverisse jõudis, on igas failis konstant:

```r
API_VERSIOON <- "2026-07-17-fix-yg-read-nrow"
```

See lisatakse iga veavastuse/logi külge. Kui logis näed vana versiooninumbrit,
pole uus kood veel deploy'itud — enne muud debugimist kontrolli seda.

## Andmemudel

Vt `Supabase_skeem_ja_tooajaotus.docx` — 7 tabelit, nende FK-seosed ja tööjaotus
(kes millist tabelit kirjutab/loeb, mis etapis). RLS on kõigil tabelitel
**teadlikult väljas** demo/arendusfaasis (pole reaalseid kasutajaandmeid) — see
tuleb enne reaalsete kasutajateni jõudmist sisse lülitada (SQL selle jaoks on
sama dokumendi lõpus).

## Teoreetiline taust

Vt `Spetsifikatsioon.docx` kontseptsiooni ja kasutajateekonna kohta, ja
`ATA_TP_arhitektuur.xml` (draw.io fail — ava [app.diagrams.net](https://app.diagrams.net)
kaudu) visuaalse ATA/TP komponentide ja andmevoo skeemi kohta.

Meetod on Knowledge Space Theory (KST, Doignon & Falmagne 1999) — kasutatavad
R paketid: `kst`, `kstMatrix`, `pks`. Kui miski KST-terminoloogiast (teadmusseisund,
väline/sisemine äär, BLIM) segaseks jääb, küsi — see on eraldi teema R-i enda
süntaksist.
