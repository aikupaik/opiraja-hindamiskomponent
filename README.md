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

Compose käivitab neli eraldi teenust:

- `web` – administraatori Reacti rakendus ja ainus avaldatud port;
- `player` – õppija Reacti testirakendus, kuhu `web` suunab `/test/*`;
- `api` – FastAPI, kuhu `web` suunab `/api/*`; ja
- `r-service` – sisemine KST arvutusteenus.

`/` avab administraatori rakenduse, `/test/{test_id}` õppija rakenduse ning
paljas `/test` tagastab `404`. Brauser suhtleb API-ga samal origin'il. Enne JWT
etappi on õppija link peidetud, kuid mitte turvatud: kehtivat UUID-d teadev
kasutaja saab testi avada. Rakendust ei tohi seetõttu avalikku keskkonda panna
enne autoriseerimise etapi lõpetamist.

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
