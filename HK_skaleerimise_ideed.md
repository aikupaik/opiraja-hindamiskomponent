# Rakenduse skaleerimise tulevikuplaan

Siia dokumenti on kirjeldatud võimalikud skaleerimise suunad - ideed selle dokumendi koostamiseks tulid [LinkedIn artiklist](https://www.linkedin.com/pulse/why-digital-assessment-platforms-break-pmwbe/): 
Praeguse piloodi arhitektuur loob juba hea aluse edasiseks skaleerimiseks. Eelkõige on oluline, et **kasutaja autentimine on testimängija teenusest eraldatud**, mistõttu autentimisega seotud vastutus ja riskid ei koorma otseselt testimislahendust. Edasine arendus võiks keskenduda järgmistele suundadele.

## 1. Sõltuvuse vähendamine välistest teenustest

Praegu sõltub rakenduse töö Supabase'i teenusest. See tekitab riski nii võimalike teenusekatkestuste kui ka tasuta paketi piirangute tõttu.

**Edasine suund:**

* võtta ülikooli taristul kasutusele enda hallatav PostgreSQL andmebaas;
* migreerida vajalikud andmed Supabase'ist;
* viia teenuse toimimiseks kriitilised komponendid võimalikult suures ulatuses enda hallatavasse taristusse.

**Eesmärk:** suurendada süsteemi töökindlust ning vähendada sõltuvust kolmandatest osapooltest.

## 2. Arhitektuuri ettevalmistamine mikroteenusteks

Praegune piloot on üles ehitatud viisil, mis juba osaliselt sarnaneb mikroteenuste arhitektuuriga. Süsteemi kasvades tasub hinnata, millised komponendid oleks mõistlik eraldada iseseisvateks teenusteks.

Üleminek ei pea toimuma korraga. Mõistlik on liikuda selles suunas järk-järgult, näiteks koos enda majutatud andmebaasi kasutuselevõtuga.

**Eesmärk:** võimaldada tulevikus süsteemi eri osade sõltumatut arendamist, juurutamist ja skaleerimist.

## 3. Puhverdamise (caching) kasutuselevõtt

Testi jooksul korduvalt kasutatavaid ja harva muutuvaid andmeid, näiteks ülesandepanga küsimusi, ei ole vaja iga vastuse järel uuesti andmebaasist pärida.

**Edasine suund:**

* laadida testi koostamisel vajalikud ülesanded puhvrisse;
* kasutada testi jooksul võimalusel puhverdatud andmeid;
* hinnata selleks Redise või sarnase enda taristul majutatava lahenduse kasutamist.

**Eesmärk:** vähendada andmebaasipäringute hulka, kiirendada küsimuste kuvamist ja parandada süsteemi võimekust suurema kasutajate arvu korral.

## 4. Automaatne skaleerimine

Pikemas perspektiivis võiks süsteem olla võimeline reageerima suure koormusega perioodidele, näiteks eksamiperioodile, automaatselt.

See tähendaks võimalust:

* suurendada vajaduse korral protsessori- ja mäluressurssi;
* käivitada automaatselt täiendavaid teenusekonteinereid;
* vähendada koormuse lõppedes ressursikasutust tagasi tavapärasele tasemele.

Automaatne skaleerimine on **madalama prioriteediga**, sest enne selle rakendamist on võimalik saavutada märkimisväärne jõudluse kasv koodi optimeerimise, puhverdamise ja arhitektuuri parandamise kaudu.

## Prioriteedid

**Lähiajal:** enda PostgreSQL andmebaas ja Supabase'i sõltuvuse vähendamine.
**Keskmises perspektiivis:** puhverdamine ning arhitektuuri järkjärguline ettevalmistamine mikroteenusteks.
**Pikas perspektiivis:** automaatne skaleerimine vastavalt süsteemi tegelikule koormusele.

Üldine põhimõte on liikuda skaleerimise suunas **järk-järgult ja tegeliku vajaduse põhjal**, lahendades esmalt olemasolevad sõltuvused ja jõudlusprobleemid ning lisades keerukamaid skaleerimismehhanisme alles siis, kui kasutuskoormus neid õigustab.
