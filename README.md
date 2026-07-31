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

## Hindamiskomponendi teenuse käivitamine virtuaalmasinas
Virtuaalmasinasse on kloonitud giti repositoorium `opiraja-hindamiskomponent`.

Arendusfaasis on Andrease arendatud hindamiskomponendi loogika "pilot" harus.
```
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
```