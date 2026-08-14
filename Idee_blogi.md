## Siia saab lihtsalt ideid ja lahendamist vajavaid probleeme üles kirjuta
(ametlik backlog tekib Jira piletitena)

#### HK jõudluse testimine

Andreas: jõudlist tuleb peatselt testida.
kuidas lahendada, kas see võib olla süsteemil mingi alaline vahend  küljes?

#### Aasta alguses matemaatiliste lausete redaktor
Kuna LLM genereerib teksti, siis saab ta kirjutada ka Latex vm koodi. Meil on vaja pluginat külge, mis ülesande infot lugedes teeb ülesannetesse kenad võrrandid

#### Õppejõu OR/HK töölaud
Margus kiirustab tagant mõttega, et panna kokku vahend, mis laseb õppejõul OR ja HK võimalusi hästi mugavalt kasutada

- hallata enda õpitulemusi (graaf - ülikooli dokumendid)
- linkida/lisada HK materjale
- üle vaadata HK ülesandeid

Kaugem mõte: n-ö Moodle pipe-line <- eeldab, et õppejõud organiseerivad oma materjalid sarnase loogikaga resp. masin peab õppima iga nurga tagant materjale otsima ja objekti materjalina tuvastama
vt https://moodle.org/mod/forum/discuss.php?d=429107

#### Mitmekeelne HK
Toote toimimise arendamisel otseselt pole oluline (algselt HK visandatud eesti tavakeelele)
Ilmne, et kõrghariduses ei saa ilma mitmekeelsuse võimeta teenuseid kasutada/skaleerida
Kuna HK on taustal töötav, siis lähtekohad:

- keel signaliseeritakse OR tellimuses
- tõlkevõime lahendust vaja juhistele  ja tagasisidele (saab kavaldada ka - nt Ava test --> Start, aga see väga piiratud)
- YG tellimuse ja promti arendamine: OR tellimusest paneb ATA keele tunnuse YG tellimusse ning see läheb llm jaoks vihjeks, mis keeles ülesandeid tuleb teha
- YP lisada keeletunnus (nt tavalised rahvusvahelisi lühendid), mis näitab ülesande keelt
- keeletavandi ja konteksti mõttes pigem genereerida väljunditele uusi teises keeles ülesandeid kui tõlkida (?)

#### Ülesannete kasutamise ja tootmise reeglid

- lisatud reeglid kasutuse sageduse jälgimiseks globaalselt ja antud testis (demo ATA/TP olemas, eraldi kirjeldatud ka)
- lisada sügise jooksul: ülesannente omaduste arvestamine
- lisada reeglid vanadele ülesannetele uute juurde tootmiseks (nt kui testides on pidevalt ühe profiili jaoks 4-5 ülesannet kasutusel, siis ATA teab tellida uue hindamispäringu jaoks 2 uut ülesannet juurde, lähtudes kasutusajaloost.
