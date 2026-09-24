# opiraja-hindamiskomponent
Hindamiskomponent (HK) on AI abil toimiv tegum, mis toetab õpiraja teenust kasutaja teadmiste-oskuste automaatse testimise ja tagasisidega. Siinsed materjalid puudutavad demo ja  katse korraldamist.

Hindamiskomponent on loodud kui õpiraja laiendusmoodul, mis töötab taustal. Hindamiskomponent lisab õpirajale funktsioonid:

 * Kasutaja hindamise tellimuse põhjal testi ülesehituse disainimine
 * Ülesannete koostamine
 * Testimise läbiviimine (õpiraja UI)
 * Tulemuse leidmine
 * Tagasiside andmine õpirajale (masin-sisend)
 * Tagasiside andmine kasutajale (õpiraja UI)
 * Mõõtmiskvaliteedi määratlemine

Hindamiskomponent luuakse autonoomselt töötavana. Kasutajad saavad hindamist täpsustada esitades hindamiskomponendile kontkesti andvaid materjale ja reegleid ülesannete koostamiseks. Hindamistulemust määratlevad põhiprotsessid on komponendis deterministlikud. 

## Rakendused ja marsruutimine

Compose'i vaikimisi käivitus sisaldab nelja rakendusteenust:

- `web` – administraatori Reacti rakendus ja ainus avaldatud rakenduse port;
- `player` – õppija Reacti testirakendus, kuhu `web` suunab `/test/*`;
- `api` – FastAPI, kuhu `web` suunab `/api/*`; ja
- `r-service` – sisemine KST arvutusteenus.

VM-is lisab `observability` Compose'i profiil veel kolm logiteenust:

- `loki` – sisemine 14-päevase säilitusega logihoidla;
- `alloy` – ainult API ja R Dockeri logide koguja; ning
- `grafana` – loopback-pordil avaldatud operatiivvaade hosti Nginxi jaoks.

`/` avab administraatori rakenduse, `/test/{test_id}` õppija rakenduse ning
paljas `/test` tagastab `404`. Brauser suhtleb API-ga samal origin'il. Avalik
tootmisots on `https://193.40.157.124/`, kasutab usaldatud Let's Encrypti
IP-sertifikaati ning JWT-põhist autoriseerimist. HTTP port 80 teenindab ainult
ACME kontrolli ja HTTPS-i ümbersuunamist.

Iseseisva player'i arenduse, taastamise ja testimise juhised on
[`frontend/README.md`](frontend/README.md).

## Lokaalne Docker-arendus

Lokaalne Compose käivitab tootmislähedase nelja konteineri pinu ilma Loki,
Alloy ja Grafanata. Kopeeri näidis, sisesta kinnitatud tootmise Supabase'i ja
serveri võtmed ning käivita:

```sh
cp .env.local.example .env.local
# Muuda .env.local väärtused enne jätkamist.
docker compose --env-file .env.local config --quiet
docker compose --env-file .env.local up --build
```

Ava administraatori rakendus aadressil `http://127.0.0.1:8080`; player'i lingid
kasutavad sama origin'i. Kontrollimiseks kasuta `docker compose --env-file .env.local ps`,
`/health/live` ja `/health/ready`. Rakenduse logid on saadaval
`docker compose --env-file .env.local logs api r-service` kaudu. Peata pinu
`docker compose --env-file .env.local down` käsuga.

`.env.local` on Gitist väljas. See ühendub kasutaja valikul tootmise
Supabase'iga, seega täismahuline lokaalne testimine võib luua või muuta päris
andmeid ja käivitada ülesannete genereerimise.

## Hindamiskomponendi teenuse käivitamine virtuaalmasinas
Virtuaalmasinasse on kloonitud giti repositoorium `opiraja-hindamiskomponent`.

Arendusfaasis on Andrease arendatud hindamiskomponendi loogika "pilot" harus.
```
docker compose --profile observability config --quiet
docker compose --profile observability build --pull
docker compose --profile observability up -d
docker compose --profile observability ps
```

Reaalne VM-i uuendamine, hosti Nginxi seadistus ja avaliku HTTPS-i kontroll
tuleb endiselt teha deployment VM-is. `--profile observability` on VM-is
kohustuslik, et keskne logikogumine ja Grafana käivituksid.

Avaliku võrgu, sertifikaadi uuendamise, igapäevase kontrolli ja hädaolukorra
tagasipööramise juhised on
[`docs/public-vpn-access-runbook.md`](docs/public-vpn-access-runbook.md).

## API ja R logide jälgimine

`observability` profiili Compose'i Grafana Alloy kogub ainult märgendatud `api` ja `r-service`
konteinerite struktureeritud Docker `json-file` logid. Loki säilitab neid VM-i
failisüsteemis 14 päeva ning Grafana pakub CIDR-piiratud `/grafana/` töölaua ja
Explore'i vaate. Loki ja Alloy ei avalda hosti porte; Grafana on hostil
kättesaadav ainult loopback-aadressil Nginxi pöördproksi jaoks.

VM-i ettevalmistuse, paigalduse, päringute, varunduse, kontrollimise ja
tagasipööramise juhised on
[`docs/observability-runbook.md`](docs/observability-runbook.md).
