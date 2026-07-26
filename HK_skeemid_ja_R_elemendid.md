

<!-- Start of picture text -->
Lépetab uue teema<br>6ppimise<br>GEE TUEEE 1. Tellib = , 3. Loeb Plaanib<br>plaanitud . + 2. Taidab testi sat, Py<br>hindamiseks hindamise tagasisidet Oppimist<br>Ei oska piiritleda oma<br>Opivajadust<br><!-- End of picture text -->



<!-- Start of picture text -->
Opirada (OR) 1. Hindamise paring<br>(Susteemi kese / Al agent) (Teadmusgraafi objektid)<br>1<br>1<br>1<br>' Oo<br>1<br>1<br>(Raja korrigeerimiseks) [Application Service]<br>3. Testi esitamine vastamiseks<br>4. Tulemuste kuva<br>=0<br>(Opiraja. ORKasutajaliides)Ul<br>[Application Interface]<br><!-- End of picture text -->



<!-- Start of picture text -->
Ee 0. Soovib tagasisidet<br>= teatab OR agendile<br>POST laa: ceate parsi JSON2. Rada sisend, 1-2:loo test_id<br>Gee arvuta graafi rasi SHA-256 hash<br>3. Rada 3-4<br>vordle rasi: kas teha uus test<br>Jah — KST struktuuri arvutamine|<br>4 Rada5<br>testi jaoks YP katvuse kontroll<br>*--on puudu:<br>‘ \ INSERT<br>‘s6ltumata= 'ief 5.a . |hi trigger<br>Katvusest | jiS@YG telimus}<br>Seeeeeeeeeeee!lisab puuduvad 5.b Webhook— uued read— LLM kutse YP<br>a Sj]<br>8. Rada6<br>Loo hindamismudel (kst)<br>9. test_id — kasutaja<br>panebloob Ul-sseURL-i selletest_id-gaiframe’i | 10. Avab testi<br>11. Kaivita testimine<br>Polli testi valmimist<br>GET /api/test/status?test_id=X<br>(=Rada 6: loo hindamismudel)<br>12. (halt-spiit)Vali ilesanne 13. Lahendab UlesandedEs<br>ry<br>kuni peatub<br>14. Bayes+salvesta<br>vastuse digsus/kirjuta<br>TPn/posterior vaartused<br>peatub<br>jalgi15.  stop-kriteeriumiPeata — loo lopp_profiiltaitmist GE) Uae<br>leia ustavad olekud tagasiside 3 rubrilki<br>liigita seisundid oskadijargmiseksfkorda<br>' 17. festresult ‘« |------(realiseerimata) ---------------4----------------""<br>' (formaadi ettepanek) |<br>18. lopp_profiil<br>— 6piraja korrigeerimine<br><!-- End of picture text -->



<!-- Start of picture text -->
Markused<br><!-- End of picture text -->

> OR- 6pirajateenus, millega kasutaja saab valida ja eesmargistada enda tegevusi Sppimisel. ATA - testi koostaja, vtab OR tellimuse ja disainib testi 

YG - Ulesandegeneraator, loob testides vajalikud Ulesanded. TP - testi pleier, kuvab Ulesanded kasutajale, jargides ATA néudeid, skoorib, esitab tagasiside. 

YP - dlesandepank, ilesannete ja nende meta-andmete hoidla TPn - tulemuste pank, Ulesannete skooride hoidla. Kasutaja - inimene, kes kasutab Sppimisel OR, omades seal Uks véi enam Spirada. 

Rada 1_.n tahistab siin algses protsessi kirjelduses nimetatud samme. 



<!-- Start of picture text -->
0 po|<br>F f og |<br>a8 : $8 | o<br>32i '1 Beog H' O<br>£2 i 83 | &2<br>53&= H', =£8Ze {{| =.<br>3 | 28 |<br>g<br>|'' &.<br>|<br>ec '' '<br>2 2<br>28 g<br>£5 32<br>[4 :<br>28 55 "<br>4<br>Hae a A<br>33 g<br>rt 2 5<br>a35a3<br>= 3°<br>0<br>e<br>i<br>: :<br>4) | 83 2 3 &<br>| | 8H: : H3 fe=)$ aBPs: 3AE<br>z|g | 22eas 55 E : : i<br><4 oe Ss 2<br>g & :<br>3<br>°<br>z8 _2EE S= g<br>— 58 o 3 ai|<br>><br>© 5B Fig BeeaE 4id 3<br>if<br>i Ee i:<br>: qe (| |<br>8oo a3 ~<br>58 iu<br>a<br>sé<br>BS ae aan<br>[=]<br>8E 3<br>,<br>oO<br>2<br>: 2<br>at<¢ a°A<br>eS? 0 iO}<br>=<br>i is 4 i<br>; ag 2 1 BE |<br>5 if}|<br>; : S i 28<br><!-- End of picture text -->

# HOW to R 

## _Dockeris vajalikud kihid:_ 

Base image: rocker/r-ver:4.5.0 või rocker/shiny:4.5.0 kui Shiny enda võimalusi on vaja säilitada 

Süsteemitasandi teegid apt-get install kaudu:  libcurl4-openssl-dev, libssl-dev (httr jaos, millel suhtlus Supabase’ga), libxml2-dev, uuid-dev (uuid jaoks, mis praegu annab test_id) + Build tööriistad (nt build-essentials) 

R paketid ise: plumber, shiny, httr, jsonlite, kst, kstMatrix, digest, uuid. Need toovad pakette kaasa (nt kst – sets ja relations) 

Keskkonnamuutujad, mis peavad tulema docker run -e või docker-compose.yml kaudu 

Port + käivituskäsk (entrypoint). ATA_kst praegust kuju app.r vaja pole, plumber käivitub otse: 

<u>pr <- plumber::plumb("api.R") pr$run(host = "0.0.0.0", port = 8000)</u> 

## _R võimekuse (ühelõimelisuse piirang) laiendamine:_ 

Horisontaalsne laiendamine 

Käivitad mitu koopiat samast konteinerist (docker-compose scale ata=3 või Kubernetes/Docker Swarm replicas) + load balancer (Traefik, HAProxy, nginx) 

# docker-compose.yml services: ata: build: ./ata deploy: replicas: 3          # kolm R/Plumber protsessi paralleelselt environment: - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY} labels: - "traefik.http.routers.ata.rule=Host(`ata.example.com`)" - "traefik.http.services.ata.loadbalancer.server.port=8000" tp: build: ./tp deploy: replicas: 3 environment: - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY} - ATA_BASE_URLS=http://ata:8000 labels: - "traefik.http.routers.tp.rule=Host(`tp.example.com`)" - "traefik.http.services.tp.loadbalancer.server.port=3838" 

# KRIITILINE TP jaoks – nn kleepuv sessioon, et kasutaja ei satuks keset testi teise  protsessi (nt uue ülesande valiku hetkel): - "traefik.http.services.tp.loadbalancer.sticky.cookie=true" 

- "traefik.http.services.tp.loadbalancer.sticky.cookie.name=tp_session" 

traefik: image: traefik:v3.0 command: --providers.docker=true --entrypoints.web.address=:80 ports: - "80:80" volumes: - /var/run/docker.sock:/var/run/docker.sock 

Asünkroonne I/O orotsessi sees, paketid future ja promise 

See oleks täitsa asjakohane HK koodi jaoks, kuna ATA/TP ei ole reeglina n-ö CPUmahukad — need ootavad enamasti võrku (Supabase päringud, LLM kutsed). future_promise({...}) võimaldab ühel R protsessil alustada uue päringu töötlemist, kui teine parasjagu HTTP-vastust ootab. Vähem mälu vaja kui ainult horisontaalsel. Efekt puuduks nt väga ebatavaliselt suure KST arvutuse puhul. 

Katse osas vbl 2-3 koopia haldamine optimaalne. 

ATA osas Plumber, api.R on olekuta – iga päring tegeleb otse Supabase’ga ega hoia midagi mälus. Päringuid saab piiranguteta mitme koopia vahel jagada. 

TP (Shiny/ app.R) on olekuga ja iga kasutaja sessioon hoiab ühendust (websocket) ühe kindla R protsessiga kogu testi ajal. Sticky sessioon lubamine balancer’is  koopiate puhul tähtis, et ühendus ei katkeks (vt märkus koodis). 

## _Põhiline R-kood skriptis_ : 

**Räsi loomine** , protsessi vaade, 2. samm 

library(digest) 

arvuta_graafi_hash <- function(solmed, seosed) { kanooniline <- list( solmed = sort(unique(solmed)), seosed = seosed[order(seosed[[1]], seosed[[2]]), , drop = FALSE] ) digest(kanooniline, algo = "sha256") <u>}</u> 

**KST struktuuri arvutamine** , protsessi vaade, 3. samm 

Pakett _kst_ laseb testi moodustamiseks ja edasise testimise läbiviimiseks moodustada maatriksi (sõlmede ja seoste kirjeldus, mis sisuliselt on OR tellimuses olemas). Millegi tõttu teeb pakett seda puudulikult ning lahendamiseks tuleks kaasata teine pakett _relations_ . 

# 1. Teisendus: data.frame (seosed) -> endorelation objekt seosed_suhtena <- endorelation(graph = set( do.call(rbind, lapply(seq_len(nrow(seosed)), function(i) tuple(seosed[i, 1], seosed[i, 2]))) )) # 2. Sulund: lisa refleksiivsed + transit vsed paarid, mida "seosed" ise ei sisalda kvaasijarjestus <- reflexive_closure(transitive_closure(seosed_suhtena)) kstructure(kvaasijarjestus) 

Tegelikult sai selle kst kitsenduse märkamisel maatriks koostatud koodis otse. 

library(kst)   # toob kaasa sets, relations koosta_teadmusmudel <- function(metoodika, graaf_hash, solmed, seosed) { if (metoodika != "kst") stop("Ainult 'kst' realiseeritud") # 1. Siia paigutatud ka cache-kontroll - kas see graafi objektide hash on juba varem arvutatud? olemasolev <- sb_get(sprintf( "/graafid_kst?graaf_hash=eq.%s&select=graaf_hash,teadmusruum_maatriks", graaf_hash )) if (length(olemasolev) > 0 && nrow(olemasolev) > 0) { teadmusruum_raw <- fromJSON(olemasolev$teadmusruum_maatriks[[1]]) return(list(uus = FALSE, teadmusruum = teadmusruum_raw, solmed = solmed)) } # 2. Kehtivuse kontroll IGA võimaliku alamhulga jaoks - OTSE, mitte # kst::kstructure() suhte-tuletuse kaudu (vt allolev NB!) on_kehtiv_olek <- function(S, seosed) { if (nrow(seosed) == 0) return(TRUE) for (i in seq_len(nrow(seosed))) { eeldus <- seosed[i, 1]; solmus <- seosed[i, 2] if (solmus %in% S && !(eeldus %in% S)) return(FALSE) } TRUE } koik_alamhulgad <- unlist( lapply(0:length(solmed), function(k) combn(solmed, k, simplify = FALSE)), recursive = FALSE ) kehtivad_olekud <- Filter(function(S) on_kehtiv_olek(S, seosed), koik_alamhulgad) struktuur <- kstructure(as.set(lapply(kehtivad_olekud, as.set))) 

teadmusruum_raw <- lapply(as.list(struktuur), function(s) as.character(s)) # 3. Salvestamine (võidujooksu-kaitsega paralleelsete ATA replikate jaoks – kui seda kasutada) sb_post("/graafid_kst", list( graaf_hash = graaf_hash, graafi_struktuur = toJSON(list(solmed = solmed, seosed = seosed), auto_unbox = TRUE), teadmusruum_maatriks = toJSON(teadmusruum_raw, auto_unbox = TRUE) ), prefer = "return=minimal,resolution=ignore-duplicates") list(uus = TRUE, teadmusruum = teadmusruum_raw, solmed = solmed) <u>}</u> 

Selle ülesande saab ka Pythonis lahendada otse, kuigi soovitan järjepidevuse mõttes tugineda teadaoleva ajaloo ja publikatsioonidega R pakettidele. 

## **Hindamismudeli loomine (kst)** , protsessi vaade, 8. samm 

Ei kasuta ühtegi analüüsipaketti, ainult R base vahendid, mida NumPy saab array abil asendada. 

koosta_hindamismudel <- function(metoodika, teadmusruum_raw, solmed, sõlme_parameetrid) { if (metoodika != "kst") stop("Ainult 'kst' realiseeritud") 

# 1. Olekute × sõlmede 0/1 maatriks K <- t(sapply(teadmusruum_raw, function(seisund) as.integer(solmed %in% seisund))) colnames(K) <- solmed n_seisundeid <- nrow(K) 

# 2. Ühtlane prior üle olekute P.K <- rep(1 / n_seisundeid, n_seisundeid) # 3. Sõlme-tasandi beta/eta (katvuskontrollist saadud ülesannete parameetrid) beta <- sapply(solmed, function(s) sõlme_parameetrid[[s]]$beta) eta  <- sapply(solmed, function(s) sõlme_parameetrid[[s]]$eta) list( metoodika = "kst", K         = K, P_K       = setNames(P.K, apply(K, 1, function(r) paste(solmed[r == 1], collapse = ","))), solmed    = solmed, beta      = setNames(beta, solmed), eta       = setNames(eta, solmed), yp_id     = setNames(sapply(solmed, function(s) sõlme_parameetrid[[s]]$yp_id), solmed), ntotal    = 0, koostatud = as.character(Sys.time()) ) <u>}</u> 

**K maatriks** — iga sammu (2) kehtiv olek muudetakse 0/1 reaks: 1, kui sõlm on selles olekus, 0 kui mitte. See ongi see maatriks, mida hiljem TP (sammud 10, 12-13) kasutab. 

**P_K** —algne prior eeldus (enne ühtegi saadud vastust on iga olek võrdselt tõenäoline) — 1/(nolekud) igale olekule. Nimed (setNames) on olekute sõnalised kirjeldused (nt "A,B“). 

**beta/eta** — võetakse sammu **"YP katvuse kontroll"** tulemusest (sõlme_parameetrid, mis sisaldab iga sõlme jaoks valitud ülesande beeta_error/g_guess väärtusi). Praegu on kasutusel fikt vsed vaikeväärtused (0.05/0.25), sest kalibreerimist pole seni tehtud. 

**yp_id** — milline konkreetne ülesanne testis iga sõlme "esindab" selle mudeli raames. 

**ntotal, koostatud** — metaandmed (kalibreerimiseks kavandatud, hetkel kasutuseta / ajatempel). 

## **Testimisel ülesande adapti vne valimine,** protsessi vaade, 12. samm 

Eelnevalt loodud testi mudel viitab ära kõik seisundite kirjeldamiseks vajalikud ülesanded. Tegelikult viiakse läbi adapt vne testimine, mis püüab vähima ülesannete hulgaga välja peilida, milline on kasutaja teadmisseisund. Tegelikult hakkab TP esitama kasutajale ülesandeid ligikaudu teadmisruumi keskkoha juurest. Sõltuvalt vastuste kehtivusest esitatakse edasi ülesandeid kas nõrgemate või tugevamate teadmusseisundite kohta (kui teeb ära, siis esitatakse raskem, kui ei tee ära, siis kergem ülesanne). 

library(kstMatrix) # a) Otsusta, mis _sõlme_ kohta järgmisena küsida vali_jargmine_solm <- function(posterior, K) { kmassesshalfsplit(posterior, K)   # tagastab veeru-indeksi (sõlme) } 

# b) Vali sellele sõlmele konkreetne ja selles testis veel kasutamata ülesanne 

vali_ylesanne_solmele <- function(solm, kysitud_yp_idd) { kandidaadid <- sb_get_q("/ylesandepank", list( graafi_objekt = paste0("eq.", solm),   # AINULT sõlme järgi, mitte kursuse (vt "sõlme identiteedi põhimõte") staatus = "eq.kasutatav", select = "yp_id,beeta_error,g_guess,kasutamiste_arv" )) if (n_rida(kandidaadid) == 0) stop(sprintf("Sõlmele '%s' ei leitud ühtegi kasutatavat ülesannet.", solm)) kasutamata <- kandidaadid[!(kandidaadid$yp_id %in% kysitud_yp_idd), ] valik <- if (nrow(kasutamata) > 0) kasutamata[1, ] else kandidaadid[1, ]  # kõik juba küsitud - korda list(yp_id = valik$yp_id, beta = valik$beeta_error, eta = valik$g_guess, kasutamiste_arv = valik$kasutamiste_arv) } # c) Laadi kasutajale kuvamiseks valitud ülesande sisu YP-st lae_ylesanne <- function(yp_id) { rida <- sb_get(sprintf("/ylesandepank?yp_id=eq.%s&select=*", <u>yp_id))</u> 

rida <- rida[1, ] list( yp_id = rida$yp_id, juhis = rida$juhis, tyvi = rida$tyvi, st mul = if (length(rida$st mul) == 0 || is.na(rida$st mul)) NULL else rida$st mul, voti = rida$voti, variandid = jarjesta_variandid(rida$voti, c(rida$distraktor_1, rida$distraktor_2, rida$distraktor_3)) ) <u>}</u> 

## Protseduur kulgeb: 

- (a) kmassesshalfsplit() ütleb, milline SÕLM tuleb (nt "B") —puhas KST-arvutus ega puuduta andmebaasi. 

- (b) kuna igal sõlmel on vähemalt 3 ülesannet YP-s, tuleb valida üks konkreetne, mida veel pole selles testis kasutatud (kysitud_yp_idd on andmed$kysitud yp_id-de loend). 

- (c) viimasena laeb ülesande täisteksti kuvamiseks — sh järjestades valikud juhuslikult (tekst)/kahanevalt (arvud). 

## **Tulemuste kontroll ja tõenäosused** , protsessi vaade, 14. samm 

Vastuste õigsuse ja vastava skoori (1-0) leidmine, tuleb salvestada tulemuste panka. 

library(kstMatrix) library(kmassessbayesian) # a) Vastuse õigsuse kontroll + logi vastus_oige <- identical(seisund$valitud_vastus, praegune$ylesanne$voti) sb_post("/tulemustepank", list( test_id = andmed$test_id, yp_id = praegune$item$yp_id, skoor = as.integer(vastus_oige), valitud_vastus = seisund$valitud_vastus )) # b) Bayes-uuendus - beta/eta TÄISVEKTORID (mudeli tasand), mitte üksuse skalaar uuenda_posterior <- function(posterior, K, solm_indeks, vastus_oige, beta, eta) { kmassessbayesian(posterior, K, beta, eta, solm_indeks, as.integer(vastus_oige)) } uus_posterior <- uuenda_posterior( andmed$posterior, andmed$K, praegune$solm_indeks, vastus_oige, andmed$testi_loogika$beta, andmed$testi_loogika$eta ) # c) Salvesta uuendatud olek - unname() kohustuslik (vt eelmine viga) uus_kysitud <- c(andmed$kysitud, list(list( yp_id = praegune$item$yp_id, solm = praegune$solm, vastus_oige = vastus_oige ))) salvesta_tp_seisund <- function(test_id, posterior, kysitud) { sb_patch(sprintf("/testisessioonid?test_id=eq.%s", test_id), list( 

tp_seisund = toJSON(list(posterior = unname(posterior), kysitud = kysitud), auto_unbox = TRUE) )) } 

salvesta_tp_seisund(andmed$test_id, uus_posterior, uus_kysitud) 

## Protseduur kulgeb: 

- (a) lihtne tekstivõrdlus aitab, kirjutab otse tulemuste panka (püsiv salvestus). 

- (b) kmassessbayesian() võtab kogu K-maatriksi + mudeli-tasandi beta/eta + info, mis sõlme kohta küsiti ja hinnangu, kas vastati õigesti — ning tagastab uue tõenäosusjaotuse üle kõigi olekute. 

- (c) salvestamine tp_seisund’ina — unname() on siin tähtis, kuna kmassessbayesian() tagastab posterior'i duplikaat-nimedega, mis JSON-serialiseerimisel muidu kokku varisevad. 

Esitatud skeemid ja koodi kommentaarid ei käsitle praegu analüüsi komponenti (AN), millega analüüsida vastuseid tulemuste pangas ning korrigeerida ülesannete parameetreid ülesandepangas. See element lisandub edaspidi. 

