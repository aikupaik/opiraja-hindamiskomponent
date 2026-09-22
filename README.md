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

Compose käivitab seitse eraldi teenust:

- `web` – administraatori Reacti rakendus ja ainus avaldatud rakenduse port;
- `player` – õppija Reacti testirakendus, kuhu `web` suunab `/test/*`;
- `api` – FastAPI, kuhu `web` suunab `/api/*`; ja
- `r-service` – sisemine KST arvutusteenus;
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

## Hindamiskomponendi teenuse käivitamine virtuaalmasinas
Virtuaalmasinasse on kloonitud giti repositoorium `opiraja-hindamiskomponent`.

Arendusfaasis on Andrease arendatud hindamiskomponendi loogika "pilot" harus.
```
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
```

Samad käsud sobivad lokaalseks Compose kontrolliks. Reaalne VM-i uuendamine,
hosti Nginxi seadistus ja avaliku HTTPS-i kontroll tuleb endiselt teha
deployment VM-is; player'i rakenduse ja sisemise Compose marsruutimise saab
täielikult kontrollida kohalikus Dockeris.

Avaliku võrgu, sertifikaadi uuendamise, igapäevase kontrolli ja hädaolukorra
tagasipööramise juhised on
[`docs/public-vpn-access-runbook.md`](docs/public-vpn-access-runbook.md).

## API ja R logide jälgimine

Compose'i Grafana Alloy kogub ainult märgendatud `api` ja `r-service`
konteinerite struktureeritud Docker `json-file` logid. Loki säilitab neid VM-i
failisüsteemis 14 päeva ning Grafana pakub CIDR-piiratud `/grafana/` töölaua ja
Explore'i vaate. Loki ja Alloy ei avalda hosti porte; Grafana on hostil
kättesaadav ainult loopback-aadressil Nginxi pöördproksi jaoks.

VM-i ettevalmistuse, paigalduse, päringute, varunduse, kontrollimise ja
tagasipööramise juhised on
[`docs/observability-runbook.md`](docs/observability-runbook.md).
