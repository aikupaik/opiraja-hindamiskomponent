# HK / TP — Ülesannete valiku ja testi peatamise reeglid

Seisuga 11.08.2026. Viitab failidele `TP_loogika.R` (TP_kst), `app.R` (TP_kst) ja `api.R` (ATA_kst).

## 1. Sõlme valik (mida küsida järgmisena)

Iga küsimuse jaoks valitakse **sõlm** (mitte veel ülesanne) KST half-split algoritmiga:

```r
solm_indeks <- kmassesshalfsplit(posterior, K)
```

Valib sõlme, mis jagab hetkel usutavate teadmusseisundite tõenäosusmassi kõige ühtlasemalt kaheks — kõige informatiivsem järgmine küsimus, arvestades kõiki seniseid vastuseid.

*Asukoht: `TP_loogika.R` → `vali_jargmine_solm()`*

## 2. Ülesande valik sõlme sees

Kui sõlm on valitud, tuleb selle sõlme jaoks valida **konkreetne ülesanne** `ylesandepank` tabelist.

**Filter:**
- `graafi_objekt = <valitud sõlm>`
- `staatus = "kasutatav"`

**Kursust ei arvestata siin.** Sõlm (`graafi_objekt`) on ülesande sobivuse tegelik identiteet — kursus on ainult abistav viide, mida YG kasutab materjali leidmiseks ülesande *loomisel*, mitte 
ligipääsu piirav filter selle *kasutamisel*. Sama sõlme jaoks loodud ülesanne sobib igale testile, mis seda sõlme küsib, sõltumata algsest kursusest.

**Valikureegel, kahes etapis:**

1. **Selles testis veel kasutamata** ülesannete seast eelistatakse seda, mille **globaalne** `kasutamiste_arv` on väikseim.
   → Jaotab kasutuse pika aja jooksul õiglaselt kogu ülesandepanga sees, mitte ei koorma alati sama (nt madalaima ID-ga) ülesannet.

2. Kui **kõik** selle sõlme ülesanded on juba selles testis küsitud (pool ammendunud) — mis võib juhtuda, kui half-split peab sama sõlme korduvalt informatiivseks (vt p 4) —, valitakse **selles testis** kõige vähem korratud ülesanne.
   → Jaotab paratamatud kordused õiglaselt testi enda sees, mitte ei kuhjab neid ühele ja samale ülesandele.

*Asukoht: `TP_loogika.R` → `vali_ylesanne_solmele()`*

Valikureegleid on kavas täiendada

* vajaduspõhiselt UX piloodi käigus - selgub, milliseid ja kuidas organiseeritud struktuuriga väljundeid hinnatakse,
* lähtudes ülesannete empiirilistest mõõtmisomadustest - seame juurde parameetrite põhjal hülgamislävendid ja valiku kriteeriumid.


## 3. Mitu ülesannet sõlme kohta luuakse (YG tellimus)

Kui mõnel sõlmel pole ühtegi kasutatavat ülesannet, tellib ATA YG-lt:

```r
maht = 5   # ülesannet sõlme kohta
```

**Miks 5, mitte vähem:** simulatsioonid ja päris andmebaasi juhtumid näitasid, et testi käigus võib sama sõlme küsida rohkem kui korra (vt § 4 — miinimum-vaatluste nõue), mistõttu väiksem pool (nt 3) sundis mõnel juhul sama ülesannet mitmel korral kordama ühe testi sees.

*Asukoht: `api.R` → `trigger_yg_kui_vaja()`*

## 4. Testi peatamise reeglid

Kaks tingimust, mis koos määravad, millal test lõpeb:

```r
reliaabluse_pohi(n) = min(max(7, ceiling(1.5 * n)), 10)   # miinimum vaatlusi KOKKU
turvapiir(n)         = max(2 * n, reliaabluse_pohi(n) + 1)  # maksimum vaatlusi KOKKU

loomulik_valmis = max(posterior) >= 0.9  JA  vaatlusi >= reliaabluse_pohi(n)

PEATU kui: loomulik_valmis  VÕI  vaatlusi >= turvapiir(n)
```

kus `n` = sõlmede arv testis.

| Reegel | Tähendus | Miks |
|---|---|---|
| **Miinimum** (`reliaabluse_pohi`) | Test ei tohi peatuda enne seda, olenemata kindlusest | Väldib, et paar juhuslikku (õiget/valet) vastust kinnitaks vale teadmusseisundi liiga vara |
| **Kindluse lävi** (0,9) | Loomulik peatumine nõuab, et kõige tõenäolisema seisundi tõenäosus ületaks 90% | Tõstetud 0,8-lt — simulatsioonid näitasid selget täpsuse paranemist, eriti äraarvava vastamisstiili korral |
| **Maksimum** (`turvapiir`) | Test peatub sundkorras, kui kindlust ei saavutata | Väldib lõputult pikka testi, kui vastaja on ebajärjekindel - või väljundite struktuur on kusagil varem ekslikult defineeritud |

**Globaalne, mitte per sõlm nõue:** miinimum kehtib testi **kõigi** vaatluste arvu kohta, mitte iga üksiku sõlme kohta eraldi. Struktuurilt juba tuletatavaid sõlmi ei pea eraldi küsima — see on adaptiivse testimise mõte.

*Asukoht: `app.R` → peatumiskontroll `edasi_btn` observer'i sees*

## 5. Tuntud piirang: vastamise ebaühtlus

Ülaltoodud reeglid parandavad täpsust hästi nn **äraarvava/õnneliku** vastamisstiili korral, aga **hooletu** (kõrge juhusliku vigade määraga) vastaja puhul on paranemine palju piiratum — see on struktuurne piirang, mitte olukord, mida reegleid manipuleerides saaks ära lahendada. Täiendava info jaoks vt `Testi maht ja kalibreerimine...` simulatsiooni kokkuvõtet.

## Muudatuste ajalugu (lühidalt)

- **01.08.2026** — kindluse lävi 0,8 → 0,9; ülesande maht 3 → 5 sõlme kohta; ülesande valikusse lisatud globaalse `kasutamiste_arv` eelistus
- **19.07.2026** — miinimumnõue muudetud per-sõlme reeglist globaalseks (kogu testi) reegliks