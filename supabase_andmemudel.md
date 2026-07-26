**Õpiraja hindamiskomponent (HK) — ATA, YG, TP**

*Andmemudel ja tööjaotus — v2*

*supabase*

Projekt: kwwxpsrojgtziluguqkm · Seisuga: 20. juuli 2026 (eelmine
versioon: 13. juuli 2026)

Koostas: Aivar koos Claude'iga (Anthropic)

# Sissejuhatus

See dokument kirjeldab õpiraja hindamiskomponendi (HK) Supabase
andmemudelit: milliseid tabeleid süsteem kasutab, mis andmed neisse
käivad, ja milline osa süsteemist (ATA, YG või TP) millise tabeliga
töötab. Eesmärk on anda arendajale ja teistele meeskonnaliikmetele
ühtne, ajakohane pilt, mille pealt edasist, skaleeritavat arhitektuuri
kavandada.

Lühendid:

ATA = Automated Test Assembly (testi kokkupanemise mootor);

YG = Ülesandegeneraator (AI-põhine, loob uusi testiülesandeid);

TP = Testipleier (testi läbiviimise komponent);

OR = Õpiraja teenus (tellimuse esitaja, väljaspool HK-d);

HK = Hindamiskomponent tervikuna, sh admin-tööriistad;

AN = Analüüsikomponent (kalibreerimine, veel realiseerimata).

# Muudatused võrreldes 13.07 versiooniga

Eelmise versiooni koostamise ajal ei olnud TP (testipleier) demo valmis.
Vahepeal on TP loodud ja testitud (sh 4-rubriigiline tagasiside,
adaptiivne peatumisloogika). See versioon:

- lisab TP tsükli täieliku kirjelduse (küsimuse valik, Bayes-uuendus,
  peatumisloogika, tulemuse koostamine) — vt uus peatükk "TP tsükkel";

- täpsustab testi_loogika ja lopp_profiil JSONB väljade sisemist;

- lisab kriitilise arhitektuuripõhimõtte: graafi_objekt (sõlm), mitte
  kursus, on ülesande sobivuse tegelik identiteet (vt "Sõlme identiteedi
  põhimõte")

- selgitab YG-LLM suhet täpsemalt: LLM kutse teeb AINULT YG (TP ja LLM
  ei suhtle omavahel);

- lisab OR-suhtluse hetkeseisu ja ettepaneku puuduva "kas test on
  valmis" mehhanismi jaoks (vt "OR suhtlus");

- esitab ridade ja tabelite kirjeldused vastavuses praeguse Supabase
  skeemile (vt tabelite juures kuupäevastatud reakogused);

- lisab konsolideeritud "Lahtised küsimused" peatüki, mis vastab osale
  13.07 dokumenti lisatud NB!-küsimustest ja loetleb, mis asjad seni on
  lahendamata.

# Tabelite seosed

Andmemudeli tuum on testisessioonid tabel, mis seob kokku
teadmusstruktuuri (graafid_kst), ülesannete panga (ylesandepank) ja
hilisemad testitulemused (tulemustepank). yg_tellimused, repo_materjalid
ja yg_reeglid on lõdvemalt seotud tugitabelid.

| **Tabel** | **Peamine võti** | **Seotud tabelid (FK)** | **Ridu praegu** |
|-----------------|-------------|--------------------------|--------|
| graafid_kst | graaf_hash | testisessioonid.graaf_hash | 9 |
| testisessioonid | test_id | graafid_kst, tulemustepank | 38 |
| ylesandepank | yp_id | tulemustepank | 67 |
| tulemustepank | id | testisessioonid, ylesandepank | 48 |
| yg_tellimused | id | — (test_id on vaba viide, mitte FK) | 25 |
| repo_materjalid | id | — (iseseisev) | 3 |
| yg_reeglid | id | — (iseseisev, hetkel tühi) | 0 |

*Lisaks eksisteerib Supabase projektis tabel event_publication (0 rida)
— see EI ole HK loogika osa; tundub olevat raamistiku/extension'i
automaatselt loodud jäänuk.*

# Tabelid detailselt

## graafid_kst (9 rida)

*Cache/dedublitseeritud KST teadmusruumi struktuurid, võtmestatud graafi
sisu hash'i järgi. Kui kaks tellimust kirjeldavad täpselt sama graafi
(samad sõlmed + seosed), taaskasutatakse siin juba arvutatud
struktuuri.*

| **Veerg** | **Tüüp** | **Märkused** |
|-----------------|------------|-----------------------------------|
| graaf_hash | text | Primaarvõti |
| graafi_struktuur | jsonb | Algne sõlmed + seosed kirjeldus |
| teadmusruum_maatriks | jsonb | KST arvutuse väljund — olekute loend (nt \[\[\], \["A"\], \["A","B"\], …\]) |
| loodud | timestamptz | Vaikeväärtus: praegune aeg |

## testisessioonid (38 rida)

*Iga testi elutsükli keskne kirje — algusest (planeerimine) lõpuni
(lõpetatud). testi_loogika ja lopp_profiil sisemine struktuur on nüüd
täpsustatud eraldi peatükis "testi_loogika ja lopp_profiil struktuur".*

| **Veerg** | **Tüüp** | **Märkused** |
|----------------|------------|------------------------------------|
| test_id | text | Primaarvõti; genereerib ATA (uuid), DB defaulti pole |
| kasutaja_id | text | — |
| rada_id | text | Õpiraja ID (OR-i vastutusalast) |
| graaf_hash | text | Viide graafid_kst tabelile (nullable) |
| staatus | text | planeerimisel / aktiivne / lõpetatud / katkenud (CHECK piirang) |
| alustatud | timestamptz | Vaikeväärtus: praegune aeg |
| lopp_profiil | jsonb | Täidetakse testi lõppedes — TP vastutus (lopeta_test()), nullable. Struktuur täpsustatud eraldi peatükis. |
| testi_loogika | jsonb | ATA väljund (rada 6); vaikeväärtus tühi objekt. Struktuur täpsustatud eraldi peatükis. |
| metoodika | text | ct / kst / irt / dina (vaikeväärtus: kst; CHECK piirang). Praegu realiseeritud ainult kst haru. |
| tp_seisund | jsonb | UUS (lisandunud pärast 13.07): TP jooksva testi olek — posterior (tõenäosusjaotus üle olekute) + kysitud (juba küsitud ülesannete logi). Vaikeväärtus tühi objekt. |
| eesmark | text | OR-i tellimuse osa (kasutaja hindamise kavatsus, nt "arusaamine"/"ajaviide") — määrab metoodika, eristab demo/päris kasutust hilisemaks kalibreerimiseks. Nullable, veel CHECK-piiranguta. |

## ylesandepank (67 rida)

*Ülesandepank (YP) — sisaldab nii ülesande sisu kui ka hindamismudelite
(IRT/pks) parameetreid ja kalibreerimise jälgimist.*

| **Veerg** | **Tüüp** | **Märkused** |
|----------------|------------|------------------------------------|
| yp_id | bigint | Primaarvõti |
| kursus | text | Abistav viide YG materjali/konteksti jaoks — EI ole ülesande sobivuse identiteet (vt "Sõlme identiteedi põhimõte") |
| graafi_objekt | text | Õpiväljundi / sõlme viide — ülesande TEGELIK sobivuse identiteet |
| graafi_ema_objekt | text | Endiselt kasutuseta praktikas — lahtine küsimus, kust/kuidas seda mõistlikult täita, et säilitada seos õige väljundite skeemiga (vt "Lahtised küsimused") |
| kognitiivne_tase | text | mäletab / mõistab / rakendab / analüüsib / hindab / loob (CHECK piirang) |
| juhis, tyvi, stiimul | text | Ülesande sisu (stiimul nullable — praktikas sageli tühi, vt allpool) |
| voti, distraktor_1-3 | text | Valikvastuste komponendid |
| skoor | integer | Vaikeväärtus: 1 |
| irt_a, irt_b | numeric | IRT parameetrid (vaikeväärtus 1.00 / 0.00) — metoodika pole veel kasutusel (kst ainus realiseeritud haru) |
| beeta_error, g_guess | numeric | pks/BLIM parameetrid (vaikeväärtus 0.05 / 0.25 — fiktiivsed algväärtused, kalibreerimata) |
| staatus | text | kavand / kasutatav / läbi vaatamisel / arhiivis (CHECK piirang) |
| kasutamiste_arv | integer | Vaikeväärtus: 0 — kalibreerimise läve jälgimiseks |
| viimane_kasutus | timestamptz | Nullable |

*Valdaval osal ridadest (nähtud nt füüsika ülesannete puhul, 7/9) on
stiimul tühi — YG prompt ei nõua praegu järjekindlalt kontekstilauset,
nt pole reeglina vajalik lünktekst-tüüpi ülesannete puhul (vt ka
"Lahtised küsimused").*

## tulemustepank (48 rida)

*Testivastuste logi. TP kirjutab siia iga vastuse järel; kalibreerimise
komponent (AN, veel realiseerimata) loeb siit analüüsi sisendi.*

| **Veerg**      | **Tüüp**    | **Märkused**                              |
|----------------|-------------|-------------------------------------------|
| id             | bigint      | Primaarvõti                               |
| test_id        | text        | Viide testisessioonid tabelile (nullable) |
| yp_id          | bigint      | Viide ylesandepank tabelile (nullable)    |
| skoor          | integer     | Ülesande eest saadud punktid (0/1)        |
| valitud_vastus | text        | Variandi tekst, mille vastaja valis       |
| vastatud_ajal  | timestamptz | Vaikeväärtus: praegune aeg                |
| vastus_id  | uuid | Vaikeväärtus: gen_random_uuid() | Unikaalsuse reegel                |

## yg_tellimused (25 rida)

*YG (ülesandegeneraator, Edge Function + LLM) tööjärjekord. ATA lisab
siia rea, kui mõne õpiväljundi jaoks pole veel ülesandeid; YG jälgib
tabelit (Supabase Database Webhook INSERT peale) ja täidab tellimuse.
Maht ühe defineeritud ülesande kohta on hetkel fikseeritud väärtusega 3,
sõltumata testi kavandatud pikkusest. Demos tagas see kogus testile
piisavalt ülesandeid ning samas ei ammendanud tasuta LLM litsentsi
piiranguid*

| **Veerg** | **Tüüp** | **Märkused** |
|----------------|------------|------------------------------------|
| id | bigint | Primaarvõti |
| test_id | text | Vaba viide (mitte FK) |
| kursus | text | — |
| graafi_objektid | jsonb | Puuduvate sõlmede loend |
| kognitiivne_tase | text | Sama valikute loend, mis ylesandepank |
| maht | integer | Nullable, vaikeväärtus 1; ATA saadab praktikas alati 3 |
| staatus | text | ootel / tootmises / tehtud / viga (CHECK piirang) |
| loodud | timestamptz | Vaikeväärtus: praegune aeg |

## repo_materjalid (3 rida)

*Kursuste alusmaterjalide tekstipuhver — lihtne, kerge alternatiiv päris
vektorandmebaasile/RAG-ile. YG saab siit materjali oma prompti kaasata
ja parandada päris õppetöö konteksti esindatust. Seose annab kursuse
nimi (õppekorralduslik ühik: õppejõud ootab, et üliõpilased teaks tema
käsitletud teemasid).*

| **Veerg** | **Tüüp** |
|--------------------------------|--------------------------------|
| id | bigint (Primaarvõti) |
| kursus, pealkiri, allika_url, sisu_tekst | text |
| lisatud | timestamptz (vaikeväärtus: praegune aeg) |

## yg_reeglid (0 rida, hetkel kasutamata)

| **Veerg**                | **Tüüp**             |
|--------------------------|----------------------|
| id                       | bigint (Primaarvõti) |
| kursus, reegli_kirjeldus | text                 |
| naidis_json              | jsonb                |

# testi_loogika ja lopp_profiil struktuur

13.07 versioonis oli mõlema JSONB välja sisemine kuju veel täpsustamata.
Mõlemal on praegu oma formaat, mida on korduvalt demo tsüklite käigus
kasutatud.

## testisessioonid.testi_loogika (ATA kirjutab rada 6-s)

| **Väli** | **Kuju** | **Sisu** |
|-------------|-------------------|--------------------------------|
| metoodika | string | Praegu alati "kst" (teisi meetodeid pole lisatud) |
| K | 0/1 maatriks (olekud × sõlmed) | KST teadmusruumi kehtivad olekud BLIM-vormingus |
| P_K | arv-vektor | Prior tõenäosusjaotus üle olekute (ühtlane algseis) |
| solmed | tekstivektor | Sõlmede nimed, samas järjekorras mis K veerud |
| beta | arv-vektor | Hooletusvea parameeter sõlme kohta (mudeli tasand, mitte üksuse tasand) |
| eta | arv-vektor | Äraarvamise parameeter sõlme kohta (mudeli tasand) |
| yp_id | arv-vektor | Iga sõlme jaoks valitud (esindus-)ülesande yp_id |
| ntotal | integer | Hetkel alati 0 — kalibreerimiseks kavandatud, veel kasutuseta |
| koostatud | timestamp string | Millal *rada 6* hindamisloogika koostas |

## testisessioonid.tp_seisund (TP kirjutab iga vastuse järel)

<table style="width:88%;">
<colgroup>
<col style="width: 17%" />
<col style="width: 25%" />
<col style="width: 45%" />
</colgroup>
<thead>
<tr>
<th><strong>Väli</strong></th>
<th><strong>Kuju</strong></th>
<th><strong>Sisu</strong></th>
</tr>
</thead>
<tbody>
<tr>
<td>posterior</td>
<td>arv-vektor</td>
<td><p>Jooksev tõenäosusjaotus üle K olekute.</p>
<p>KRIITILINE: peab olema salvestamisel unname()-itud (nimeta), muidu
JSON-serialiseerimine variseb kokku duplikaat-võtmete tõttu — vt
"Lahtised küsimused" ja koodikommentaarid.</p></td>
</tr>
<tr>
<td>kysitud</td>
<td>list of {yp_id, solm, vastus_oige}</td>
<td>Kõigi selle testi jooksul küsitud ülesannete logi</td>
</tr>
</tbody>
</table>

## testisessioonid.lopp_profiil (TP kirjutab testi lõppedes, lopeta_test())

Sõlme klassifikatsioon põhineb usutavate olekute hulgal C (olekud
kahanevas tõenäosuses, kuni kumulatiivne tõenäosus ületab τ = 0.9),
millele rakendatakse KST äärt (fringe) kõigil C olekutel korraga — mitte
ainult ühel, kõige tõenäolisemal olekul.

| **Väli** | **Kuju** | **Sisu** |
|---------------|-------------|------------------------------------|
| omandatud | tekstivektor | Sõlmed, mis kuuluvad KÕIKIDESSE usutavatesse olekutesse (kindel omandatus) |
| valmis_oppima | tekstivektor | Sõlmed, mis on väline äär KÕIGIS usutavates olekutes (kindel "järgmine samm") |
| ebamaarane_edasi | tekstivektor | Ebamäärased sõlmed, mis asuvad struktuuriliselt EDASI mõnest omandatud sõlmest — julgustav ebamäärasus |
| ebamaarane_tagasi | tekstivektor | Ebamäärased sõlmed, mis on struktuuriliselt EELDUS mõnele omandatud sõlmele — üllatav ebamäärasus, väärib kordustestimist |
| veel_mitte | tekstivektor | Sõlmed, mis pole ei omandatud ega äärel üheski usutavas olekus — struktuuriliselt kauge samm, kasutajale ei kuvata |
| kokkuvote | string / null | Erijuhu tekst (nt "Teadsid kõike!" kui kõik sõlmed omandatud, või fork-teade mitme võrdväärse järgmise sammu korral) |
| peatumise_pohjus | string | "loomulik" (kindlus saavutati) või "turvapiir" (küsimuste piir täitus) — aus metatasandi märge tulemuse usaldusväärsuse kohta |
| kindlus_parim_olek | arv | Kõige tõenäolisema üksiku oleku tõenäosus |
| kindlus_C_hulgas | arv | Usutavate olekute hulga C summaarne tõenäosus (≥ τ=0.9) |
| n_usutavaid_olekuid | integer | Mitu olekut C hulka kuulus |

Praegu OR-i nõutud kolmeväärtuseline formaat (olemas / osaliselt olemas
/ puudub) tuleb OR-i poolel tuletada ülaltoodud viiest kategooriast — vt
"OR suhtlus" täpsemaks aruteluks.

# ATA rada 1-6 kokkuvõte

ATA (Automated Test Assembly) ehitab testisessiooni kuue nn raja kaupa.
Rada 1-2 ja rada 5 on hindamismetoodikast sõltumatud (samad kõigi
metoodikate — kst, irt, dina, ct — puhul); rada 3-4 ja rada 6 on
metoodikaspetsiifilised ja harunevad edaspidi metoodika järgi. Praegu on
täielikult realiseeritud ainult kst haru.

| **Rada** | **Tegevus** | **Metoodika?** | **Andmebaasi mõju** |
|-------|----------------------|----------------|-------------------|
| 1-2 | Tellimuse vastuvõtt + graafi hash arvutus | Jagatud | Ei kirjuta — ainult loeb tellimust ja arvutab hashi |
| 3-4 | Teadmusmudeli ehitus (KST struktuur) | Metoodikaspetsiifiline | Loeb/kirjutab graafid_kst (taaskasutab, kui hash juba olemas) |
| 5 | YP katvuse kontroll + YG käivitus vajadusel | Jagatud | Loeb ylesandepank; kirjutab yg_tellimused (ainult kui ülesandeid puudu) |
| 6 | Adaptiivse hindamisloogika koostamine (blim vms) | Metoodikaspetsiifiline | Loeb ylesandepank (parameetrid); kirjutab testisessioonid.testi_loogika + staatus |

Kaks API otspunkti kaardistuvad radadele nii:

- POST /api/test/create käivitab rada 1-5 (loob testisessioonid rea
  staatusega planeerimisel);

- GET /api/test/status kontrollib rada 5 uuesti (ülesanded võivad olla
  vahepeal valmis saanud) ja käivitab rada 6, kui kõik on olemas —
  sellel hetkel läheb staatus planeerimisel → aktiivne. See üleminek on
  ATA enda vastutus, mitte TP oma.

# TP tsükkel (adaptiivne testimine)

TP (app.R + TP_loogika.R) on iseseisev Shiny rakendus. Pärast testi
aktiveerumist (ATA rada 6) kordab TP järgmist tsüklit, kuni
peatumistingimus täitub:

- 1\. Küsimuse valik: kmassesshalfsplit(posterior, K) valib sõlme, mis
  jagab jooksva tõenäosusjaotuse kõige ühtlasemalt kaheks

- 2\. Ülesande valik: vali_ylesanne_solmele() otsib sellele sõlmele
  sobiva, veel kasutamata ülesande ylesandepank tabelist (ainult
  graafi_objekt järgi, vt "Sõlme identiteedi põhimõte")

- 3\. Vastuse hindamine ja Bayes-uuendus: kmassessbayesian(posterior, K,
  beta, eta, sõlme_indeks, vastus_õige) arvutab uue tõenäosusjaotuse;
  salvestatakse tulemustepank + tp_seisund

- 4\. Peatumiskontroll: test lõpeb, kui (a) kindlus on piisav JA
  vaatlusi on piisavalt ("loomulik"), või (b) vaatluste turvapiir täitub
  ("turvapiir") — vt allolev valem

Peatumisloogika valem (kehtestatud 19.07, asendab varasema,
adaptiivsusega vastuolus olnud n vaatlust *per* sõlm katvusnõude):

- reliaabluse_pohi(n) = min(max(7, ceiling(1.5×n)), 10) — miinimum
  vaatluste arv KOKKU, sõltumata jaotusest sõlmede vahel; kasvab
  väikestel graafidel, platoo'ub 10 juures alates n≥7 sõlmest, et
  suuremate graafide puhul domineeriks jälle tavaline, säästlik
  adaptiivne käitumine

- turvapiir(n) = max(2×n, reliaabluse_pohi(n)+1) — kõva ülempiir, tagab
  alati floor \< cap

Kui test peatub, koostab lopeta_test() lõpp-profiili (vt eelmine
peatükk) ja kirjutab selle testisessioonid.lopp_profiil väljale, muutes
staatuse lõpetatud.

# YG ja LLM ülesande tootmistsükkel

LLM-iga (Gemini praegu, ülikooli teenus/OpenAI võimalik tulevikus)
suhtleb AINULT YG (Edge Function, index.ts). Ahel:

- 1\. ATA tuvastab katvuse kontrollis puuduva ülesande → kirjutab rea
  yg_tellimused tabelisse

- 2\. Supabase Database Webhook (INSERT trigger) käivitab YG Edge
  Function'i

- 3\. YG teeb HTTP kutse LLM-ile (prompt: õpiväljundi kirjeldus +
  valikuline alusmaterjal repo_materjalid'ist)

- 4\. YG kirjutab LLM-i vastuse põhjal uued read ylesandepank tabelisse

- 5\. TP loeb hiljem ylesandepank tabelist valmis ülesandeid

Kui LLM-teenus vahetub (nt: Gemini → ülikooli teenus/OpenAI), muutub
ainult YG (index.ts) kood. TP ja ATA jäävad täiesti puutumata.

Index.ts sisaldab sissekirjutatud ülesande koostamise reegleid, mis
laienevad kõigile ülesannetele ja on osa iga päringuga LLM-le antavast
kontekstist.

# Sõlme identiteedi põhimõte

**Kriitiline arhitektuuripõhimõte, mis selgus 19.07 aruteludest ja
mõjutab kogu andmemudeli tõlgendust: GRAAFI OBJEKT (sõlm) on ülesande
sobivuse tegelik identiteet, mitte kursus.**

Kursus on abistav instrument, mida YG kasutab materjali/konteksti
leidmiseks ülesande LOOMISEL — see ei ole nt ligipääsu piirav võti
ülesande KASUTAMISEL. Sama sõlme jaoks loodud ülesanne saab sobida igale
kursusele, mis seda sõlme küsib, sõltumata sellest, mis kursuse all see
algselt loodi. See tähendab:

- ATA katvuskontroll (kontrolli_yp_katvust) filtreerib AINULT
  graafi_objekt järgi — see on algusest peale õigesti tehtud

- TP ülesande valik (vali_ylesanne_solmele) filtreeris varem ekslikult
  ka kursuse järgi — see muudeti 19.07, kuna rikkus testimist, kui testi
  kursuse-väli erines sellest, mille all vastav ülesanne algselt
  genereeriti

- Andmebaasi tasandil pole see reegel jõustatud (ylesandepank.kursus on
  lihtsalt tekstiväli, mitte piirang) — kood peab seda põhimõtet ise
  järgima

Praegune lahendus ei täielik, sest lahendamata on *ülesande vastavus
populatsioonile*, samuti peaks eelistama antud kursusega seotud
päringute puhul *selle sama kursuse materjale arvestavaid ülesandeid*,
neist materjalidest sõltumatult loodud ülesannetele

# Tööjaotus: kes millist tabelit millal kasutab

Ülevaade, milline HK komponent (ATA, YG, TP või admin-tööriistad) iga
tabeliga suhtleb ja mis etapis.

| **Tabel** | **Kirjutab** | **Loeb** | **Millal** |
|------------|---------------------|--------------------|-------------|
| graafid_kst | ATA (rada 3-4) | ATA | Testi loomisel — KST struktuuri arvutus/taaskasutus |
| testisessioonid | ATA (loob rea, uuendab staatust ja testi_loogika); TP (tp_seisund iga vastuse järel; staatus ja lopp_profiil testi lõppedes) | ATA, TP, OR (staatuse/tulemuse päring — vt "OR suhtlus") | Kogu testi elutsükli vältel |
| ylesandepank | YG (loob uued read); TP (kasutamiste_arv, viimane_kasutus); tulevikus AN (kalibreerib beeta_error, g_guess) | ATA (rada 5, katvuse kontroll); TP (ülesande sisu testi ajal) | Pidevalt täienev |
| tulemustepank | TP (iga vastuse järel) | Tulevikus AN kalibreerimiseks; TP skoori arvutuseks | Testi läbiviimise ajal |
| yg_tellimused | ATA (rada 5, loob tellimuse); YG (uuendab staatust) | YG (jälgib webhook'i kaudu); ATA (kontrollib, kas juba pooleli) | Kui YP-s ülesanne puudub |
| repo_materjalid | HK admin-tööriist (käsitsi lisamine) | YG (alusmaterjal prompti jaoks) | Materjalide ettevalmistamisel |
| yg_reeglid | — | — | Kavandatud tulevikuks (reeglipõhine YG juhendamine) |

# OR suhtlus — hetkeseis ja ettepanek

OR (Õpirada) esitab tellimuse (POST /api/test/create — nodes, relations,
kursus, eesmark, kasutaja_id, rada_id) ja saab kohe tagasi test_id.
Kasutaja test/tagasiside-liides on OR-i vastutusalas (TP on hetkel
tehniline stand-in selle liidese jaoks, kuni OR oma UI valmis ehitab).

**Lahtine koht: kuidas OR saab teada, millal test on LÕPPENUD ja
lopp_profiil on valmis. Praegu ei ole selleks ühtki mehhanismi olemas.
Arutelu käigus (19.07) kaaluti kolme varianti:**

- \(a\) Rippuv HTTP-ühendus kogu testi vältel — TEHNILISELT VÕIMATU
  (test kestab õppija tempos minuteid kuni tunde, HTTP-ühendused pole
  selleks mõeldud)

- \(b\) Callback/webhook OR-ile testi lõppedes — toimiv, aga nõuab
  OR-ilt avalikku sisenevat endpointi ja autentimist

- \(c\) Pollimine — SOOVITATUD: OR küsib perioodiliselt uut ATA
  endpointi GET /api/test/result?test_id=X, mis tagastab kas {staatus:
  "pooleli"} või lopp_profiil'i sisu. See on identne mustriga, mida TP
  juba täna ATA suunas kasutab (GET /api/test/status) — vähem uut, mida
  arendajal õppida, ei vaja OR-ilt sisenevat endpointi ega autentimist.

**See endpoint (GET /api/test/result) on VEEL LOOMATA — soovitatav
esimeste sammude hulka Python-kesta arendajale.**

# Lahtised küsimused / tuntud piirangud

Konsolideeritud nimekiri, mis on oluline Python-kesta arendaja jaoks
teadlik olla:

- β/η (beeta_error, g_guess) on kõikjal fiktiivsed vaikeväärtused
  (0.05/0.25), kalibreerimata. Mudeli väljendatud "kindlus" (posterior)
  on seetõttu osaliselt ligikaudne — ei ole sõltumatult valideeritud.
  Kalibreerimiskomponent (AN) on realiseerimata; kaalutakse ka eraldi
  "seemne" kalibreerimisplokki katse alguses (kalibreerida üliõpilaste
  rühmatestimistega õppeaasta alguses nende kursustega seotud
  ülesandeid).

- graafi_ema_objekt (ylesandepank) — endiselt selgusetu, kuidas seda
  sisukalt täita; praktikas seni tühi. Ülesannete hulga kasvades võib
  ilma selleta tekkida ebaadekvaatset ülesannete kasutamist (sama knobit
  võib olla mitmes „tervikus“ unikaalsus avaldub kontekstis, kuhu knobit
  või knobitite kogum kuulub – ehk kõrgema taseme väljund on mõeldud
  nagu n-ö perekonnanime rolli kandma)

- LLM-teenuse valik (Gemini / ülikooli teenus / OpenAI) ei ole lõplikult
  otsustatud. Mõjutab üldist jõudlust, aga ka nt kuidas kõige paremini
  prompt kokku panna (nt konteksti mahukus)

- Teadmusgraafi (sõlmed + seosed) täitmine toimub eraldi AI agendi
  poolt, mille täitmisloogikat käesoleva dokumendi autor ei tunne —
  senised katsegraafid on olnud madala spetsiifilisusega (enamasti
  lineaarsed 3-4 sõlmega või isegi 2 sõlmega ahelad); see osa vajab
  tõenäoliselt ülevaatust enne suuremahulisemat katsetamist.

- GET /api/test/result (OR-ile testi tulemuse kättesaamiseks) on veel
  loomata — vt "OR suhtlus".

- event_publication tabel Supabases — päritolu selgusetu.

- Sõlme tasandi tagasiside (lopp_profiil) annab viis kategooriat
  (omandatud / valmis_oppima / ebamaarane_edasi / ebamaarane_tagasi /
  veel_mitte); OR-i algselt nõutud kolmeväärtuseline formaat (nt olemas
  / osaliselt olemas / puudub) tuleb OR-i poolel neist tuletada —
  vastavus pole veel kokku lepitud.

- Puhta marginaalse tõenäosuse (p_i = iga sõlme tõenäosus üle kõigi
  olekute, mitte ainult usutavate olekute hulga C põhjal) lisamine
  lopp_profiil'i on arutlusel, aga realiseerimata. Kokkuvõttes tuleb
  jälgitavaks muuta hinnangu kvaliteet/täpsus.
