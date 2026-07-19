# Õpiraja hindamiskomponent (HK) — ATA / YG / TP

Järgnev materjal sisaldab õpiraja teenuse hindamiskomponendi (HK) algse demo lähtekoodi: kolm osaliselt
iseseisvat R/Shiny rakendust + üks Supabase Edge Function, mis kõik suhtlevad
läbi ühise Supabase Postgres andmebaasi.

Kui sa pole varem R-iga töötanud — see dokument on kirjutatud just sulle. Enamik
sellest ei ole "mida kood teeb" (see on koodis endas kommentaaridena), vaid
**"mida sa R-i kohta teadma pead, et see kood üldse loogiline tunduks"**.

## Komponendid ja nende paiknemine

| Komponent | Mis see on | Kus jookseb | Peafailid |
| --- | --- | --- | --- |
| **ATA** (Automated Test Assembly) | Testi kokkupanemise mootor: KST-mudeli arvutus, ülesannete sidumine | shinyapps.io, rakendus `ATA_kst` | `app.R`, `api.R` |
| **TP** (Testipleier) | Kasutajale nähtav testi läbiviimise UI, adaptiivne küsimuste valik | shinyapps.io, rakendus `TP_kst` | `app.R`, `TP_loogika.R` |
| **YG** (Ülesandegeneraator) | AI-põhine (Gemini) uute testiülesannete loomine | Supabase Edge Function | `index.ts` |
| **HK_admin** | Arendusaegne simulaator/testtööriist (pole rkenduse osa(!)) | shinyapps.io, rakendus `HK_admin` | `app.R` |

Kõik komponendid on **täiesti eraldiseisvad protsessid** — nad ei kutsu teineteist
otse funktsioonikutsetega (nagu tavaliselt monoliitrakenduses), vaid suhtlevad
KAHEL viisil:
1. **Ühiste Supabase tabelite kaudu** (vt `Supabase_skeem_ja_toojaotus.docx`) — see on
   peamine andmekanal.
2. **HTTP kutsetena üle Plumber-API otspunktide** (nt TP kutsub ATA `/api/test/status`
   endpoint'i pollimiseks) — see on OLEKUmasina edenemise signaal, mitte andmekanal.

## Miks "app.R sees peidetud API"? (ATA eripära)

ATA on tegelikult [Plumber](https://www.rplumber.io/) API (nagu Flask/Express, aga
R-is) — aga see on peidetud tavalise Shiny app'i `app.R` sisse, sest organisatsiooni
shinyapps.io konto ei luba Posit Connect'ita otsest Plumber-tüüpi deploy'mist, ainult
Shiny-tüüpi rakendusi. `app.R` käivitab Plumber'i "sisemiselt". Sellepärast asub
API loogika failis, mida tavaliselt peetaks Shiny UI koodiks — `api.R` on
päris API, `app.R` on käivitusmehhanism.

## R-i eripärad, mis TÄNA (17.07.2026) mitmel korral vigu tekitasid

Need pole üksikud juhtumid, vaid mustrid, mis korduvad uue koodiga. Lisas iga kord 1+ debug-tsükli.

### 1. Tühja andmebaasi-tulemuse "kuju" pole ennustatav

R-is teeb `httr`+`jsonlite` kombinatsioon midagi, mis teistest keeltest tulles
üllatab: kui Supabase (PostgREST) tagastab **mittetühja** tulemuse, saad
`data.frame`'i (tabelilaadne struktuur, `nrow()` töötab). Kui tulemus on **tühi**
(`"[]"`), saad tüübina **tavalise `list()`-i** (pikkus 0) — MITTE 0-realist `data.frame`'i.

```r
nrow(data.frame())   # 0  -- ok
nrow(list())         # NULL  -- "vale" kuju!
if (nrow(list()) > 0) ...   # viskab "argument is of length zero"
```

See oli rea vigade (`yg_read`/`nrow`) juurpõhjus. 
Kasuta abifunktsiooni `n_rida()` (defineeritud
`api.R` ja `TP_loogika.R` alguses), mitte otse `nrow()`, kui tulemus kasutamisel võib olla või peab olema tühi:

```r
n_rida <- function(x) {
  if (is.null(x)) return(0L)
  if (is.data.frame(x)) return(nrow(x))
  length(x)
}
```

### 2. JSONB-veerud võivad tulla tagasi kahel eri kujul

Sama probleemi teine väljendus: `testisessioonid.testi_loogika` (jsonb-veerg) tuleb
tagasi **stringina**, kui meie enda kood on sinna varem midagi kirjutanud, aga
**0-veeruga `data.frame`'ina**, kui väli on ikka veel vaikeväärtuses `{}`. Kasuta
`loe_jsonb_vali()` abifunktsiooni (`TP_loogika.R`), mitte otse `fromJSON()`.

### 3. R funktsioonid ootavad tihti täisvektoreid, mitte üksikväärtusi

KST lahenduses `kstMatrix::kmassessbayesian(probs, ks, beta, eta, question, response)`:
- `beta`ja `eta` peavad olema vektorid **üle KÕIGI mudeli sõlmede** (pikkus = `K` veergude
arv), mitte ühe konkreetse küsimuse skalaarväärtus.
See on matemaatiline nõue (Bayesi uuendus arvutab korraga üle kogu teadmusruumi), mitte R-ist tulenev —
aga viga, mis tekib valest kujust ("beta and pks do not fit in size"), on R-i nõrk tüübikontroll:
R ei takista sind saatmast valet pikkust, enne funktsiooni kui funktsioon sisemiselt selle kasutusele võtab.

### 4. Komadega PostgREST-filtrid lähevad katki eestikeelse teksti peal

Kui sõlme/õpiväljundi nimi ise sisaldab koma (tavaline eestikeelse lause konstruktsioonis), ja
sa ehitad PostgREST `in.(a,b,c)` filtri komadega ühendades, läheb filter katki
lause keskel katki. Kasuta eraldajana midagi, mis eestikeelses tekstis ei esine
(demos kasutab nt ` -> ` — nool koos tühikutega), ja/või ehita korduskutsed
(`eq.` üksikult tsüklis) `in.()` asemel, kui väli võib vaba teksti sisaldada.

### 5. Shiny app "ei logi" tavalist edukat täitmist vaikimisi

Kui midagi läheb valesti Shiny observer'i sees ilma nähtava veata, on server-log
sageli **tühi**, isegi kui midagi tegelikult juhtus (nt katkes vaikselt, taaskäivitus
vms). Kui logis pole midagi, siis pole kõik korras, vaid viga jäi märkmata — lisa
`message()`-logimine igasse olulisse sammu, kui midagi debugid (vt
`dbg()`/`samm()` abifunktsioonid `api.R`-is).

### 6. shinyapps.io tasuta tase "magab", kui rakendust mõnda aega ei kasutata

Esimene päring pärast pausi (cold start) võtab 1-2s kauem ja mõnikord tagastab
platvormi enda vahepealse vastuse enne, kui rakendus reaalselt üleval on — see
võib välja näha nagu koodiviga, aga pole. 
Korduva päringu/taaskatse loogika (vt `api.R` `wake_tp()` muster) leevendab seda.

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
tuleb enne reaalsete kasutajateni jõudmist sisse lülitada (SQL selleks on
sama dokumendi lõpus).

## Teoreetiline taust

Vt `Spetsifikatsioon.docx` kontseptsiooni ja kasutajateekonna kohta, ja
`ATA_TP_arhitektuur.xml` (draw.io fail — ava [app.diagrams.net](https://app.diagrams.net)
kaudu) visuaalse ATA/TP komponentide ja andmevoo skeemi kohta.

HK on mõeldid pakkuma erineva metoodikaga hindamisvõimalusi. Demos kasutatud meetod on Knowledge Space Theory 
(KST, Doignon & Falmagne 1999).

### Kasutatavad R paketid: 
`kst`, `kstMatrix`, `pks`. Kui miski KST-terminoloogiast (teadmusseisund,
väline/sisemine äär, BLIM) segaseks jääb, saab ülevaate käsitlusviisi rtiklitest või küsi.
